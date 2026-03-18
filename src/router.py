import networkx as nx

class MetroRouter:
    def __init__(self, graph, api_client):
        self.graph = graph
        self.api = api_client

    def find_path(self, start_node, end_node):
        # 1. Cập nhật dữ liệu sống cho ga xuất phát
        wait_time = self.api.get_realtime_prediction(start_node)
        print(f"--- Đang tính toán... Thời gian chờ tàu: {wait_time} phút ---")

        # 2. Tìm đường ngắn nhất bằng thuật toán Dijkstra
        try:
            path = nx.shortest_path(self.graph, 
                                    source=start_node, 
                                    target=end_node, 
                                    weight='weight')
            
            # Tính tổng thời gian dự kiến
            travel_time = nx.shortest_path_length(self.graph, start_node, end_node, weight='weight')
            total_time = wait_time + travel_time
            
            return {
                "path": [self.graph.nodes[node]['name'] for node in path],
                "total_time": total_time
            }
        except nx.NetworkXNoPath:
            return None