
import os
from datetime import datetime, timezone

import requests

from classify import predict_panel, estimate_expected_power
from heatmap import make_heatmap
from weather import rain_expected
from forecast import forecast_kwh_7d


ELECTRICITY_RATE_INR = 8.0
CLEAN_COST_INR = 2.0
MINIMUM_TANK_LEVEL = 20

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


def decide(reading, history=None, cleaning_result=None):
    prediction = predict_panel(
        reading,
        history=history,
        cleaning_result=cleaning_result
    )

    state = prediction["state"]

    grid = reading["temps_c"]
    heatmap = make_heatmap(grid)

    expected_power = estimate_expected_power(float(reading["ldr_lux"]))
    actual_power = float(reading["voltage_v"]) * float(reading["current_a"])

    efficiency_loss = (
        (expected_power - actual_power) / expected_power
    ) * 100

    efficiency_loss = round(
        max(0, min(100, efficiency_loss)),
        2
    )

    forecast_values = [0.0] * 7
    loss_inr_per_day = 0.0
    clean_now = False

    reason = "Panel operating normally; no cleaning required."

    if state in ("fault", "hotspot"):
        reason = (
            f"{state.capitalize()} detected. "
            "Manual inspection and repair required. Automatic cleaning disabled."
        )

    elif state == "dust":
        if float(reading["tank_level_pct"]) < MINIMUM_TANK_LEVEL:
            reason = "Dust detected, but water tank level is too low."

        else:
            try:
                irradiance, temperatures = get_forecast_weather(
                    SITE_LATITUDE,
                    SITE_LONGITUDE
                )

                forecast_values = forecast_kwh_7d(
                    irradiance,
                    temperatures,
                    efficiency_loss
                )

                baseline_forecast = forecast_kwh_7d(
                    irradiance,
                    temperatures,
                    0
                )

                loss_inr_per_day = round(
                    sum(
                        max(0, baseline - actual)
                        for baseline, actual in zip(
                            baseline_forecast,
                            forecast_values
                        )
                    ) / 7 * ELECTRICITY_RATE_INR,
                    2
                )

                rain = rain_expected(
                    SITE_LATITUDE,
                    SITE_LONGITUDE,
                    hours=48
                )

                if rain is None:
                    reason = "Weather service unavailable. Cleaning deferred."

                elif rain:
                    reason = "Rain expected within 48 hours. Natural cleaning may occur."

                elif loss_inr_per_day > CLEAN_COST_INR:
                    clean_now = True
                    reason = (
                        "Dust detected, no significant rain expected, "
                        "and estimated daily energy loss exceeds cleaning cost."
                    )

                else:
                    reason = "Estimated energy loss does not justify cleaning."

            except (requests.RequestException, KeyError, TypeError, ValueError) as error:
                reason = f"Forecast unavailable. Cleaning deferred: {error}"

    elif state == "shading":
        reason = "Shading detected. Check for nearby objects or obstructions."

    return {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "panel_id": reading["panel_id"],
        "state": state,
        "efficiency_loss_pct": efficiency_loss,
        "clean_now": clean_now,
        "reason": reason,
        "heatmap": heatmap,
        "forecast_kwh_7d": forecast_values,
        "loss_inr_per_day": loss_inr_per_day,
        "clean_cost_inr": CLEAN_COST_INR
    }


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
