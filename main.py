from src.graph_builder import MetroGraphBuilder
from src.wmata_api import WmataAPI
from src.router import MetroRouter

# Cấu hình
GTFS_FILE = "data/google_transit.zip"
MY_API_KEY = "1b189a39a39f4a209b91cdac2fa01c26"

def main():
    # Bước 1: Dựng đồ thị từ dữ liệu tĩnh
    builder = MetroGraphBuilder(GTFS_FILE)
    metro_map = builder.build()

    # Bước 2: Khởi tạo API và Router
    api = WmataAPI(MY_API_KEY)
    router = MetroRouter(metro_map, api)

    # Bước 3: Chạy thử tìm đường
    # Ví dụ: A01 là Metro Center, C01 là Metro Center (tầng khác) hoặc ga khác
    start_ga = "A01" # Metro Center
    end_ga = "A15"   # Shady Grove
    
    result = router.find_path(start_ga, end_ga)

    if result:
        print(f"\nLộ trình từ {result['path'][0]} đến {result['path'][-1]}:")
        print(" -> ".join(result['path']))
        print(f"Tổng thời gian dự kiến: {result['total_time']} phút")
    else:
        print("Không tìm thấy đường đi!")

if __name__ == "__main__":
    main()