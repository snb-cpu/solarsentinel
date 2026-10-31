# SolarSentinel: problem and solution in detail

Team TRUENO: Shashank P, Pratham BR, Sanjay Niranjan Balaji

## 1. Problem statement

Solar panels lose energy silently, and the people who own them find out late or never.

**Dust and soiling.** Dust, bird droppings and rain stains block sunlight. Published studies report losses from a few percent to over 25% depending on the region, and dusty, dry areas like much of India are on the bad end. The loss builds up slowly, so nobody notices it day to day.

**Hidden faults.** Shading, a failing cell, a hotspot or a micro-crack also lower output, and they look the same as dirt on a power meter. A cracked cell that overheats damages the panel permanently if nobody acts.

**Cleaning is blind.** Most plants clean on a fixed calendar. That wastes water and labour when the panel is clean or when rain is about to wash it, and it cleans too late when dust builds up fast.

**Inspection is expensive.** Finding faults means people walking the rows with a thermal camera or gun. Thermal cameras are costly, and small rooftop, school, farm and community plants cannot afford regular O&M staff.

**Water is scarce.** Washing with raw tap or borewell water is wasteful, and hard water leaves mineral spots that bake onto the glass in the sun and cut output further.

**In short:** nobody knows when a panel should be cleaned, whether the loss is dust or damage, or what the loss costs in money, and the existing ways to find out are too expensive for small installations.

## 2. Our solution

SolarSentinel is a low-cost sensor node with a cleaning system that decides for itself when washing is worth it. It watches each panel, uses machine learning to work out what is wrong, checks the weather, and cleans only when it makes economic sense.

### 2.1 Sense (hardware)
- A **grid of cheap analog temperature sensors** under the panel, placed at several points. This replaces an expensive thermal camera and gives a coarse thermal map.
- A **voltage sensor and a current sensor** to measure the panel's real power output.
- An **LDR** to measure how much sunlight is available, so we know how much power the panel should be producing.
- A **tank level** reading for the rainwater store.
- An **ESP32** reads everything every minute and sends it over Wi-Fi.

### 2.2 Understand (ML, `2-ml-ai/`)
1. **Thermal heatmap.** The model turns the temperature grid into a 2D heatmap. Dust, droppings and shadows make heat build up in patches.
2. **Dust vs real fault.** A classifier looks at the pattern and labels the panel `ok`, `dust`, `shading`, `hotspot` or `fault`.
   - Dust usually warms the grid fairly evenly and power recovers after a wash.
   - A hotspot or crack is one cell running much hotter than the rest.
   - A permanent `fault` stays hot and power never recovers after cleaning.
   - Faults are reported to a human and never trigger washing, so no water is wasted on them.
3. **Expected vs actual power.** Using the LDR reading, the model estimates what the panel should produce and compares it with what it produces. The gap is the efficiency loss.

### 2.3 Check the weather
The software reads a live weather forecast (rain probability, irradiance, temperature, wind). If dust is detected but heavy rain is forecast in the next 24 to 48 hours, cleaning is suppressed and the rain does the work for free.

### 2.4 Forecast and ROI
A regression model (LightGBM or random forest) predicts energy output over the next 7 days from weather forecasts, history and the current soiling level. The system then works out:
- rupees lost per day because of the current dust, and
- the cost of one cleaning cycle (water, air, power).

It cleans only when the loss is greater than the cost. Owners also get a clear number for their energy yield.

### 2.5 Act (cleaning loop)
When the decision is "clean now":
1. **Water flush.** A solenoid valve, switched by a relay, sends a short pulse of water through a mini pipe-irrigation line on each panel to loosen and wash off dust and stains.
2. **Air dry.** A blower then blows the remaining droplets off, so no mineral spots dry on the glass.
3. **Backup timer.** Independently of the AI, a 2-hour timer can run a cycle, and the ESP32 keeps working locally if Wi-Fi drops.

The water comes from **harvested rainwater**, so cleaning uses no mains water.

### 2.6 Show (UI, `1-ui-design/`)
A dashboard shows live voltage, current, light and tank level, the thermal heatmap, the decision card (state, loss, rupees lost per day, clean yes/no and the reason), the 7-day forecast, and the cleaning history with a manual "clean now" button.

## 3. How the parts connect

```
Sensors -> ESP32 -> MQTT -> ML (heatmap, classify, weather, forecast, ROI) -> decision
                                                                  |-> UI dashboard
                                                                  |-> command -> ESP32 -> valve + blower
```
The exact messages are in [`contract.md`](contract.md).

## 4. What makes it different
- Thermal-grid mapping from cheap sensors instead of a thermal camera.
- Tells dust apart from permanent damage, so water is never wasted on faults.
- Weather-aware: skips washing when rain is coming.
- Money-based decision: cleans only when the loss costs more than the wash.
- Rainwater plus air drying: no mains water use and no mineral spots.
- Built from low-cost parts and 3D printing, suited to Indian rooftops, farms and small plants.

## 5. Plan and status

| Part | Owner | Folder | Status |
|---|---|---|---|
| UI and pitch | Shashank | `1-ui-design/` | not started |
| ML | Pratham | `2-ml-ai/` | not started |
| Hardware and simulation | Sanjay | `3-hardware-sim/` | not started |

Results are reported honestly: accuracy on synthetic data is labelled synthetic until the real rig produces data.

## 6. Future work
Outdoor field trials, LoRa or mesh links for large plants, an optional thermal camera or dust sensor as an upgrade, and integration with cleaning robots.
