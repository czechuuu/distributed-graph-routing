from typing import List, Dict, Set
import collections

import bigtable_storage_pb2

class RoutingGraph:
    """
    A graph class that serves as a unified interface over distributed graph shards
    and a global overlay graph for bidirectional Dijkstra.
    """
    
    Neighbor = collections.namedtuple('Neighbor', ['node_id', 'weight'])

    def __init__(self):
        # Maps node_id -> list of Neighbor(node_id, weight)
        self._adjacency_list: Dict[int, List['RoutingGraph.Neighbor']] = collections.defaultdict(list)
        self._reverse_adjacency_list: Dict[int, List['RoutingGraph.Neighbor']] = collections.defaultdict(list)
        
        # Maps node_id -> list of Neighbor(node_id, weight) (Overlay)
        self._overlay_adjacency_list: Dict[int, List['RoutingGraph.Neighbor']] = collections.defaultdict(list)
        self._overlay_reverse_adjacency_list: Dict[int, List['RoutingGraph.Neighbor']] = collections.defaultdict(list)

    def load_shard(self, shard: bigtable_storage_pb2.ShardGraph):
        """
        Loads a ShardGraph into the main adjacency lists.
        """
        for edge in shard.edges:
            # Forward: u -> v
            self._adjacency_list[edge.from_node_id].append(
                self.Neighbor(edge.to_node_id, edge.weight)
            )
            
            # Reverse: v -> u (incoming edge for v)
            self._reverse_adjacency_list[edge.to_node_id].append(
                self.Neighbor(edge.from_node_id, edge.weight)
            )

            if edge.bidirectional:
                # If bidirectional, edge also implies v -> u
                
                # Forward: v -> u
                self._adjacency_list[edge.to_node_id].append(
                    self.Neighbor(edge.from_node_id, edge.weight)
                )
                
                # Reverse: u -> v (incoming edge for u)
                self._reverse_adjacency_list[edge.from_node_id].append(
                    self.Neighbor(edge.to_node_id, edge.weight)
                )

    def load_overlay(self, overlay: bigtable_storage_pb2.OverlayGraph):
        """
        Loads an OverlayGraph into the overlay adjacency lists.
        """
        all_edges = []
        all_edges.extend(overlay.bridges)
        all_edges.extend(overlay.shortcuts)

        for edge in all_edges:
            self._overlay_adjacency_list[edge.from_node_id].append(
                self.Neighbor(edge.to_node_id, edge.weight)
            )
            self._overlay_reverse_adjacency_list[edge.to_node_id].append(
                self.Neighbor(edge.from_node_id, edge.weight)
            )

            if edge.bidirectional:
                self._overlay_adjacency_list[edge.to_node_id].append(
                    self.Neighbor(edge.from_node_id, edge.weight)
                )
                self._overlay_reverse_adjacency_list[edge.from_node_id].append(
                    self.Neighbor(edge.to_node_id, edge.weight)
                )

    def get_neighbors(self, node_id: int) -> List['RoutingGraph.Neighbor']:
        """
        Returns a list of outgoing neighbors (node_id, weight) from the given node.
        If the node is in the overlay graph, returns both local and overlay edges.
        """
        edges = list(self._adjacency_list.get(node_id, []))
        
        # Check if node has overlay edges (is a boundary node)
        overlay_edges = self._overlay_adjacency_list.get(node_id)
        if overlay_edges:
            edges.extend(overlay_edges)
            
        return edges

    def get_reverse_neighbors(self, node_id: int) -> List['RoutingGraph.Neighbor']:
        """
        Returns a list of incoming neighbors (node_id, weight) to the given node.
        These are nodes u such that (u, node_id) exists.
        """
        edges = list(self._reverse_adjacency_list.get(node_id, []))
        
        # Check if node has overlay edges (is a boundary node)
        overlay_edges = self._overlay_reverse_adjacency_list.get(node_id)
        if overlay_edges:
            edges.extend(overlay_edges)
            
        return edges
