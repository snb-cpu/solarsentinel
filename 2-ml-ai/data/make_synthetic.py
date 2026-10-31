
import numpy as np
import pandas as pd
from pathlib import Path

rng = np.random.default_rng(42)

SAMPLES_PER_CLASS = 500
OUTPUT_FILE = Path(__file__).parent / "synthetic.csv"

STATES = ["ok", "dust", "shading", "hotspot", "fault"]


def expected_power_from_ldr(ldr):
    normalized_irradiance = ldr / 4095
    return 100 * normalized_irradiance


def make_grid(base, state):
    grid = np.full((2, 3), base) + rng.normal(0, 0.7, (2, 3))

    if state == "dust":
        grid += rng.uniform(2, 4)

    elif state == "shading":
        shaded_side = rng.integers(0, 2)
        grid[:, shaded_side] -= rng.uniform(5, 9)

    elif state == "hotspot":
        row = rng.integers(0, 2)
        col = rng.integers(0, 3)
        grid[row, col] += rng.uniform(6, 15)

    elif state == "fault":
        row = rng.integers(0, 2)
        col = rng.integers(0, 3)
        grid[row, col] += rng.uniform(13, 20)

    return grid


def make_features(state):
    ldr = rng.uniform(1500, 4095)
    expected_power = expected_power_from_ldr(ldr)

    loss_ranges = {
        "ok": (0, 4),
        "dust": (5, 15),
        "shading": (25, 45),
        "hotspot": (8, 20),
        "fault": (15, 35)
    }

    loss = rng.uniform(*loss_ranges[state])
    actual_power = expected_power * (1 - loss / 100)

    voltage = rng.uniform(17, 20)
    current = actual_power / voltage

    ambient = rng.uniform(25, 38)
    base_temp = ambient + rng.uniform(5, 10)

    grid = make_grid(base_temp, state)

    if state == "fault":
        history_grid = grid.copy()
        history_power = actual_power * rng.uniform(0.98, 1.02)
    else:
        history_grid = grid + rng.normal(0, 0.6, (2, 3))
        history_power = actual_power * rng.uniform(0.95, 1.05)

    if state == "dust":
        after_grid = grid - rng.uniform(2, 4)
        after_power = actual_power * rng.uniform(1.05, 1.15)

    elif state == "fault":
        after_grid = grid.copy()
        after_power = actual_power * rng.uniform(0.98, 1.02)

    elif state == "hotspot":
        after_grid = grid.copy()
        after_power = actual_power * rng.uniform(0.98, 1.02)

    else:
        after_grid = grid + rng.normal(0, 0.3, (2, 3))
        after_power = actual_power * rng.uniform(0.98, 1.02)

    median = np.median(grid)

    power_loss = (
        (expected_power - actual_power) / expected_power
    ) * 100

    power_recovery = (
        (after_power - actual_power) / actual_power
    ) * 100

    temperature_recovery = grid.mean() - after_grid.mean()

    hotspot_after = after_grid.max() - np.median(after_grid)

    return {
        "state": state,
        "voltage_v": voltage,
        "current_a": current,
        "ldr_lux": ldr,
        "expected_power_w": expected_power,
        "actual_power_w": actual_power,
        "power_loss_pct": power_loss,
        "grid_mean": grid.mean(),
        "grid_std": grid.std(),
        "max_minus_median": grid.max() - median,
        "left_right_gradient": (
            grid[:, 0].mean() - grid[:, 2].mean()
        ),
        "top_bottom_gradient": (
            grid[0, :].mean() - grid[1, :].mean()
        ),
        "history_power_w": history_power,
        "history_temp_mean": history_grid.mean(),
        "power_trend_pct": (
            (actual_power - history_power) / history_power
        ) * 100,
        "temp_trend_c": grid.mean() - history_grid.mean(),
        "cleaning_done": 1,
        "power_recovery_pct": power_recovery,
        "temperature_recovery_c": temperature_recovery,
        "hotspot_after_clean_c": hotspot_after
    }


def main():
    records = []

    for state in STATES:
        for _ in range(SAMPLES_PER_CLASS):
            records.append(make_features(state))

    df = pd.DataFrame(records)
    df = df.sample(frac=1, random_state=42).reset_index(drop=True)

    df.to_csv(OUTPUT_FILE, index=False)

    print("SolarSentinel synthetic dataset generated!")
    print("Total records:", len(df))
    print("Saved to:", OUTPUT_FILE)

    print("\nClass distribution:")
    print(df["state"].value_counts())

    print("\nExpected power range:")
    print(df["expected_power_w"].min(), "to",
          df["expected_power_w"].max())

    print("\nLDR range:")
    print(df["ldr_lux"].min(), "to", df["ldr_lux"].max())


if __name__ == "__main__":
    main()
