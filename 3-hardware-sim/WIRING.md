# Wiring and build notes (classic ESP32 DevKit)

Pins live in `firmware/solarsentinel/config.h`. Change them there if your board differs.

| What | Pin | Notes |
|---|---|---|
| Panel voltage | GPIO34 | Resistor divider, ratio `VOLT_DIV`. Keep the pin under 3.3 V at the panel's open-circuit voltage |
| Current sensor out | GPIO35 | Zero-current output measured and set in `CURR_ZERO_V` |
| 4 corner LDRs | GPIO39 | Second CD4051, common pin to GPIO39, channels 0..3 = top-left, top-right, bottom-left, bottom-right corner of the panel. Each LDR in a divider with a fixed resistor, LDR on the 3.3 V side. Select lines S0/S1/S2 (GPIO25/26/27) are shared with the temperature mux |
| Temp mux common | GPIO36 | CD4051 pin 3. Temp sensors on channels 0..5 |
| Mux select A,B,C | GPIO25, 26, 27 | CD4051 pins 11, 10, 9 |
| Valve relay | GPIO16 | Drives the 12 V solenoid |
| Blower relay | GPIO17 | Drives the blower |
| Tank float switch (optional) | set `PIN_TANK` | Float switch to GND, internal pull-up |

Why a mux: the ESP32's usable ADC pins are few (ADC2 does not work with Wi-Fi), and a 2x3 temperature grid plus voltage, current and light would run out of pins. A CD4051 turns one pin into 8 temperature inputs.

## Why four light sensors
If the only light sensor sits in one corner, a shadow or passing cloud on the rest of the panel looks like dirt (power drops, light reading does not). With one LDR at each corner the system sees when light is uneven (a shadow or cloud: no wash) and averages them for the expected power. Mount them flat, at the panel corners, facing the sun like the glass, not behind the frame.

## Parts to have on the bench
ESP32 DevKit, 2x CD4051 (one for temperatures, one for the 4 light sensors), 4 LDRs + 4 fixed resistors, 6 analog temperature sensors (LM35 assumed; if NTC, tell me and the conversion changes), voltage divider resistors, current sensor, LDR + resistor, 2-channel relay module, 12 V solenoid valve, blower, 12 V supply, 1N4007 diode across the solenoid.

## Safety (read before powering)
- Solenoid is inductive: put a 1N4007 diode across it (stripe toward +12 V). Without it the relay and ESP32 can be damaged.
- Keep the 12 V supply and the water side away from the ESP32 and breadboard. Relays isolate the signal only.
- The panel's open-circuit voltage is higher than its working voltage. Size the divider for the open-circuit value.
- Firmware caps water at 10 s and air at 20 s, and both relays are off at boot.

## Calibrate (the part that makes real readings right)
1. Voltage: compare against a multimeter, adjust `VOLT_DIV`.
2. Current: with the panel disconnected, read the output voltage and set `CURR_ZERO_V`. Check `CURR_V_PER_A` against the datasheet and a known load.
3. Temperature: put all sensors in the same room, compare with a reference thermometer, set `TEMP_OFFSET_C[]`.

## Build and flash
```
cd firmware
cp solarsentinel/secrets.example.h solarsentinel/secrets.h    # edit Wi-Fi + broker IP
arduino-cli compile --fqbn esp32:esp32:esp32 solarsentinel
arduino-cli upload  --fqbn esp32:esp32:esp32 -p /dev/cu.usbserial-XXXX solarsentinel
arduino-cli monitor -p /dev/cu.usbserial-XXXX -c baudrate=115200
```
The reading has no timestamp because the ESP32 has no clock. The ML side stamps `ts` when it receives it.

## Simulator (no hardware)
```
python3 sim/sim.py --scenario dust            # prints readings; type "clean" + Enter to wash
python3 sim/sim.py --scenario hotspot --mqtt localhost
python3 sim/test_sim.py                       # self-check
```
