# ☀️ SolarSentinel
### Autonomous Solar Panel Monitoring, Intelligent Diagnosis & Cleaning System

SolarSentinel is an intelligent solar panel monitoring and maintenance system designed to improve solar energy efficiency through sensor-based monitoring, Machine Learning (ML), real-time decision-making, and automated cleaning.

The system continuously monitors solar panel conditions, identifies possible faults and dust accumulation, estimates energy losses, and decides whether cleaning is required. It aims to reduce unnecessary maintenance, minimize energy losses, and improve the overall performance of solar installations.

---

## 🌐 Live Applications

Explore the live SolarSentinel applications:

| Application | Description | Live Link |
|---|---|---|
| Customer App | Main application for viewing solar panel information and monitoring system activity. | [Open Customer App](https://solarsentinel-app.pages.dev) |
| Hardware Dashboard | ESP32 and hardware monitoring interface for viewing sensor and device activity. | [Open Hardware View](https://solarsentinel-hw.pages.dev) |
| ML Console | Machine Learning dashboard for panel diagnosis, thermal visualization, cleaning decisions, and energy forecasting. | [Open ML Console](https://solarsentinel-ml.pages.dev) |

**ML API:** [https://solarsentinel-api.pages.dev](https://solarsentinel-api.pages.dev)

---

## 🎯 Problem Statement

Solar panels can lose efficiency due to dust accumulation, partial shading, overheating, and physical damage.

Traditional maintenance often depends on manual inspection or fixed cleaning schedules. This can result in:

- Unnecessary cleaning and water consumption.
- Delayed detection of panel faults.
- Reduced energy generation.
- Increased maintenance costs.
- Difficulty identifying the exact cause of performance loss.

SolarSentinel addresses these challenges by combining sensor monitoring with intelligent diagnosis and condition-based cleaning decisions.

---

## 💡 Our Solution

SolarSentinel uses data collected from solar panels to understand their operating conditions and determine the appropriate maintenance action.

The system follows this workflow:

1. **Sensor Monitoring:** Collects panel voltage, current, light intensity, temperature, and water tank information.
2. **Data Processing:** Converts sensor readings into useful features for analysis.
3. **ML Diagnosis:** Classifies the panel condition and identifies possible performance problems.
4. **Thermal Analysis:** Uses temperature readings to identify unusual heat patterns.
5. **Weather Analysis:** Checks expected rainfall before recommending cleaning.
6. **Energy Forecasting:** Estimates energy generation for the upcoming seven days.
7. **Decision Engine:** Determines whether cleaning is economically and operationally suitable.
8. **Hardware Communication:** Sends the required decision to the hardware system for execution.

---

## ⚙️ Key Features

### 1. Intelligent Panel Diagnosis
The Machine Learning system identifies different panel conditions:

- Healthy
- Dust
- Shading
- Hotspot / Hot cell
- Fault / Cracked cell

### 2. Thermal Heatmap Visualization
Displays panel temperature readings in a visual heatmap to help identify abnormal temperature patterns and potential hotspots.

### 3. Automated Cleaning Decisions
The decision engine evaluates panel conditions, estimated energy losses, weather conditions, and cleaning costs before recommending a wash.

### 4. Weather Integration
Checks rainfall forecasts to avoid unnecessary cleaning when rain is expected.

### 5. Seven-Day Energy Forecast
Estimates upcoming energy generation using weather-related and panel-performance information.

### 6. Financial Analysis
Estimates daily energy losses and compares the financial impact of lost generation against the cost of cleaning.

### 7. Hardware Monitoring
Provides a dedicated interface for monitoring ESP32 and hardware-related activity.

### 8. Decision History
Displays previous panel diagnoses, cleaning decisions, and explanations for the actions taken.

---

## 🧠 Machine Learning & AI

The ML module is responsible for intelligent panel diagnosis and maintenance recommendations.

**Main components:**

- Random Forest Classifier for panel-condition classification.
- Feature engineering using electrical, light, and temperature readings.
- Separate before-wash and after-wash diagnosis stages.
- Thermal heatmap generation.
- Weather-based cleaning decisions.
- LightGBM-based energy forecasting.
- Rule-based decision engine for maintenance recommendations.

### Diagnosis and Decision Logic

The system distinguishes between problems that may be resolved through cleaning and problems that require manual inspection.

| Panel Condition | Recommended Action |
|---|---|
| Healthy | No cleaning required |
| Dust | Evaluate whether cleaning is beneficial |
| Shading | No automatic cleaning |
| Hotspot | Manual inspection and repair |
| Fault / Cracked cell | Manual inspection and repair |

Cleaning decisions also consider rainfall forecasts, water availability, estimated energy losses, and cleaning costs.

**Model accuracy note:** The deployed ML console reports approximately 99.8% accuracy on data generated by the project's physics simulator. This is not a real-world field accuracy measurement. Performance on actual solar panels still requires validation and further training with real sensor data.

---

## 🏗️ System Architecture

SolarSentinel consists of three major application modules:

### 1. Customer Application
Provides the main interface for users to access solar monitoring information and system activity.

### 2. Hardware / ESP32 Module
Handles sensor readings and hardware operations, including the cleaning mechanism.

### 3. ML / AI Module
Processes sensor readings, performs panel diagnosis, generates predictions, and determines maintenance decisions.

### Overall Workflow

```text
       SOLAR PANEL
            |
            v
      ESP32 SENSORS
            |
            v
      SENSOR READINGS
            |
            v
       ML / AI ENGINE
            |
     +------+------+
     |             |
     v             v
  DIAGNOSIS    FORECASTING
     |             |
     +------+------+
            |
            v
     DECISION ENGINE
            |
            v
     CLEANING DECISION
            |
            v
      HARDWARE SYSTEM
            |
            v
    CLEANING / MONITORING
```

The three application interfaces provide visibility into the customer, hardware, and ML sides of the system.

---

## 🛠️ Technology Stack

| Component | Technology |
|---|---|
| Programming Language | Python |
| Machine Learning | Scikit-learn |
| Classification | Random Forest |
| Energy Forecasting | LightGBM |
| Data Processing | Pandas, NumPy |
| Hardware | ESP32 |
| Communication | MQTT |
| Weather Information | Open-Meteo API |
| Model Serialization | Pickle |
| Web Deployment | Cloudflare Pages |

---

## 📂 Repository Structure

```text
SolarSentinel/
│
├── 1-ui-design/
│   └── Customer application and UI resources
│
├── 2-ml-ai/
│   ├── api/
│   ├── data/
│   ├── models/
│   ├── classify.py
│   ├── decide.py
│   ├── forecast.py
│   ├── heatmap.py
│   ├── weather.py
│   ├── serve.py
│   ├── requirements.txt
│   └── README.md
│
├── 3-hardware-sim/
│   └── ESP32 and hardware simulation resources
│
├── docs/
│   └── Project documentation
│
└── README.md
```

*The folders above represent the major project modules. Refer to the repository for the latest file-level structure.*

---

## 🔬 How the ML Decision Is Made

The ML module follows these main stages:

**Step 1 – Read Sensor Data**

Collects electrical readings, light measurements, temperature values, and tank-level information.

**Step 2 – Feature Extraction**

Processes the readings to calculate useful indicators such as power loss, temperature differences, and light distribution.

**Step 3 – Panel Classification**

Predicts the current panel condition using the trained classification model.

**Step 4 – Post-Cleaning Verification**

Uses the after-wash diagnosis stage to help distinguish removable dust from persistent faults.

**Step 5 – Decision Evaluation**

Checks weather conditions, water availability, energy loss, and cleaning costs.

**Step 6 – Send the Verdict**

Returns a structured decision for the application and hardware system.

---

## 👥 Team TRUENO

Built by **Team TRUENO**.

| Team Member | Responsibility |
|---|---|
| Pratham B R | Machine Learning & Artificial Intelligence |
| Sanjay | ESP32 & Hardware Development |
| Shashank | UI Design & Application Interface |

---

## 🚀 Project Vision

Our vision is to make solar panel maintenance smarter, more efficient, and more sustainable.

By combining Machine Learning, IoT, sensor monitoring, and intelligent automation, SolarSentinel aims to reduce energy losses, avoid unnecessary maintenance, and support reliable solar energy generation.

---

## ⚠️ Current Limitations

- Model performance is currently reported on simulator-generated data and requires real-world validation.
- Real hardware performance depends on sensor calibration and reliable communication.
- Energy forecasts are estimates and may differ from actual energy generation.
- Hardware cleaning operations require appropriate safety checks and hardware-level protection.

---

## 📌 Project Information

**Project:** SolarSentinel – Autonomous Solar O&M Intelligence  
**Team:** TRUENO  
**Category:** Artificial Intelligence / Machine Learning / Internet of Things  
**Repository:** [snb-cpu/solarsentinel](https://github.com/snb-cpu/solarsentinel)

---

### Built with ☀️ by Team TRUENO

*Making solar maintenance intelligent, efficient, and sustainable.*
