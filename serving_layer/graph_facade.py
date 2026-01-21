import logging
import networkx as nx
from typing import Dict, List, Tuple

logger = logging.getLogger("GraphFacade")

try:
    from google.cloud import bigtable
    from google.cloud.bigtable.row_set import RowSet
except ImportError:
    bigtable = None
    RowSet = None
    logger.warning("google-cloud-bigtable not installed.")

from serving_layer.storage_types import bigtable_storage_pb2

class GraphFacade:
    def __init__(self, project_id: str, instance_id: str, overlay_table_id: str, shortcuts_table_id: str, intra_table_id: str, node_index_table_id: str, use_mock: bool = False):
        self.use_mock = use_mock
        self.overlay = nx.DiGraph()
        # Cache for expansions of shortcuts (to avoid asking Bigtable for the same thing repeatedly)
        self.shortcut_cache: Dict[Tuple[int, int], List[int]] = {}
        self.node_coord_cache: Dict[int, Tuple[float, float]] = {}
        
        if not self.use_mock:
            try:
                self.client = bigtable.Client(project=project_id, admin=True)
                self.instance = self.client.instance(instance_id)
                self.overlay_table = self.instance.table(overlay_table_id)
                self.shortcuts_table = self.instance.table(shortcuts_table_id)
                self.intra_table = self.instance.table(intra_table_id)
                self.node_index_table = self.instance.table(node_index_table_id)
                self._load_overlay_graph()
            except Exception as e:
                logger.error(f"Bigtable connection failed: {e}")

    def _load_overlay_graph(self):
        """Loads Overlay using Pure Protobuf."""
        logger.info("Loading Overlay Graph from Bigtable (Protobuf)...")
        try:
            row_key = b"O#"
            row = self.overlay_table.read_row(row_key)
            
            if not row:
                logger.warning("Overlay row 'O#' not found!")
                return

            cell = row.cells.get('cf', {}).get(b'val', [])
            
            if cell:
                overlay_pb = bigtable_storage_pb2.OverlayGraph()
                overlay_pb.ParseFromString(cell[0].value)
                
                # Load shortcuts (only topology)
                for edge in overlay_pb.shortcuts:
                    u, v, w = edge.from_node_id, edge.to_node_id, edge.weight
                    self.overlay.add_edge(u, v, weight=w)
                    if edge.bidirectional:
                        self.overlay.add_edge(v, u, weight=w)

                # Load bridges
                for edge in overlay_pb.bridges:
                    self.overlay.add_edge(edge.from_node_id, edge.to_node_id, weight=edge.weight)
                        
            logger.info(f"Overlay Loaded. Nodes: {self.overlay.number_of_nodes()}, Edges: {self.overlay.number_of_edges()}")
            
        except Exception as e:
            logger.error(f"Error loading Overlay: {e}")

    def get_query_graph(self, start_node: int, end_node: int, node_to_shard: Dict[int, int]) -> nx.DiGraph:
        query_graph = self.overlay.copy()
        
        start_shard = node_to_shard.get(start_node)
        end_shard = node_to_shard.get(end_node)
        
        if start_shard is None or end_shard is None:
            logger.warning("Start or End node not found in shard mapping.")
            return query_graph

        logger.info(f"Fetching Start Shard {start_shard}...")
        self._merge_shard_into_graph(query_graph, start_shard)
        if start_shard != end_shard:
            logger.info(f"Fetching End Shard {end_shard}...")
            self._merge_shard_into_graph(query_graph, end_shard)
            
        return query_graph

    def _merge_shard_into_graph(self, graph: nx.DiGraph, shard_id: int):
        if self.use_mock: return
        try:
            row_key = f"S#{shard_id}".encode('utf-8')
            row = self.intra_table.read_row(row_key)
            
            if row:
                cell = row.cells.get('cf', {}).get(b'val', [])
                if cell:
                    shard_pb = bigtable_storage_pb2.ShardGraph()
                    shard_pb.ParseFromString(cell[0].value)
                    
                    logger.info(f"Shard Content: {len(shard_pb.edges)} edges, {len(shard_pb.locations)} locations")
                    
                    # Add nodes explicitly (important for source/target nodes)
                    for loc in shard_pb.locations:
                         self.node_coord_cache[loc.node_id] = (loc.x, loc.y)
                         graph.add_node(loc.node_id, x=loc.x, y=loc.y)

                    for edge in shard_pb.edges:
                        graph.add_edge(edge.from_node_id, edge.to_node_id, weight=edge.weight)
        except Exception as e:
            logger.warning(f"Failed to load shard {shard_id}: {e}")

    def prefetch_coords(self, node_ids: List[int]):
        """
        Prefetches coordinates for missing nodes. 
        Tries to get coordinates directly from node_index (loc column).
        """
        if self.use_mock: return
        
        # Identify missing nodes
        missing_nodes = [n for n in node_ids if n not in self.node_coord_cache]
        if not missing_nodes:
            return
            
        try:
            # Look up Node Index (get NodeLocation)
            node_rowset = RowSet()
            for n in missing_nodes:
                node_rowset.add_row_key(f"N#{n}".encode('utf-8'))
                
            rows = self.node_index_table.read_rows(row_set=node_rowset)
            
            for row in rows:
                # Try to get coordinates directly
                loc_cell = row.cells.get('cf', {}).get(b'loc', [])
                if loc_cell:
                    loc_pb = bigtable_storage_pb2.NodeLocation()
                    loc_pb.ParseFromString(loc_cell[0].value)
                    self.node_coord_cache[loc_pb.node_id] = (loc_pb.x, loc_pb.y)
                        
        except Exception as e:
            logger.error(f"Error in prefetch_coords: {e}")

    def get_expansion(self, u: int, v: int) -> List[int]:
        """
        Fetches the full path for shortcut u->v.
        First checks cache, then Bigtable (row P#u#v).
        """
        # Check cache
        if (u, v) in self.shortcut_cache:
            return self.shortcut_cache[(u, v)]

        # Fetch from Bigtable
        if self.use_mock: 
            return []

        try:
            row_key = f"P#{u}#{v}".encode('utf-8')
            row = self.shortcuts_table.read_row(row_key) # Shortcuts table
            
            if row:
                cell = row.cells.get('cf', {}).get(b'val', [])
                if cell:
                    path_proto = bigtable_storage_pb2.ShortcutPath()
                    path_proto.ParseFromString(cell[0].value)
                    path = list(path_proto.nodes)
                    
                    # Save in cache for future use
                    self.shortcut_cache[(u, v)] = path
                    return path
        except Exception as e:
            logger.warning(f"Failed to fetch expansion for {u}->{v}: {e}")
            
    def get_node_coords(self, node_id: int) -> Tuple[float, float]:
        """Returns (lat, lng) for a node if found in cache."""
        return self.node_coord_cache.get(node_id)
            
        return []
