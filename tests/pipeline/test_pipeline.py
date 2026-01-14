import unittest
import apache_beam as beam
from preprocessing.dataflow.model import Node, Edge
from preprocessing.dataflow.pipeline import EmitShardsForEdge, ProcessShard

class TestLogic(unittest.TestCase):

    def test_emit_shards(self):
        # Nodes: 1 (Shard 1), 2 (Shard 1), 3 (Shard 2)
        # Edges: 1->2 (Internal), 1->3 (Boundary), 3->1 (Boundary incoming)
        
        dofn = EmitShardsForEdge()
        
        # Test 1->2 (Internal to Shard 1)
        # Input: (Edge, ShardU=1, ShardV=1)
        # Should emit (1, Edge)
        e1 = Edge(1, 2, 1.0)
        out1 = list(dofn.process((e1, 1, 1)))
        self.assertEqual(len(out1), 1)
        self.assertEqual(out1[0][0], 1) # Shard 1
        
        # Test 1->3 (Boundary: U=1(S1), V=3(S2))
        # Input: (Edge, ShardU=1, ShardV=2)
        # Should emit (1, Edge) AND (2, Edge)
        e2 = Edge(1, 3, 2.0)
        out2 = list(dofn.process((e2, 1, 2)))
        self.assertEqual(len(out2), 2)
        shards = sorted([x[0] for x in out2])
        self.assertEqual(shards, [1, 2])
        
    def test_process_shard(self):
        # Shard 1:
        # Nodes: 1 (Boundary In), 2 (Internal intermediate), 3 (Boundary Out)
        # Shard 2:
        # Nodes: 4 
        # Edges provided to shard:
        # 1->2 (Internal)
        # 2->3 (Internal)
        # 4->1 (Boundary In)
        # 3->4 (Boundary Out)
        
        shard_id = 1
        nodes = [
            Node(1, 0.0, 0.0, 1),
            Node(2, 0.0, 0.0, 1),
            Node(3, 0.0, 0.0, 1),
            # We don' receive node 4 - its only referenced via edges
        ]
        edges = [
            Edge(1, 2, 2.0), # Internal
            Edge(2, 3, 5.0),  # Internal
            Edge(4, 1, 20.0),  # Boundary In
            Edge(3, 4, 10.0),  # Boundary Out
        ]
        
        dofn = ProcessShard()
        
        results = list(dofn.process((shard_id, {'nodes': nodes, 'edges': edges})))
        
        shortcuts_result = [x for x in results if x.tag == 'shortcuts'][0]
        intra_result = [x for x in results if x.tag == 'intra'][0]
        
        shard_id, shortcuts, inter_edges = shortcuts_result.value
        
        # Check Shortcut
        # 1->3 weight 7.0
        self.assertTrue(any(s.u == 1 and s.v == 3 and s.weight == 7.0 for s in shortcuts))

        # Check Inter-edges
        self.assertTrue(any(e.u == 4 and e.v == 1 and e.weight == 20.0 for e in inter_edges))
        self.assertTrue(any(e.u == 3 and e.v == 4 and e.weight == 10.0 for e in inter_edges))

        _, G = intra_result.value
        self.assertTrue(G.has_edge(1, 2))
        self.assertTrue(G.has_edge(2, 3))
        
if __name__ == '__main__':
    unittest.main()
