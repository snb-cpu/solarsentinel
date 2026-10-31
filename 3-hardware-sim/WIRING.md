# Wiring and build notes (ESP32-WROOM-32: DFRobot FireBeetle ESP32 or a classic DevKit)

Pins live in `firmware/solarsentinel/config.h`. The exact parts are listed in [`../docs/COMPONENTS.md`](../docs/COMPONENTS.md).

## Pin table

| Function | GPIO | Connected to |
|---|---|---|
| I2C SDA | 21 | ADS1115 (0x48) and INA219 (0x40) |
| I2C SCL | 22 | ADS1115 and INA219 |
| Multiplexer select S0, S1, S2 | 25, 26, 27 | both CD74HC4051E chips, pins 11, 10, 9 |
| Sensor rail switch | 23 | TPS22918 ON pin (100 kohm pull-down). High = the 5 V sensor rail is on |
| Relay K1, spray valve | 16 | relay module IN1 |
| Relay K2, tap inlet valve | 17 | relay module IN2 |
| Relay K3, blower | 18 | relay module IN3 |
| Tank ultrasonic TRIG | 4 | JSN-SR04T-2.0 |
| Tank ultrasonic ECHO | 5 | JSN-SR04T-2.0, through a 1 kohm / 2 kohm divider (the echo is 5 V) |
| Float switch, low | 32 | to GND when the water is above it (internal pull-up) |
| Float switch, high | 33 | to GND when the water is above it (internal pull-up) |
| Rain sensor DO | 34 | FC-37 board (input-only pin) |

## ADS1115 channels (all single-ended, 0 to 3.3 V)

| Input | Source | Gain | Resolution |
|---|---|---|---|
| A0 | CD74HC4051E #1 common pin: 8x LM35DZ on channels 0..7 | +-2.048 V | 62.5 microvolts, 0.006 C |
| A1 | CD74HC4051E #2 common pin: 4x GL5528 LDR on channels 0..3 (top-left, top-right, bottom-left, bottom-right) | +-4.096 V | 125 microvolts |
| A2 | panel voltage divider, 56 kohm + 10 kohm | +-4.096 V | 125 microvolts |
| A3 | ACS712ELCTR-20A-T output | +-4.096 V | 125 microvolts |

Both multiplexers share S0-S2, so reading "temperature 3" and "light 3" use the same select value. Put a 1 kohm resistor and 100 nF capacitor between each LM35DZ output and its multiplexer channel, and wait 2 ms after changing the select lines.

## The 5 V sensor rail (what is switched off while it sleeps)
The TPS22918 load switch feeds: the eight LM35DZ, the ACS712, the JSN-SR04T, the FC-37 and the relay module's logic side. While the ESP32 is in deep sleep, GPIO23 is held low (`gpio_hold_en`), so none of them draw anything. The ADS1115 and INA219 stay on 3.3 V; they power down on their own between readings (about half a microamp).

## Why four light sensors
If the only light sensor sits in one corner, a shadow or passing cloud on the rest of the panel looks like dirt (power drops, light reading does not). With one LDR at each corner the system sees when light is uneven (a shadow or cloud: no wash) and averages them for the expected power. Mount them flat, at the panel corners, facing the sun like the glass, not behind the frame.

## Calibrate (the part that makes real readings right)
1. **Voltage:** compare against a multimeter and adjust `VOLT_DIV` (nominal 6.6).
2. **Current:** with the panel disconnected, read the ACS712 output and set `CURR_ZERO_V` (nominal 2.5). Check `CURR_V_PER_A` against the datasheet and a known load.
3. **Temperature:** put all eight LM35DZ in the same room, compare each with a reference thermometer, set `TEMP_OFFSET_C[]`.
4. **Light:** compare the four LDRs under one lamp; scale `LDR_MAX_LUX` against a lux meter or a phone.
5. **Tank:** set `TANK_EMPTY_CM` and `TANK_FULL_CM` by measuring the distance from the sensor to the water when the tank is empty and full.
6. **Power:** check the INA219 reading against a multimeter in series with the battery.

## Safety (read before powering)
- Every valve is inductive: put a 1N4007 across each one (stripe toward +12 V). Without it the relay contacts and the module suffer.
- The panel's open-circuit voltage is higher than its working voltage. The divider is sized for about 21 V.
- Keep the 12 V and the water away from the ESP32 and breadboard. The relay module isolates the signal only.
- The tap pipe must end above the tank's water level (air gap) so tank water can never flow back into the mains.
- The firmware caps spray at 10 s and air at 20 s, closes the tap after 3 minutes whatever the sensor says, and has every output off at boot.

## Build and flash
```
cd firmware
cp solarsentinel/secrets.example.h solarsentinel/secrets.h    # edit Wi-Fi and the API address
arduino-cli compile --fqbn esp32:esp32:esp32 solarsentinel
arduino-cli upload  --fqbn esp32:esp32:esp32 -p /dev/cu.usbserial-XXXX solarsentinel
arduino-cli monitor -p /dev/cu.usbserial-XXXX -c baudrate=115200
```
No extra Arduino libraries are needed: the ADS1115 and INA219 are driven directly over `Wire`. The reading has no timestamp because the ESP32 has no clock; the API stamps `ts` when it arrives.

## Simulator (no hardware)
```
python3 sim/virtual_node.py --api http://localhost:8000     # the full virtual node and hardware view at http://localhost:8100
python3 sim/test_node.py                                     # self-checks for the tap refill and the day-only sleep logic
python3 sim/sim.py --scenario dust                           # the older, simpler reading generator
```
