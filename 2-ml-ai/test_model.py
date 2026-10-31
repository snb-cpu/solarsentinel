
from classify import predict_panel

normal_reading = {
    "panel_id": "PANEL_01",
    "voltage_v": 18.5,
    "current_a": 4.8,
    "ldr_lux": 850,
    "temps_c": [
        [32, 33, 32],
        [33, 34, 33]
    ],
    "tank_level_pct": 90
}

dust_reading = {
    "panel_id": "PANEL_02",
    "voltage_v": 17.0,
    "current_a": 3.9,
    "ldr_lux": 850,
    "temps_c": [
        [35, 36, 35],
        [36, 37, 36]
    ],
    "tank_level_pct": 90
}

hotspot_reading = {
    "panel_id": "PANEL_03",
    "voltage_v": 17.5,
    "current_a": 4.2,
    "ldr_lux": 850,
    "temps_c": [
        [34, 35, 34],
        [35, 55, 36]
    ],
    "tank_level_pct": 90
}

test_cases = [
    normal_reading,
    dust_reading,
    hotspot_reading
]

for reading in test_cases:
    result = predict_panel(reading)

    print("\nPanel ID:", reading["panel_id"])
    print("Prediction:", result)
