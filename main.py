from src.graph_builder import MetroGraphBuilder
from src.wmata_api import WmataAPI
from src.router import MetroRouter

GTFS_FILE = "data/google_transit.zip"
MY_API_KEY = "1b189a39a39f4a209b91cdac2fa01c26"

def main():
    builder = MetroGraphBuilder(GTFS_FILE)
    metro_map = builder.build()

    api = WmataAPI(MY_API_KEY)
    router = MetroRouter(metro_map, api)

    start_ga = "A01" 
    end_ga = "A15"   
    
    result = router.find_path(start_ga, end_ga)

    if result:
        print(f"\nLộ trình từ {result['path'][0]} đến {result['path'][-1]}:")
        print(" -> ".join(result['path']))
        print(f"Tổng thời gian dự kiến: {result['total_time']} phút")
    else:
        print("Không tìm thấy đường đi!")

if __name__ == "__main__":
    main()