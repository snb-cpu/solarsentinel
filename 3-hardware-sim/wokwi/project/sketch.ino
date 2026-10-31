#define WOKWI 1
// SolarSentinel node: read sensors -> POST reading to the API; poll for clean commands; 2-hour backup timer.
// JSON is defined in docs/contract.md. virtual_node.py is a line-for-line port of this file.
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include "config.h"
#include "secrets.h"


enum CleanState { IDLE, WATER, AIR };
CleanState cs = IDLE;
uint32_t csStart = 0, waterMs = 0, airMs = 0, lastClean = 0;

// ---------- http (plain for the LAN, TLS for a tunnel URL like https://xxxx.trycloudflare.com) ----------
WiFiClientSecure tlsClient; WiFiClient plainClient;
bool httpBegin(HTTPClient& http, const String& path) {
  String url = String(API_URL) + path;
  if (url.startsWith("https")) { tlsClient.setInsecure(); return http.begin(tlsClient, url); }   // demo: no certificate check
  return http.begin(plainClient, url);
}

// ---------- sensors ----------
#ifndef WOKWI
float adcVolts(int pin) {            // averaged, calibrated reading in volts at the pin
  uint32_t mv = 0;
  for (int i = 0; i < 16; i++) mv += analogReadMilliVolts(pin);
  return mv / 16000.0f;
}
float readTempC(int ch) {            // select CD4051 channel, let it settle, read
  digitalWrite(PIN_MUX_S0, ch & 1);
  digitalWrite(PIN_MUX_S1, (ch >> 1) & 1);
  digitalWrite(PIN_MUX_S2, (ch >> 2) & 1);
  delay(5);
  analogReadMilliVolts(PIN_MUX);     // throw away first sample after switching
  return adcVolts(PIN_MUX) * 1000.0f / TEMP_MV_PER_C + TEMP_OFFSET_C[ch];
}
#else                                // ---- Wokwi: pots for V/I/light, NTC thermistors on direct pins, no mux ----
float adcRaw(int pin) { uint32_t t = 0; for (int i = 0; i < 16; i++) t += analogRead(pin); return t / 16.0f; }
float adcVolts(int pin) { return adcRaw(pin) / 4095.0f * 3.3f; }
float readTempC(int ch) {            // Wokwi NTC module (beta 3950), as in the Wokwi docs
  float raw = adcRaw(WOKWI_TEMP_PINS[ch]);
  if (raw < 1) raw = 1; if (raw > 4094) raw = 4094;
  return 1.0f / (log(1.0f / (4095.0f / raw - 1.0f)) / 3950.0f + 1.0f / 298.15f) - 273.15f + TEMP_OFFSET_C[ch];
}
#endif
float readLux() {                    // LDR divider: more light -> higher voltage (wire LDR to 3.3V side)
  return adcVolts(PIN_LDR) / 3.3f * LDR_MAX_LUX;
}
int tankPct() {
  if (PIN_TANK < 0) return -1;       // -1 = no tank sensor
  return digitalRead(PIN_TANK) == LOW ? 100 : 0;
}

void publishReading() {
  float v = adcVolts(PIN_VOLT) * VOLT_DIV;
  float a = (adcVolts(PIN_CURR) - CURR_ZERO_V) / CURR_V_PER_A;
  if (a < 0) a = 0;
  char grid[160]; int n = 0;
  n += snprintf(grid + n, sizeof(grid) - n, "[");
  for (int r = 0; r < GRID_ROWS; r++) {
    n += snprintf(grid + n, sizeof(grid) - n, "%s[", r ? "," : "");
    for (int c = 0; c < GRID_COLS; c++)
      n += snprintf(grid + n, sizeof(grid) - n, "%s%.1f", c ? "," : "", readTempC(r * GRID_COLS + c));
    n += snprintf(grid + n, sizeof(grid) - n, "]");
  }
  snprintf(grid + n, sizeof(grid) - n, "]");
  char msg[360];
  snprintf(msg, sizeof(msg),
    "{\"panel_id\":\"%s\",\"voltage_v\":%.2f,\"current_a\":%.2f,\"ldr_lux\":%.0f,\"temps_c\":%s,\"tank_level_pct\":%d,\"clean_state\":%d}",
    PANEL_ID, v, a, readLux(), grid, tankPct(), (int)cs);
  Serial.println(msg);
  if (WiFi.status() != WL_CONNECTED) return;
  HTTPClient http; http.setTimeout(1500);
  if (httpBegin(http, "/api/reading")) { http.addHeader("Content-Type", "application/json"); http.POST((uint8_t*)msg, strlen(msg)); http.end(); }
}

// ---------- cleaning state machine (non-blocking) ----------

void relays(bool valve, bool blower) {
  digitalWrite(PIN_VALVE, valve ? RELAY_ON : RELAY_OFF);
  digitalWrite(PIN_BLOWER, blower ? RELAY_ON : RELAY_OFF);
}
void startClean(uint32_t w, uint32_t a) {
  if (cs != IDLE) return;                                  // already cleaning
  if (PIN_TANK >= 0 && tankPct() == 0) { Serial.println("clean skipped: tank empty"); return; }
  waterMs = min(w, MAX_WATER_MS); airMs = min(a, MAX_AIR_MS);
  cs = WATER; csStart = millis(); lastClean = csStart;
  relays(true, false);
  Serial.printf("clean start water=%lu air=%lu\n", waterMs, airMs);
}
void cleanLoop() {
  uint32_t t = millis() - csStart;
  if (cs == WATER && t >= waterMs) { cs = AIR; csStart = millis(); relays(false, true); }
  else if (cs == AIR && t >= airMs) { cs = IDLE; relays(false, false); Serial.println("clean done"); }
}

// ---------- comms ----------
void pollCommand() {                 // ask the API if there is a clean command waiting
  if (WiFi.status() != WL_CONNECTED) return;
  HTTPClient http; http.setTimeout(800);
  if (!httpBegin(http, String("/api/command?panel=") + PANEL_ID)) return;
  if (http.GET() == 200) {
    String s = http.getString();
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

void setup() {
  Serial.begin(115200);
#ifndef WOKWI
  pinMode(PIN_MUX_S0, OUTPUT); pinMode(PIN_MUX_S1, OUTPUT); pinMode(PIN_MUX_S2, OUTPUT);
#endif
  pinMode(PIN_VALVE, OUTPUT); pinMode(PIN_BLOWER, OUTPUT);
  relays(false, false);                                      // both off at boot
  if (PIN_TANK >= 0) pinMode(PIN_TANK, INPUT_PULLUP);
  analogSetAttenuation(ADC_11db);
  WiFi.begin(WIFI_SSID, WIFI_PASS, 6);          // channel 6 connects fastest in Wokwi, harmless elsewhere
}
void loop() {
  static uint32_t lastReport = 0, lastPoll = 0, lastLink = 0;
  if (WiFi.status() != WL_CONNECTED && millis() - lastLink > 10000) { lastLink = millis(); WiFi.reconnect(); }   // never block
  cleanLoop();                                               // runs with or without Wi-Fi
  if (millis() - lastPoll >= 1000) { lastPoll = millis(); pollCommand(); }
  if (millis() - lastReport >= REPORT_MS) { lastReport = millis(); publishReading(); }
  if (cs == IDLE && millis() - lastClean >= AUTO_CLEAN_MS) startClean(4000, 8000);   // backup timer
}
