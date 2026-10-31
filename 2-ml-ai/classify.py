
import numpy as np
import pandas as pd
import joblib

from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix
)

BASE_DIR = Path(__file__).parent
PHYSICS_FILE = BASE_DIR / "data" / "physics.csv"      # labelled episodes from the physics simulator (digital twin)
DATA_FILE = PHYSICS_FILE if PHYSICS_FILE.exists() else BASE_DIR / "data" / "synthetic.csv"
MODEL_FILE = BASE_DIR / "model.pkl"
_SAVED = None

CLASSES = ["ok", "dust", "shading", "hotspot", "fault"]

LDR_FULL_SCALE_LUX = 100000.0   # the LDR reading (lux) at full sun
MAX_POWER_W = 101.75             # panel power at full sun and 25 C (18.5 V x 5.5 A); calibrate on the real rig

BASE_FEATURES = [
    "voltage_v",
    "current_a",
    "ldr_lux",
    "power_w",
    "power_loss_pct",
    "grid_mean",
    "grid_std",
    "max_minus_median",
    "left_right_gradient",
    "top_bottom_gradient",
    "history_power_w",
    "history_temp_mean",
    "power_trend_pct",
    "temp_trend_c"
]

CLEANING_FEATURES = [
    "power_recovery_pct",
    "temperature_recovery_c",
    "hotspot_after_clean_c"
]


def validate_grid(grid):
    grid = np.asarray(grid, dtype=float)

    if grid.ndim != 2 or grid.shape[0] < 1 or grid.shape[1] < 2:
        raise ValueError("Temperature grid must be 2-D with at least 2 columns (any size, e.g. 2x4 or 1x3).")

    if not np.isfinite(grid).all():
        raise ValueError("Invalid temperature values.")

    return grid


def extract_grid_features(grid):
    median = np.median(grid)

    return {
        "grid_mean": float(grid.mean()),
        "grid_std": float(grid.std()),
        "max_minus_median": float(grid.max() - median),
        "left_right_gradient": float(
            grid[:, 0].mean() - grid[:, -1].mean()
        ),
        "top_bottom_gradient": float(
            grid[0, :].mean() - grid[-1, :].mean()
        )
    }


def estimate_expected_power(lux, grid_mean_c=25.0):
    """Power the panel should make at this light level and temperature (hot silicon loses ~0.35 %/C)."""
    if not np.isfinite(lux) or lux < 0:
        raise ValueError("Light reading must be a non-negative number of lux.")

    return (
        MAX_POWER_W
        * min(lux, LDR_FULL_SCALE_LUX) / LDR_FULL_SCALE_LUX
        * (1 - 0.0035 * (grid_mean_c - 25.0))
    )


def prepare_training_features(df):
    features = pd.DataFrame(index=df.index)

    features["voltage_v"] = df["voltage_v"]
    features["current_a"] = df["current_a"]
    features["ldr_lux"] = df["ldr_lux"]
    features["power_w"] = df["voltage_v"] * df["current_a"]
    features["power_loss_pct"] = df["power_loss_pct"]

    for column in [
        "grid_mean",
        "grid_std",
        "max_minus_median",
        "left_right_gradient",
        "top_bottom_gradient",
        "history_power_w",
        "history_temp_mean",
        "power_trend_pct",
        "temp_trend_c"
    ]:
        features[column] = df[column]

    for column in CLEANING_FEATURES:
        features[column] = df[column]

    return features


def train_model():
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            "Synthetic dataset not found. Run python data/make_synthetic.py"
        )

    df = pd.read_csv(DATA_FILE)

    required_columns = [
        "state",
        "voltage_v",
        "current_a",
        "ldr_lux",
        "power_loss_pct",
        "grid_mean",
        "grid_std",
        "max_minus_median",
        "left_right_gradient",
        "top_bottom_gradient",
        "history_power_w",
        "history_temp_mean",
        "power_trend_pct",
        "temp_trend_c",
        "power_recovery_pct",
        "temperature_recovery_c",
        "hotspot_after_clean_c"
    ]

    missing = set(required_columns) - set(df.columns)

    if missing:
        raise ValueError(
            f"Dataset is missing columns: {sorted(missing)}"
        )

    if not np.isfinite(
        df[required_columns[1:]].to_numpy(dtype=float)
    ).all():
        raise ValueError("Dataset contains invalid numeric values.")

    X = prepare_training_features(df)
    y = df["state"]

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y
    )

    models = {}

    configurations = [
        ("before_cleaning", BASE_FEATURES),
        ("after_cleaning", BASE_FEATURES + CLEANING_FEATURES)
    ]

    for mode, feature_columns in configurations:
        print(f"\nTraining {mode} model...")

        model = RandomForestClassifier(
            n_estimators=300,
            max_depth=15,
            min_samples_split=4,
            random_state=42,
            class_weight="balanced"
        )

        model.fit(
            X_train[feature_columns],
            y_train
        )

        predictions = model.predict(
            X_test[feature_columns]
        )

        accuracy = accuracy_score(y_test, predictions)

        print(f"\n{mode} accuracy: {accuracy * 100:.2f}%")
        print("\nClassification report:")
        print(
            classification_report(
                y_test,
                predictions,
                labels=CLASSES,
                zero_division=0
            )
        )

        print("Confusion matrix:")
        print(
            confusion_matrix(
                y_test,
                predictions,
                labels=CLASSES
            )
        )

        models[mode] = {
            "model": model,
            "features": feature_columns
        }

    joblib.dump(
        {
            "models": models,
            "classes": CLASSES,
            "version": 1
        },
        MODEL_FILE
    )

    print(f"\nModels saved successfully: {MODEL_FILE}")


def build_prediction_features(reading, history=None, cleaning_result=None):
    required = [
        "ts",
        "panel_id",
        "voltage_v",
        "current_a",
        "ldr_lux",
        "temps_c",
        "tank_level_pct"
    ]

    missing = [key for key in required if key not in reading]

    if missing:
        raise ValueError(
            f"Sensor reading is missing fields: {missing}"
        )

    grid = validate_grid(reading["temps_c"])

    voltage = float(reading["voltage_v"])
    current = float(reading["current_a"])
    ldr = float(reading["ldr_lux"])

    if not np.isfinite([voltage, current, ldr]).all():
        raise ValueError("Sensor reading contains invalid numbers.")

    if voltage <= 0 or current < 0:
        raise ValueError("Voltage must be positive and current non-negative.")

    power = voltage * current
    expected_power = estimate_expected_power(ldr, float(grid.mean()))

    if expected_power <= 0:
        raise ValueError("Expected power is zero; check the LDR reading.")

    power_loss = (
        (expected_power - power) / expected_power
    ) * 100

    current_temp_mean = float(grid.mean())

    if history is None:
        previous_power = power
        previous_temp_mean = current_temp_mean

    else:
        if isinstance(history, dict):
            history = [history]

        if not isinstance(history, list) or not history:
            raise ValueError("History must be a reading or a non-empty list.")

        history_powers = []
        history_temperatures = []

        for old_reading in history:
            old_grid = validate_grid(old_reading["temps_c"])
            old_voltage = float(old_reading["voltage_v"])
            old_current = float(old_reading["current_a"])

            history_powers.append(old_voltage * old_current)
            history_temperatures.append(float(old_grid.mean()))

        previous_power = float(np.mean(history_powers))
        previous_temp_mean = float(np.mean(history_temperatures))

    power_trend = (
        (power - previous_power) / max(previous_power, 0.01)
    ) * 100

    temp_trend = current_temp_mean - previous_temp_mean

    features = {
        "voltage_v": voltage,
        "current_a": current,
        "ldr_lux": ldr,
        "power_w": power,
        "power_loss_pct": power_loss,
        **extract_grid_features(grid),
        "history_power_w": previous_power,
        "history_temp_mean": previous_temp_mean,
        "power_trend_pct": power_trend,
        "temp_trend_c": temp_trend
    }

    mode = "before_cleaning"

    if cleaning_result is not None:
        before_power = float(cleaning_result["power_before_w"])
        after_power = float(cleaning_result["power_after_w"])

        before_grid = validate_grid(
            cleaning_result["temps_before_c"]
        )

        after_grid = validate_grid(
            cleaning_result["temps_after_c"]
        )

        if before_power <= 0 or after_power < 0:
            raise ValueError("Invalid cleaning power measurements.")

        features.update({
            "power_recovery_pct": (
                (after_power - before_power) / before_power
            ) * 100,
            "temperature_recovery_c": float(
                before_grid.mean() - after_grid.mean()
            ),
            "hotspot_after_clean_c": float(
                after_grid.max() - np.median(after_grid)
            )
        })

        mode = "after_cleaning"

    return pd.DataFrame([features]), mode


def predict_panel(reading, history=None, cleaning_result=None):
    if not MODEL_FILE.exists():
        raise FileNotFoundError(
            "Model not found. Run python classify.py first."
        )

    global _SAVED
    if _SAVED is None:
        _SAVED = joblib.load(MODEL_FILE)           # load once, not on every reading
    saved_data = _SAVED
    models = saved_data["models"]

    input_data, mode = build_prediction_features(
        reading,
        history,
        cleaning_result
    )

    saved_model = models[mode]
    model = saved_model["model"]
    features = saved_model["features"]

    prediction = model.predict(input_data[features])[0]
    probabilities = model.predict_proba(input_data[features])[0]

    scores = {
        name: round(float(value) * 100, 2)
        for name, value in zip(model.classes_, probabilities)
    }

    return {
        "panel_id": reading["panel_id"],
        "state": str(prediction),
        "model_score_pct": round(float(max(probabilities)) * 100, 2),
        "diagnosis_stage": mode,
        "class_probabilities": scores
    }


if __name__ == "__main__":
    train_model()
