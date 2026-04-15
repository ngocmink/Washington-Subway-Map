def find_path(self):
    G = self.graph
    dep_time = to_seconds(self.dep_time)

    # ── 1. Index helpers ──────────────────────────────────────────────────────
    # Lấy tất cả station nodes (type == 'station')
    all_stations = [
        n for n, d in G.nodes(data=True) if d.get('type') == 'station'
    ]
    # Map station_id → node key (giống nhau trong code của bạn, nhưng tường minh)
    sid_to_node = {G.nodes[n]['station_id']: n for n in all_stations}

    name_to_node = {d['name']: n for n, d in G.nodes(data=True) if 'name' in d}
    src_node = name_to_node.get(self.source)
    tgt_node = name_to_node.get(self.target)

    if src_node is None or tgt_node is None:
        print("Source hoặc target không tồn tại.")
        return None

    src_id = G.nodes[src_node]['station_id']
    tgt_id = G.nodes[tgt_node]['station_id']

    # ── 2. Khởi tạo tau và tau_star ───────────────────────────────────────────
    # tau[k][sid]   = earliest arrival tại station sid dùng đúng k chuyến
    # tau_star[sid] = earliest arrival tại sid dùng bất kỳ số chuyến nào (τ*)
    INF = float('inf')
    tau      = [{sid: INF for sid in sid_to_node} for _ in range(self.k + 1)]
    tau_star = {sid: INF for sid in sid_to_node}

    tau[0][src_id]      = dep_time
    tau_star[src_id]    = dep_time
    marked              = {src_id}          # stations được update ở round trước

    # parent[sid] = (prev_sid, route_id | 'walk', board_time, alight_time)
    # dùng để reconstruct path sau này
    parent = {}

    # ── 3. Walking relaxation (helper) ────────────────────────────────────────
    def relax_walking(round_k: int, updated: set[str]) -> set[str]:
        """
        Với mỗi station vừa được update trong round này,
        relax walking edges sang station lân cận.
        Trả về tập stations mới được improve.
        """
        newly_marked = set()
        for sid in list(updated):
            node = sid_to_node[sid]
            t    = tau[round_k][sid]
            if t == INF:
                continue
            for nbr in G.successors(node):
                if G.nodes[nbr].get('type') != 'station':
                    continue
                edge = G[node][nbr]
                if edge.get('label') != 'walk':
                    continue
                nbr_sid  = G.nodes[nbr]['station_id']
                arr_walk = t + edge['weight']
                if arr_walk < tau_star[nbr_sid]:
                    tau[round_k][nbr_sid] = min(tau[round_k][nbr_sid], arr_walk)
                    tau_star[nbr_sid]     = arr_walk
                    parent[nbr_sid]       = (sid, 'walk', t, arr_walk)
                    newly_marked.add(nbr_sid)
        return newly_marked

    # Walking từ source trước khi bắt đầu vòng lặp (round 0)
    marked |= relax_walking(0, marked)

    # ── 4. RAPTOR main loop ───────────────────────────────────────────────────
    for k in range(1, self.k + 1):

        # Kế thừa từ round trước: tau[k] bắt đầu từ tau[k-1]
        for sid in all_stations:
            tau[k][sid] = tau[k - 1][sid]

        # 4a. Thu thập các route đi qua ít nhất một marked station
        #     route_id → earliest marked station trên route đó (theo thứ tự trip)
        routes_to_scan: dict[str, tuple[str, int]] = {}  # route_id → (sid, arr)

        for sid in marked:
            node = sid_to_node[sid]
            for nbr in G.successors(node):
                if G.nodes[nbr].get('type') != 'route_stop':
                    continue
                route_id = G.nodes[nbr].get('route')
                if route_id is None:
                    continue
                # Nếu route chưa có, hoặc station này sớm hơn, thay thế
                if route_id not in routes_to_scan:
                    routes_to_scan[route_id] = (sid, tau_star[sid])
                else:
                    _, best_t = routes_to_scan[route_id]
                    if tau_star[sid] < best_t:
                        routes_to_scan[route_id] = (sid, tau_star[sid])

        # 4b. Traverse từng route
        newly_marked = set()

        for route_id, (board_sid, _) in routes_to_scan.items():
            # Tìm route_stop node tương ứng với board_sid trên route này
            board_node_id = f"{board_sid}_{route_id}"
            if board_node_id not in G:
                continue

            # Tìm chuyến sớm nhất có thể lên tại board_sid
            arr_times = G.nodes[board_node_id].get('arr_time', [])
            earliest  = tau[k - 1][board_sid]       # τ(k-1, board_sid)
            idx       = bisect.bisect_left(arr_times, earliest)
            if idx >= len(arr_times):
                continue                             # không có chuyến nào kịp

            trip_dep   = arr_times[idx]
            board_time = trip_dep
            node       = board_node_id

            # Traverse dọc theo route
            while True:
                nd        = G.nodes[node]
                sid       = nd['station_id']
                arr       = tau[k][sid]

                # Prune: nếu đã tệ hơn tau_star[tgt_id] thì bỏ
                if trip_dep > tau_star[tgt_id]:
                    break

                # Update nếu tốt hơn
                if trip_dep < tau_star[sid]:
                    tau[k][sid]   = trip_dep
                    tau_star[sid] = trip_dep
                    parent[sid]   = (board_sid, route_id, board_time, trip_dep)
                    newly_marked.add(sid)

                # Sang station tiếp theo
                next_node = nd.get('next_node')
                if next_node is None:
                    break

                # next_node trong graph builder của bạn hiện là stop_id thô,
                # cần map sang route_stop node
                next_rs = f"{next_node}_{route_id}"
                if next_rs not in G:
                    break

                edge      = G[node].get(next_rs)
                if edge is None:
                    break
                trip_dep  = trip_dep + edge['weight']   # cộng dồn travel time
                node      = next_rs

        # 4c. Walking relaxation sau khi traverse xong round này
        newly_marked |= relax_walking(k, newly_marked)
        marked        = newly_marked

        # Early termination nếu không còn station nào được improve
        if not marked:
            break

    # ── 5. Reconstruct path ───────────────────────────────────────────────────
    if tau_star[tgt_id] == INF:
        print("Không tìm thấy đường đi hợp lệ.")
        return None

    legs   = []
    cur_id = tgt_id
    while cur_id != src_id:
        info = parent.get(cur_id)
        if info is None:
            print("Lỗi truy vết đường đi.")
            return None
        prev_sid, route_or_walk, t_board, t_alight = info
        legs.append({
            'from'      : prev_sid,
            'to'        : cur_id,
            'route'     : route_or_walk,
            'board_time': seconds_to_hms(t_board),
            'alight_time': seconds_to_hms(t_alight),
        })
        cur_id = prev_sid

    legs.reverse()
    return legs