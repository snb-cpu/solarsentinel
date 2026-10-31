# Components: the exact parts

One node per panel. Every part below is a real, common part; the firmware (`3-hardware-sim/firmware/solarsentinel/`) and the simulator are written for exactly these. Pins and I2C addresses are in [`3-hardware-sim/WIRING.md`](../3-hardware-sim/WIRING.md).

## Which parts are I2C, and which are not

| Part | Bus | Address | What it does |
|---|---|---|---|
| **ADS1115** (Texas Instruments) | I2C | **0x48** | 16-bit, 4-channel analog-to-digital converter. Reads every analog sensor on the node |
| **INA219** (Texas Instruments) | I2C | **0x40** | Measures the node's own voltage, current and power on the 12 V battery rail |
| **CD74HC4051E** (Texas Instruments) x2 | not I2C | none (3 select pins) | 8-channel analog multiplexer. Turns one ADS1115 input into 8 temperature inputs, and another into 4 light inputs. Controlled by GPIO25/26/27 |

The multiplexers are plain logic chips with three select pins, not I2C devices. The I2C devices are the ADS1115 and the INA219, on one two-wire bus (SDA GPIO21, SCL GPIO22).

## Why the ADS1115 (and not the ESP32's own ADC)
The panel's hot-spot detection works on differences of a few degrees between temperature sensors. The ESP32's built-in 12-bit ADC is nonlinear and noisy (errors of tens of millivolts, which is several degrees on an LM35), and half its pins stop working when Wi-Fi is on. The ADS1115 gives 16 bits, a programmable gain (62.5 microvolts per count for the temperatures, which is 0.006 degrees C per count), and frees all the GPIO pins. One ADS1115 reads everything on the node because the multiplexers fan its inputs out.

## Bill of materials, one node

| # | Function | Part | Qty | Notes |
|---|---|---|---|---|
| 1 | Controller | **DFRobot FireBeetle ESP32 (DFR0478)**, an ESP32-WROOM-32 board | 1 | About 10 microamps in deep sleep. A generic ESP32 DevKit (DOIT V1, DevKitC) works for the demo, but its USB-serial chip and regulator draw several milliamps even asleep, which would eat the saving |
| 2 | I2C ADC | **ADS1115** 16-bit ADC module (TI ADS1115IDGSR) | 1 | Address 0x48 (ADDR to GND). Powered from 3.3 V. Inputs must stay between 0 and 3.3 V |
| 3 | Node power monitor | **INA219** I2C current/power monitor module (TI INA219) with the on-board 0.1 ohm shunt | 1 | Address 0x40. On the 12 V battery rail, so it counts the valves and blower as well as the electronics. Up to 3.2 A |
| 4 | Analog multiplexer | **CD74HC4051E** (TI, DIP-16) | 2 | Powered from 3.3 V. #1: eight temperature sensors. #2: four LDRs. Select pins S0-S2 wired to both |
| 5 | Panel temperature | **LM35DZ** (TI, TO-92), 10 mV per degree C | 8 | Glued to the back sheet in a 2 x 4 grid. Needs 4 V or more, so on the 5 V rail. Each output through 1 kohm and 100 nF to the multiplexer. Range 0 to 100 degrees C |
| 6 | Corner light | **GL5528** LDR + 10 kohm 1% resistor, as a divider on 3.3 V | 4 | One at each corner of the panel, flat, facing the sun. Catches shadows and clouds |
| 7 | Panel voltage | Resistor divider **56 kohm + 10 kohm (1%)**, 100 nF, **BZX55C3V3** 3.3 V zener across the 10 kohm | 1 set | Ratio 6.6, handles an open-circuit voltage up to about 21 V |
| 8 | Panel current | **ACS712ELCTR-20A-T** (Allegro) module, 100 mV per amp | 1 | 5 V part, output 2.5 V at zero, wired straight to the ADS1115. Use the 5 A version (185 mV/A) for a panel under about 40 W |
| 9 | Tank level | **JSN-SR04T-2.0** waterproof ultrasonic module | 1 | On the tank lid, 30 cm above the full line. Its 5 V echo goes through a 1 kohm / 2 kohm divider |
| 10 | Tank limits | **PP vertical float switch**, normally open | 2 | One near the bottom (dry-run protection), one near the top (overflow protection). Closed to GND when the water is above them |
| 11 | Rain | **FC-37 / YL-83** rain sensor with the LM393 board | 1 | Next to the panel. Digital output goes LOW when wet |
| 12 | Switching 5 V loads | **TPS22918** load switch (TI) on a SOT-23-6 breakout (or an AO3401A P-MOSFET + 2N7002 pair) | 1 | Turns the whole 5 V sensor rail off while the ESP32 sleeps. ON pin from GPIO23, 100 kohm pull-down |
| 13 | Relays | **4-channel 5 V relay module, SRD-05VDC-SL-C**, opto-isolated, active LOW | 1 | K1 spray valve, K2 tap valve, K3 blower, K4 spare. Logic supply on the switched rail |
| 14 | Valves | **12 V DC normally-closed solenoid valve, 1/2 inch**, plastic | 2 | Spray valve (tank to spray pipe) and tap inlet valve (tap to tank). About 4 to 6 W each when open |
| 15 | Air | **12 V 5015 centrifugal blower** | 1 | Dries the glass after the wash. Under 3 W |
| 16 | Flyback diodes | **1N4007** | 3 | Across each valve and the blower |
| 17 | Spray pipe | Drip or mini-sprinkler line with 4 nozzles | 1 | Along the top edge of each panel, fed by the spray valve |
| 18 | Tank | 20 L food-grade tank with lid and overflow pipe | 1 | Rain gutter into the top, tap inlet through an air gap, outlet at the bottom |
| 19 | Power | 12 V battery + solar charge controller, **MP1584EN** buck module (12 V to 5 V) | 1 set | The node runs from the solar system it looks after. The buck module's own idle current matters: pick a low-quiescent one |

## Plumbing and safety notes
- **Gravity or pump:** mount the tank above the panel's top edge so the spray is gravity fed, or add a 12 V diaphragm pump after the spray valve.
- **Air gap on the tap inlet:** the tap pipe must end above the tank's water level, never under it, so tank water can never flow back into the mains.
- **Overflow:** the tank has an overflow pipe, and the high float closes the tap valve even if the ultrasonic sensor is wrong.
- **Mains side:** all valves are 12 V DC, so there is no mains wiring on the node.

## What changed from the first sketch
- The multiplexers were written as "CD4051". They are now the **CD74HC4051E** (the HC version works properly at 3.3 V).
- The sensors are no longer read by the ESP32's own ADC. They go through the **ADS1115** over I2C.
- Added: the **INA219** (node power), the **JSN-SR04T-2.0** and two floats (tank), the **FC-37** (rain), the **TPS22918** (sensor rail switch) and a third relay for the tap valve.
- The servo wiper was dropped from the build (water and air do the cleaning).
