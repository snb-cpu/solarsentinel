
import numpy as np
from lightgbm import LGBMRegressor

MODEL = None


def train_forecast_model():
    global MODEL

    rng = np.random.default_rng(42)

    samples = 3000

    irradiance = rng.uniform(2, 8, samples)
    temperature = rng.uniform(20, 45, samples)
    soiling_loss = rng.uniform(0, 40, samples)

    daily_energy = (
        irradiance
        * 0.22
        * (1 - soiling_loss / 100)
        * (1 - 0.004 * (temperature - 25))
    )

    X = np.column_stack([
        irradiance,
        temperature,
        soiling_loss
    ])

    MODEL = LGBMRegressor(
        n_estimators=150,
        learning_rate=0.05,
        max_depth=5,
        random_state=42,
        verbosity=-1
    )

    MODEL.fit(X, daily_energy)

    return MODEL


def forecast_kwh_7d(irradiance_forecast, temperature_forecast, soiling_loss_pct):
    if len(irradiance_forecast) != 7 or len(temperature_forecast) != 7:
        raise ValueError("Exactly seven daily forecast values are required.")

    if not 0 <= soiling_loss_pct <= 100:
        raise ValueError("Soiling loss must be between 0 and 100.")

    if MODEL is None:
        train_forecast_model()

    X = np.column_stack([
        irradiance_forecast,
        temperature_forecast,
        [soiling_loss_pct] * 7
    ])

    predictions = MODEL.predict(X)

    return [
        round(max(0, float(value)), 2)
        for value in predictions
    ]


if __name__ == "__main__":
    train_forecast_model()

    result = forecast_kwh_7d(
        [5.5, 6.0, 5.8, 6.2, 5.4, 5.9, 6.1],
        [30, 31, 32, 30, 29, 31, 30],
        10
    )

    print("7-day energy forecast:")
    print(result)
