import webbrowser
import threading
import os
import re
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .graph import MetroGraphBuilder, seconds_to_hms, to_seconds
from .algorithm import MetroRouter, DisruptionManager


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

    def open_browser():
        import time
        time.sleep(1.5)
        webbrowser.open("http://127.0.0.1:8000")
    
    threading.Thread(target=open_browser, daemon=True).start()

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


def parse_legs(path: list[str], fallback_origin: str, fallback_dep: str) -> tuple[list["LegInfo"], int]:
    if not path or not path[0].startswith("Depart at"):
        return [], 0

    dep_time = path[0].replace("Depart at ", "").strip()
    legs: list[LegInfo] = []

    current_station = fallback_origin
    current_time = dep_time
    i, n = 1, len(path)

    def is_walk_tok(t: str) -> bool:
        return t.startswith("Walk to") or t.startswith("Walking from")

    while i < n:
        tok = path[i]

        if tok.startswith("Take route"):
            route_name = tok.replace("Take route ", "").strip()
            i += 1

            # token đầu (chỉ leg đầu tiên) lặp lại đúng tên ga hiện tại -> bỏ qua
            if i < n and path[i] == current_station:
                i += 1

            arr_time = path[i] if i < n and _is_time(path[i]) else current_time
            if i < n and _is_time(path[i]):
                i += 1
            to_station = path[i] if i < n else current_station
            if i < n:
                i += 1

            legs.append(LegInfo(
                type="board", route=route_name,
                from_stop=current_station, to_stop=to_station,
                dep_time=current_time, arr_time=arr_time,
            ))
            current_station = to_station
            current_time = arr_time

            # ngay sau khi xuống tàu nếu phải đi bộ tiếp
            if i < n and is_walk_tok(path[i]):
                i += 1
                walk_arr = path[i] if i < n and _is_time(path[i]) else current_time
                if i < n and _is_time(path[i]):
                    i += 1
                walk_station = path[i] if i < n else current_station
                if i < n:
                    i += 1
                legs.append(LegInfo(
                    type="walk", route="walk",
                    from_stop=current_station, to_stop=walk_station,
                    dep_time=current_time, arr_time=walk_arr,
                ))
                current_station = walk_station
                current_time = walk_arr
            elif i < n and _is_time(path[i]):
                # giờ khởi hành cho chặng kế tiếp sau khi đổi tuyến
                current_time = path[i]
                i += 1

        elif is_walk_tok(tok):
            i += 1
            walk_arr = path[i] if i < n and _is_time(path[i]) else current_time
            if i < n and _is_time(path[i]):
                i += 1
            walk_station = path[i] if i < n else current_station
            if i < n:
                i += 1
            legs.append(LegInfo(
                type="walk", route="walk",
                from_stop=current_station, to_stop=walk_station,
                dep_time=current_time, arr_time=walk_arr,
            ))
            current_station = walk_station
            current_time = walk_arr

        else:
            i += 1  # token thừa (thời gian/tên ga lặp) -> bỏ qua

    transfers = max(0, len([l for l in legs if l.type == "board"]) - 1)
    return legs, transfers


@app.post("/route", response_model=list[JourneyResult])
async def find_route(req: RouteRequest):
    if graph is None:
        raise HTTPException(status_code=503, detail="Graph chưa sẵn sàng, thử lại sau.")

    try:
        dm = DisruptionManager()

        dm.disable_route("YELLOW")
        dm.disable_station("Pentagon")
        dm.disable_segment("Smithsonian", "Federal Triangle", "BLUE")
        router = MetroRouter(
            graph=graph,
            source=req.origin,
            target=req.destination,
            dep_time=req.dep_time,
            k=req.k,
            disruptions=dm
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

@app.get("/")
async def serve_index():
    return FileResponse("transit_route.html")

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "graph_ready": graph is not None,
        "nodes": graph.number_of_nodes() if graph else 0,
        "edges": graph.number_of_edges() if graph else 0,
    }