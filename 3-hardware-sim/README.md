# 3-hardware-sim  (owner: Sanjay)

- `firmware/solarsentinel/` ESP32 firmware (compiles clean). Reads V, I, light and a temperature grid, publishes MQTT readings, runs the water-then-air cleaning cycle on command and on a 2-hour backup timer.
- `sim/` fake node that emits the same readings, so Pratham and Shashank can build without hardware.
- `WIRING.md` pins, parts, safety, calibration, flash steps.

Branch: `hw/sanjay`. Final integration on the Mac.
