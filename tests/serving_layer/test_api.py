
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
        state.node_index = {}
        
    def test_health_check_mock_mode(self):
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertIn('mock', data)
        self.assertIn('nodes_indexed', data)

    def test_route_success(self):
        state.node_index = {1: 10, 5: 10}
        
        with patch('serving_layer.app.find_shortest_path') as mock_algo:
            mock_algo.return_value = [1, 2, 3, 4, 5]
            
            payload = {"start_node": 1, "end_node": 5}
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

    def test_route_not_found_in_index(self):
        with patch('serving_layer.app.USE_MOCK', False):
            state.node_index = {} # Empty index
            
            payload = {"start_node": 999, "end_node": 888}
            response = client.post("/route", json=payload)
            
            self.assertEqual(response.status_code, 404)
            self.assertIn("not found", response.json()['detail'])

    def test_route_no_path_found(self):
        state.node_index = {1: 1, 2: 2}
        
        with patch('serving_layer.app.find_shortest_path') as mock_algo:
            mock_algo.return_value = [] # No path
            
            payload = {"start_node": 1, "end_node": 2}
            response = client.post("/route", json=payload)
            
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data['status'], 'no_path_found')
            self.assertEqual(data['path'], [])
            self.assertEqual(data['steps_count'], 0)

    def test_server_uninitialized(self):
        state.facade = None
        
        payload = {"start_node": 1, "end_node": 2}
        response = client.post("/route", json=payload)
        
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['detail'], "Server not initialized")

if __name__ == '__main__':
    unittest.main()
