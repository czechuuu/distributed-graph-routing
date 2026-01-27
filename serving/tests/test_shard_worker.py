"""Tests for the ShardWorkerService gRPC service."""


import pytest

from serving.shard_cache import ShardCache, ShardData
from serving.shard_worker import ShardWorkerService
import shard_worker_pb2


class TestShardWorkerService:
    """Tests for ShardWorkerService class."""

    @pytest.fixture
    def sample_shard(self):
        """Create a sample shard for testing."""
        return ShardData(
            shard_id=123,
            adjacency={
                1: [(2, 10.0), (3, 20.0)],
                2: [(3, 5.0), (4, 15.0)],
                3: [(4, 10.0)],
            },
            reverse_adjacency={
                2: [(1, 10.0)],
                3: [(1, 20.0), (2, 5.0)],
                4: [(2, 15.0), (3, 10.0)],
            },
            node_locations={
                1: (51.5, -0.1),
                2: (51.6, -0.2),
                3: (51.7, -0.3),
                4: (51.8, -0.4),
            },
            boundary_in={1, 2},
            boundary_out={3, 4},
        )

    @pytest.fixture
    def service_with_shard(self, sample_shard):
        """Create a service with a pre-loaded shard."""
        cache = ShardCache(max_size=10)
        cache.put(123, sample_shard)
        return ShardWorkerService(bucket="", prefix="", cache=cache)

    def test_health_returns_ok(self):
        """Test Health RPC returns ok."""
        cache = ShardCache(max_size=10)
        service = ShardWorkerService(bucket="", prefix="", cache=cache)
        
        response = service.Health(shard_worker_pb2.HealthRequest(), None)
        
        assert response.ok is True

    def test_snap_and_boundary_dists_shard_not_loaded(self):
        """Test SnapAndBoundaryDists when shard is not loaded."""
        cache = ShardCache(max_size=10)
        service = ShardWorkerService(bucket="", prefix="", cache=cache)
        
        request = shard_worker_pb2.SnapAndBoundaryDistsRequest(
            shard_id=999,
            lat=51.5,
            lng=-0.1,
            mode=shard_worker_pb2.BOUNDARY_OUT,
        )
        
        response = service.SnapAndBoundaryDists(request, None)
        
        assert response.ok is False
        assert response.error == "shard_not_loaded"

    def test_snap_and_boundary_dists_success_boundary_out(self, service_with_shard):
        """Test SnapAndBoundaryDists with BOUNDARY_OUT mode."""
        request = shard_worker_pb2.SnapAndBoundaryDistsRequest(
            shard_id=123,
            lat=51.5,
            lng=-0.1,
            mode=shard_worker_pb2.BOUNDARY_OUT,
        )
        
        response = service_with_shard.SnapAndBoundaryDists(request, None)
        
        assert response.ok is True
        assert response.snapped.node_id == 1
        assert set(response.boundary_node_ids) == {3, 4}

    def test_snap_and_boundary_dists_success_boundary_in(self, service_with_shard):
        """Test SnapAndBoundaryDists with BOUNDARY_IN mode."""
        request = shard_worker_pb2.SnapAndBoundaryDistsRequest(
            shard_id=123,
            lat=51.8,
            lng=-0.4,
            mode=shard_worker_pb2.BOUNDARY_IN,
        )
        
        response = service_with_shard.SnapAndBoundaryDists(request, None)
        
        assert response.ok is True
        assert response.snapped.node_id == 4
        assert set(response.boundary_node_ids) == {1, 2}

    def test_expand_path_shard_not_loaded(self):
        """Test ExpandPath when shard is not loaded."""
        cache = ShardCache(max_size=10)
        service = ShardWorkerService(bucket="", prefix="", cache=cache)
        
        request = shard_worker_pb2.ExpandPathRequest(
            shard_id=999,
            u_node_id=1,
            v_node_id=4,
        )
        
        response = service.ExpandPath(request, None)
        
        assert response.ok is False
        assert response.error == "shard_not_loaded"

    def test_expand_path_success(self, service_with_shard):
        """Test ExpandPath with valid path."""
        request = shard_worker_pb2.ExpandPathRequest(
            shard_id=123,
            u_node_id=1,
            v_node_id=4,
        )
        
        response = service_with_shard.ExpandPath(request, None)
        
        assert response.ok is True
        assert len(response.polyline) >= 2
        assert response.total_weight > 0

    def test_expand_path_no_path(self, service_with_shard):
        """Test ExpandPath when no path exists."""
        request = shard_worker_pb2.ExpandPathRequest(
            shard_id=123,
            u_node_id=4,  # No outgoing edges from 4
            v_node_id=1,
        )
        
        response = service_with_shard.ExpandPath(request, None)
        
        assert response.ok is False
        assert response.error == "path_not_found"
