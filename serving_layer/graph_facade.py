import logging
import networkx as nx

logger = logging.getLogger("GraphFacade")

try:
    from google.cloud import bigtable
    from google.cloud.bigtable import row_filters
except ImportError:
    bigtable = None
    row_filters = None
    logger.warning("google-cloud-bigtable not installed. Only mock mode will work.")
from typing import Dict, List, Tuple, Optional, OrderedDict as OrderedDictType
from collections import OrderedDict

from serving_layer import bigtable_storage_pb2

class GraphFacade:
    def __init__(self, project_id: str, instance_id: str, overlay_table_id: str, intra_table_id: str, shortcuts_table_id: str, use_mock: bool = False, max_cache_size: int = 10000):
        self.use_mock = use_mock
        self.max_cache_size = max_cache_size
        self.overlay = nx.DiGraph()
        self.shortcut_expansions: OrderedDictType[Tuple[int, int], List[int]] = OrderedDict()
        self.known_shortcuts: set[Tuple[int, int]] = set()
        
        if not self.use_mock:
            self.client = bigtable.Client(project=project_id, admin=True)
            self.instance = self.client.instance(instance_id)
            self.overlay_table = self.instance.table(overlay_table_id)
            self.intra_table = self.instance.table(intra_table_id)
            self.shortcuts_table = self.instance.table(shortcuts_table_id)
            
            self._load_overlay_graph()
        else:
            logger.info("GraphFacade initialized in mock mode.")

    def _load_overlay_graph(self):
        """Loads Overlay using Pure Protobuf."""
        logger.info("Loading Overlay Graph from Bigtable (Protobuf)...")
        try:
            rows = self.overlay_table.read_rows()
            for row in rows:
                # Load Proto structure
                cell_proto = row.cells.get('cf', {}).get(b'shortcuts_proto', [])
                
                # Parse Shortcuts
                if cell_proto:
                    overlay_pb = bigtable_storage_pb2.OverlayGraph()
                    overlay_pb.ParseFromString(cell_proto[0].value)
                    
                    for edge in overlay_pb.shortcuts:
                        u, v, w = edge.from_node_id, edge.to_node_id, edge.weight
                        self.overlay.add_edge(u, v, weight=w)
                        
                        # Register as known shortcut (lazy load path later)
                        self.known_shortcuts.add((u, v))
                            
                        # Handle Bidirectionality
                        if edge.bidirectional:
                            self.overlay.add_edge(v, u, weight=w)
                            self.known_shortcuts.add((v, u))

                # Parse Bridges (Inter-shard edges)
                cell_bridges = row.cells.get('cf', {}).get(b'inter_edges_proto', [])
                if cell_bridges:
                    bridges_pb = bigtable_storage_pb2.OverlayGraph()
                    bridges_pb.ParseFromString(cell_bridges[0].value)
                    for edge in bridges_pb.bridges:
                        self.overlay.add_edge(edge.from_node_id, edge.to_node_id, weight=edge.weight)
                        
            logger.info(f"Overlay Loaded. Nodes: {self.overlay.number_of_nodes()}, Edges: {self.overlay.number_of_edges()}")
            
        except Exception as e:
            logger.error(f"Error loading Overlay: {e}")

    def get_expansion(self, u: int, v: int) -> Optional[List[int]]:
        """
        Lazily loads the shortcut expansion path for edge u->v.
        """
        # 1. Check if it is a known shortcut
        if (u, v) not in self.known_shortcuts:
            return None

        # 2. Check in-memory cache
        if (u, v) in self.shortcut_expansions:
            # LRU: Move to end (most recently used)
            self.shortcut_expansions.move_to_end((u, v))
            return self.shortcut_expansions[(u, v)]

        # 3. Fetch from Bigtable
        if self.use_mock or getattr(self, 'shortcuts_table', None) is None:
            # In mock mode or if table not initialized, rely only on cache (checked above)
            if self.use_mock:
                logger.warning(f"Mock mode: Shortcut expansion for {u}->{v} not found in cache.")
            return None

        try:
            row_key = f"P#{u}#{v}".encode('utf-8')
            row = self.shortcuts_table.read_row(row_key)
            gsutil ls
            if row:
                cell = row.cells.get('cf', {}).get(b'val', [])
                if cell:
                    path_proto = bigtable_storage_pb2.ShortcutPath()
                    path_proto.ParseFromString(cell[0].value)
                    
                    path_list = list(path_proto.nodes)
                    self.shortcut_expansions[(u, v)] = path_list
                    
                    # LRU: Check size and evict if necessary
                    if len(self.shortcut_expansions) > self.max_cache_size:
                        self.shortcut_expansions.popitem(last=False) # Remove FIFO (oldest)
                    
                    return path_list
            
            logger.warning(f"Shortcut path for {u}->{v} not found in Bigtable.")
            return None
            
        except Exception as e:
            logger.error(f"Error fetching shortcut expansion {u}->{v}: {e}")
            return None

    def get_query_graph(self, start_node: int, end_node: int, node_to_shard: Dict[int, int]) -> nx.DiGraph:
        """
        Builds the specific graph for a query by combining:
        1. The Overlay Graph (Highways)
        2. Full detailed graph of the Start Shard
        3. Full detailed graph of the End Shard
        """
        # Start with the Overlay Graph
        query_graph = self.overlay.copy()
        
        start_shard = node_to_shard.get(start_node)
        end_shard = node_to_shard.get(end_node)
        
        if start_shard is None or end_shard is None:
            raise ValueError("Start or End node not found in shard mapping.")

        logger.info(f"Fetching Start Shard {start_shard}...")
        self._merge_shard_into_graph(query_graph, start_shard)
        
        if start_shard != end_shard:
            logger.info(f"Fetching End Shard {end_shard}...")
            self._merge_shard_into_graph(query_graph, end_shard)
            
        return query_graph

    def _merge_shard_into_graph(self, graph: nx.DiGraph, shard_id: int):
        """Fetches intra-edges using Protobuf."""
        if self.use_mock: return

        row_key = f"{shard_id}".encode('utf-8')
        row = self.intra_table.read_row(row_key)
        
        if row:
            # Load Proto for the whole shard
            cell = row.cells.get('cf', {}).get(b'shard_graph_proto', [])
            if cell:
                shard_pb = bigtable_storage_pb2.ShardGraph()
                shard_pb.ParseFromString(cell[0].value)
                
                for edge in shard_pb.edges:
                    graph.add_edge(
                        edge.from_node_id, 
                        edge.to_node_id, 
                        weight=edge.weight
                    )