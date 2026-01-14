import unittest
import networkx as nx
import random
import logging
from typing import Dict, List, Tuple
from collections import defaultdict

from fastapi.testclient import TestClient
from serving_layer.app import app, state



from serving_layer.graph_facade import GraphFacade
from serving_layer.engine import find_shortest_path
from shared.model import Node, Edge, Shortcut
from shared.algo import build_shard_graph, identify_boundary_nodes, compute_shortcuts

client = TestClient(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("StressTest")

class LocalGraphFacade(GraphFacade):
    """
    A unified facade that holds all shards in memory to simulate Bigtable.
    """
    def __init__(self, overlay_graph: nx.DiGraph, shard_graphs: Dict[int, nx.DiGraph], shortcuts_map: Dict[Tuple[int, int], List[int]]):
        # Initialize parent with mock=True logic but we override accessors
        super().__init__("test-proj", "test-instance", "shortcuts", "intra", use_mock=True)
        self.overlay = overlay_graph
        self.shard_graphs = shard_graphs
        self.shortcut_expansions = shortcuts_map

    def _merge_shard_into_graph(self, graph: nx.DiGraph, shard_id: int):
        """Merges the specific shard graph into the query graph from memory."""
        if shard_id in self.shard_graphs:
            shard_G = self.shard_graphs[shard_id]
            # Copy edges from shard graph to query graph
            for u, v, data in shard_G.edges(data=True):
                graph.add_edge(u, v, weight=data['weight'])

class TestRandomGraphRouting(unittest.TestCase):
    
    def generate_random_graph(self, n=5000, p=0.02, num_shards=50):
        """Generates a connected random graph and partitions it."""
        while True:
            # simple Erdos-Renyi graph
            G = nx.erdos_renyi_graph(n, p, directed=True)
            # Assign random weights
            for u, v in G.edges():
                G[u][v]['weight'] = random.randint(1, 10)
            
            if nx.is_strongly_connected(G):
                break
        
        # Partition
        node_to_shard = {}
        nodes_by_shard = defaultdict(list)
        for node in G.nodes():
            s_id = random.randint(1, num_shards)
            node_to_shard[node] = s_id
            nodes_by_shard[s_id].append(Node(node, 0, 0, s_id))
            
        return G, node_to_shard, nodes_by_shard

    def build_distributed_system(self, G, node_to_shard, nodes_by_shard):
        """Emulates the Pipeline logic to build Shard Graphs and Overlay."""
        shard_graphs = {}
        overlay = nx.DiGraph()
        shortcut_expansions = {}
        
        # 1. Build Shard Graphs
        for s_id, nodes in nodes_by_shard.items():
            # Find edges belonging to this shard (intra-shard)
            edges_list = []
            for u in [n.id for n in nodes]:
                if u not in G: continue
                for v in G[u]:
                    # Edges where u is in this shard. But we only store INTRA edges in ShardGraph (u->v where v is also in shard)
                    # Pipeline logic: "Filter only internal edges" (CreateMutations.process for INTRA)
                    # "if u_node.get('shard_id') == shard_id and v_node.get('shard_id') == shard_id:"
                    if node_to_shard[v] == s_id: 
                        edges_list.append(Edge(u, v, G[u][v]['weight']))
            
            # Use shared logic
            shard_G = build_shard_graph(nodes, edges_list)
            shard_graphs[s_id] = shard_G
            
            # 2. Identify Boundary
            in_b, out_b = identify_boundary_nodes(shard_G, s_id)
            
            in_b, out_b = identify_boundary_nodes(shard_G, s_id)
            
            # Re-collect all edges touching this shard
            all_shard_edges = []
            for u in [n.id for n in nodes]:
                if u not in G: continue
                for v in G[u]:
                    all_shard_edges.append(Edge(u, v, G[u][v]['weight']))
            
            current_shard_edges = []
            # Incoming edges too?
            for u, v in G.edges():
                s_u = node_to_shard[u]
                s_v = node_to_shard[v]
                if s_u == s_id or s_v == s_id:
                     current_shard_edges.append(Edge(u, v, G[u][v]['weight']))
            
            # Now build graph with ALL edges touching this shard
            # (Note: standard build_shard_graph only adds nodes from `nodes` list which are strictly in this shard?
            # shared.algo.build_shard_graph: `for n in nodes: G.add_node...`
            # then `for e in edges: G.add_edge...`
            # It might add extra nodes implicitly via add_edge? No, networkx add_edge adds nodes.
            # But the nodes might miss shard_id attribute if not in `nodes` list.)
            shard_G_full = build_shard_graph(nodes, current_shard_edges)
            
            # Manually patch shard_ids for external nodes so identification works
            for n in shard_G_full.nodes():
                if n not in node_to_shard: continue # Should not happen if G is closed
                shard_G_full.nodes[n]['shard_id'] = node_to_shard[n]

            in_b, out_b = identify_boundary_nodes(shard_G_full, s_id)
            shortcuts = compute_shortcuts(shard_G_full, in_b, out_b)
            
            for s in shortcuts:
                overlay.add_edge(s.u, s.v, weight=s.weight)
                shortcut_expansions[(s.u, s.v)] = s.path
            
            intra_edges_only = []
            for u, v in G.edges():
                if node_to_shard[u] == s_id and node_to_shard[v] == s_id:
                    intra_edges_only.append(Edge(u, v, G[u][v]['weight']))
            
            shard_graphs[s_id] = build_shard_graph(nodes, intra_edges_only)

        # 4. Add Inter-shard edges (Bridges) to Overlay
        for u, v in G.edges():
            s_u = node_to_shard[u]
            s_v = node_to_shard[v]
            if s_u != s_v:
                # This is a bridge
                overlay.add_edge(u, v, weight=G[u][v]['weight'])
                
        return LocalGraphFacade(overlay, shard_graphs, shortcut_expansions)

    def test_routing_correctness(self):
        N = 500
        logger.info(f"Generating random graph with {N} nodes...")
        G, node_to_shard, nodes_by_shard = self.generate_random_graph(n=N, p=0.03, num_shards=4)
        
        logger.info("Building distributed system (Overlay + Shards)...")
        facade = self.build_distributed_system(G, node_to_shard, nodes_by_shard)
        
        logger.info(f"Overlay has {facade.overlay.number_of_nodes()} nodes and {facade.overlay.number_of_edges()} edges.")

        # Inject Mock State into App
        state.facade = facade
        
        # Run random queries
        num_queries = 50
        logger.info(f"Running {num_queries} random queries...")
        
        success_count = 0
        for _ in range(num_queries):
            u = random.choice(list(G.nodes()))
            v = random.choice(list(G.nodes()))
            
            if u == v: continue
            
            # 1. Ground Truth (NetworkX)
            try:
                expected_len = nx.shortest_path_length(G, u, v, weight='weight')
            except nx.NetworkXNoPath:
                expected_len = None
            
            # 2. Distributed Engine via FastAPI
            response = client.post("/route", json={
                "start_node": u, "start_node_shard": node_to_shard[u],
                "end_node": v, "end_node_shard": node_to_shard[v]
            })
            
            if response.status_code == 200:
                result = response.json()
                actual_path = result['path']
                status = result['status']
            else:
                 logger.error(f"API Error: {response.status_code} {response.text}")
                 actual_path = []
            
            if expected_len is None:
                self.assertEqual(actual_path, [], f"Expected no path between {u}->{v}, got {actual_path}")
            else:
                self.assertTrue(actual_path, f"Expected path for {u}->{v}, got None/Empty")
                
                # Calculate cost of actual path
                actual_len = 0
                for i in range(len(actual_path)-1):
                    p1, p2 = actual_path[i], actual_path[i+1]
                    self.assertTrue(G.has_edge(p1, p2), f"Edge {p1}->{p2} does not exist in original graph")
                    actual_len += G[p1][p2]['weight']
                
                self.assertEqual(actual_len, expected_len, f"Path cost mismatch for {u}->{v}. Expected {expected_len}, got {actual_len}")
                success_count += 1
                
        logger.info(f"Successfully verified {success_count} queries.")

if __name__ == '__main__':
    unittest.main()
