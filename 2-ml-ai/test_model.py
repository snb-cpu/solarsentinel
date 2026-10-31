"""Sanity checks for the physics-trained classifier. Needs model.pkl (python classify.py)."""
import unittest
from classify import predict_panel

def reading(current, temps, lux=70000):
    return {"ts": "2026-01-01T00:00:00Z", "panel_id": "P1", "voltage_v": 16.9, "current_a": current, "ldr_lux": lux,
            "temps_c": temps, "tank_level_pct": 70}

FLAT = [[47.0, 47.2, 47.1, 47.4], [47.3, 47.1, 47.5, 47.0]]

class ModelTests(unittest.TestCase):
    def test_clean_panel_is_ok(self):
        self.assertEqual(predict_panel(reading(3.85, FLAT))["state"], "ok")

    def test_big_power_loss_with_even_heat_is_dust(self):
        self.assertEqual(predict_panel(reading(3.1, FLAT))["state"], "dust")

    def test_one_very_hot_cell_without_power_loss_is_a_hotspot(self):
        hot = [[47.0, 47.2, 47.1, 47.4], [47.3, 61.0, 47.5, 47.0]]
        self.assertIn(predict_panel(reading(3.85, hot))["state"], ("hotspot", "fault"))

if __name__ == "__main__":
    unittest.main(verbosity=2)
