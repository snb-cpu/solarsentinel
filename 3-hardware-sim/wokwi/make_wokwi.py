"""Builds the Wokwi project from the real firmware, so it never drifts. Run:  python3 wokwi/make_wokwi.py
Output: wokwi/project/{sketch.ino, config.h, secrets.h, diagram.json}  -> paste these into a new Wokwi ESP32 project."""
import json
from pathlib import Path
HERE = Path(__file__).parent; FW = HERE.parent / "firmware" / "solarsentinel"; OUT = HERE / "project"; OUT.mkdir(exist_ok=True)
(OUT / "sketch.ino").write_text("#define WOKWI 1\n" + (FW / "solarsentinel.ino").read_text())
(OUT / "config.h").write_text((FW / "config.h").read_text())
(OUT / "secrets.h").write_text('''#pragma once
#define WIFI_SSID "Wokwi-GUEST"
#define WIFI_PASS ""
// The public address of laptop B's API, from the tunnel (no trailing slash). Example: "https://random-words.trycloudflare.com"
#define API_URL "https://CHANGE-ME.trycloudflare.com"
''')
parts = [
 {"type": "wokwi-esp32-devkit-v1", "id": "esp", "top": 0, "left": 0, "attrs": {}},
 {"type": "wokwi-potentiometer", "id": "potV", "top": -140, "left": -200, "attrs": {}},
 {"type": "wokwi-potentiometer", "id": "potI", "top": -40, "left": -200, "attrs": {}},
 {"type": "wokwi-potentiometer", "id": "potL", "top": 60, "left": -200, "attrs": {}},
 {"type": "wokwi-ntc-temperature-sensor", "id": "ntc1", "top": -150, "left": 240, "attrs": {}},
 {"type": "wokwi-ntc-temperature-sensor", "id": "ntc2", "top": -60, "left": 240, "attrs": {}},
 {"type": "wokwi-ntc-temperature-sensor", "id": "ntc3", "top": 30, "left": 240, "attrs": {}},
 {"type": "wokwi-relay-module", "id": "relay1", "top": 220, "left": -60, "attrs": {}},
 {"type": "wokwi-relay-module", "id": "relay2", "top": 220, "left": 160, "attrs": {}},
 {"type": "wokwi-led", "id": "ledV", "top": 330, "left": -10, "attrs": {"color": "blue", "label": "valve"}},
 {"type": "wokwi-led", "id": "ledB", "top": 330, "left": 210, "attrs": {"color": "green", "label": "blower"}},
 {"type": "wokwi-resistor", "id": "r1", "top": 300, "left": 20, "attrs": {"value": "220"}},
 {"type": "wokwi-resistor", "id": "r2", "top": 300, "left": 240, "attrs": {"value": "220"}},
]
W = lambda a, b, c="green": [a, b, c, []]
conn = [
 W("potV:GND", "esp:GND.1", "black"), W("potV:VCC", "esp:3V3", "red"), W("potV:SIG", "esp:D34", "green"),
 W("potI:GND", "esp:GND.1", "black"), W("potI:VCC", "esp:3V3", "red"), W("potI:SIG", "esp:D35", "green"),
 W("potL:GND", "esp:GND.1", "black"), W("potL:VCC", "esp:3V3", "red"), W("potL:SIG", "esp:VN", "green"),
 W("ntc1:GND", "esp:GND.2", "black"), W("ntc1:VCC", "esp:3V3", "red"), W("ntc1:OUT", "esp:D32", "orange"),
 W("ntc2:GND", "esp:GND.2", "black"), W("ntc2:VCC", "esp:3V3", "red"), W("ntc2:OUT", "esp:D33", "orange"),
 W("ntc3:GND", "esp:GND.2", "black"), W("ntc3:VCC", "esp:3V3", "red"), W("ntc3:OUT", "esp:VP", "orange"),
 W("relay1:VCC", "esp:VIN", "red"), W("relay1:GND", "esp:GND.1", "black"), W("relay1:IN", "esp:RX2", "blue"),
 W("relay2:VCC", "esp:VIN", "red"), W("relay2:GND", "esp:GND.1", "black"), W("relay2:IN", "esp:TX2", "blue"),
 W("relay1:COM", "esp:3V3", "red"), W("relay1:NO", "r1:1", "blue"), W("r1:2", "ledV:A", "blue"), W("ledV:C", "esp:GND.1", "black"),
 W("relay2:COM", "esp:3V3", "red"), W("relay2:NO", "r2:1", "green"), W("r2:2", "ledB:A", "green"), W("ledB:C", "esp:GND.1", "black"),
]
(OUT / "diagram.json").write_text(json.dumps({"version": 1, "author": "TRUENO", "editor": "wokwi", "parts": parts, "connections": conn, "dependencies": {}}, indent=2))
print("wrote", sorted(p.name for p in OUT.iterdir()))
