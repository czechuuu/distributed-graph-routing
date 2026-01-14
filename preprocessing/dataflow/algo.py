
import networkx as nx
from typing import List, Tuple, Set
from .model import Node, Edge, Shortcut

def build_shard_graph(nodes: List[Node], edges: List[Edge]) -> nx.DiGraph:
    """Builds a NetworkX DiGraph for the shard."""
    G = nx.DiGraph()
    for n in nodes:
        G.add_node(n.id, x=n.x, y=n.y, shard_id=n.shard_id)
    
    for e in edges:
        G.add_edge(e.u, e.v, weight=e.weight)
    return G

def identify_boundary_nodes(graph: nx.DiGraph, current_shard_id: int) -> Tuple[Set[int], Set[int]]:
    """
    Identifies in-boundary and out-boundary nodes based on graph structure.
    
    in-boundary: node IN this shard having an incoming edge FROM a different shard
    out-boundary: node IN this shard having an outgoing edge TO a different shard
    """
    in_boundary = set()
    out_boundary = set()

    for u, v in graph.edges():
        u_data = graph.nodes.get(u, {})
        v_data = graph.nodes.get(v, {})
        
        u_shard = u_data.get('shard_id')
        v_shard = v_data.get('shard_id')
        
        # Check Out-Boundary: u is internal, v is external
        if u_shard == current_shard_id and v_shard != current_shard_id:
            out_boundary.add(u)
            
        # Check In-Boundary: v is internal, u is external
        if v_shard == current_shard_id and u_shard != current_shard_id:
            in_boundary.add(v)
            
    return in_boundary, out_boundary

def compute_shortcuts(graph: nx.DiGraph, in_nodes: Set[int], out_nodes: Set[int]) -> List[Shortcut]:
    shortcuts = []
    
    for src in in_nodes:
        if not graph.has_node(src):
            continue
            
        try:
            # Calculate weights and paths from src to all reachable nodes
            weights, paths = nx.single_source_dijkstra(graph, src, weight='weight')
            
            for dst in out_nodes:
                if dst in weights:
                    if src == dst: continue
                    
                    # Create Shortcut object with full path
                    shortcuts.append(Shortcut(
                        u=src, 
                        v=dst, 
                        weight=weights[dst], 
                        path=paths[dst] 
                    ))
                    
        except Exception as e:
            print(f"Error for {src}: {e}")
            continue

    return shortcuts
