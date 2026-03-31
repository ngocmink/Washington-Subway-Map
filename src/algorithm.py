import math
from collections import defaultdict
import networkx as nx

from .graph import MetroGraphBuilder

class MetroRouter:
    def __init__(self, graph, source, target, dep_time, k=5):
        self.graph = graph
        self.source = source
        self.target = target
        self.dep_time = dep_time
        self.k = k

    def find_path(self):
        et = {}
        best_trip_possible = {}

        for node in range(self.graph.nodes()):
            best_trip_possible[node] = float('inf')
        for i in range(self.k):
            for node in self.graph.nodes():
                et[(i, node)] = float('inf')

        if self.source not in self.graph or self.target not in self.graph:
            print("Source hoặc target không tồn tại trong graph.")
            return None
        
        name_to_node = {d['name']: n for n, d in self.graph.nodes(data=True) if 'name' in d}
        source_node = name_to_node.get(self.source)
        target_node = name_to_node.get(self.target)