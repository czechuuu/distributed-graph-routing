import argparse
import networkx as nx
from google.cloud import bigtable
from serving_layer.storage_types import bigtable_storage_pb2

def find_bridge_nodes(project_id, instance_id):
    client = bigtable.Client(project=project_id, admin=True)
    instance = client.instance(instance_id)
    
    # 1. Get Overlay Graph to find a bridge
    overlay_table = instance.table("overlay_graph")
    row_key = b"O#"
    row = overlay_table.read_row(row_key)
    
    if not row:
        print("Overlay graph not found.")
        return

    cell = row.cells.get('cf', {}).get(b'val', [])
    if not cell:
        print("Overlay graph empty.")
        return

    overlay = bigtable_storage_pb2.OverlayGraph()
    overlay.ParseFromString(cell[0].value)
    
    print(f"Overlay contains {len(overlay.bridges)} bridges and {len(overlay.shortcuts)} shortcuts.")
    
    if not overlay.bridges:
        print("No bridges found!")
        return
        
    # Pick the first bridge
    bridge = overlay.bridges[0]
    u, v = bridge.from_node_id, bridge.to_node_id
    print(f"Found Bridge: {u} -> {v}")
    
    # 2. Get Shard IDs for u and v
    node_index = instance.table("node_index")
    
    def get_shard(node_id):
        rk = f"N#{node_id}".encode('utf-8')
        r = node_index.read_row(rk)
        if r:
            c = r.cells.get('cf', {}).get(b'val', [])
            if c:
                lookup = bigtable_storage_pb2.ShardLookup()
                lookup.ParseFromString(c[0].value)
                return lookup.shard_id
        return None
        
    shard_u = get_shard(u)
    shard_v = get_shard(v)
    
    print(f"Start Node: {u} (Shard {shard_u})")
    print(f"End Node:   {v} (Shard {shard_v})")
    
    if shard_u == shard_v:
        print("WARNING: Bridge connects nodes in the SAME shard? Skipping.")
        return

    # Helper to load a shard graph
    def load_shard_graph(sid):
        t = instance.table("shards")
        rk = f"S#{sid}".encode('utf-8')
        r = t.read_row(rk)
        if not r: return None
        c = r.cells.get('cf', {}).get(b'val', [])
        if not c: return None
        shard_pb = bigtable_storage_pb2.ShardGraph()
        shard_pb.ParseFromString(c[0].value)
        g = nx.DiGraph()
        for e in shard_pb.edges:
            g.add_edge(e.from_node_id, e.to_node_id, weight=e.weight)
        return g

    print(f"Loading Shard {shard_u} to extend path backwards...")
    G_u = load_shard_graph(shard_u)
    
    start_node = u
    # Find a node that reaches 'u' with some hops
    # Reverse graph to finding incoming paths easily
    if G_u:
        try:
            # Dijkstra on reversed graph from u
            lengths = nx.single_source_dijkstra_path_length(G_u.reverse(), u)
            # Find a node at least 1 hop away
            candidates = [n for n, dist in lengths.items() if dist > 0]
            if candidates:
                start_node = candidates[0] # Pick any
                print(f"  Found predecessor: {start_node} -> ... -> {u} (dist {lengths[start_node]})")
        except Exception as e:
            print(f"  Could not extend backwards: {e}")

    print(f"Loading Shard {shard_v} to extend path forwards...")
    G_v = load_shard_graph(shard_v)
    
    end_node = v
    if G_v:
        try:
            lengths = nx.single_source_dijkstra_path_length(G_v, v)
            candidates = [n for n, dist in lengths.items() if dist > 0]
            if candidates:
                end_node = candidates[0]
                print(f"  Found successor: {v} -> ... -> {end_node} (dist {lengths[end_node]})")
        except Exception as e:
            print(f"  Could not extend forwards: {e}")

    print("\n--- COMPLEX CROSS-SHARD TEST CASE ---")
    print(f"Start Node: {start_node} (Shard {shard_u})")
    print(f"End Node:   {end_node} (Shard {shard_v})")
    
    path_len = 1 # The bridge itself
    if start_node != u: path_len += 1
    if end_node != v: path_len += 1
    
    print(f"Estimated Minimum Hops: {path_len}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', default='repetitive-shortest-paths')
    parser.add_argument('--instance', default='routing-instance')
    args = parser.parse_args()
    
    find_bridge_nodes(args.project, args.instance)
