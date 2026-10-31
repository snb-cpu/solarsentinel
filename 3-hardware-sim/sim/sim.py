"""Fake SolarSentinel node. Emits readings in the shape of docs/contract.md.

  python3 sim/sim.py --scenario dust                 # prints a reading every 2 s
  python3 sim/sim.py --scenario hotspot --mqtt localhost   # needs: pip install paho-mqtt
Scenarios: ok, dust, shading, hotspot, fault. Dust drops after a "clean" command; fault does not.
Send a clean in MQTT mode by publishing to solar/P1/command, or type "clean" + Enter in stdout mode.
"""
import argparse, json, random, sys, threading, time
from datetime import datetime, timezone

ROWS, COLS, PANEL = 2, 3, "P1"

class Node:
    def __init__(self, scenario):
        self.scenario = scenario
        self.soil = {"dust": 0.12, "shading": 0.0}.get(scenario, 0.0)   # fraction of light lost to dust
        self.tank = 70
    def clean(self):
        if self.scenario != "fault":
            self.soil = 0.0
        self.tank = max(0, self.tank - 5)
    def reading(self):
        sun = random.uniform(52000, 56000)
        temps = [[35 + 6 * (sun / 55000) + random.gauss(0, 0.3) for _ in range(COLS)] for _ in range(ROWS)]
        light_eff = 1 - self.soil
        if self.scenario == "dust":
            for r in temps:
                for c in range(COLS): r[c] += 4 * self.soil / 0.12       # dust holds heat evenly
        if self.scenario == "shading":
            light_eff *= 0.55
            for r in range(ROWS): temps[r][0] -= 3                       # one side cooler
        if self.scenario == "hotspot": temps[1][1] += random.uniform(8, 14)
        if self.scenario == "fault":
            temps[0][2] += 10; light_eff *= 0.8                          # stays hot, never recovers
        v = 18.0 + random.gauss(0, 0.1)
        a = 5.0 * (sun / 55000) * light_eff + random.gauss(0, 0.05)
        return {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "panel_id": PANEL,
                "voltage_v": round(v, 2), "current_a": round(max(a, 0), 2), "ldr_lux": round(sun),
                "temps_c": [[round(x, 1) for x in r] for r in temps], "tank_level_pct": self.tank}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="ok", choices=["ok", "dust", "shading", "hotspot", "fault"])
    ap.add_argument("--mqtt", help="broker host; omit to print to stdout")
    ap.add_argument("--every", type=float, default=2.0)
    ap.add_argument("--count", type=int, default=0, help="stop after N readings (0 = forever)")
    a = ap.parse_args()
    node, publish = Node(a.scenario), lambda m: print(json.dumps(m), flush=True)
    if a.mqtt:
        import paho.mqtt.client as mqtt
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2) if hasattr(mqtt, "CallbackAPIVersion") else mqtt.Client()
        c.on_message = lambda cl, u, msg: (print("command:", msg.payload.decode(), file=sys.stderr), node.clean()) if b'"clean"' in msg.payload else None
        c.connect(a.mqtt, 1883); c.subscribe(f"solar/{PANEL}/command"); c.loop_start()
        publish = lambda m: c.publish(f"solar/{PANEL}/reading", json.dumps(m))
    else:
        threading.Thread(target=lambda: [node.clean() for line in sys.stdin if line.strip() == "clean"], daemon=True).start()
    n = 0
    while a.count == 0 or n < a.count:
        publish(node.reading()); n += 1; time.sleep(a.every)

if __name__ == "__main__":
    main()
