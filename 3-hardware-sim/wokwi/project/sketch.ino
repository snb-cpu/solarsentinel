#define WOKWI 1
// SolarSentinel node (ESP32).
// Day-only: it works while the sun is up and it is not raining, and deep-sleeps otherwise, so the node never eats the energy it saves.
// While awake: read sensors -> POST reading to the API, poll for clean commands, run the water-then-air wash, refill the tank from the tap when low.
// JSON is defined in docs/contract.md. virtual_node.py is a line-for-line port of this file.
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <Wire.h>
#include <esp_sleep.h>
#include "driver/gpio.h"
#include "config.h"
#include "secrets.h"

// ---------- state that survives deep sleep ----------
RTC_DATA_ATTR bool wasDay = false;       // for the dawn/dusk hysteresis
RTC_DATA_ATTR float nodeWh = 0;          // energy the node itself has used, from the INA219 plus an estimate while asleep
RTC_DATA_ATTR float tapOpenS = 0;        // seconds the tap inlet valve has been open (tap litres = this x the valve flow)
RTC_DATA_ATTR float sprayS = 0;          // seconds the spray valve has been open

enum CleanState { IDLE, WATER, AIR };
CleanState cs = IDLE;
uint32_t csStart = 0, waterMs = 0, airMs = 0, lastClean = 0;
bool tapOpen = false, tapHold = false;   // tapHold: the API says rain is coming, so do not buy tap water yet
uint32_t tapStart = 0, tapLockUntil = 0;
float tankPct = -1;                      // -1 = unknown
float lastLux = 0; bool lastWet = false;
uint32_t lastEnergyMs = 0;

// ---------- http (plain for the LAN, TLS for a tunnel URL like https://xxxx.trycloudflare.com) ----------
WiFiClientSecure tlsClient; WiFiClient plainClient;
bool httpBegin(HTTPClient& http, const String& path) {
  String url = String(API_URL) + path;
  if (url.startsWith("https")) { tlsClient.setInsecure(); return http.begin(tlsClient, url); }   // demo: no certificate check
  return http.begin(plainClient, url);
}

// ---------- outputs ----------
void relay(int pin, bool on) { digitalWrite(pin, on ? RELAY_ON : RELAY_OFF); }
void setSpray(bool on)  { relay(PIN_SPRAY, on); }
void setBlower(bool on) { relay(PIN_BLOWER, on); }
void setTap(bool on)    { relay(PIN_TAP, on); }

// ---------- the 5 V sensor rail (TPS22918 load switch): off while asleep ----------
void sensorsOn() {
  if (PIN_SENSOR_PWR < 0) return;
  gpio_hold_dis((gpio_num_t)PIN_SENSOR_PWR);
  pinMode(PIN_SENSOR_PWR, OUTPUT); digitalWrite(PIN_SENSOR_PWR, HIGH);
  delay(SENSOR_SETTLE_MS);
}
void sensorsOff() {
  if (PIN_SENSOR_PWR < 0) return;
  digitalWrite(PIN_SENSOR_PWR, LOW);
  gpio_hold_en((gpio_num_t)PIN_SENSOR_PWR); gpio_deep_sleep_hold_en();   // keep it off while the ESP32 sleeps
}

// ---------- sensors ----------
#ifndef WOKWI
// ADS1115: single-shot read of one input at 860 samples per second. The ESP32's own ADC is too noisy to tell a 3 C hot spot from nothing.
int16_t adsRaw(uint8_t ch, uint8_t pga) {
  uint16_t cfg = 0x8000 | ((4 + ch) << 12) | (pga << 9) | 0x0100 | (0x7 << 5) | 0x0003;   // start, input chN vs GND, gain, single-shot, 860 SPS, comparator off
  Wire.beginTransmission(ADS_ADDR); Wire.write(0x01); Wire.write(cfg >> 8); Wire.write(cfg & 0xFF); Wire.endTransmission();
  delay(2);                                                                                // conversion takes about 1.2 ms
  Wire.beginTransmission(ADS_ADDR); Wire.write(0x00); Wire.endTransmission();
  Wire.requestFrom((uint8_t)ADS_ADDR, (uint8_t)2);
  int16_t hi = Wire.read(); return (hi << 8) | Wire.read();
}
float adsVolts(uint8_t ch, uint8_t pga) {
  static const float LSB[3] = {187.5e-6f, 125e-6f, 62.5e-6f};   // volts per count for gain codes 0, 1, 2
  long sum = 0;
  for (int i = 0; i < ADS_SAMPLES; i++) sum += adsRaw(ch, pga);
  return sum / (float)ADS_SAMPLES * LSB[pga];
}
void muxSelect(int k) {              // both CD74HC4051E chips share the select lines
  digitalWrite(PIN_MUX_S0, k & 1); digitalWrite(PIN_MUX_S1, (k >> 1) & 1); digitalWrite(PIN_MUX_S2, (k >> 2) & 1);
  delay(2);                          // settle through the 1 kOhm / 100 nF filter
}
float readTempC(int ch)  { muxSelect(ch); return adsVolts(ADS_CH_TEMP, ADS_PGA_TEMP) * 1000.0f / TEMP_MV_PER_C + TEMP_OFFSET_C[ch]; }
float readLdrLux(int k)  { muxSelect(k);  return adsVolts(ADS_CH_LDR, ADS_PGA_WIDE) / 3.3f * LDR_MAX_LUX; }   // more light -> higher voltage (LDR on the 3.3 V side)
float readPanelV()       { return adsVolts(ADS_CH_VOLT, ADS_PGA_WIDE) * VOLT_DIV; }
float readPanelA()       { float a = (adsVolts(ADS_CH_CURR, ADS_PGA_WIDE) - CURR_ZERO_V) / CURR_V_PER_A; return a < 0 ? 0 : a; }
// INA219 on the 12 V battery rail: how much the whole node is drawing right now (milliwatts)
uint16_t inaRead(uint8_t reg) {
  Wire.beginTransmission(INA_ADDR); Wire.write(reg); Wire.endTransmission();
  Wire.requestFrom((uint8_t)INA_ADDR, (uint8_t)2);
  uint16_t hi = Wire.read(); return (hi << 8) | Wire.read();
}
float nodeMilliwatts() {
  float amps = (int16_t)inaRead(0x01) * 10e-6f / INA_SHUNT_OHM;   // shunt voltage register: 10 uV per count
  float volts = (inaRead(0x02) >> 3) * 0.004f;                    // bus voltage register: 4 mV per count
  return volts * amps * 1000.0f;
}
#else                                // ---- Wokwi: pots for V/I/light, NTC thermistors on direct pins, no ADS1115, no INA219 ----
float adcRaw(int pin) { uint32_t t = 0; for (int i = 0; i < 16; i++) t += analogRead(pin); return t / 16.0f; }
float adcVolts(int pin) { return adcRaw(pin) / 4095.0f * 3.3f; }
float readTempC(int ch) {            // Wokwi NTC module (beta 3950), as in the Wokwi docs
  float raw = adcRaw(WOKWI_TEMP_PINS[ch]);
  if (raw < 1) raw = 1; if (raw > 4094) raw = 4094;
  return 1.0f / (log(1.0f / (4095.0f / raw - 1.0f)) / 3950.0f + 1.0f / 298.15f) - 273.15f + TEMP_OFFSET_C[ch];
}
float readLdrLux(int k)  { return adcVolts(WOKWI_PIN_LDR) / 3.3f * LDR_MAX_LUX; }
float readPanelV()       { return adcVolts(WOKWI_PIN_VOLT) * VOLT_DIV; }
float readPanelA()       { float a = (adcVolts(WOKWI_PIN_CURR) - CURR_ZERO_V) / CURR_V_PER_A; return a < 0 ? 0 : a; }
float nodeMilliwatts()   { return 0; }
#endif
float readLuxAvg() { float s = 0; for (int k = 0; k < LDR_COUNT; k++) s += readLdrLux(k); return s / LDR_COUNT; }
bool rainingNow()  { return PIN_RAIN >= 0 && digitalRead(PIN_RAIN) == LOW; }            // FC-37: LOW = wet
bool isDaylight(float lux) { return wasDay ? lux >= DAY_LUX_OFF : lux >= DAY_LUX_ON; }  // hysteresis so dawn and dusk do not flap

// Tank level from the JSN-SR04T ultrasonic sensor (median of three pings), corrected by the float switches. -1 = no idea.
float readTankPct() {
  float pct = -1;
  if (PIN_TRIG >= 0) {
    float d[3];
    for (int i = 0; i < 3; i++) {
      digitalWrite(PIN_TRIG, LOW); delayMicroseconds(2);
      digitalWrite(PIN_TRIG, HIGH); delayMicroseconds(10); digitalWrite(PIN_TRIG, LOW);
      long us = pulseIn(PIN_ECHO, HIGH, 30000);
      d[i] = us ? us / 58.0f : 0; delay(30);
    }
    float m = max(min(d[0], d[1]), min(max(d[0], d[1]), d[2]));
    if (m > 0) pct = constrain((TANK_EMPTY_CM - m) / (TANK_EMPTY_CM - TANK_FULL_CM) * 100.0f, 0.0f, 100.0f);
  }
  bool lowOk  = PIN_FLOAT_LOW  >= 0 ? digitalRead(PIN_FLOAT_LOW)  == LOW : true;    // LOW = float is up = water above it
  bool highOk = PIN_FLOAT_HIGH >= 0 ? digitalRead(PIN_FLOAT_HIGH) == LOW : false;
  if (pct < 0) {                                                                   // no echo: coarse level from the floats alone
    if (PIN_FLOAT_LOW < 0 && PIN_FLOAT_HIGH < 0) return -1;
    return highOk ? 95.0f : (lowOk ? 50.0f : 5.0f);
  }
  if (!lowOk) pct = min(pct, 5.0f);                                                // trust a float over a sloshing echo
  if (highOk) pct = max(pct, 95.0f);
  return pct;
}

void publishReading() {
  float v = readPanelV(), a = readPanelA();
  char grid[160]; int n = 0;
  n += snprintf(grid + n, sizeof(grid) - n, "[");
  for (int r = 0; r < GRID_ROWS; r++) {
    n += snprintf(grid + n, sizeof(grid) - n, "%s[", r ? "," : "");
    for (int c = 0; c < GRID_COLS; c++)
      n += snprintf(grid + n, sizeof(grid) - n, "%s%.1f", c ? "," : "", readTempC(r * GRID_COLS + c));
    n += snprintf(grid + n, sizeof(grid) - n, "]");
  }
  snprintf(grid + n, sizeof(grid) - n, "]");
  float lux[LDR_COUNT];
  for (int k = 0; k < LDR_COUNT; k++) lux[k] = readLdrLux(k);
  lastLux = (lux[0] + lux[1] + lux[2] + lux[3]) / 4; lastWet = rainingNow();
  float mw = nodeMilliwatts(); uint32_t now = millis();                              // the node's own energy bill
  nodeWh += mw * (float)(now - lastEnergyMs) / 3.6e9f; lastEnergyMs = now;
  float tapS = tapOpenS + (tapOpen ? (now - tapStart) / 1000.0f : 0);
  char msg[600];
  snprintf(msg, sizeof(msg),
    "{\"panel_id\":\"%s\",\"voltage_v\":%.2f,\"current_a\":%.2f,\"ldr_lux\":%.0f,\"ldr_corners_lux\":[%.0f,%.0f,%.0f,%.0f],\"temps_c\":%s,"
    "\"tank_level_pct\":%.0f,\"clean_state\":%d,\"tap_open\":%d,\"rain\":%d,\"node_mw\":%.0f,\"node_wh\":%.4f,\"tap_s\":%.0f,\"spray_s\":%.0f}",
    PANEL_ID, v, a, lastLux, lux[0], lux[1], lux[2], lux[3], grid, tankPct, (int)cs, tapOpen ? 1 : 0, lastWet ? 1 : 0, mw, nodeWh, tapS, sprayS);
  Serial.println(msg);
  if (WiFi.status() != WL_CONNECTED) return;
  HTTPClient http; http.setTimeout(1500);
  if (httpBegin(http, "/api/reading")) { http.addHeader("Content-Type", "application/json"); http.POST((uint8_t*)msg, strlen(msg)); http.end(); }
}

// ---------- cleaning state machine (non-blocking) ----------
void startClean(uint32_t w, uint32_t a) {
  if (cs != IDLE) return;                                  // already cleaning
  if (tankPct >= 0 && tankPct < MIN_WASH_PCT) { Serial.println("clean skipped: tank too low, waiting for the refill"); return; }
  waterMs = min(w, MAX_WATER_MS); airMs = min(a, MAX_AIR_MS);
  cs = WATER; csStart = millis(); lastClean = csStart;
  setSpray(true);
  Serial.printf("clean start water=%lu air=%lu\n", waterMs, airMs);
}
void cleanLoop() {
  uint32_t t = millis() - csStart;
  if (cs == WATER && t >= waterMs) { cs = AIR; csStart = millis(); setSpray(false); setBlower(true); sprayS += waterMs / 1000.0f; }
  else if (cs == AIR && t >= airMs) { cs = IDLE; setBlower(false); Serial.println("clean done"); }
}

// ---------- tap-water back-up for the rainwater tank ----------
void tapLoop() {
  static uint32_t lastTank = 0;
  if (millis() - lastTank >= 1000) { lastTank = millis(); tankPct = readTankPct(); }   // one measurement a second is plenty
  bool floatFull = PIN_FLOAT_HIGH >= 0 && digitalRead(PIN_FLOAT_HIGH) == LOW;
  if (!tapOpen) {
    bool low = tankPct >= 0 && tankPct < TANK_LOW_PCT, critical = tankPct >= 0 && tankPct < TANK_CRITICAL_PCT;
    if (((low && !tapHold) || critical) && millis() > tapLockUntil) {
      tapOpen = true; tapStart = millis(); setTap(true);
      Serial.printf("tap refill start (tank %.0f%%%s)\n", tankPct, tapHold ? ", rain expected but tank is critical" : "");
    }
  } else {
    bool full = tankPct >= TANK_FULL_PCT || floatFull;
    bool timeout = millis() - tapStart > TAP_MAX_MS;
    if (full || timeout) {
      tapOpen = false; setTap(false); tapOpenS += (millis() - tapStart) / 1000.0f;
      if (timeout) { tapLockUntil = millis() + TAP_LOCKOUT_MS; Serial.println("tap refill TIMED OUT: check the level sensor and the valve"); }
      else Serial.printf("tap refill done (tank %.0f%%)\n", tankPct);
    }
  }
}

// ---------- comms ----------
bool jsonTrue(const String& s, const char* key) {
  int i = s.indexOf(key); if (i < 0) return false;
  int c = s.indexOf(':', i); if (c < 0) return false;
  String rest = s.substring(c + 1); rest.trim(); return rest.startsWith("true");
}
void pollCommand() {                 // ask the API if there is a clean command waiting, and whether to hold off buying tap water
  if (WiFi.status() != WL_CONNECTED) return;
  HTTPClient http; http.setTimeout(800);
  if (!httpBegin(http, String("/api/command?panel=") + PANEL_ID)) return;
  if (http.GET() == 200) {
    String s = http.getString();
    tapHold = jsonTrue(s, "\"tap_hold\"");
    if (s.indexOf("\"clean\"") >= 0) {
      auto num = [&](const char* key, uint32_t def) {          // tiny JSON number grab, enough for our fixed format
        int i = s.indexOf(key); if (i < 0) return def;
        return (uint32_t)s.substring(s.indexOf(':', i) + 1).toInt();
      };
      startClean(num("water_ms", 4000), num("air_ms", 8000));
    }
  }
  http.end();
}

// ---------- day-only power management ----------
void sleepNow(const char* reason, uint32_t seconds, bool tellApi) {
  if (tellApi && WiFi.status() == WL_CONNECTED) {                  // tell the API this is sleep, not a failure
    char b[160]; snprintf(b, sizeof(b), "{\"panel_id\":\"%s\",\"mode\":\"sleep\",\"reason\":\"%s\",\"wake_s\":%lu}", PANEL_ID, reason, (unsigned long)seconds);
    HTTPClient http; http.setTimeout(1500);
    if (httpBegin(http, "/api/status")) { http.addHeader("Content-Type", "application/json"); http.POST((uint8_t*)b, strlen(b)); http.end(); }
  }
  Serial.printf("sleeping (%s) for %lu s\n", reason, (unsigned long)seconds);
#if ENABLE_SLEEP
  setSpray(false); setBlower(false); setTap(false);
  sensorsOff();
  WiFi.disconnect(true); WiFi.mode(WIFI_OFF);
  nodeWh += SLEEP_POWER_MW * seconds / 3.6e6f;
  wasDay = false;
  esp_sleep_enable_timer_wakeup((uint64_t)seconds * 1000000ULL);
  esp_deep_sleep_start();
#endif
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_SPRAY, OUTPUT); pinMode(PIN_TAP, OUTPUT); pinMode(PIN_BLOWER, OUTPUT);
  setSpray(false); setBlower(false); setTap(false);          // everything off first
#ifndef WOKWI
  pinMode(PIN_MUX_S0, OUTPUT); pinMode(PIN_MUX_S1, OUTPUT); pinMode(PIN_MUX_S2, OUTPUT);
  Wire.begin(PIN_SDA, PIN_SCL);
#endif
  if (PIN_FLOAT_LOW >= 0) pinMode(PIN_FLOAT_LOW, INPUT_PULLUP);
  if (PIN_FLOAT_HIGH >= 0) pinMode(PIN_FLOAT_HIGH, INPUT_PULLUP);
  if (PIN_RAIN >= 0) pinMode(PIN_RAIN, INPUT_PULLUP);
  if (PIN_TRIG >= 0) { pinMode(PIN_TRIG, OUTPUT); pinMode(PIN_ECHO, INPUT); }
  analogSetAttenuation(ADC_11db);
  sensorsOn();
  // a quick look at the sun, with no Wi-Fi: is it worth waking up?
  float lux = readLuxAvg(); bool wet = rainingNow(), day = isDaylight(lux);
  Serial.printf("wake: %.0f lux, %s, %s\n", lux, day ? "daylight" : "dark", wet ? "raining" : "dry");
  if (!day || wet) sleepNow(wet ? "rain" : "dark", wet ? SLEEP_RAIN_S : SLEEP_NIGHT_S, false);
  wasDay = true;
  WiFi.begin(WIFI_SSID, WIFI_PASS, 6);          // channel 6 connects fastest in Wokwi, harmless elsewhere
}

void loop() {
  static uint32_t lastReport = 0, lastPoll = 0, lastLink = 0; static uint8_t darkReports = 0;
  if (WiFi.status() != WL_CONNECTED && millis() - lastLink > 10000) { lastLink = millis(); WiFi.reconnect(); }   // never block
  cleanLoop(); tapLoop();                                    // run with or without Wi-Fi
  if (millis() - lastPoll >= 1000) { lastPoll = millis(); pollCommand(); }
  if (millis() - lastReport >= REPORT_MS) {
    lastReport = millis(); publishReading();
    bool dark = !isDaylight(lastLux) || lastWet;             // dusk, heavy cloud or rain: no point being awake
    darkReports = dark ? darkReports + 1 : 0;
    if (darkReports >= SLEEP_AFTER_REPORTS && cs == IDLE && !tapOpen) sleepNow(lastWet ? "rain" : "dark", lastWet ? SLEEP_RAIN_S : SLEEP_NIGHT_S, true);
  }
  if (cs == IDLE && millis() - lastClean >= AUTO_CLEAN_MS) startClean(4000, 8000);   // backup timer
}
