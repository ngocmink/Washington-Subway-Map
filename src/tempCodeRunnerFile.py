G = builder.build()
path = nx.shortest_path(G, source='STN_G02', target='STN_G01', weight='weight')
print("Đường đi tối ưu:", path)