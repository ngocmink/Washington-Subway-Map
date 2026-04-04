import math
from collections import defaultdict, deque
import networkx as nx
import bisect

from .graph import MetroGraphBuilder, to_seconds

class MetroRouter:
    def __init__(self, graph, source, target, dep_time, k=5):
        self.graph = graph
        self.source = source
        self.target = target
        self.dep_time = dep_time
        self.k = k

    def find_path(self):
        # Prepare data structures
        tau = {}
        best_trip_possible = {}
        parent = {}
        prev_change_nodes = deque()
        station_to_node = {
            data['station_id']: n 
            for n, data in self.graph.nodes(data=True) 
            if data.get('type') == 'station'
        }

        for node, data in self.graph.nodes(data=True):
            if data.get('type') == 'station':
                best_trip_possible[self.graph.nodes[node]['station_id']] = float('inf')
        for i in range(self.k):
            for node, data in self.graph.nodes(data=True):
                if data.get('type') == 'station':
                    tau[(i, self.graph.nodes[node]['station_id'])] = float('inf')

        
        dep_time = to_seconds(self.dep_time)
        name_to_node = {d['name']: n for n, d in self.graph.nodes(data=True) if 'name' in d}
        source_node = name_to_node.get(self.source)
        target_node = name_to_node.get(self.target)

        if source_node is None or target_node is None:
            print("Source hoặc target không tồn tại trong graph.")
            return None

        source_id = self.graph.nodes[source_node]['station_id']
        tau[(0, source_id)] = dep_time
        best_trip_possible[source_id] = dep_time

        for k in range(self.k):
            if k == 0:
                prev_change_nodes.append(source_node)
                for node in self.graph.successors(source_node):
                    if self.graph.nodes[node]['type'] == 'station':
                        if best_trip_possible[self.graph.nodes[node]['station_id']] > tau[(k, source_id)] + self.graph[source_node][node]['weight']:
                            best_trip_possible[self.graph.nodes[node]['station_id']] = tau[(k, source_id)] + self.graph[source_node][node]['weight']
                            parent[self.graph.nodes[node]['station_id']] = source_id
                            prev_change_nodes.append(node)

            else:
                current_nodes = list(prev_change_nodes)
                prev_change_nodes.clear()

                for pv_node in current_nodes:

                    for node in self.graph.successors(pv_node):

                        # Cần update tất cả các node trên từng route
                        if self.graph.nodes[node]['type'] == 'station' and k > 1:
                            station_id = node
                            pv_station_id = pv_node
                            # Xét với thời gian đi bộ
                            if best_trip_possible[station_id] > tau[(k-1, pv_station_id)] + self.graph[pv_node][node]['weight']:
                                best_trip_possible[station_id] = tau[(k-1, pv_station_id)] + self.graph[pv_node][node]['weight']
                                parent[station_id] = pv_station_id
                                prev_change_nodes.append(node)

                        elif self.graph.nodes[node]['type'] == 'route_stop':
                            arr_times = self.graph.nodes[node]['arr_time']
                            station_id = self.graph.nodes[node]['station_id']
                            pv_station_id = pv_node

                            # Tìm chuyến sớm nhất đón được
                            pv_tau = tau.get((k-1, pv_station_id), float('inf'))
                            if pv_tau == float('inf'):
                                continue
                            idx = bisect.bisect_right(arr_times, pv_tau + 60)

                            # Check nếu có chuyến hợp lệ
                            if idx < len(arr_times):
                                tau[(k, station_id)] = arr_times[idx]
                            else:
                                continue

                            if best_trip_possible[station_id] > tau[(k, station_id)]:
                                best_trip_possible[station_id] = tau[(k, station_id)]
                                parent[station_id] = pv_station_id
                                prev_change_nodes.append(station_to_node[station_id])

                            while self.graph.nodes[node]['type'] == 'route_stop':
                                station_id = self.graph.nodes[node]['station_id']
                                next_node = self.graph.nodes[node].get('next_node')
                                next_node_id = self.graph.nodes[next_node].get('station_id') if next_node else None
                                if next_node is None:
                                    break
                                tau[(k, next_node_id)] = tau[(k, station_id)] + self.graph[node][next_node]['weight']
                                if best_trip_possible[next_node_id] > tau[(k, next_node_id)]:
                                    best_trip_possible[next_node_id] = tau[(k, next_node_id)]
                                    parent[next_node_id] = station_id
                                    prev_change_nodes.append(station_to_node[next_node_id])
                                node = next_node

        # Skip trường hợp tệ hơn best_trip_possible[target_id] 


        # Reconstruct path