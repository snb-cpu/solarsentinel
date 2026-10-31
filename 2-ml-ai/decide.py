import numpy as np

import os
from datetime import datetime, timezone

import requests

from classify import predict_panel, estimate_expected_power, light_features, LDR_FULL_SCALE_LUX
from heatmap import make_heatmap
from weather import rain_expected
from forecast import forecast_kwh_7d


ELECTRICITY_RATE_INR = 8.0
CLEAN_COST_INR = 2.0
MINIMUM_TANK_LEVEL = 20
MIN_LUX = 20000                  # below this the panel is in the dark or under heavy cloud: no analysis
STRING_AREA_M2 = 6.8             # each node watches a 1.5 kW string; forecast_kwh_7d is per square metre
PEAK_SUN_HOURS = 4.8             # clear-day irradiance in kWh/m2/day, scaled by the weather feed
UNEVEN_LIGHT_PCT = 25.0          # corner light sensors disagree by more than this: a shadow or passing cloud, not dirt
HOT_PATCH_C = 5.0                # a cell this far above the median is a hot patch: wash once to find out if it is dirt

SITE_LATITUDE = float(os.getenv("SOLAR_LATITUDE", "12.9716"))
SITE_LONGITUDE = float(os.getenv("SOLAR_LONGITUDE", "77.5946"))

API_URL = "https://api.open-meteo.com/v1/forecast"


def get_forecast_weather(lat, lon):
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "shortwave_radiation_sum,temperature_2m_mean",
        "forecast_days": 7,
        "timezone": "auto"
    }

    response = requests.get(API_URL, params=params, timeout=15)
    response.raise_for_status()

    data = response.json()["daily"]

    irradiance = [
        max(0, float(value or 0)) / 3.6
        for value in data["shortwave_radiation_sum"]
    ]

    temperatures = [
        float(value if value is not None else 25)
        for value in data["temperature_2m_mean"]
    ]

    if len(irradiance) != 7 or len(temperatures) != 7:
        raise ValueError("Weather service did not return seven forecast days.")

    return irradiance, temperatures


def weather_from_feed(weather):
    """Turn the weather feed laptop A posts to the API into what the forecast model wants."""
    irradiance = [round(PEAK_SUN_HOURS * float(f), 2) for f in weather["day_factor"]]
    temperature = [float(weather.get("ambient_c") or 30.0)] * 7
    return irradiance, temperature, bool(weather["rain_48h"])


def forecast_pair(irradiance, temperature, efficiency_loss):
    """(with today's dirt, if clean) in kWh per day for the whole string."""
    scale = STRING_AREA_M2
    now = [round(v * scale, 2) for v in forecast_kwh_7d(irradiance, temperature, efficiency_loss)]
    clean = [round(v * scale, 2) for v in forecast_kwh_7d(irradiance, temperature, 0)]
    return now, clean


def decide(reading, history=None, cleaning_result=None, weather=None):
    """Decide what to do about one panel.

    weather: the live feed {"rain_48h", "day_factor": [7], "ambient_c"}. If missing, Open-Meteo is asked instead.
    cleaning_result: before/after a wash (see classify.py). If given, the after-cleaning model judges the panel.
    """
    lux = float(reading["ldr_lux"])
    grid = np.asarray(reading["temps_c"], dtype=float)
    heatmap = make_heatmap(reading["temps_c"])
    out = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "panel_id": reading["panel_id"], "heatmap": heatmap,
        "clean_cost_inr": CLEAN_COST_INR, "forecast_kwh_7d": [0.0] * 7, "forecast_clean_kwh_7d": [0.0] * 7,
        "loss_inr_per_day": 0.0, "clean_now": False,
    }

    if lux < MIN_LUX:
        return {**out, "state": "ok", "efficiency_loss_pct": 0.0, "model_score_pct": 0.0,
                "reason": "Low sunlight (night or heavy cloud). Analysis paused."}

    prediction = predict_panel(reading, history=history, cleaning_result=cleaning_result)
    state = prediction["state"]
    light = light_features(reading)
    uneven = light["light_spread_pct"] > UNEVEN_LIGHT_PCT
    if uneven and state in ("dust", "ok"):
        state = "shading"                                 # never call a shadow dirt
    expected_power = estimate_expected_power(lux, float(grid.mean()))
    actual_power = float(reading["voltage_v"]) * float(reading["current_a"])
    efficiency_loss = round(max(0.0, min(100.0, (expected_power - actual_power) / expected_power * 100)), 2)
    out.update(state=state, efficiency_loss_pct=efficiency_loss, light_spread_pct=round(light["light_spread_pct"], 1), model_score_pct=prediction.get("model_score_pct", 0.0),
               diagnosis_stage=prediction.get("diagnosis_stage", "before_cleaning"))

    # weather and forecast (from the feed; Open-Meteo only if no feed was given)
    try:
        if weather:
            irradiance, temperature, rain = weather_from_feed(weather)
        else:
            irradiance, temperature = get_forecast_weather(SITE_LATITUDE, SITE_LONGITUDE)
            rain = rain_expected(SITE_LATITUDE, SITE_LONGITUDE, hours=48)
        out["forecast_kwh_7d"], out["forecast_clean_kwh_7d"] = forecast_pair(irradiance, temperature, efficiency_loss)
        out["loss_inr_per_day"] = round(
            sum(max(0, c - n) for c, n in zip(out["forecast_clean_kwh_7d"], out["forecast_kwh_7d"])) / 7 * ELECTRICITY_RATE_INR, 2)
    except (requests.RequestException, KeyError, TypeError, ValueError) as error:
        rain = None
        out["reason"] = f"Forecast unavailable. Cleaning deferred: {error}"

    hot_patch = float(grid.max() - np.median(grid)) > HOT_PATCH_C
    tank_ok = float(reading["tank_level_pct"]) < 0 or float(reading["tank_level_pct"]) >= MINIMUM_TANK_LEVEL   # -1 = no tank sensor

    if state in ("fault", "hotspot"):
        out["reason"] = (f"{'Cracked cell' if state == 'fault' else 'Overheating cell'} confirmed"
                         f"{' after a wash' if cleaning_result else ''}. A wash will not fix it, so no water is used. Send a technician.")
    elif state == "shading":
        out["reason"] = ("Uneven light across the panel (a shadow or passing cloud), not dirt. No wash." if uneven
                         else "Part of the panel is in shade, not dirt. Washing will not help. Check for nearby objects.")
    elif state == "dust":
        if not tank_ok:
            out["reason"] = "Dust detected, but the water tank is too low."
        elif cleaning_result is None and hot_patch:
            out["clean_now"] = True                      # a hot patch is risky: wash first, then judge by the after-wash model
            out["reason"] = "Local hot patch, probably a bird dropping or dirt. Washing first to find out."
        elif rain is None:
            out.setdefault("reason", "Weather service unavailable. Cleaning deferred.")
        elif rain:
            out["reason"] = "Dust detected, but rain is forecast within 48 hours. Letting the rain clean it."
        elif out["loss_inr_per_day"] > CLEAN_COST_INR:
            out["clean_now"] = True
            out["reason"] = f"Dust is costing Rs {out['loss_inr_per_day']:.0f}/day, more than the Rs {CLEAN_COST_INR:.0f} wash. Cleaning now."
        else:
            out["reason"] = "Dust loss is still smaller than the cost of a wash."
    else:
        out["reason"] = "Panel is clean and producing as expected."
    return out


if __name__ == "__main__":
    import json

    sample_reading = {
        "ts": "2026-10-31T10:00:00Z",
        "panel_id": "P1",
        "voltage_v": 18.2,
        "current_a": 4.1,
        "ldr_lux": 3000,
        "temps_c": [
            [41.2, 41.5, 41.0],
            [41.3, 44.0, 41.1]
        ],
        "tank_level_pct": 70
    }

    result = decide(sample_reading)

    print(json.dumps(result, indent=4))
