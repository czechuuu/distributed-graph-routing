"""Tests for the routing API endpoints."""



from serving.models import Coordinate, RouteRequest


class TestHealthEndpoint:
    """Tests for the /healthz endpoint."""

    def test_healthz_returns_ok(self):
        """Test that healthz endpoint returns ok status."""
        # Import app without triggering startup (which needs GCS)
        from serving.routing_api import healthz
        
        result = healthz()
        assert result == {"status": "ok"}


class TestHelperFunctions:
    """Tests for routing API helper functions."""

    def test_node_ref(self):
        """Test _node_ref helper function."""
        from serving.routing_api import _node_ref
        
        result = _node_ref(12345, 51.5, -0.1)
        
        assert result["node_id"] == "12345"
        assert result["lat"] == 51.5
        assert result["lng"] == -0.1

    def test_segment(self):
        """Test _segment helper function."""
        from serving.routing_api import _segment
        
        start = {"node_id": "1", "lat": 51.5, "lng": -0.1}
        end = {"node_id": "2", "lat": 51.6, "lng": -0.2}
        
        result = _segment(start, end, expandable=True)
        
        # _segment converts dicts to NodeRef objects
        assert result.start.node_id == "1"
        assert result.start.lat == 51.5
        assert result.end.node_id == "2"
        assert result.end.lat == 51.6
        assert result.expandable is True
        assert len(result.polyline) == 2


class TestS2ShardResolution:
    """Tests for S2 cell shard resolution."""

    def test_shard_id_for_lat_lng(self):
        """Test that shard_id_for_lat_lng returns consistent results."""
        from serving.s2 import shard_id_for_lat_lng
        
        # Same location should return same shard
        shard1 = shard_id_for_lat_lng(51.5, -0.1)
        shard2 = shard_id_for_lat_lng(51.5, -0.1)
        
        assert shard1 == shard2
        assert isinstance(shard1, int)

    def test_different_locations_may_have_different_shards(self):
        """Test that distant locations have different shards."""
        from serving.s2 import shard_id_for_lat_lng
        
        # London
        shard_london = shard_id_for_lat_lng(51.5, -0.1)
        # Tokyo
        shard_tokyo = shard_id_for_lat_lng(35.6, 139.7)
        
        # Very distant locations should have different shards
        assert shard_london != shard_tokyo


class TestModels:
    """Tests for Pydantic models."""

    def test_coordinate_model(self):
        """Test Coordinate model."""
        coord = Coordinate(lat=51.5, lng=-0.1)
        assert coord.lat == 51.5
        assert coord.lng == -0.1

    def test_route_request_model(self):
        """Test RouteRequest model."""
        request = RouteRequest(
            start=Coordinate(lat=51.5, lng=-0.1),
            end=Coordinate(lat=51.6, lng=-0.2),
        )
        assert request.start.lat == 51.5
        assert request.end.lat == 51.6
