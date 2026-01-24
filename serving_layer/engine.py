import logging
import networkx as nx
from typing import List, Dict
from .graph_facade import GraphFacade

logger = logging.getLogger("RoutingEngine")

def find_shortest_path(facade: GraphFacade, start_node: int, end_node: int, node_to_shard: Dict[int, int]) -> List[int]:
    """
    Orchestrates the routing process:
    1. Build the Query Graph (Overlay + Source Shard + Target Shard)
    2. Run Bidirectional Dijkstra
    3. Unpack Shortcuts
    """
    
    # Component Assembly
    try:
        graph = facade.get_query_graph(start_node, end_node, node_to_shard)
    except ValueError as e:
        logger.error(f"Routing Error: {e}")
        return []

    # Pathfinding
    try:
        path = nx.bidirectional_dijkstra(graph, start_node, end_node, weight='weight')[1]

        logger.debug(f"Raw Path found: {path}")
    except nx.NetworkXNoPath:
        logger.info("No path found.")
        return []
    except Exception as e:
        logger.error(f"Pathfinding failed: {e}")
        return []

    # Path Reconstruction (Unpacking Shortcuts)
    return unpack_path(path, facade)

def unpack_path(path_nodes: List[int], facade: GraphFacade) -> List[int]:
    """
    Expands any shortcut edges in the path into their full sequence of nodes.
    """
    full_path = []
    
    if not path_nodes:
        return []

    # Add the first node
    full_path.append(path_nodes[0])

    # Pre-fetch expansions for all edges in the path
    edges = []
    for i in range(len(path_nodes) - 1):
        edges.append((path_nodes[i], path_nodes[i+1]))
    
    facade.get_expansions_batch(edges)
    
    for i in range(len(path_nodes) - 1):
        u = path_nodes[i]
        v = path_nodes[i+1]
        
        # Check if (u, v) is a shortcut known to the facade
        expansion = facade.get_expansion(u, v)
        if expansion:
            logger.debug(f"Unpacking shortcut {u}->{v}...")
            # Expansion path includes u and v: [u, x, y, z, v]
            
            # We already added 'u' (it was the last element derived or the start)
            # So we append everything FROM index 1
            full_path.extend(expansion[1:])
        else:
            # Regular edge
            full_path.append(v)
            
    return full_path
