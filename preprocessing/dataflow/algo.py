
from typing import List, Tuple, Set, Dict, Any
from .model import Node, Edge, Shortcut


def build_shard_graph(nodes: List[Node], edges: List[Edge]) -> Tuple[Any, Dict[int, int], List[int]]:
    """
    Builds an igraph Graph for the shard from internal nodes and edges only.
    
    Returns:
        - G: the igraph Graph
        - id_to_idx: mapping from node_id to igraph vertex index
        - idx_to_id: list mapping igraph vertex index to node_id
    """
    # Lazy import - only load igraph when actually running on Dataflow workers
    import igraph as ig
    
    # Build node ID mappings
    node_ids = [n.id for n in nodes]
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
    idx_to_id = node_ids
    
    # Create graph
    G = ig.Graph(n=len(node_ids), directed=True)
    G.vs['node_id'] = node_ids
    
    # Add edges - all internal edges should have both endpoints in the shard
    edge_tuples = []
    weights = []
    for e in edges:
        edge_tuples.append((id_to_idx[e.u], id_to_idx[e.v]))
        weights.append(e.weight)
    
    if edge_tuples:
        G.add_edges(edge_tuples)
        G.es['weight'] = weights
    
    return G, id_to_idx, idx_to_id


def compute_shortcuts(graph: Any, id_to_idx: Dict[int, int], idx_to_id: List[int],
                      in_nodes: Set[int], out_nodes: Set[int]) -> List[Shortcut]:
    """
    Compute shortcuts between in-boundary and out-boundary nodes using Dijkstra.
    
    in_nodes: set of node IDs that are IN-boundary (have incoming edges from other shards)
    out_nodes: set of node IDs that are OUT-boundary (have outgoing edges to other shards)
    
    All boundary nodes must exist in this shard's node set.
    """
    shortcuts = []
    
    for src_id in in_nodes:
        src_idx = id_to_idx[src_id]
        
        # Get shortest paths from source to all reachable nodes
        paths = graph.get_shortest_paths(src_idx, weights='weight', output='vpath')
        distances = graph.shortest_paths(source=src_idx, weights='weight')[0]
        
        for dst_id in out_nodes:
            if src_id == dst_id:
                continue
                
            dst_idx = id_to_idx[dst_id]
            weight = distances[dst_idx]
            
            # Only create shortcut if path exists (not infinity)
            if weight != float('inf'):
                path_indices = paths[dst_idx]
                if not path_indices:
                    raise ValueError(f"Path is empty but distance is finite from {src_id} to {dst_id}")
                    
                path_node_ids = [idx_to_id[i] for i in path_indices]
                
                shortcuts.append(Shortcut(
                    u=src_id,
                    v=dst_id,
                    weight=weight,
                    path=path_node_ids
                ))
    
    return shortcuts

