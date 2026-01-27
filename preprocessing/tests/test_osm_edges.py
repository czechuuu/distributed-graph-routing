import unittest

from dataflow.osm_edges import expand_way_nodes


class TestOsmEdges(unittest.TestCase):
    def test_expand_oneway_forward(self):
        tags = {"oneway": "yes", "highway": "primary"}
        edges = list(expand_way_nodes([1, 2, 3], tags))
        self.assertEqual([(e.u, e.v, e.direction) for e in edges], [(1, 2, 1), (2, 3, 1)])

    def test_expand_oneway_reverse(self):
        tags = {"oneway": "-1", "highway": "primary"}
        edges = list(expand_way_nodes([1, 2, 3], tags))
        self.assertEqual([(e.u, e.v, e.direction) for e in edges], [(2, 1, -1), (3, 2, -1)])

    def test_expand_bidirectional(self):
        tags = {"highway": "primary"}
        edges = list(expand_way_nodes([1, 2], tags))
        self.assertEqual(
            [(e.u, e.v, e.direction) for e in edges],
            [(1, 2, 1), (2, 1, -1)],
        )

    def test_tags_propagation(self):
        tags = {
            "highway": "residential",
            "maxspeed": "50",
            "surface": "gravel",
            "tracktype": "grade3",
        }
        edges = list(expand_way_nodes([1, 2], tags))
        self.assertEqual(edges[0].tags.highway, "residential")
        self.assertEqual(edges[0].tags.maxspeed, "50")
        self.assertEqual(edges[0].tags.surface, "gravel")
        self.assertEqual(edges[0].tags.tracktype, "grade3")


if __name__ == "__main__":
    unittest.main()
