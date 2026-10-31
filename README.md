# 3-hardware-sim  (owner: Sanjay, laptop A)

- `firmware/solarsentinel/` real ESP32 firmware (compiles). Reads V, I, light and the temperature grid, POSTs readings, polls for clean commands, runs the water-then-air cycle, 2-hour backup timer.
- `sim/virtual_node.py` the virtual panel + ESP32: sun cycle, clouds, dust, rain, heat, faults, water tank, plus a port of the firmware logic using the same constants (read from `config.h`) and imperfect "hardware" (ADC noise, divider error, sensor error).
- `sim/world.py` the physics.
- `sim/sim.py` older simple generator, still handy for quick tests.
- `WIRING.md` pins, parts, safety, calibration, flash.

```
python3 sim/virtual_node.py --api http://<PRATHAM-IP>:8000     # operator console: http://localhost:8100
```
Branch: `hw/sanjay`.
