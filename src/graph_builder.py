import zipfile
import math
from collections import defaultdict

import pandas as pd
import networkx as nx


def to_seconds(t: str) -> int:
    h, m, s = map(int, t.strip().split(':'))
    return h * 3600 + m * 60 + s


def seconds_to_hms(sec: int) -> str:
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Tính khoảng cách (mét) giữa 2 điểm trên mặt cầu Trái Đất.

    Công thức Haversine:
        a = sin²(Δlat/2) + cos(lat1)·cos(lat2)·sin²(Δlon/2)
        c = 2·atan2(√a, √(1−a))
        d = R · c

    R = 6_371_000 m (bán kính Trái Đất trung bình)
    """
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi       = math.radians(lat2 - lat1)
    dlambda    = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class MetroGraphBuilder:

    WALK_SPEED_MPS   = 1.2   
    WALK_MAX_METERS  = 800   

    def __init__(
        self,
        gtfs_path: str,
        transfer_penalty: int = 300,
        walk_max_meters: float | None = None,
        walk_speed_mps: float | None = None,
    ):
        self.gtfs_path        = gtfs_path
        self.transfer_penalty = transfer_penalty
        self.walk_max_meters  = walk_max_meters  or self.WALK_MAX_METERS
        self.walk_speed_mps   = walk_speed_mps   or self.WALK_SPEED_MPS
        self.graph            = nx.DiGraph()

    def _read_gtfs(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        str_cols = {
            'stops.txt'      : ['stop_id'],
            'trips.txt'      : ['trip_id', 'route_id'],
            'stop_times.txt' : ['trip_id', 'stop_id'],
        }
        with zipfile.ZipFile(self.gtfs_path) as zf:
            stops      = pd.read_csv(zf.open('stops.txt'),
                                     dtype={c: str for c in str_cols['stops.txt']})
            trips      = pd.read_csv(zf.open('trips.txt'),
                                     dtype={c: str for c in str_cols['trips.txt']})
            stop_times = pd.read_csv(zf.open('stop_times.txt'),
                                     dtype={c: str for c in str_cols['stop_times.txt']})
        return stops, trips, stop_times

    def _add_walking_edges(self, station_stops: pd.DataFrame) -> int:
        stations = (
            station_stops[station_stops['location_type'] == 1]
            [['stop_id', 'stop_name', 'stop_lat', 'stop_lon']]
            .dropna(subset=['stop_lat', 'stop_lon'])
            .reset_index(drop=True)
        )

        records = stations.to_dict('records')  
        n       = len(records)
        added   = 0

        for i in range(n):
            a = records[i]
            for j in range(i + 1, n):
                b = records[j]

                dist_m = haversine_meters(
                    a['stop_lat'], a['stop_lon'],
                    b['stop_lat'], b['stop_lon'],
                )

                if dist_m > self.walk_max_meters:
                    continue

                walk_sec = math.ceil(dist_m / self.walk_speed_mps)

                for src, dst in [(a['stop_id'], b['stop_id']),
                                  (b['stop_id'], a['stop_id'])]:
                    self.graph.add_edge(
                        src, dst,
                        weight   = walk_sec,
                        label    = 'walk',
                        dist_m   = round(dist_m, 1),
                        walk_sec = walk_sec,
                    )
                added += 2

        return added

    def build(self) -> nx.DiGraph:
        stops, trips, stop_times = self._read_gtfs()

        for _, row in stops.iterrows():
            self.graph.add_node(
                row['stop_id'],
                name = row['stop_name'],
                pos  = (float(row['stop_lat']), float(row['stop_lon'])),
            )

        trip_to_route = dict(zip(trips['trip_id'], trips['route_id']))
        trip_to_sv    = dict(zip(trips['trip_id'], trips['service_id']))

        stop_times_sorted = stop_times.sort_values(['trip_id', 'stop_sequence'])

        for trip_id, group in stop_times_sorted.groupby('trip_id', sort=False):
            route_id = trip_to_route.get(trip_id)
            if route_id is None:
                continue

            rows          = group.reset_index(drop=True)
            nodes_in_trip = rows['stop_id'].tolist()

            for i in range(len(nodes_in_trip)):
                stop_id    = nodes_in_trip[i]
                route_node = f"{stop_id}_{route_id}"

                if route_node not in self.graph or 'arr_time' not in self.graph.nodes[route_node]:
                    self.graph.add_node(
                        route_node,
                        type     = 'route_stop',
                        route    = route_id,
                        arr_time = [to_seconds(rows.loc[i, 'arrival_time'])],
                        sv_id    = trip_to_sv[trip_id],
                    )
                    self.graph.add_edge(route_node, stop_id,
                                        weight=self.transfer_penalty, label='exit_to_hub')
                    self.graph.add_edge(stop_id, route_node,
                                        weight=self.transfer_penalty, label='enter_from_hub')
                else:
                    self.graph.nodes[route_node]['arr_time'].append(
                        to_seconds(rows.loc[i, 'arrival_time'])
                    )

                if i < len(nodes_in_trip) - 1:
                    next_stop_id    = nodes_in_trip[i + 1]
                    next_route_node = f"{next_stop_id}_{route_id}"

                    travel_time = (
                        to_seconds(rows.loc[i + 1, 'arrival_time'])
                        - to_seconds(rows.loc[i, 'arrival_time'])
                    )
                    if travel_time >= 0:
                        self.graph.add_edge(route_node, next_route_node,
                                            weight=travel_time, label='travel')

        walk_edges = self._add_walking_edges(stops)

        print(
            f"[Build] Hoàn tất — "
            f"{self.graph.number_of_nodes()} nodes, "
            f"{self.graph.number_of_edges()} edges "
            f"(trong đó {walk_edges} cạnh đi bộ, "
            f"ngưỡng {self.walk_max_meters}m)."
        )
        return self.graph

    def walking_pairs(self) -> list[dict]:
        seen = set()
        result = []
        for u, v, data in self.graph.edges(data=True):
            if data.get('label') != 'walk':
                continue
            key = tuple(sorted([u, v]))
            if key in seen:
                continue
            seen.add(key)
            result.append({
                'from'    : u,
                'to'      : v,
                'dist_m'  : data['dist_m'],
                'walk_sec': data['walk_sec'],
                'walk_min': round(data['walk_sec'] / 60, 1),
            })
        return sorted(result, key=lambda x: x['dist_m'])


if __name__ == '__main__':
    builder = MetroGraphBuilder(
        './data/rail.zip',
        transfer_penalty = 300,
        walk_max_meters  = 800,   
        walk_speed_mps   = 1.2,   
    )
    G = builder.build()

    print("\n--- Các cặp bến có thể đi bộ ---")
    for p in builder.walking_pairs():
        print(
            f"  {p['from']:20s} <-> {p['to']:20s} "
            f"  {p['dist_m']:6.0f} m  "
            f"  {p['walk_min']} phút"
        )

    path = nx.shortest_path(G, source='STN_G02', target='STN_C02', weight='weight')
    print("\nĐường đi tối ưu:", path)