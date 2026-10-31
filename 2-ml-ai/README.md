# SolarSentinel – ML/AI Intelligence Module

Pratham B R

## 1. Overview

The ML/AI module is the intelligence engine of **SolarSentinel – Autonomous Solar O&M Intelligence**. It monitors solar panel performance, identifies abnormal operating conditions, estimates energy production, calculates financial losses and recommends appropriate maintenance actions.

The system processes sensor readings received from the hardware layer, analyzes panel conditions using Machine Learning models and rule-based decision logic, and publishes maintenance decisions through MQTT.

The primary objective is to distinguish between normal operation, dust accumulation, partial shading, hotspots and hardware faults while preventing unsafe automatic cleaning operations.

## 2. Key Features

- **Solar Panel Condition Classification:** Identifies five operating conditions: OK, Dust, Shading, Hotspot and Fault.
- **Thermal Heatmap Generation:** Converts a 2×3 temperature sensor grid into a normalized heatmap for identifying abnormal temperature patterns.
- **Dust Detection:** Identifies uniform temperature increases and performance reduction associated with dust accumulation.
- **Shading Detection:** Identifies uneven panel temperature and power loss patterns associated with partial shading.
- **Hotspot and Fault Detection:** Detects abnormal temperature patterns and recommends manual inspection and repair.
- **Weather Integration:** Uses weather forecast information to determine whether rainfall is expected within the next 48 hours.
- **Energy Forecasting:** Estimates solar energy generation for the next seven days using a LightGBM regression model.
- **Financial Loss Estimation:** Calculates estimated daily energy loss in INR and compares it with cleaning costs.
- **Autonomous Maintenance Decisions:** Determines whether cleaning should be performed, delayed or avoided.
- **MQTT Communication:** Receives sensor readings and publishes decisions and maintenance commands.
- **Safety Mechanisms:** Prevents automatic cleaning for hotspots, hardware faults, shading conditions and unsuitable cleaning conditions.

## 3. System Architecture

The ML/AI module follows this processing pipeline:

```text
ESP32 / Hardware Sensors
          |
          v
     MQTT Broker
          |
          v
   Sensor Reading
          |
          v
   Data Processing
          |
          v
  ML Classification
          |
          v
  Thermal Heatmap
          |
          v
 Weather Integration
          |
          v
 Energy Forecasting
          |
          v
 Decision Engine
          |
          v
   MQTT Broker
      /       \
     v         v
 Decision   Cleaning Command
     |         |
     v         v
 Dashboard   Hardware
```

## 4. Machine Learning Models

### 4.1 Solar Panel Condition Classification

The classification module uses **Random Forest Classifier** to identify the operating condition of a solar panel.

The model classifies readings into five categories:

| State | Description | Recommended Action |
|---|---|---|
| OK | Normal panel operation | No action |
| Dust | Dust accumulation affecting performance | Evaluate cleaning |
| Shading | Partial shading affecting panel output | Inspect shading |
| Hotspot | Abnormal localized temperature increase | Manual inspection |
| Fault | Potential hardware or electrical fault | Manual repair |

Two classification stages are implemented:

- Before Cleaning: Uses the initial sensor readings to identify panel conditions.
- After Cleaning: Uses additional cleaning-response information to evaluate changes in panel performance.

The trained models are saved in `model.pkl` for reuse during prediction.

**Note:** The current training dataset is synthetically generated for demonstration and development. Its reported accuracy must not be interpreted as real-world field accuracy.

### 4.2 Thermal Heatmap Generation

The heatmap module processes the 2×3 temperature sensor grid.

It performs the following operations:

1. Validates the temperature grid.
2. Calculates the median temperature.
3. Measures temperature deviations from the median.
4. Removes negative deviations.
5. Normalizes the remaining values between 0 and 1.
6. Generates a heatmap representing temperature abnormalities.

Example:

```json
{
  "heatmap": [
    [0.0, 0.04, 0.0],
    [0.01, 1.0, 0.0]
  ]
}
```

A higher normalized value indicates a stronger temperature deviation relative to the other sensor locations.

### 4.3 Weather Integration

The weather module integrates with the **Open-Meteo Weather API**.

It retrieves weather forecast information to determine whether rainfall is expected within the next 48 hours.

The system uses this information to make cleaning decisions:

- Rain expected: Cleaning can be postponed.
- No rain expected: Other cleaning conditions are evaluated.
- Weather unavailable: Automatic cleaning is deferred for safety.

Weather results are cached to reduce repeated API requests.

### 4.4 Energy Forecasting

The forecasting module uses **LightGBM Regressor** to estimate solar energy production for the next seven days.

The model considers:

- Forecast irradiance.
- Temperature.
- Current soiling loss.

Output:

```json
{
  "forecast_kwh_7d": [
    3.1, 3.4, 2.9, 3.3, 3.5, 3.2, 3.0
  ]
}
```

The values represent estimated daily energy production for seven consecutive days.

The current forecasting implementation is a demonstration model trained using synthetic data.

## 5. Intelligent Decision Engine

The decision engine combines classification results, thermal analysis, weather information, energy forecasting and financial calculations.

It determines whether the solar panel should continue normal operation, be inspected or undergo cleaning.

### Decision Rules

**OK:**
- Panel operates under normal conditions.
- No automatic cleaning is required.

**Dust:**
- Checks whether sufficient water is available.
- Checks rainfall probability for the next 48 hours.
- Estimates daily financial loss.
- Compares energy loss against cleaning cost.
- Recommends cleaning only when conditions are suitable and cleaning is economically beneficial.

**Shading:**
- Recommends inspection of the panel's surroundings.
- Automatic cleaning is disabled.

**Hotspot:**
- Recommends manual inspection and repair.
- Automatic cleaning is disabled.

**Fault:**
- Recommends manual inspection and repair.
- Automatic cleaning is disabled.

### Financial Calculations

The decision engine estimates:

- Daily energy loss in kWh.
- Daily financial loss in INR.
- Cleaning cost in INR.

The current demonstration configuration uses:

- Electricity rate: ₹8 per kWh.
- Cleaning cost: ₹2.
- Minimum tank level: 20%.

These values are configurable and should be calibrated for the actual deployment.

## 6. MQTT Communication

The ML module communicates with the hardware layer through MQTT.

### MQTT Topics

| Topic | Purpose |
|---|---|
| `solar/<panel_id>/reading` | Receives sensor readings |
| `solar/<panel_id>/decision` | Publishes ML decisions |
| `solar/<panel_id>/command` | Publishes cleaning commands |

### Sensor Reading Format

Example input received from the hardware:

```json
{
  "ts": "2026-10-31T10:00:00Z",
  "panel_id": "P1",
  "voltage_v": 18.2,
  "current_a": 4.1,
  "ldr_lux": 54000,
  "temps_c": [
    [41.2, 41.5, 41.0],
    [41.3, 47.9, 41.1]
  ],
  "tank_level_pct": 70
}
```

### Decision Output Format

Example output generated by the ML module:

```json
{
  "ts": "2026-10-31T10:00:02Z",
  "panel_id": "P1",
  "state": "dust",
  "efficiency_loss_pct": 8.4,
  "clean_now": true,
  "reason": "Cleaning conditions are suitable",
  "heatmap": [
    [0.1, 0.2, 0.1],
    [0.2, 0.9, 0.1]
  ],
  "forecast_kwh_7d": [
    3.1, 3.4, 2.9, 3.3, 3.5, 3.2, 3.0
  ],
  "loss_inr_per_day": 12.5,
  "clean_cost_inr": 2.0
}
```

### Cleaning Command Format

When cleaning is approved, the ML module publishes:

```json
{
  "panel_id": "P1",
  "action": "clean",
  "water_ms": 4000,
  "air_ms": 8000
}
```

The command follows the shared hardware contract: water spraying occurs first, followed by air blowing.

Automatic cleaning is disabled for hotspot and fault conditions.

## 7. Project Structure

```text
2-ml-ai/
│
├── classify.py
├── heatmap.py
├── weather.py
├── forecast.py
├── decide.py
├── serve.py
│
├── model.pkl
│
├── data/
│   ├── make_synthetic.py
│   ├── synthetic.csv
│   └── sample_reading.json
│
├── models/
│
├── test_decide.py
├── test_model.py
│
├── requirements.txt
└── README.md
```

### File Description

| File | Description |
|---|---|
| `classify.py` | Trains and runs Random Forest classification models |
| `heatmap.py` | Generates normalized thermal heatmaps |
| `weather.py` | Retrieves rainfall forecast information |
| `forecast.py` | Predicts seven-day energy generation |
| `decide.py` | Combines ML predictions and maintenance rules |
| `serve.py` | MQTT subscriber and publisher for hardware communication |
| `model.pkl` | Saved trained classification models |
| `data/make_synthetic.py` | Generates synthetic training data |
| `data/synthetic.csv` | Synthetic dataset for model training |
| `data/sample_reading.json` | Sample sensor input |
| `test_decide.py` | Tests decision engine scenarios |
| `test_model.py` | Tests classification functionality |
| `requirements.txt` | Python dependency list |

## 8. Technologies Used

| Technology | Purpose |
|---|---|
| Python | Core development language |
| Scikit-learn | Random Forest classification |
| LightGBM | Energy forecasting |
| Pandas | Dataset processing |
| NumPy | Numerical operations |
| Paho-MQTT | MQTT communication |
| Requests | Weather API integration |
| Open-Meteo API | Weather forecasting |
| Mosquitto | MQTT broker |
| JSON | Hardware and ML data exchange |

## 9. Installation and Setup

### Prerequisites

- Python 3.10 or later
- pip
- Git
- Mosquitto MQTT Broker

### Step 1: Navigate to the ML directory

```bash
cd 2-ml-ai
```

### Step 2: Create a virtual environment

```bash
python3 -m venv venv
```

### Step 3: Activate the virtual environment

```bash
source venv/bin/activate
```

### Step 4: Install dependencies

```bash
pip install -r requirements.txt
```

### Step 5: Install and start Mosquitto

On Ubuntu:

```bash
sudo apt update
sudo apt install mosquitto mosquitto-clients
sudo systemctl start mosquitto
```

## 10. Running the ML Module

### Train the synthetic dataset and classification models

```bash
python data/make_synthetic.py
python classify.py
```

This generates the synthetic dataset and trains the classification models.

### Run the decision engine

```bash
python decide.py
```

### Start the MQTT server

```bash
python serve.py
```

The server subscribes to incoming solar panel readings, processes them through the ML decision engine and publishes the resulting decisions.

### Run the tests

```bash
python -m pytest test_decide.py -v
```

For model testing:

```bash
python test_model.py
```

## 11. Testing and Validation

The decision engine has been tested using simulated scenarios, including:

1. Normal solar panel operation.
2. Fault detection and prevention of automatic cleaning.
3. Hotspot detection and prevention of automatic cleaning.
4. Dust detection when rainfall is expected.
5. Economically beneficial dust cleaning.
6. Low water tank level.
7. Weather API unavailability.

The MQTT communication pipeline has also been tested using simulated sensor readings through Mosquitto.

The simulation demonstrated the following workflow:

**Simulated Sensor Reading → MQTT Broker → ML Processing → Decision Generation → MQTT Decision Publishing**

Actual ESP32 hardware validation and field testing are still required.

## 12. Safety and Reliability

SolarSentinel follows safety-first maintenance logic.

- Hotspots must be inspected manually.
- Hardware faults must be repaired manually.
- Shading conditions must be inspected before maintenance.
- Cleaning is postponed when rainfall is expected.
- Cleaning is disabled when the water tank level is insufficient.
- Cleaning is deferred when weather information is unavailable.
- Financial benefits are evaluated before recommending cleaning.

The ML system provides maintenance recommendations. Real-world hardware safety interlocks
