import unittest

from dataflow.osm_weights import (
    choose_speed_kph,
    default_speed_kph,
    distance_equirectangular_m,
    parse_maxspeed_kph,
    weight_seconds,
)


class TestOsmWeights(unittest.TestCase):
    def test_parse_maxspeed_kph(self):
        self.assertEqual(parse_maxspeed_kph("50"), 50.0)
        self.assertEqual(parse_maxspeed_kph("50 km/h"), 50.0)
        self.assertAlmostEqual(parse_maxspeed_kph("30 mph"), 48.2802, places=3)
        self.assertIsNone(parse_maxspeed_kph("signals"))
        self.assertIsNone(parse_maxspeed_kph(""))
        self.assertIsNone(parse_maxspeed_kph(None))

    def test_default_speed_caps(self):
        self.assertEqual(default_speed_kph("residential", None, None, None), 35.0)
        self.assertEqual(default_speed_kph("residential", "gravel", None, None), 30.0)
        self.assertEqual(default_speed_kph("service", None, None, "driveway"), 10.0)

    def test_choose_speed_kph_directional(self):
        speed_forward = choose_speed_kph(
            highway="primary",
            maxspeed="70",
            maxspeed_forward="80",
            maxspeed_backward="60",
            surface=None,
            tracktype=None,
            service=None,
            direction=1,
        )
        speed_backward = choose_speed_kph(
            highway="primary",
            maxspeed="70",
            maxspeed_forward="80",
            maxspeed_backward="60",
            surface=None,
            tracktype=None,
            service=None,
            direction=-1,
        )
        self.assertEqual(speed_forward, 80.0)
        self.assertEqual(speed_backward, 60.0)

    def test_distance_equirectangular(self):
        dist = distance_equirectangular_m(0.0, 0.0, 0.0, 0.001)
        self.assertAlmostEqual(dist, 111.0, delta=2.0)

    def test_weight_seconds(self):
        self.assertEqual(weight_seconds(1000.0, 36.0), 100)


if __name__ == "__main__":
    unittest.main()
