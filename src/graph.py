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
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi       = math.radians(lat2 - lat1)
    dlambda    = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

class MetroGraphBuilder:

    def __init__(
        self,
        gtfs_path: str,
        transfer_penalty: int = 300,
        walk_max_meters: float = 800,
        walk_speed_mps: float = 1.2
    ):
        self.gtfs_path        = gtfs_path
        self.transfer_penalty = transfer_penalty
        self.walk_max_meters  = walk_max_meters  
        self.walk_speed_mps   = walk_speed_mps   
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
    
    def build(self, cache_path: str = './data/graph.pkl', force_rebuild: bool = False) -> nx.DiGraph:
        import os, pickle, time

        if not force_rebuild and os.path.exists(cache_path):
            if os.path.getmtime(cache_path) > os.path.getmtime(self.gtfs_path):
                t0 = time.perf_counter()
                with open(cache_path, 'rb') as f:
                    self.graph = pickle.load(f)
                print(f"[Cache] Load xong trong {time.perf_counter()-t0:.2f}s — "
                      f"{self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges.")
                return self.graph
            
        stops, trips, stop_times = self._read_gtfs()

        platform_to_hub = (
            stops[stops['parent_station'].notna() & (stops['parent_station'] != '')]
            .set_index('stop_id')['parent_station']
            .to_dict()
        )

        for _, row in stops.iterrows():
            self.graph.add_node(
                row['stop_id'],
                name = row['stop_name'],
                type = 'station',
                pos  = (float(row['stop_lat']), float(row['stop_lon'])), # xem xét loại bỏ
            )

        trip_to_route = dict(zip(trips['trip_id'], trips['route_id']))
        trip_to_sv = dict(zip(trips['trip_id'], trips['service_id'])) # Lấy service_id
        stop_id_to_name = dict(zip(stops['stop_id'], stops['stop_name']))
        
        stop_times_sorted = stop_times.sort_values(['trip_id', 'stop_sequence'])

        for trip_id, group in stop_times_sorted.groupby('trip_id', sort=False):
            route_id = trip_to_route.get(trip_id)
            if route_id is None:
                continue

            rows = group.reset_index(drop=True)
            nodes_in_trip = rows['stop_id'].tolist()

            for i in range(len(nodes_in_trip)):
                stop_id = nodes_in_trip[i]
                route_node = f"{stop_id}_{route_id}"
                hub_id = platform_to_hub.get(stop_id, stop_id)

                if route_node not in self.graph or 'arr_time' not in self.graph.nodes[route_node]:
                    self.graph.add_node(
                        route_node,
                        name = stop_id_to_name.get(stop_id),
                        type='route_stop',
                        station_id=stop_id,
                        next_node=nodes_in_trip[i+1] if i < len(nodes_in_trip) - 1 else None,
                        route=route_id, 
                        arr_time=[to_seconds(rows.loc[i, 'arrival_time'])], 
                        sv_id=trip_to_sv[trip_id]
                    )
                    self.graph.add_edge(route_node, hub_id, weight=self.transfer_penalty, label='route_hub')
                    self.graph.add_edge(hub_id, route_node, weight=self.transfer_penalty, label='route_hub')
                else:
                    new_arr_time = to_seconds(rows.loc[i, 'arrival_time'])
                    self.graph.nodes[route_node]['arr_time'].append(new_arr_time)

                if i < len(nodes_in_trip) - 1:
                    next_stop_id = nodes_in_trip[i+1]
                    next_route_node = f"{next_stop_id}_{route_id}"
                    
                    travel_time = to_seconds(rows.loc[i+1, 'arrival_time']) - to_seconds(rows.loc[i, 'arrival_time'])
                    if travel_time >= 0:
                        self.graph.add_edge(route_node, next_route_node, weight=travel_time, label='travel')

        self._add_walking_edges(stops)

        import os, pickle
        os.makedirs(os.path.dirname(cache_path) if os.path.dirname(cache_path) else '.', exist_ok=True)
        with open(cache_path, 'wb') as f:
            pickle.dump(self.graph, f, protocol=pickle.HIGHEST_PROTOCOL)
        print(f"[Cache] Đã lưu tại {cache_path}")

        print(
            f"[Build] Hoàn tất — "
            f"{self.graph.number_of_nodes()} nodes, "
            f"{self.graph.number_of_edges()} edges."
        )
        return self.graph

if __name__ == '__main__':
    MGB = MetroGraphBuilder('./data/rail.zip', transfer_penalty=300)
    G = MGB.build()
    path = nx.shortest_path(G, source='STN_G02', target='STN_C02', weight='weight')
    print("Đường đi:")
    for node in path:
        attrs = G.nodes[node].get('name')
        print(attrs)
