import os
from google.cloud import bigtable
from google.cloud.bigtable import row_filters
import data_domain.storage_types.bigtable_storage_pb2 as pb
# If running as a module, imports might need adjustment. 
# We assume this is run as 'python -m data_domain.main'

class BigtableClient:
    def __init__(self, project_id=None, instance_id=None):
        self.project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT", "repetitive-shortest-paths")
        self.instance_id = instance_id or os.environ.get("BIGTABLE_INSTANCE", "routing-instance")
        
        # If project_id is None, the client will attempt to infer it from credentials
        self.client = bigtable.Client(project=self.project_id, admin=True)
        self.instance = self.client.instance(self.instance_id)

        self.table_shards = self.instance.table("shards")
        self.table_shortcuts = self.instance.table("shortcuts")
        self.table_node_index = self.instance.table("node_index")
        self.table_overlay = self.instance.table("overlay_graph")

    def get_node_shard(self, node_id: str) -> int:
        row_key = f"N#{node_id}".encode('utf-8')
        row = self.table_node_index.read_row(row_key)
        if not row:
            return None
        
        try:
            cell = row.cells['cf'][b'data'][0]
            lookup = pb.ShardLookup()
            lookup.ParseFromString(cell.value)
            return lookup.shard_id
        except (KeyError, IndexError):
            return None

    def get_node_shards_batch(self, node_ids: list[str]) -> dict[str, int]:
        row_set = bigtable.row_set.RowSet()
        for nid in node_ids:
            row_set.add_row_key(f"N#{nid}".encode('utf-8'))
        
        rows = self.table_node_index.read_rows(row_set=row_set)
        result = {}
        for row in rows:
            try:
                nid = row.row_key.decode('utf-8')[2:]
                cell = row.cells['cf'][b'data'][0]
                lookup = pb.ShardLookup()
                lookup.ParseFromString(cell.value)
                result[nid] = lookup.shard_id
            except (KeyError, IndexError):
                continue
        return result

    def get_shard(self, shard_id: str) -> pb.ShardGraph:
        row_key = f"S#{shard_id}".encode('utf-8')
        row = self.table_shards.read_row(row_key)
        if not row:
            return None
        
        try:
            cell = row.cells['cf'][b'data'][0]
            shard = pb.ShardGraph()
            shard.ParseFromString(cell.value)
            return shard
        except (KeyError, IndexError):
            return None

    def get_shortcut(self, from_node: int, to_node: int) -> pb.ShortcutPath:
        # Key: "P#" + from + "#" + to
        row_key = f"P#{from_node}#{to_node}".encode('utf-8')
        row = self.table_shortcuts.read_row(row_key)
        if not row:
            return None
        
        try:
            cell = row.cells['cf'][b'data'][0]
            path = pb.ShortcutPath()
            path.ParseFromString(cell.value)
            return path
        except (KeyError, IndexError):
            return None

    def get_overlay(self) -> pb.OverlayGraph:
        row_key = b"O#"
        row = self.table_overlay.read_row(row_key)
        if not row:
            return pb.OverlayGraph()
        
        try:
            cell = row.cells['cf'][b'data'][0]
            overlay = pb.OverlayGraph()
            overlay.ParseFromString(cell.value)
            return overlay
        except (KeyError, IndexError):
            return pb.OverlayGraph()
