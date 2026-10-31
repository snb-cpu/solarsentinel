
import requests
import time

API_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_DURATION = 3600
_cache = {}


def rain_expected(lat, lon, hours=48):
    key = (lat, lon, hours)
    now = time.time()

    if key in _cache:
        cached_time, result = _cache[key]
        if now - cached_time < CACHE_DURATION:
            return result

    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "precipitation_probability",
        "forecast_days": 3,
        "timezone": "auto"
    }

    try:
        response = requests.get(API_URL, params=params, timeout=15)
        response.raise_for_status()

        data = response.json()
        probabilities = data["hourly"]["precipitation_probability"][:hours]

        result = any(
            value is not None and value >= 50
            for value in probabilities
        )

        _cache[key] = (now, result)
        return result

    except (requests.RequestException, KeyError, TypeError, ValueError) as error:
        print(f"Weather service error: {error}")
        return None
