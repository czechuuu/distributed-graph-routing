import argparse
from google.cloud import bigtable
from serving_layer.storage_types import bigtable_storage_pb2

def get_node_shard(project_id, instance_id, node_id):
    client = bigtable.Client(project=project_id, admin=True)
    instance = client.instance(instance_id)
    table = instance.table("node_index")
    
    row_key = f"N#{node_id}".encode('utf-8')
    row = table.read_row(row_key)
    
    if row:
        cell = row.cells.get('cf', {}).get(b'val', [])
        if cell:
            print(f"Raw Hex: {cell[0].value.hex()}")
            lookup = bigtable_storage_pb2.ShardLookup()
            lookup.ParseFromString(cell[0].value)
            print(f"Node {node_id} is in Shard: {lookup.shard_id}")
            return lookup.shard_id
    else:
        print(f"Node {node_id} NOT FOUND in node_index")
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--node_id', required=True, type=int)
    parser.add_argument('--project', default='repetitive-shortest-paths')
    parser.add_argument('--instance', default='routing-instance')
    args = parser.parse_args()
    
    get_node_shard(args.project, args.instance, args.node_id)
