"""Tests for the ShardCache and ShardData classes."""

import pytest

from serving.shard_cache import ShardCache, ShardData


class TestShardData:
    """Tests for ShardData class."""

    def test_nearest_node_simple(self):
        """Test finding nearest node to a location."""
        shard = ShardData(
            shard_id=1,
            adjacency={},
            reverse_adjacency={},
            node_locations={
                100: (51.5, -0.1),  # London
                200: (48.8, 2.3),   # Paris
                300: (52.5, 13.4),  # Berlin
            },
            boundary_in=set(),
            boundary_out=set(),
        )
        
        # Location near London should return node 100
        nearest = shard.nearest_node(51.4, -0.2)
        assert nearest == 100

    def test_nearest_node_empty_locations(self):
        """Test nearest node with no locations."""
        shard = ShardData(
            shard_id=1,
            adjacency={},
            reverse_adjacency={},
            node_locations={},
            boundary_in=set(),
            boundary_out=set(),
        )
        
        nearest = shard.nearest_node(51.5, -0.1)
        assert nearest is None

    def test_nearest_node_exact_match(self):
        """Test nearest node when querying exact location."""
        shard = ShardData(
            shard_id=1,
            adjacency={},
            reverse_adjacency={},
            node_locations={100: (51.5, -0.1)},
            boundary_in=set(),
            boundary_out=set(),
        )
        
        nearest = shard.nearest_node(51.5, -0.1)
        assert nearest == 100


class TestShardCache:
    """Tests for ShardCache class."""

    def test_put_and_get(self):
        """Test basic put and get operations."""
        cache = ShardCache(max_size=10)
        shard = ShardData(
            shard_id=1,
            adjacency={},
            reverse_adjacency={},
            node_locations={},
            boundary_in=set(),
            boundary_out=set(),
        )
        
        cache.put(1, shard)
        result = cache.get(1)
        
        assert result is not None
        assert result.shard_id == 1

    def test_get_nonexistent(self):
        """Test getting a shard that doesn't exist."""
        cache = ShardCache(max_size=10)
        result = cache.get(999)
        assert result is None

    def test_lru_eviction(self):
        """Test that LRU eviction works correctly."""
        cache = ShardCache(max_size=2)
        
        shard1 = ShardData(1, {}, {}, {}, set(), set())
        shard2 = ShardData(2, {}, {}, {}, set(), set())
        shard3 = ShardData(3, {}, {}, {}, set(), set())
        
        cache.put(1, shard1)
        cache.put(2, shard2)
        
        # Access shard 1 to make it recently used
        cache.get(1)
        
        # Add shard 3, should evict shard 2 (least recently used)
        cache.put(3, shard3)
        
        assert cache.get(1) is not None
        assert cache.get(2) is None  # Should be evicted
        assert cache.get(3) is not None

    def test_update_existing(self):
        """Test updating an existing shard."""
        cache = ShardCache(max_size=10)
        
        shard_v1 = ShardData(1, {}, {}, {100: (1.0, 2.0)}, set(), set())
        shard_v2 = ShardData(1, {}, {}, {200: (3.0, 4.0)}, set(), set())
        
        cache.put(1, shard_v1)
        cache.put(1, shard_v2)
        
        result = cache.get(1)
        assert 200 in result.node_locations
        assert 100 not in result.node_locations
