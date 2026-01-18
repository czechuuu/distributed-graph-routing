
import unittest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from serving_layer.app import app, state, RouteResponse
from serving_layer.graph_facade import GraphFacade

client = TestClient(app)

class TestServingLayerAPI(unittest.TestCase):
    
    def setUp(self):
        # Reset state before each test
        state.facade = MagicMock(spec=GraphFacade)
        
    def test_health_check_mock_mode(self):
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertIn('mock', data)

    def test_route_success(self):
        state.node_index = {1: 10, 5: 10}
        
        with patch('serving_layer.app.find_shortest_path') as mock_algo:
            mock_algo.return_value = [1, 2, 3, 4, 5]
            
            payload = {"start_node": 1, "start_node_shard": 10, "end_node": 5, "end_node_shard": 10}
            response = client.post("/route", json=payload)
            
            self.assertEqual(response.status_code, 200)
            data = response.json()
            
            self.assertEqual(data['status'], 'success')
            self.assertEqual(data['path'], [1, 2, 3, 4, 5])
            self.assertEqual(data['steps_count'], 5)
            
            self.assertEqual(data['steps_count'], 5)
            
            mock_algo.assert_called_once()
            args, _ = mock_algo.call_args
            self.assertEqual(args[1], 1) # u
            self.assertEqual(args[2], 5) # v
            self.assertEqual(args[3], {1: 10, 5: 10}) # node_map

    def test_route_no_path_found(self):
        with patch('serving_layer.app.find_shortest_path') as mock_algo:
            mock_algo.return_value = [] # No path
            
            payload = {"start_node": 1, "start_node_shard": 1, "end_node": 2, "end_node_shard": 2}
            response = client.post("/route", json=payload)
            
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data['status'], 'no_path')
            self.assertEqual(data['path'], [])
            self.assertEqual(data['steps_count'], 0)

    def test_server_uninitialized(self):
        state.facade = None
        
        payload = {"start_node": 1, "start_node_shard": 1, "end_node": 2, "end_node_shard": 2}
        response = client.post("/route", json=payload)
        
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['detail'], "Service not ready")

if __name__ == '__main__':
    unittest.main()
