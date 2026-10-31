// All the knobs in one place. Change pins/calibration here, not in the .ino.
// Board assumed: classic ESP32 DevKit. ADC2 pins are unusable with Wi-Fi, so only ADC1 pins (32-39) are used.
#pragma once

#define PANEL_ID "P1"
#define REPORT_MS 2000UL           // send a reading every 2 s for the demo (use 60000 for a real install)
#define AUTO_CLEAN_MS 7200000UL    // backup timer: clean every 2 hours

// ---- analog inputs (ADC1) ----
#define PIN_VOLT 34                // panel voltage via resistor divider
#define PIN_CURR 35                // current sensor output
#define PIN_LDR  39                // common pin of a SECOND CD4051 (shares the select lines): 4 LDRs on channels 0..3 = top-left, top-right, bottom-left, bottom-right corners
#define LDR_COUNT 4                // corner light sensors, so a shadow or cloud is not mistaken for dirt
#define PIN_MUX  36                // CD4051 common pin -> temperature sensors 0..7
#define PIN_MUX_S0 25
#define PIN_MUX_S1 26
#define PIN_MUX_S2 27

// ---- temperature grid: sensors wired to CD4051 channels 0..N-1 ----
#define GRID_ROWS 2
#define GRID_COLS 4                // rows*cols must be <= 8 (one CD4051 mux)
// LM35 = 10 mV per deg C. Per-sensor offsets (deg C) fix sensor-to-sensor error: calibrate against a reference thermometer.
#define TEMP_MV_PER_C 10.0f
static const float TEMP_OFFSET_C[8] = {0, 0, 0, 0, 0, 0, 0, 0};

// ---- voltage sensor: Vpanel = Vadc * VOLT_DIV ----
#define VOLT_DIV 6.0f              // e.g. 50k + 10k divider = 6. Tune with a multimeter.
// ---- current sensor: I = (Vadc - CURR_ZERO_V) / CURR_V_PER_A ----
#define CURR_ZERO_V 1.65f          // sensor output at 0 A (measure it with the panel disconnected)
#define CURR_V_PER_A 0.100f        // e.g. ACS712-20A = 0.100 V/A. Check your sensor's datasheet.
// ---- LDR: lux ~ LDR_K / resistance-ish. Rough on purpose; ML only needs a monotonic light signal. ----
#define LDR_MAX_LUX 100000.0f

// ---- actuators (relay modules are usually active LOW) ----
#define PIN_VALVE 16               // solenoid valve relay
#define PIN_BLOWER 17              // blower relay
#define RELAY_ON  LOW
#define RELAY_OFF HIGH
#define MAX_WATER_MS 10000UL       // safety caps, whatever the command says
#define MAX_AIR_MS   20000UL

// ---- optional tank float switch: LOW = water present. Set to -1 if not fitted. ----
#define PIN_TANK -1

// ---- WOKWI overrides (only used when the sketch starts with #define WOKWI; the Python sim stops reading at the marker above) ----
#ifdef WOKWI
#undef PANEL_ID
#define PANEL_ID "W1"              // shows up as a 4th panel next to the simulated P1-P3
#undef GRID_ROWS
#undef GRID_COLS
#define GRID_ROWS 1
#define GRID_COLS 3                // three NTC sensors on direct pins
#undef PIN_VOLT
#undef PIN_CURR
#undef PIN_LDR
#define PIN_VOLT 34                // pot: 0-3.3 V pin -> x6 = 0-19.8 V
#define PIN_CURR 35                // pot: 1.65 V (middle) = 0 A, turn up for amps
#define PIN_LDR  39                // pot: light level (VN)
static const int WOKWI_TEMP_PINS[3] = {32, 33, 36};   // NTC sensors (VP = GPIO36)
#undef RELAY_ON
#undef RELAY_OFF
#define RELAY_ON  HIGH             // if the relay LEDs look inverted in Wokwi, swap HIGH/LOW here
#define RELAY_OFF LOW
#endif
