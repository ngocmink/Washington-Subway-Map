import zipfile
import heapq
import bisect
from collections import defaultdict

import pandas as pd
import networkx as nx


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def to_seconds(t: str) -> int:
    h, m, s = map(int, t.strip().split(':'))
    return h * 3600 + m * 60 + s


def seconds_to_hms(sec: int) -> str:
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


# ─────────────────────────────────────────────────────────────────────────────
# Builder
# ─────────────────────────────────────────────────────────────────────────────

class MetroGraphBuilder:

    def __init__(self, gtfs_path: str, transfer_penalty: int = 300):
        self.gtfs_path        = gtfs_path
        self.transfer_penalty = transfer_penalty
        self.graph            = nx.DiGraph()

    def build(self, cache_path: str = './data/metro_graph.pkl', force_rebuild: bool = False) -> nx.DiGraph:
        import os, pickle, time

        if not force_rebuild and os.path.exists(cache_path):
            if os.path.getmtime(cache_path) > os.path.getmtime(self.gtfs_path):
                t0 = time.perf_counter()
                with open(cache_path, 'rb') as f:
                    self.graph = pickle.load(f)
                print(f"[Cache] Load xong trong {time.perf_counter()-t0:.2f}s — "
                      f"{self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges.")
                return self.graph

        import time
        t0 = time.perf_counter()

        stops, trips, stop_times = self._read_gtfs()
        print(f"  [1/4] Đọc GTFS: {time.perf_counter()-t0:.2f}s")

        node_attrs = {
            row['stop_id']: {
                'name': row['stop_name'],
                'pos' : (float(row['stop_lat']), float(row['stop_lon'])),
            }
            for row in stops.to_dict('records')   
        }
        self.graph.add_nodes_from(node_attrs.items())   
        print(f"  [2/4] Thêm nodes: {time.perf_counter()-t0:.2f}s")

        def col_to_seconds(series: pd.Series) -> pd.Series:
            parts = series.str.split(':', expand=True).astype(int)
            return parts[0] * 3600 + parts[1] * 60 + parts[2]

        stop_times['dep_sec'] = col_to_seconds(stop_times['departure_time'])
        stop_times['arr_sec'] = col_to_seconds(stop_times['arrival_time'])

        st = (stop_times
              .sort_values(['trip_id', 'stop_sequence'])
              .merge(trips[['trip_id', 'route_id']], on='trip_id', how='inner'))

        st['next_stop_id'] = st.groupby('trip_id')['stop_id'].shift(-1)
        st['next_arr_sec'] = st.groupby('trip_id')['arr_sec'].shift(-1)

        edges_df = (st
                    .dropna(subset=['next_stop_id', 'next_arr_sec'])
                    .query('next_arr_sec >= dep_sec')
                    [['stop_id', 'next_stop_id', 'trip_id', 'route_id', 'dep_sec', 'next_arr_sec']]
                    .rename(columns={
                        'stop_id'      : 'u',
                        'next_stop_id' : 'v',
                        'dep_sec'      : 'dep_time',
                        'next_arr_sec' : 'arr_time',
                    }))

        print(f"  [3/4] Vectorized shift: {time.perf_counter()-t0:.2f}s  ({len(edges_df):,} cặp trạm)")

        edge_schedules = defaultdict(list)

        for rec in edges_df.to_dict('records'):
            edge_schedules[(rec['u'], rec['v'])].append({
                'trip_id'  : rec['trip_id'],
                'route_id' : rec['route_id'],
                'dep_time' : int(rec['dep_time']),
                'arr_time' : int(rec['arr_time']),
            })

        for (u, v), schedules in edge_schedules.items():
            schedules.sort(key=lambda s: s['dep_time'])
            self.graph.add_edge(u, v, schedules=schedules)

        elapsed = time.perf_counter() - t0
        print(f"  [4/4] Build graph: {elapsed:.2f}s — "
              f"{self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges.")

        import os, pickle
        os.makedirs(os.path.dirname(cache_path) if os.path.dirname(cache_path) else '.', exist_ok=True)
        with open(cache_path, 'wb') as f:
            pickle.dump(self.graph, f, protocol=pickle.HIGHEST_PROTOCOL)
        print(f"[Cache] Đã lưu tại {cache_path}")

        return self.graph

    def earliest_arrival(
        self,
        source     : str,
        target     : str,
        start_time : int,           
    ) -> tuple[int, list[str], list[dict]]:

        if source not in self.graph:
            raise ValueError(f"stop '{source}' không tồn tại trong đồ thị.")
        if target not in self.graph:
            raise ValueError(f"stop '{target}' không tồn tại trong đồ thị.")

        earliest: dict[str, int] = {source: start_time}

        heap: list = [(start_time, source, [source], None, [])]

        while heap:
            cur_time, cur_stop, path, cur_trip, legs = heapq.heappop(heap)

            if cur_stop == target:
                return cur_time, path, legs

            if cur_time > earliest.get(cur_stop, float('inf')):
                continue

            for neighbor in self.graph.successors(cur_stop):
                edge_data  = self.graph[cur_stop][neighbor]
                schedules  = edge_data['schedules']

                if not schedules:
                    continue

                dep_times = edge_data.get('dep_times_cache')
                if dep_times is None:
                    dep_times = [s['dep_time'] for s in schedules]
                    edge_data['dep_times_cache'] = dep_times
                idx = bisect.bisect_left(dep_times, cur_time)

                if idx >= len(schedules):
                    continue  

                next_sched = schedules[idx]
                trip_id    = next_sched['trip_id']
                route_id   = next_sched['route_id']
                dep_time   = next_sched['dep_time']
                arr_time   = next_sched['arr_time']

                is_transfer = cur_trip is not None and cur_trip != trip_id
                penalty     = self.transfer_penalty if is_transfer else 0

                effective_dep = dep_time + penalty          
                if is_transfer:
                    earliest_board = cur_time + penalty
                    idx2 = bisect.bisect_left(dep_times, earliest_board)
                    if idx2 >= len(schedules):
                        continue
                    next_sched  = schedules[idx2]
                    trip_id     = next_sched['trip_id']
                    route_id    = next_sched['route_id']
                    dep_time    = next_sched['dep_time']
                    arr_time    = next_sched['arr_time']

                if arr_time < earliest.get(neighbor, float('inf')):
                    earliest[neighbor] = arr_time

                    leg = {
                        'from_stop'  : cur_stop,
                        'to_stop'    : neighbor,
                        'route_id'   : route_id,
                        'trip_id'    : trip_id,
                        'dep_time'   : seconds_to_hms(dep_time),
                        'arr_time'   : seconds_to_hms(arr_time),
                        'wait_sec'   : dep_time - cur_time,
                        'travel_sec' : arr_time - dep_time,
                        'transfer'   : is_transfer,
                    }

                    heapq.heappush(heap, (
                        arr_time,
                        neighbor,
                        path + [neighbor],
                        trip_id,
                        legs + [leg],
                    ))

        return float('inf'), [], []


    def _read_gtfs(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        str_cols = {
            'stops.txt'      : ['stop_id'],
            'trips.txt'      : ['trip_id', 'route_id'],
            'stop_times.txt' : ['trip_id', 'stop_id'],
        }
        with zipfile.ZipFile(self.gtfs_path) as zf:
            available = zf.namelist()
            for fname in str_cols:
                if fname not in available:
                    raise FileNotFoundError(
                        f"File '{fname}' không có trong {self.gtfs_path}"
                    )

            stops      = pd.read_csv(zf.open('stops.txt'),
                                     dtype={c: str for c in str_cols['stops.txt']})
            trips      = pd.read_csv(zf.open('trips.txt'),
                                     dtype={c: str for c in str_cols['trips.txt']})
            stop_times = pd.read_csv(zf.open('stop_times.txt'),
                                     dtype={c: str for c in str_cols['stop_times.txt']})

        required = {
            'stops'      : ['stop_id', 'stop_name', 'stop_lat', 'stop_lon'],
            'trips'      : ['trip_id', 'route_id'],
            'stop_times' : ['trip_id', 'stop_id', 'stop_sequence',
                            'arrival_time', 'departure_time'],
        }
        for df, name in [(stops, 'stops'), (trips, 'trips'), (stop_times, 'stop_times')]:
            missing = [c for c in required[name] if c not in df.columns]
            if missing:
                raise ValueError(f"{name}.txt thiếu cột: {missing}")

        return stops, trips, stop_times

    # ──────────────────────────────────────────────────────────────────────
    # Tiện ích
    # ──────────────────────────────────────────────────────────────────────

    def stop_name(self, stop_id: str) -> str:
        return self.graph.nodes[stop_id].get('name', stop_id)

    def print_journey(
        self,
        arrival_time : int,
        path         : list[str],
        legs         : list[dict],
        start_time   : int,
    ) -> None:
        
        if arrival_time == float('inf'):
            print("Không tìm thấy đường.")
            return

        total_min = (arrival_time - start_time) // 60
        print("=" * 60)
        print(f"Xuất phát : {seconds_to_hms(start_time)}")
        print(f"Đến nơi   : {seconds_to_hms(arrival_time)}")
        print(f"Tổng thời gian: {total_min} phút")
        print("=" * 60)

        for i, leg in enumerate(legs, 1):
            transfer_tag = " [ĐỔI TUYẾN]" if leg['transfer'] else ""
            print(
                f"  Chặng {i}{transfer_tag}: "
                f"{self.stop_name(leg['from_stop'])} → {self.stop_name(leg['to_stop'])}"
            )
            print(
                f"    Tuyến {leg['route_id']} | Chuyến {leg['trip_id']}"
            )
            print(
                f"    Khởi hành {leg['dep_time']} — Đến {leg['arr_time']} "
                f"(đi {leg['travel_sec']//60} phút, chờ {leg['wait_sec']//60} phút)"
            )

        print("=" * 60)
        print("Hành trình:", " → ".join(self.stop_name(s) for s in path))


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    GTFS_PATH  = './data/rail.zip'
    SOURCE     = 'STN_G02'
    TARGET     = 'STN_C02'
    START_TIME = to_seconds('08:00:00')

    builder = MetroGraphBuilder(GTFS_PATH, transfer_penalty=300)
    builder.build(cache_path='./data/graph.pkl')

    arrival, path, legs = builder.earliest_arrival(SOURCE, TARGET, START_TIME)
    builder.print_journey(arrival, path, legs, START_TIME)
