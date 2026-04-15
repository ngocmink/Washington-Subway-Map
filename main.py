import networkx as nx
from src.graph import MetroGraphBuilder
from src.algorithm import MetroRouter


MY_API_KEY = "1b189a39a39f4a209b91cdac2fa01c26"

def main():
    MGB = MetroGraphBuilder('./data/rail.zip', transfer_penalty=300)
    metro_map = MGB.build()
    path = MetroRouter(metro_map, source='Capitol Heights', target='McPherson Sq', dep_time='08:00:00', k=3)()
    print("Đường đi:")
    print(path)
    path_nx = nx.shortest_path(metro_map, source='STN_G02', target='STN_C02', weight='weight')
    print(path_nx)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()