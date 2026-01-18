import argparse
from google.cloud import bigtable
from serving_layer.storage_types import bigtable_storage_pb2

def inspect_shard(project_id, instance_id, shard_id_str):
    client = bigtable.Client(project=project_id, admin=True)
    instance = client.instance(instance_id)
    table = instance.table("shards")
    
    row_key = f"S#{shard_id_str}".encode('utf-8')
    row = table.read_row(row_key)
    
    if row:
        cell = row.cells.get('cf', {}).get(b'val', [])
        if cell:
            print(f"Raw Hex: {cell[0].value.hex()}")
            shard = bigtable_storage_pb2.ShardGraph()
            shard.ParseFromString(cell[0].value)
            print(f"Shard {shard_id_str} parsed object:\n{shard}")
            print(f"Shard {shard_id_str} contains {len(shard.locations)} locations.")
            print("Nodes found in shard:")
            for loc in shard.locations:
                print(f" - {loc.node_id}")
    else:
        print(f"Shard {shard_id_str} NOT FOUND")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--shard_id', required=True, type=str)
    parser.add_argument('--project', default='repetitive-shortest-paths')
    parser.add_argument('--instance', default='routing-instance')
    args = parser.parse_args()
    
    inspect_shard(args.project, args.instance, args.shard_id)
