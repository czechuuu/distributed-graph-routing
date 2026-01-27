"""Tests for the Dijkstra algorithm implementations."""

import math


from serving.dijkstra import (
    dijkstra_path,
    dijkstra_targets,
    bidirectional_multi_source_dijkstra,
    reconstruct_bidirectional_path,
    reverse_adjacency,
)


class TestDijkstraTargets:
    """Tests for dijkstra_targets function."""

    def test_simple_graph(self):
        """Test finding distances to targets in a simple graph."""
        adjacency = {
            1: [(2, 1.0), (3, 4.0)],
            2: [(3, 2.0), (4, 5.0)],
            3: [(4, 1.0)],
        }
        targets = {3, 4}
        result = dijkstra_targets(adjacency, 1, targets)
        
        assert result[3] == 3.0  # 1 -> 2 -> 3
        assert result[4] == 4.0  # 1 -> 2 -> 3 -> 4

    def test_empty_targets(self):
        """Test with empty targets set."""
        adjacency = {1: [(2, 1.0)]}
        result = dijkstra_targets(adjacency, 1, set())
        assert result == {}

    def test_unreachable_target(self):
        """Test when target is unreachable."""
        adjacency = {1: [(2, 1.0)], 3: [(4, 1.0)]}
        targets = {4}
        result = dijkstra_targets(adjacency, 1, targets)
        assert 4 not in result

    def test_source_is_target(self):
        """Test when source is one of the targets."""
        adjacency = {1: [(2, 1.0)]}
        targets = {1, 2}
        result = dijkstra_targets(adjacency, 1, targets)
        assert result[1] == 0.0
        assert result[2] == 1.0


class TestDijkstraPath:
    """Tests for dijkstra_path function."""

    def test_simple_path(self):
        """Test finding shortest path in a simple graph."""
        adjacency = {
            1: [(2, 1.0), (3, 4.0)],
            2: [(3, 2.0)],
        }
        path, weight = dijkstra_path(adjacency, 1, 3)
        
        assert path == [1, 2, 3]
        assert weight == 3.0

    def test_no_path(self):
        """Test when no path exists."""
        adjacency = {1: [(2, 1.0)], 3: [(4, 1.0)]}
        path, weight = dijkstra_path(adjacency, 1, 4)
        
        assert path is None
        assert weight is None

    def test_source_equals_target(self):
        """Test when source equals target."""
        adjacency = {1: [(2, 1.0)]}
        path, weight = dijkstra_path(adjacency, 1, 1)
        
        assert path == [1]
        assert weight == 0.0


class TestReverseAdjacency:
    """Tests for reverse_adjacency function."""

    def test_simple_reversal(self):
        """Test reversing a simple graph."""
        adjacency = {
            1: [(2, 1.0), (3, 2.0)],
            2: [(3, 3.0)],
        }
        rev = reverse_adjacency(adjacency)
        
        assert (1, 1.0) in rev[2]
        assert (1, 2.0) in rev[3]
        assert (2, 3.0) in rev[3]


class TestBidirectionalDijkstra:
    """Tests for bidirectional multi-source Dijkstra."""

    def test_simple_bidirectional(self):
        """Test bidirectional search on a simple graph."""
        adjacency = {
            1: [(2, 1.0)],
            2: [(3, 1.0)],
            3: [(4, 1.0)],
        }
        rev_adjacency = reverse_adjacency(adjacency)
        
        sources = {1: 0.0}
        targets = {4: 0.0}
        
        meeting, cost, prev_fwd, prev_bwd = bidirectional_multi_source_dijkstra(
            adjacency, rev_adjacency, sources, targets
        )
        
        assert meeting is not None
        assert cost == 3.0

    def test_no_path_bidirectional(self):
        """Test bidirectional search when no path exists."""
        adjacency = {1: [(2, 1.0)]}
        rev_adjacency = reverse_adjacency(adjacency)
        
        sources = {1: 0.0}
        targets = {5: 0.0}  # Node 5 doesn't exist
        
        meeting, cost, _, _ = bidirectional_multi_source_dijkstra(
            adjacency, rev_adjacency, sources, targets
        )
        
        assert meeting is None
        assert cost == math.inf

    def test_empty_sources(self):
        """Test with empty sources."""
        adjacency = {1: [(2, 1.0)]}
        rev_adjacency = reverse_adjacency(adjacency)
        
        meeting, cost, _, _ = bidirectional_multi_source_dijkstra(
            adjacency, rev_adjacency, {}, {2: 0.0}
        )
        
        assert meeting is None


class TestReconstructBidirectionalPath:
    """Tests for reconstruct_bidirectional_path function."""

    def test_simple_reconstruction(self):
        """Test path reconstruction."""
        prev_fwd = {2: 1, 3: 2}
        prev_bwd = {3: 4}
        
        path = reconstruct_bidirectional_path(3, prev_fwd, prev_bwd)
        
        assert path == [1, 2, 3, 4]

    def test_meeting_is_source(self):
        """Test when meeting point is the source."""
        prev_fwd = {}
        prev_bwd = {1: 2, 2: 3}
        
        path = reconstruct_bidirectional_path(1, prev_fwd, prev_bwd)
        
        assert path == [1, 2, 3]
