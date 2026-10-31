// All the knobs in one place. Change pins/calibration here, not in the .ino.
// Board assumed: classic ESP32 DevKit. ADC2 pins are unusable with Wi-Fi, so only ADC1 pins (32-39) are used.
#pragma once

#define PANEL_ID "P1"
#define REPORT_MS 60000UL          // send a reading every 60 s
#define AUTO_CLEAN_MS 7200000UL    // backup timer: clean every 2 hours

// ---- analog inputs (ADC1) ----
#define PIN_VOLT 34                // panel voltage via resistor divider
#define PIN_CURR 35                // current sensor output
#define PIN_LDR  32                // LDR in a divider with a fixed resistor
#define PIN_MUX  36                // CD4051 common pin -> temperature sensors 0..7
#define PIN_MUX_S0 25
#define PIN_MUX_S1 26
#define PIN_MUX_S2 27

// ---- temperature grid: sensors wired to CD4051 channels 0..N-1 ----
#define GRID_ROWS 2
#define GRID_COLS 3                // rows*cols must be <= 8
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
