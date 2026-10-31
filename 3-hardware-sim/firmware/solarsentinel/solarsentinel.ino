// SolarSentinel node: read sensors -> MQTT reading; listen for clean commands; 2-hour backup timer.
// Topics and JSON are defined in docs/contract.md.
#include <WiFi.h>
#include <PubSubClient.h>
#include "config.h"
#include "secrets.h"

WiFiClient net;
PubSubClient mqtt(net);
String tReading = String("solar/") + PANEL_ID + "/reading";
String tCommand = String("solar/") + PANEL_ID + "/command";

// ---------- sensors ----------
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
  char msg[320];
  snprintf(msg, sizeof(msg),
    "{\"panel_id\":\"%s\",\"voltage_v\":%.2f,\"current_a\":%.2f,\"ldr_lux\":%.0f,\"temps_c\":%s,\"tank_level_pct\":%d}",
    PANEL_ID, v, a, readLux(), grid, tankPct());
  mqtt.publish(tReading.c_str(), msg);
  Serial.println(msg);
}

// ---------- cleaning state machine (non-blocking) ----------
enum CleanState { IDLE, WATER, AIR };
CleanState cs = IDLE;
uint32_t csStart = 0, waterMs = 0, airMs = 0, lastClean = 0;

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
void onMsg(char* topic, byte* p, unsigned int len) {
  String s; for (unsigned i = 0; i < len; i++) s += (char)p[i];
  if (s.indexOf("\"clean\"") < 0) return;
  auto num = [&](const char* key, uint32_t def) {            // tiny JSON number grab, enough for our fixed format
    int i = s.indexOf(key); if (i < 0) return def;
    return (uint32_t)s.substring(s.indexOf(':', i) + 1).toInt();
  };
  startClean(num("water_ms", 4000), num("air_ms", 8000));
}
void ensureLink() {
  if (WiFi.status() != WL_CONNECTED) { WiFi.begin(WIFI_SSID, WIFI_PASS); return; }   // retry each loop, never block
  if (!mqtt.connected() && mqtt.connect(PANEL_ID)) mqtt.subscribe(tCommand.c_str());
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_MUX_S0, OUTPUT); pinMode(PIN_MUX_S1, OUTPUT); pinMode(PIN_MUX_S2, OUTPUT);
  pinMode(PIN_VALVE, OUTPUT); pinMode(PIN_BLOWER, OUTPUT);
  relays(false, false);                                      // both off at boot
  if (PIN_TANK >= 0) pinMode(PIN_TANK, INPUT_PULLUP);
  analogSetAttenuation(ADC_11db);
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMsg);
}
void loop() {
  static uint32_t lastReport = 0, lastLink = 0;
  if (millis() - lastLink > 5000 && (WiFi.status() != WL_CONNECTED || !mqtt.connected())) { lastLink = millis(); ensureLink(); }
  mqtt.loop();
  cleanLoop();                                               // runs with or without Wi-Fi
  if (millis() - lastReport >= REPORT_MS) { lastReport = millis(); publishReading(); }
  if (cs == IDLE && millis() - lastClean >= AUTO_CLEAN_MS) startClean(4000, 8000);   // backup timer
}
