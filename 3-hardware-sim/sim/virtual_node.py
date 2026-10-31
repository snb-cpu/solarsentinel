"""Virtual ESP32 + the world around it. Run this on laptop A.

  python3 sim/virtual_node.py --api http://<laptop-B-ip>:8000
  open http://localhost:8100            # operator console: dust storm, cracked cell, rain...

It is a line-for-line port of firmware/solarsentinel/solarsentinel.ino, using the same constants
(parsed from config.h) and the same math. The "hardware" in front of it differs slightly from the
constants (divider error, current-sensor zero offset, per-sensor temperature error, ADC noise),
exactly like a real build before calibration. The one deliberate difference: AUTO_CLEAN_MS runs on
simulated time (so the 2-hour timer is visible in a demo); water/air durations run in real time.
"""
import argparse, json, math, random, re, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from world import World

HERE = Path(__file__).parent
CFG_PATH = HERE.parent / "firmware" / "solarsentinel" / "config.h"

def load_cfg():
    src = CFG_PATH.read_text()
    cfg = {m[0]: float(m[1]) for m in re.findall(r"#define\s+(\w+)\s+(-?[0-9.]+)(?:f|UL)?\b", src)}
    cfg["TEMP_OFFSET_C"] = [float(x) for x in re.search(r"TEMP_OFFSET_C\[8\]\s*=\s*\{([^}]*)\}", src).group(1).split(",")]
    cfg["RELAY_ON_LOW"] = "#define RELAY_ON  LOW" in src
    return cfg

class Node:
    def __init__(self, world, cfg):
        self.w, self.c = world, cfg
        # the imperfect real hardware in front of the ADC (what calibration is for)
        self.div_real = cfg["VOLT_DIV"] * 1.01
        self.zero_real = cfg["CURR_ZERO_V"] + 0.005
        self.t_err = [random.uniform(-0.6, 0.6) for _ in range(8)]
        # firmware state
        self.cs, self.cs_start, self.water_ms, self.air_ms = "IDLE", 0, 0, 0
        self.valve = self.blower = False
        self.boot_sim = world.t
        self.last_clean_sim = 0.0
        self.timer_on = False        # off by default so the demo shows the AI deciding; toggle in the console
        self.events = []
    # ---- ADC ----
    def adc_mv(self, v):
        v = min(3.3, max(0.0, v))
        counts = min(4095, max(0, round(v / 3.3 * 4095 + random.gauss(0, 1.2))))
        return counts * 3300 / 4095
    def adc_volts(self, v):                                   # analogReadMilliVolts averaged x16
        return sum(self.adc_mv(v) for _ in range(16)) / 16000.0
    # ---- sensors, same formulas as the .ino ----
    def read_temp(self, ch):
        pin_v = (self.w.tcell[ch] + self.t_err[ch]) * 0.010 * (self.c["TEMP_MV_PER_C"] / 10.0)
        return self.adc_volts(pin_v) * 1000.0 / self.c["TEMP_MV_PER_C"] + self.c["TEMP_OFFSET_C"][ch]
    def reading(self):
        v_true, i_true = self.w.electrical()
        v = self.adc_volts(v_true / self.div_real) * self.c["VOLT_DIV"]
        a = (self.adc_volts(self.zero_real + 0.100 * i_true) - self.c["CURR_ZERO_V"]) / self.c["CURR_V_PER_A"]
        a = max(a, 0.0)
        lux = self.adc_volts(self.w.lux() / self.c["LDR_MAX_LUX"] * 3.3) / 3.3 * self.c["LDR_MAX_LUX"]
        R, C = int(self.c["GRID_ROWS"]), int(self.c["GRID_COLS"])
        grid = [[round(self.read_temp(r * C + k), 1) for k in range(C)] for r in range(R)]
        return {"panel_id": "P1", "voltage_v": round(v, 2), "current_a": round(a, 2), "ldr_lux": round(lux),
                "temps_c": grid, "tank_level_pct": round(self.w.tank),
                "clean_state": {"IDLE": 0, "WATER": 1, "AIR": 2}[self.cs],
                "sim_clock": f"Day {self.w.day()} {int(self.w.hour()):02d}:{int(self.w.hour() % 1 * 60):02d}"}
    # ---- cleaning state machine, same as the .ino ----
    def relays(self, valve, blower):
        self.valve, self.blower = valve, blower
    def start_clean(self, water, air, why):
        if self.cs != "IDLE": return
        if self.w.tank <= 1: self.log("clean skipped: tank empty"); return
        self.water_ms, self.air_ms = min(water, self.c["MAX_WATER_MS"]), min(air, self.c["MAX_AIR_MS"])
        self.cs, self.cs_start = "WATER", time.time() * 1000
        self.last_clean_sim = self.w.t - self.boot_sim
        self.relays(True, False)
        self.log(f"clean start ({why}) water={int(self.water_ms)}ms air={int(self.air_ms)}ms")
    def clean_loop(self):
        t = time.time() * 1000 - self.cs_start
        if self.cs == "WATER" and t >= self.water_ms: self.cs, self.cs_start = "AIR", time.time() * 1000; self.relays(False, True)
        elif self.cs == "AIR" and t >= self.air_ms: self.cs = "IDLE"; self.relays(False, False); self.log("clean done")
    def timer_check(self):
        sim_ms = (self.w.t - self.boot_sim) * 1000
        if self.timer_on and self.cs == "IDLE" and sim_ms - self.last_clean_sim * 1000 >= self.c["AUTO_CLEAN_MS"]:
            self.start_clean(4000, 8000, "2-hour backup timer")
    def log(self, m):
        self.events.append(f"{time.strftime('%H:%M:%S')}  {m}"); self.events = self.events[-40:]; print(m, flush=True)

def http(api, path, body=None):
    try:
        req = urllib.request.Request(api + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "text/plain"}, method="POST" if body is not None else "GET")
        with urllib.request.urlopen(req, timeout=2) as r: return json.loads(r.read() or b"{}")
    except Exception: return None

class Sim:
    def __init__(self, api, speed):
        self.api, self.speed = api, speed
        self.w = World(); self.n = Node(self.w, load_cfg()); self.link = False
    def weather_feed(self):
        g = 1 - 0.7 * self.w.cloud
        f = [round(g, 2)] + [round(random.uniform(0.85, 1.0), 2) for _ in range(6)]
        if self.w.forecast_rain: f[0] = f[1] = 0.45
        return {"rain_48h": self.w.forecast_rain or self.w.raining, "day_factor": f, "ambient_c": round(self.w.ambient(), 1), "raining": self.w.raining}
    def run(self):
        last, t_rep, t_cmd, t_wx = time.time(), 0, 0, 0
        while True:
            now = time.time(); real = now - last; last = now
            self.w.step(real * self.speed, real, self.n.valve, self.n.blower)
            self.n.clean_loop(); self.n.timer_check()
            if now - t_rep >= 2.0:
                t_rep = now; r = http(self.api, "/api/reading", self.n.reading()); self.link = r is not None
            if now - t_cmd >= 1.0:
                t_cmd = now; c = http(self.api, "/api/command?panel=P1")
                if c and c.get("action") == "clean": self.n.start_clean(c.get("water_ms", 4000), c.get("air_ms", 8000), c.get("why", "command from API"))
            if now - t_wx >= 5.0:
                t_wx = now; http(self.api, "/api/weather", self.weather_feed())
            time.sleep(0.1)
    def state(self):
        w, n = self.w, self.n
        return {"clock": f"Day {w.day()} {int(w.hour()):02d}:{int(w.hour() % 1 * 60):02d}", "speed": self.speed, "link": self.link, "api": self.api,
                "sun_wm2": round(w.irradiance()), "ambient_c": round(w.ambient(), 1), "cloud": round(w.cloud, 2), "raining": w.raining,
                "forecast_rain": w.forecast_rain, "soil_pct": round(sum(w.soil) / 6 * 100, 1), "tank": round(w.tank), "faults": w.faults,
                "cell_temps": [round(x, 1) for x in w.tcell], "node_state": n.cs, "valve": n.valve, "blower": n.blower, "timer": n.timer_on,
                "storm": w.t < w.storm_until, "events": n.events[-12:]}
    def do(self, b):
        w, c = self.w, b.get("cmd")
        if c == "storm": w.storm_until = w.t + 3600
        elif c == "bird": w.soil[random.randrange(6)] = min(0.4, 0.4)
        elif c in ("crack", "hotspot", "shade"): w.faults[c] = not w.faults[c]
        elif c == "repair": w.faults = {"crack": False, "hotspot": False, "shade": False}
        elif c == "rain_forecast": w.forecast_rain = not w.forecast_rain; w.rain_at = None if not w.forecast_rain else w.rain_at
        elif c == "timer": self.n.timer_on = not self.n.timer_on
        elif c == "speed": self.speed = max(1, min(3000, float(b.get("value", self.speed))))
        elif c == "dirty": w.soil = [0.12] * 6

PAGE = """<!doctype html><meta charset=utf-8><title>Sim console</title><style>body{font:15px system-ui;background:#101820;color:#e8eef5;margin:20px}
button{margin:4px;padding:10px 14px;border-radius:8px;border:1px solid #345;background:#16283c;color:#e8eef5;cursor:pointer}button.on{background:#ffb703;color:#000}
.g{display:grid;grid-template-columns:1fr 1fr;gap:14px}.c{background:#16283c;padding:14px;border-radius:12px}pre{white-space:pre-wrap;font-size:12px}h3{margin:0 0 8px;color:#8fa9c2}</style>
<h2>Laptop A &middot; virtual panel + ESP32</h2><div class=g><div class=c><h3>World</h3><pre id=w></pre></div><div class=c><h3>ESP32 node</h3><pre id=n></pre></div></div>
<div class=c style="margin-top:14px"><h3>Cause trouble</h3>
<button onclick="d('storm')">Dust storm (1 h)</button><button onclick="d('bird')">Bird dropping</button><button onclick="d('dirty')">Make dirty now</button>
<button id=b_shade onclick="d('shade')">Shade</button><button id=b_hotspot onclick="d('hotspot')">Hotspot</button><button id=b_crack onclick="d('crack')">Cracked cell</button>
<button onclick="d('repair')">Repair faults</button><button id=b_rain onclick="d('rain_forecast')">Rain forecast</button><button id=b_timer onclick="d('timer')">2 h timer</button>
<br>Speed: <input id=sp type=range min=30 max=1200 value=120 oninput="d('speed',this.value)"> <span id=spv></span> sim-s per real second</div>
<div class=c style="margin-top:14px"><h3>Node log</h3><pre id=l></pre></div>
<script>const d=(cmd,value)=>fetch('/do',{method:'POST',body:JSON.stringify({cmd,value})});
async function t(){const s=await (await fetch('/state')).json();
w.textContent=`Clock ${s.clock}\\nSun ${s.sun_wm2} W/m2   Ambient ${s.ambient_c} C   Cloud ${s.cloud}\\nRaining: ${s.raining}   Rain forecast: ${s.forecast_rain}\\nDust on glass: ${s.soil_pct}%${s.storm?'  (STORM)':''}\\nTank: ${s.tank}%\\nTrue cell temps: ${s.cell_temps.join('  ')}`;
n.textContent=`API ${s.api}: ${s.link?'connected':'NOT CONNECTED'}\\nState: ${s.node_state}\\nValve: ${s.valve?'ON':'off'}   Blower: ${s.blower?'ON':'off'}\\n2 h timer: ${s.timer?'on':'off'}`;
l.textContent=s.events.join('\\n');spv.textContent=s.speed;
for(const k of ['shade','hotspot','crack'])document.getElementById('b_'+k).className=s.faults[k]?'on':'';
b_rain.className=s.forecast_rain?'on':'';b_timer.className=s.timer?'on':'';}
setInterval(t,700);t();</script>"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000"); ap.add_argument("--speed", type=float, default=120)
    ap.add_argument("--console-port", type=int, default=8100); a = ap.parse_args()
    sim = Sim(a.api.rstrip("/"), a.speed)
    threading.Thread(target=sim.run, daemon=True).start()
    class H(BaseHTTPRequestHandler):
        def log_message(self, *x): pass
        def do_GET(self):
            body, ct = (json.dumps(sim.state()).encode(), "application/json") if self.path == "/state" else (PAGE.encode(), "text/html; charset=utf-8")
            self.send_response(200); self.send_header("Content-Type", ct); self.end_headers(); self.wfile.write(body)
        def do_POST(self):
            sim.do(json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")); self.send_response(200); self.end_headers()
    print(f"Virtual node sending to {a.api}. Operator console: http://localhost:{a.console_port}")
    ThreadingHTTPServer(("0.0.0.0", a.console_port), H).serve_forever()

if __name__ == "__main__":
    main()
