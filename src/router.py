import networkx as nx
from fastapi import FastAPI, Query

app = FastAPI()

class MetroRouter:
    def __init__(self, graph, api_client):
        self.graph = graph
        self.api = api_client

    def find_path(self, start_node, end_node):
        wait_time = self.api.get_realtime_prediction(start_node)
        print(f"--- Đang tính toán... Thời gian chờ tàu: {wait_time} phút ---")

        try:
            path = nx.shortest_path(self.graph, 
                                    source=start_node, 
                                    target=end_node, 
                                    weight='weight')
            
            travel_time = nx.shortest_path_length(self.graph, start_node, end_node, weight='weight')
            total_time = wait_time + travel_time
            
            return {
                "path": [self.graph.nodes[node]['name'] for node in path],
                "total_time": total_time
            }
        except nx.NetworkXNoPath:
            return None

@app.get("/route")
def route(
    from_stop: str = Query(..., alias="from"),
    to_stop: str = Query(..., alias="to"),
    dep: int = Query(...)
):
    router = MetroRouter(graph, api_client)
    result = router.find_path(from_stop, to_stop)

    if result is None:
        return {"error": "No path found"}

    return result
