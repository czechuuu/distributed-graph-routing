import argparse
import networkx as nx
from google.cloud import bigtable
from serving_layer.storage_types import bigtable_storage_pb2

def find_distant_nodes(project_id, instance_id, start_row_key=None):
    client = bigtable.Client(project=project_id, admin=True)
    instance = client.instance(instance_id)
    table = instance.table("shards")
    
    # Scan for up to 100 shards
    rows = table.read_rows(limit=100)
    
    for row in rows:
        shard_id_str = row.row_key.decode('utf-8').replace('S#', '')
        cell = row.cells.get('cf', {}).get(b'val', [])
        if not cell: continue

        try:
            shard = bigtable_storage_pb2.ShardGraph()
            shard.ParseFromString(cell[0].value)
        except:
            continue

        if len(shard.locations) < 5:
            continue # Skip tiny shards
            
        print(f"Checking Shard {shard_id_str} (Size: {len(shard.locations)})...")
        
        G = nx.DiGraph()
        for e in shard.edges:
            G.add_edge(e.from_node_id, e.to_node_id, weight=e.weight)
            
        # Search for a long path
        try:
            # Get a few sample nodes
            nodes = list(G.nodes())
            if not nodes: continue
            
            # BFS from first node
            start_node = nodes[0]
            lengths = nx.single_source_dijkstra_path_length(G, start_node)
            
            # Find max length
            max_node = max(lengths, key=lengths.get)
            max_dist = lengths[max_node]
            
            path = nx.shortest_path(G, start_node, max_node)
            if len(path) > 3: # 3 hops means 4 nodes: A->B->C->D
                print(f"\n[FOUND] Shard: {shard_id_str}")
                print(f"Path Length (Steps): {len(path)}")
                print(f"Path Nodes: {path}")
                print(f"Start Node: {start_node}")
                print(f"End Node: {max_node}")
                return
        except Exception as e:
            pass

    print("No complex path found in first 100 shards.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--shard_id', default='5116266404223385600', type=str)
    parser.add_argument('--project', default='repetitive-shortest-paths')
    parser.add_argument('--instance', default='routing-instance')
    args = parser.parse_args()
    
    find_distant_nodes(args.project, args.instance, args.shard_id)
