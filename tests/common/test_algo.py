import unittest
import networkx as nx
from shared.model import Node, Edge
from shared.algo import build_shard_graph, identify_boundary_nodes, compute_shortcuts

class TestAlgo(unittest.TestCase):

    def test_build_graph(self):
        nodes = [Node(1, 0, 0, 1), Node(2, 1, 1, 1)]
        edges = [Edge(1, 2, 5.0)]
        G = build_shard_graph(nodes, edges)
        
        self.assertTrue(G.has_node(1))
        self.assertTrue(G.has_node(2))
        self.assertTrue(G.has_edge(1, 2))
        self.assertEqual(G[1][2]['weight'], 5.0)
        self.assertEqual(G.nodes[1]['shard_id'], 1)

    def test_boundary_nodes(self):
        # Shard 1
        # 1(S1) -> 2(S1) (Internal)
        # 1(S1) -> 3(S2) (1 is an out-boundary node for S1)
        # 4(S2) -> 2(S1) (2 is an in-boundary node for S1)
        
        G = nx.DiGraph()
        G.add_node(1, shard_id=1)
        G.add_node(2, shard_id=1)
        G.add_node(3, shard_id=2) 
        G.add_node(4, shard_id=2) 
        G.add_edge(1, 2)
        G.add_edge(1, 3) 
        G.add_edge(4, 2) 
        
        in_b, out_b = identify_boundary_nodes(G, 1)
        
        self.assertIn(1, out_b) # 1->3
        self.assertIn(2, in_b)  # 4->1
        self.assertNotIn(1, in_b)
        self.assertNotIn(2, out_b)

    def test_compute_shortcuts(self):
        # 1 -> 2 -> 3
        # 1 is In-Boundary
        # 3 is Out-Boundary
        # Path 1->3 cost 1+2 = 3.
        
        G = nx.DiGraph()
        G.add_edge(1, 2, weight=1.0)
        G.add_edge(2, 3, weight=2.0)
        
        in_nodes = {1}
        out_nodes = {3}
        
        shortcuts = compute_shortcuts(G, in_nodes, out_nodes)
        
        self.assertEqual(len(shortcuts), 1)
        s = shortcuts[0]
        self.assertEqual(s.u, 1)
        self.assertEqual(s.v, 3)
        self.assertEqual(s.weight, 3.0)

if __name__ == '__main__':
    unittest.main()
