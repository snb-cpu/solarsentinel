
import unittest
from unittest.mock import patch

from decide import decide


def sample_reading():
    return {
        "ts": "2026-10-31T10:00:00Z",
        "panel_id": "P1",
        "voltage_v": 18.2,
        "current_a": 4.1,
        "ldr_lux": 60000,
        "temps_c": [
            [41.2, 41.5, 41.0],
            [41.3, 42.0, 41.1]
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

    WEATHER = {"rain_48h": False, "day_factor": [1, 1, 1, 1, 1, 1, 1], "ambient_c": 30.0}

    @patch("decide.predict_panel")
    def test_weather_feed_needs_no_internet(self, prediction):
        prediction.return_value = {"state": "dust"}
        reading = sample_reading(); reading["current_a"] = 3.0          # about 45 % below expected
        result = decide(reading, weather=self.WEATHER)
        self.assertTrue(result["clean_now"])
        self.assertEqual(len(result["forecast_kwh_7d"]), 7)
        self.assertEqual(len(result["forecast_clean_kwh_7d"]), 7)

    @patch("decide.predict_panel")
    def test_rain_in_feed_stops_the_wash(self, prediction):
        prediction.return_value = {"state": "dust"}
        reading = sample_reading(); reading["current_a"] = 3.0
        result = decide(reading, weather={**self.WEATHER, "rain_48h": True})
        self.assertFalse(result["clean_now"])

    @patch("decide.predict_panel")
    def test_night_pauses_analysis(self, prediction):
        reading = sample_reading(); reading["ldr_lux"] = 500
        result = decide(reading, weather=self.WEATHER)
        self.assertFalse(result["clean_now"])
        prediction.assert_not_called()

    @patch("decide.predict_panel")
    def test_hot_patch_is_washed_once_to_find_out(self, prediction):
        prediction.return_value = {"state": "dust"}
        reading = sample_reading(); reading["temps_c"] = [[41.2, 41.5, 41.0], [41.3, 52.0, 41.1]]
        self.assertTrue(decide(reading, weather=self.WEATHER)["clean_now"])
        after = {"power_before_w": 50, "power_after_w": 50, "temps_before_c": reading["temps_c"], "temps_after_c": reading["temps_c"]}
        prediction.return_value = {"state": "fault"}
        self.assertFalse(decide(reading, cleaning_result=after, weather=self.WEATHER)["clean_now"])

    def test_any_grid_size_works(self):
        from heatmap import make_heatmap
        self.assertEqual(len(make_heatmap([[40, 41, 42, 41], [40, 50, 41, 41]])[0]), 4)
        self.assertEqual(len(make_heatmap([[40, 41, 50]])), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
