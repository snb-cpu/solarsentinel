// All the knobs in one place. Change pins/calibration here, not in the .ino.
// Parts are listed with datasheet names in docs/COMPONENTS.md:
//   ESP32 (DFRobot FireBeetle ESP32 DFR0478, or any ESP32-WROOM-32 board)   ADS1115 16-bit I2C ADC (0x48)   INA219 I2C power monitor (0x40)
//   2x CD74HC4051E analog multiplexer   8x LM35DZ   4x GL5528 LDR   ACS712ELCTR-20A-T   JSN-SR04T-2.0 ultrasonic   2x float switch
//   FC-37 rain sensor   4-channel SRD-05VDC relay module   TPS22918 load switch   2x 12 V NC solenoid valve   12 V 5015 blower
#pragma once

#define PANEL_ID "P1"
#define REPORT_MS 2000UL           // send a reading every 2 s for the demo (use 60000 for a real install)
#define AUTO_CLEAN_MS 7200000UL    // backup timer: clean every 2 hours (only while awake, so only in daylight)

// ---- I2C bus: ADS1115 ADC + INA219 power monitor ----
#define PIN_SDA 21
#define PIN_SCL 22
#define ADS_ADDR 0x48              // ADS1115, ADDR pin to GND
#define INA_ADDR 0x40              // INA219, A0 and A1 to GND
#define ADS_CH_TEMP 0              // ADS1115 A0 <- common pin of CD74HC4051E #1 (8x LM35DZ temperature sensors)
#define ADS_CH_LDR  1              // ADS1115 A1 <- common pin of CD74HC4051E #2 (4x GL5528 LDR: top-left, top-right, bottom-left, bottom-right)
#define ADS_CH_VOLT 2              // ADS1115 A2 <- panel voltage divider
#define ADS_CH_CURR 3              // ADS1115 A3 <- ACS712 output
#define ADS_PGA_TEMP 2             // gain code 2 = +-2.048 V, 62.5 uV per count (0.006 C per count on an LM35)
#define ADS_PGA_WIDE 1             // gain code 1 = +-4.096 V, 125 uV per count (inputs never go above 3.3 V)
#define ADS_SAMPLES 4              // readings averaged per value (860 samples per second, about 2 ms each)
#define LDR_COUNT 4                // corner light sensors, so a shadow or cloud is not mistaken for dirt
#define PIN_MUX_S0 25              // select lines shared by both CD74HC4051E multiplexers
#define PIN_MUX_S1 26
#define PIN_MUX_S2 27

// ---- temperature grid: LM35DZ sensors wired to multiplexer #1 channels 0..N-1 ----
#define GRID_ROWS 2
#define GRID_COLS 4                // rows*cols must be <= 8 (one CD74HC4051E)
// LM35DZ = 10 mV per deg C. Per-sensor offsets (deg C) fix sensor-to-sensor error: calibrate against a reference thermometer.
#define TEMP_MV_PER_C 10.0f
static const float TEMP_OFFSET_C[8] = {0, 0, 0, 0, 0, 0, 0, 0};

// ---- voltage sensor: 56 kOhm + 10 kOhm (1%) divider, 3.3 V zener across the 10 kOhm. Vpanel = Vadc * VOLT_DIV ----
#define VOLT_DIV 6.6f              // (56k + 10k) / 10k. Tune with a multimeter.
// ---- current sensor: ACS712ELCTR-20A-T on 5 V, output wired straight to the ADS1115. I = (Vadc - CURR_ZERO_V) / CURR_V_PER_A ----
#define CURR_ZERO_V 2.5f           // output at 0 A is half the 5 V supply (measure it with the panel disconnected)
#define CURR_V_PER_A 0.100f        // 100 mV per A for the 20 A part (185 mV/A for the 5 A part: use that for a small panel)
// ---- LDR: GL5528 + 10 kOhm divider. Rough linear mapping on purpose; the ML only needs a monotonic light signal, so calibrate against a lux meter. ----
#define LDR_MAX_LUX 100000.0f

// ---- 4-channel SRD-05VDC relay module (active LOW). Its logic supply is on the switched sensor rail, so everything is off while asleep ----
#define PIN_SPRAY  16              // relay 1: 12 V solenoid valve, tank -> spray pipe on the panel
#define PIN_TAP    17              // relay 2: 12 V solenoid valve, tap water -> tank inlet
#define PIN_BLOWER 18              // relay 3: 12 V 5015 blower
#define RELAY_ON  LOW
#define RELAY_OFF HIGH
#define MAX_WATER_MS 10000UL       // safety caps, whatever the command says
#define MAX_AIR_MS   20000UL

// ---- water tank: JSN-SR04T-2.0 ultrasonic on the lid + two float switches (closed to GND when the water is above them; -1 = not fitted) ----
#define PIN_TRIG 4
#define PIN_ECHO 5                 // 5 V echo through a 1k/2k divider
#define PIN_FLOAT_LOW  32          // below this float the tank is nearly empty (dry-run protection)
#define PIN_FLOAT_HIGH 33          // above this float the tank is full (overflow protection)
#define TANK_EMPTY_CM 60.0f        // sensor to water surface when the tank is empty
#define TANK_FULL_CM  30.0f        // ...and when it is full (the sensor cannot read closer than 25 cm)
// Tap water is a back-up for rainwater. Refill when low, stop when full, never run unattended for long.
#define TANK_LOW_PCT 25            // open the tap inlet below this (unless the API says rain is coming)
#define TANK_CRITICAL_PCT 10       // below this the tap opens even if rain is coming
#define TANK_FULL_PCT 85           // close the tap inlet at this level
#define MIN_WASH_PCT 8             // never start a wash with less water than this
#define TAP_MAX_MS 180000UL        // close the tap after 3 minutes whatever the sensor says (stuck sensor, leak)
#define TAP_LOCKOUT_MS 600000UL    // and do not try again for 10 minutes

// ---- rain sensor: FC-37 / YL-83 board with LM393, digital output goes LOW when wet ----
#define PIN_RAIN 34                // input-only pin

// ---- power: the node must not eat the energy it saves. Daylight only; deep sleep at night and in rain ----
#define ENABLE_SLEEP 1
#define PIN_SENSOR_PWR 23          // TPS22918 load switch ON pin: switches the 5 V rail for LM35s, ACS712, JSN-SR04T, FC-37, relay module logic (100k pull-down)
#define SENSOR_SETTLE_MS 30        // wait this long after switching the sensor rail on
#define DAY_LUX_ON  22000.0f       // wake up and work above this average light level
#define DAY_LUX_OFF 18000.0f       // go to sleep below this (the gap stops it flapping at dawn and dusk)
#define SLEEP_NIGHT_S 1200         // while it is dark, wake every 20 minutes just to look at the sun (no Wi-Fi)
#define SLEEP_RAIN_S 600           // while it rains, look every 10 minutes
#define SLEEP_AFTER_REPORTS 3      // dark or wet for this many reports in a row before sleeping
#define INA_SHUNT_OHM 0.1f         // INA219 module shunt (R100); it measures the whole node on the 12 V battery rail
#define SLEEP_POWER_MW 1.3f        // what the node draws asleep (buck converter quiescent current dominates); used to keep the energy count honest

// ---- WOKWI overrides (only used when the sketch starts with #define WOKWI; the Python sim stops reading at the marker above) ----
#ifdef WOKWI
#undef PANEL_ID
#define PANEL_ID "W1"              // shows up as a 4th panel next to the simulated P1-P3
#undef GRID_ROWS
#undef GRID_COLS
#define GRID_ROWS 1
#define GRID_COLS 3                // three NTC sensors on direct pins
#undef VOLT_DIV
#undef CURR_ZERO_V
#define VOLT_DIV 6.0f              // Wokwi pot: 0-3.3 V pin -> x6 = 0-19.8 V
#define CURR_ZERO_V 1.65f          // Wokwi pot: 1.65 V (middle) = 0 A, turn up for amps
#define WOKWI_PIN_VOLT 34
#define WOKWI_PIN_CURR 35
#define WOKWI_PIN_LDR  39          // pot: light level (VN), one dial stands for all four corners
static const int WOKWI_TEMP_PINS[3] = {32, 33, 36};   // NTC sensors (VP = GPIO36)
#undef RELAY_ON
#undef RELAY_OFF
#define RELAY_ON  HIGH             // if the relay LEDs look inverted in Wokwi, swap HIGH/LOW here
#define RELAY_OFF LOW
#undef PIN_TRIG                    // no ultrasonic in Wokwi: two push buttons act as the float switches
#define PIN_TRIG -1
#undef PIN_FLOAT_LOW
#undef PIN_FLOAT_HIGH
#define PIN_FLOAT_LOW  26          // button held = water above the low float
#define PIN_FLOAT_HIGH 27          // button held = water above the high float
#undef PIN_RAIN
#define PIN_RAIN 25                // slide switch to GND = raining
#undef PIN_SENSOR_PWR
#define PIN_SENSOR_PWR -1
#undef ENABLE_SLEEP
#define ENABLE_SLEEP 0             // keep the demo running; the serial log says when it would sleep
#endif
