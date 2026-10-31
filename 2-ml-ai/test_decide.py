
import unittest
from unittest.mock import patch

from decide import decide


def sample_reading():
    return {
        "ts": "2026-10-31T10:00:00Z",
        "panel_id": "P1",
        "voltage_v": 18.2,
        "current_a": 4.1,
        "ldr_lux": 3000,
        "temps_c": [
            [41.2, 41.5, 41.0],
            [41.3, 47.9, 41.1]
        ],
        "tank_level_pct": 70
    }


class DecisionTests(unittest.TestCase):

    @patch("decide.predict_panel")
    def test_normal_panel(self, prediction):
        prediction.return_value = {"state": "ok"}

        result = decide(sample_reading())

        self.assertFalse(result["clean_now"])
        self.assertEqual(result["state"], "ok")

    @patch("decide.predict_panel")
    def test_fault_never_triggers_cleaning(self, prediction):
        prediction.return_value = {"state": "fault"}

        result = decide(sample_reading())

        self.assertFalse(result["clean_now"])

    @patch("decide.predict_panel")
    def test_hotspot_never_triggers_cleaning(self, prediction):
        prediction.return_value = {"state": "hotspot"}

        result = decide(sample_reading())

        self.assertFalse(result["clean_now"])

    @patch("decide.rain_expected", return_value=True)
    @patch("decide.forecast_kwh_7d")
    @patch("decide.get_forecast_weather")
    @patch("decide.predict_panel")
    def test_dust_with_rain(
        self, prediction, weather, forecast, rain
    ):
        prediction.return_value = {"state": "dust"}
        weather.return_value = ([5] * 7, [30] * 7)
        forecast.side_effect = [[4] * 7, [5] * 7]

        result = decide(sample_reading())

        self.assertFalse(result["clean_now"])

    @patch("decide.rain_expected", return_value=False)
    @patch("decide.forecast_kwh_7d")
    @patch("decide.get_forecast_weather")
    @patch("decide.predict_panel")
    def test_profitable_dust_cleaning(
        self, prediction, weather, forecast, rain
    ):
        prediction.return_value = {"state": "dust"}
        weather.return_value = ([5] * 7, [30] * 7)
        forecast.side_effect = [[4] * 7, [5] * 7]

        result = decide(sample_reading())

        self.assertTrue(result["clean_now"])
        self.assertGreater(
            result["loss_inr_per_day"],
            result["clean_cost_inr"]
        )

    @patch("decide.predict_panel")
    def test_low_water_level(self, prediction):
        prediction.return_value = {"state": "dust"}

        reading = sample_reading()
        reading["tank_level_pct"] = 10

        result = decide(reading)

        self.assertFalse(result["clean_now"])

    @patch("decide.rain_expected", return_value=None)
    @patch("decide.forecast_kwh_7d")
    @patch("decide.get_forecast_weather")
    @patch("decide.predict_panel")
    def test_weather_unavailable(
        self, prediction, weather, forecast, rain
    ):
        prediction.return_value = {"state": "dust"}
        weather.return_value = ([5] * 7, [30] * 7)
        forecast.side_effect = [[4] * 7, [5] * 7]

        result = decide(sample_reading())

        self.assertFalse(result["clean_now"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
