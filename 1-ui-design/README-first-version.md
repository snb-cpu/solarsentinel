> **This is what Shashank wrote about his first version of the page** (`solarsentinel_enterprise_dashboard(1).html`), kept as he wrote it. The file layout, fonts and colours below are not the current ones. The current app and how to run it: [README.md](README.md).

# ☀️ SolarSentinel - Smart Solar Panel Monitor & Auto-Cleaner Dashboard

Shashank

SolarSentinel is an enterprise-grade, customer-facing web dashboard designed for homeowners and small plant operators in India. The application provides real-time solar panel performance tracking, AI/ML-driven automated cleaning triggers, uneven light and shadow detection, and dynamic energy loss analysis—all built on zero-framework, high-performance vanilla web technology.



---



## 🌟 Key Features



* **Executive Customer View**: Clear, plain-English system status banner highlighting health, financial loss impact in ₹/day, and estimated daily energy yield ($kWh$).

* **Centerpiece Thermal Camera Inspection**: High-density 2x4 surface sensor heatmap interpolated using 2D Gaussian rendering with solar cell gridlines, silver busbars, anti-reflective glass glare, real-time hotspot target reticles, and corner light lux sensors ($kLx$).

* **Pure SVG Visualizations**:

  * **Power History Chart**: Smooth gradient area chart tracking system output ($W$) over time with interactive wash markers (`c: true`).

  * **7-Day Yield Forecast**: Double-bar projection contrasting current output vs. wash-boosted energy potential ($kWh$).

* **Eco-Balance & Zero-Net Energy Assurance**: Monitors node power draw ($mW$), energy consumed ($Wh$), tap vs. sprayed water ($L$), and energy recovered through washing.

* **Preserved Live Simulator Drawer**: Integrated presenter panel to simulate dust accumulation, hotspot faults, shading, rain storms, and speed acceleration (collapsible & automatically hidden when `?demo=0` is passed).

* **Fully Responsive & Accessible**: Built with glassmorphism styling, executive typography (`Inter` & `JetBrains Mono`), dark/light theme switching, and strict contrast ratios readable from a distance.



---



## 📁 Repository Structure



```

1-ui-design/

├── index.html           # Full self-contained dashboard (Inline CSS & JS)

├── contract.md          # Telemetry payload & API spec

├── sample-snapshot.json # Real live message payload sample

└── README.md            # Repository documentation

```



---



## 🚀 How to Run



The dashboard is 100% self-contained with no npm dependencies, framework build steps, or external bundlers required.



### 1. Direct File Launch

Simply double-click `index.html` to open it in any modern browser.



### 2. Python HTTP Server

Run a standard local server from the root directory:



```bash

python3 -m http.server 8000

```

Open your browser at: `http://localhost:8000`



### 3. URL Query Parameters



* **Connect to custom SSE backend**:

  `http://localhost:8000/?api=http://your-backend-ip:8000`

* **Clean Customer View (Hide Presenter Demo Drawer)**:

  `http://localhost:8000/?demo=0`



---



## 📡 API & Telemetry Contract



### SSE Event Stream

* **Endpoint**: `GET /events`

* **Payload**: Single snapshot JSON (`sample-snapshot.json`) received per tick containing array of panels, site totals, weather stats, and decision logs.



### Clean Trigger Endpoints

* **Clean All Panels**:

  `POST /api/clean` with body `{}`

* **Clean Specific Panel**:

  `POST /api/clean` with body `{"panel_id": <id>}`



### Simulator Control Endpoint

* **Simulate Conditions**:

  `POST /api/sim` with body `{"cmd": "<cmd_name>", "panel": <index>, "value": "<value>"}`



---



## 🎨 Theme & Styling Guidelines



* **Primary Palette**:

  * Deep Navy: `#0B1D33` / Dark Page `#070F1E`

  * Sun Amber: `#FFB703` (Primary Accent)

  * Gold Hover: `#F59E0B`

  * Status Colors: Emerald (`#10B981`), Cyan (`#0284C7`), Coral Red (`#EF4444`)

* **Fonts**: `Inter` for clean corporate typography, `JetBrains Mono` for telemetry and sensor figures.



---



## 🛡️ License



Distributed under the MIT License. Built for the SolarSentinel Project.
