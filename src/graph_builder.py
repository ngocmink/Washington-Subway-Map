import pandas as pd
import networkx as nx
import zipfile

class MetroGraphBuilder:
    def __init__(self, gtfs_path, transfer_penalty=300):
        self.gtfs_path = gtfs_path
        self.graph = nx.DiGraph()
        self.transfer_penalty = transfer_penalty
    
    def to_seconds(self, t):
        h, m, s = map(int, t.split(':'))
        return h * 3600 + m * 60 + s

    def build(self):
        with zipfile.ZipFile(self.gtfs_path) as zf:
            # Read stations
            stops = pd.read_csv(zf.open('stops.txt'), dtype={'stop_id': str})
            trips = pd.read_csv(zf.open('trips.txt'), dtype={'trip_id': str, 'route_id': str})
            stop_times = pd.read_csv(zf.open('stop_times.txt'), dtype={'trip_id': str, 'stop_id': str})

            trip_to_route = dict(zip(trips['trip_id'], trips['route_id']))

            for _, row in stops.iterrows():
                self.graph.add_node(row['stop_id'], 
                                    name=row['stop_name'],
                                    pos=(row['stop_lat'], row['stop_lon']))

            # Rearrange
            stop_times = stop_times.sort_values(['trip_id', 'stop_sequence'])
            # Connect edges in 1 trip
            trips = stop_times.groupby('trip_id')

            for trip_id, group in trips:
                route_id = trip_to_route[trip_id]   # Lấy route_id từ trip_id (trip: chuyến thứ n, route: tuyến cố định)
                nodes_in_trip = group['stop_id'].tolist() # Lấy stop_id trong chuyến
                times = group['arrival_time'].apply(self.to_seconds).tolist()

                for i in range(len(nodes_in_trip)):
                    stop_id = nodes_in_trip[i]
                    route_node = f"{stop_id}_{route_id}" # route_id: chuyến tàu, stop_id: trạm dừng, route_node: node đại diện cho trạm dừng trên tuyến tàu đó

                    if route_node not in self.graph:
                        self.graph.add_node(route_node, type='route_stop', route=route_id)
                        
                        penalty = self.transfer_penalty / 2 # Phạt 1 nửa thời gian có tàu
                        self.graph.add_edge(route_node, stop_id, weight=30, label='exit_to_hub')
                        self.graph.add_edge(stop_id, route_node, weight=penalty, label='enter_from_hub')

                    if i < len(nodes_in_trip) - 1:
                        next_stop_id = nodes_in_trip[i+1]
                        next_route_node = f"{next_stop_id}_{route_id}"
                        
                        travel_time = times[i+1] - times[i]
                        if travel_time >= 0:
                            # Chỉ nối giữa các node cùng tuyến (route_node)
                            self.graph.add_edge(route_node, next_route_node, 
                                                weight=travel_time, 
                                                label='travel')
            
            print(f"Đồ thị hoàn tất: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges.")
            return self.graph



# Sử dụng
builder = MetroGraphBuilder('./data/rail.zip', transfer_penalty=300) 
G = builder.build()
path = nx.shortest_path(G, source='STN_G02', target='STN_G01', weight='weight')
print("Đường đi tối ưu:", path)