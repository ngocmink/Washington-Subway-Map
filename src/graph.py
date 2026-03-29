import zipfile
import heapq
import bisect
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


class MetroGraphBuilder:

    def __init__(self, gtfs_path: str, transfer_penalty: int = 300):
        self.gtfs_path        = gtfs_path
        self.transfer_penalty = transfer_penalty
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

    def build(self) -> nx.DiGraph:
        stops, trips, stop_times = self._read_gtfs()

        for _, row in stops.iterrows():
            self.graph.add_node(
                row['stop_id'],
                name = row['stop_name'],
                pos  = (float(row['stop_lat']), float(row['stop_lon'])),
            )

        trip_to_route = dict(zip(trips['trip_id'], trips['route_id']))

        edge_schedules: dict[tuple, list] = defaultdict(list)

        stop_times_sorted = stop_times.sort_values(['trip_id', 'stop_sequence'])

        for trip_id, group in stop_times_sorted.groupby('trip_id', sort=False):
            route_id = trip_to_route.get(trip_id)
            if route_id is None:
                continue 

            rows = group.reset_index(drop=True)

            for i in range(len(rows) - 1):
                u = rows.loc[i,     'stop_id']
                v = rows.loc[i + 1, 'stop_id']

                dep_time = to_seconds(rows.loc[i,     'departure_time'])
                arr_time = to_seconds(rows.loc[i + 1, 'arrival_time'])

                if arr_time < dep_time:
                    continue

                edge_schedules[(u, v)].append({
                    'trip_id'  : trip_id,
                    'route_id' : route_id,
                    'dep_time' : dep_time,
                    'arr_time' : arr_time,
                })

        for (u, v), schedules in edge_schedules.items():
            schedules.sort(key=lambda s: s['dep_time'])
            self.graph.add_edge(u, v, schedules=schedules)

        print(
            f"[Build] Hoàn tất — "
            f"{self.graph.number_of_nodes()} nodes, "
            f"{self.graph.number_of_edges()} edges."
        )
        return self.graph

if __name__ == 'main':
    MGB = MetroGraphBuilder('./data/rail.zip', transfer_penalty=300)