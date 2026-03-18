import pandas as pd
import networkx as nx
import zipfile

class MetroGraphBuilder:
    def __init__(self, gtfs_path):
        self.gtfs_path = gtfs_path
        self.graph = nx.Graph()

    def build(self):
        with zipfile.ZipFile(self.gtfs_path) as zf:
            # 1. Đọc danh sách ga
            stops = pd.read_csv(zf.open('stops.txt'))
            for _, row in stops.iterrows():
                # Chỉ lấy các ga chính (location_type = 1 hoặc không có parent_station)
                if pd.isna(row['parent_station']):
                    self.graph.add_node(row['stop_id'], 
                                        name=row['stop_name'], 
                                        pos=(row['stop_lat'], row['stop_lon']))

            # 2. Đọc lịch trình để nối các cạnh (Edges)
            stop_times = pd.read_csv(zf.open('stop_times.txt'))
            # Sắp xếp theo chuyến và thứ tự ga
            stop_times = stop_times.sort_values(['trip_id', 'stop_sequence'])
            
            # Nối các ga kế tiếp nhau trong cùng một chuyến (trip)
            trips = stop_times.groupby('trip_id')
            for _, group in trips:
                nodes = group['stop_id'].tolist()
                for i in range(len(nodes) - 1):
                    # Giả định trọng số mặc định là 3 phút nếu không tính toán cụ thể
                    self.graph.add_edge(nodes[i], nodes[i+1], weight=3)
        
        print(f"Đã dựng xong đồ thị với {self.graph.number_of_nodes()} ga.")
        return self.graph