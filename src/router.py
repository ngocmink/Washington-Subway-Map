import re
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .graph import MetroGraphBuilder, seconds_to_hms, to_seconds
from .algorithm import MetroRouter


graph = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global graph
    print("[Startup] Đang build graph từ GTFS...")
    builder = MetroGraphBuilder(
        gtfs_path='./data/rail.zip',
        transfer_penalty=300,
        walk_max_meters=800,
        walk_speed_mps=1.2
    )
    graph = builder.build(cache_path='./data/graph.pkl')
    print("[Startup] Graph sẵn sàng!")
    yield
    print("[Shutdown] Dọn dẹp...")

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RouteRequest(BaseModel):
    origin: str
    destination: str
    dep_time: str     # "HH:MM:SS"
    k: int = 3

class LegInfo(BaseModel):
    type: str         # "board" | "walk"
    route: str        # tên tuyến hoặc "walk"
    from_stop: str
    to_stop: str
    dep_time: str     # giờ xuất phát của leg
    arr_time: str     # giờ đến của leg

class JourneyResult(BaseModel):
    dep_time: str
    arrival_time: str
    legs: list[LegInfo]
    transfers: int


def _is_time(s: str) -> bool:
    return bool(re.match(r'^\d{2}:\d{2}:\d{2}$', s.strip()))

def parse_legs(path: list[str], fallback_origin: str, fallback_dep: str) -> tuple[list[LegInfo], int]:

    legs: list[LegInfo] = []
    overall_dep   = fallback_dep
    pending_time  = None
    current_route = None
    current_dep   = fallback_dep
    current_from  = fallback_origin
    last_station  = None
    last_arr      = None

    for item in path:

        if item.startswith("Depart at"):
            overall_dep   = item.replace("Depart at ", "").strip()
            last_station  = fallback_origin   
            current_from  = fallback_origin
            current_dep   = overall_dep
            continue

        if _is_time(item):
            pending_time = item
            continue

        if item.startswith("Take route"):
            route_name = item.replace("Take route ", "").strip()
            if current_route is not None:
                legs.append(LegInfo(
                    type="board", route=current_route,
                    from_stop=current_from, to_stop=last_station or "",
                    dep_time=current_dep,   arr_time=last_arr or "",
                ))
            current_route = route_name
            current_dep   = pending_time or overall_dep
            current_from  = last_station or fallback_origin
            pending_time  = None
            continue

        if item.startswith("Walk to") or item.startswith("Walking from"):
            dest = item.replace("Walk to ", "").replace("Walking from ", "").strip()
            legs.append(LegInfo(
                type="walk", route="walk",
                from_stop=last_station or "", to_stop=dest,
                dep_time=pending_time or "", arr_time=pending_time or "",
            ))
            pending_time = None
            continue

        # Tên ga thật
        last_station = item
        last_arr     = pending_time
        pending_time = None

    # Đóng leg cuối
    if current_route is not None:
        legs.append(LegInfo(
            type="board", route=current_route,
            from_stop=current_from, to_stop=last_station or "",
            dep_time=current_dep,   arr_time=last_arr or "",
        ))

    transfers = max(0, len([l for l in legs if l.type == "board"]) - 1)
    return legs, transfers


@app.post("/route", response_model=list[JourneyResult])
async def find_route(req: RouteRequest):
    if graph is None:
        raise HTTPException(status_code=503, detail="Graph chưa sẵn sàng, thử lại sau.")

    try:
        router = MetroRouter(
            graph=graph,
            source=req.origin,
            target=req.destination,
            dep_time=req.dep_time,
            k=req.k,
        )
        all_paths = router()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi thuật toán: {str(e)}")

    if not all_paths:
        raise HTTPException(status_code=404, detail="Không tìm thấy lộ trình phù hợp.")

    results = []
    for arrival_time, path in all_paths:
        legs, transfers = parse_legs(path, fallback_origin=req.origin, fallback_dep=req.dep_time)
        actual_dep = legs[0].dep_time if legs else req.dep_time
        results.append(JourneyResult(
            dep_time=actual_dep,
            arrival_time=arrival_time,
            legs=legs,
            transfers=transfers,
        ))

    return results

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "graph_ready": graph is not None,
        "nodes": graph.number_of_nodes() if graph else 0,
        "edges": graph.number_of_edges() if graph else 0,
    }