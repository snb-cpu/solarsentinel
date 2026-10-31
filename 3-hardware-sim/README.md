# 3-hardware-sim  (owner: Sanjay, the Mac)

- `firmware/solarsentinel/` real ESP32 firmware (compiles). Reads the panel through an **ADS1115** I2C ADC (via two **CD74HC4051E** multiplexers: 8x LM35DZ temperatures, 4x GL5528 corner LDRs), measures its own power with an **INA219**, POSTs readings, polls for clean commands, runs the water-then-air wash, refills the tank from the tap when low, and **sleeps at night and in rain**. Exact parts: [`../docs/COMPONENTS.md`](../docs/COMPONENTS.md). Design: [`../docs/POWER-AND-WATER.md`](../docs/POWER-AND-WATER.md).
- `sim/virtual_node.py` the virtual panels + ESP32s: sun cycle, clouds, dust, rain, heat, faults, a 20 L tank with rain and tap inlets, plus a port of the firmware logic using the same constants (read from `config.h`) and imperfect "hardware" (ADS1115 counts and noise, divider error, sensor error, ultrasonic noise).
- `sim/console.html` the hardware view at http://localhost:8100 (or `https://solarsentinel-hw.pages.dev` once deployed): one drawing of the water side (rain gutter, tap, tank with its sensor and floats, both valves, spray pipe, the panel with its four light sensors, the blower), one of the electronics (sensors, multiplexers, ADS1115, INA219, load switch, ESP32 pins, relay module), a sentence saying what it is doing right now, the firmware loop with the running line highlighted, the wash and power-mode state machines, the day-only power meter, the live ADS1115 table, and the trouble buttons (cloud, bird, shade, hotspot, cracked cell, drain the tank, rain, skip to dusk/night/morning). Styles and scripts are in `../shared/`.
- `sim/world.py` the physics: per-cell heat balance, mismatch hotspots, bird droppings that need extra water, sensors that lag the cells, spray cooling, rain washing, tank and water accounting, and an energy ledger that compares the cleaned panel with a never-cleaned copy.
- `sim/test_node.py` self-checks for the tap refill and the day-only sleep logic. `sim/sim.py` is the older simple generator.
- The simulator talks to the API once a second on its own thread (`POST /api/sync`), so a slow network never slows the physics, and it starts the day with the panels already warm. Time scale: `--speed N` or the Time buttons (pause, 1x, 10x, 60x, 120x, 300x, 1200x), plus "skip to" buttons that fast-forward with all the logic running. At 120x one real second is 2 simulated minutes and a day passes in 12 minutes.
- `wokwi/` the same firmware inside Wokwi, with relays and LEDs ([`wokwi/README.md`](wokwi/README.md)).
- `WIRING.md` pins, I2C addresses, ADS1115 channels, the switched sensor rail, calibration, safety, flashing.

```
python3 sim/virtual_node.py --api http://localhost:8000                         # 3 panels; hardware view and controls: http://localhost:8100
python3 sim/virtual_node.py --api https://solarsentinel-api.pages.dev            # or through Cloudflare (docs/RUN.md)
python3 sim/test_node.py                                    # 10 checks
```
Branch: `hw/sanjay`.
