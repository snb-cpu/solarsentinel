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
    src = CFG_PATH.read_text().split("// ---- WOKWI")[0]      # the Wokwi overrides are not the real hardware
    cfg = {m[0]: float(m[1]) for m in re.findall(r"#define\s+(\w+)\s+(-?[0-9.]+)(?:f|UL)?\b", src)}
    cfg["TEMP_OFFSET_C"] = [float(x) for x in re.search(r"TEMP_OFFSET_C\[8\]\s*=\s*\{([^}]*)\}", src).group(1).split(",")]
    cfg["RELAY_ON_LOW"] = "#define RELAY_ON  LOW" in src
    return cfg

class Node:
    def __init__(self, world, cfg, pid="P1"):
        self.w, self.c, self.pid = world, cfg, pid
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
        self.adc = {"volt_mv": 0, "curr_mv": 0, "ldr_mv": 0, "temp_mv": [0] * 8}
        self.last = {}
    # ---- ADC ----
    def adc_mv(self, v):
        v = min(3.3, max(0.0, v))
        counts = min(4095, max(0, round(v / 3.3 * 4095 + random.gauss(0, 1.2))))
        return counts * 3300 / 4095
    def adc_volts(self, v):                                   # analogReadMilliVolts averaged x16
        return sum(self.adc_mv(v) for _ in range(16)) / 16000.0
    # ---- sensors, same formulas as the .ino ----
    def read_temp(self, ch):
        pin_v = (self.w.tback[ch] + self.t_err[ch]) * 0.010 * (self.c["TEMP_MV_PER_C"] / 10.0)
        pv = self.adc_volts(pin_v); self.adc["temp_mv"][ch] = round(pv * 1000, 1)
        return pv * 1000.0 / self.c["TEMP_MV_PER_C"] + self.c["TEMP_OFFSET_C"][ch]
    def reading(self):
        v_true, i_true = self.w.electrical()
        vp = self.adc_volts(v_true / self.div_real); v = vp * self.c["VOLT_DIV"]
        ip = self.adc_volts(self.zero_real + 0.100 * i_true)
        a = max((ip - self.c["CURR_ZERO_V"]) / self.c["CURR_V_PER_A"], 0.0)
        lp = self.adc_volts(self.w.lux() / self.c["LDR_MAX_LUX"] * 3.3); lux = lp / 3.3 * self.c["LDR_MAX_LUX"]
        self.adc.update(volt_mv=round(vp * 1000, 1), curr_mv=round(ip * 1000, 1), ldr_mv=round(lp * 1000, 1))
        R, C = int(self.c["GRID_ROWS"]), int(self.c["GRID_COLS"])
        grid = [[round(self.read_temp(r * C + k), 1) for k in range(C)] for r in range(R)]
        self.last = {"v": round(v, 2), "a": round(a, 2), "lux": round(lux)}
        return {"panel_id": self.pid, "voltage_v": round(v, 2), "current_a": round(a, 2), "ldr_lux": round(lux),
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
    def __init__(self, api, speed, n_panels=3):
        self.api, self.speed, self.link, self.sel = api, speed, False, 0
        self.act = {"poll": 0.0, "report": 0.0, "weather": 0.0}
        cfg = load_cfg()
        self.worlds = [World(dust_mult=[1.0, 1.4, 0.8][i % 3]) for i in range(n_panels)]   # panels collect dust at different rates
        self.nodes = [Node(w, cfg, f"P{i + 1}") for i, w in enumerate(self.worlds)]       # each panel has its own ESP32, valve, blower, tank
    def weather_feed(self):
        w = self.worlds[0]; g = 1 - 0.7 * w.cloud
        f = [round(g, 2)] + [round(random.uniform(0.85, 1.0), 2) for _ in range(6)]
        if w.forecast_rain: f[0] = f[1] = 0.45
        return {"rain_48h": w.forecast_rain or w.raining, "day_factor": f, "ambient_c": round(w.ambient(), 1), "raining": w.raining}
    def sync_env(self):                                          # one sky over all panels
        w0 = self.worlds[0]
        for w in self.worlds[1:]:
            w.cloud, w.raining, w.rain_until, w.storm_until = w0.cloud, w0.raining, w0.rain_until, w0.storm_until
            w.forecast_rain, w.rain_at = False, None
    def run(self):
        last, t_rep, t_cmd, t_wx, t_sim = time.time(), 0, 0, 0, 0
        while True:
            now = time.time(); real = now - last; last = now
            for k, (w, n) in enumerate(zip(self.worlds, self.nodes)):
                if k: w.t = self.worlds[0].t - real * self.speed
                w.step(real * self.speed, real, n.valve, n.blower)
                if k == 0: self.sync_env()
                n.clean_loop(); n.timer_check()
            if now - t_rep >= 2.0:
                t_rep = now; self.act["report"] = now; self.link = all(http(self.api, "/api/reading", n.reading()) is not None for n in self.nodes)
            if now - t_cmd >= 1.0:
                t_cmd = now; self.act["poll"] = now
                for n in self.nodes:
                    c = http(self.api, f"/api/command?panel={n.pid}")
                    if c and c.get("action") == "clean": n.start_clean(c.get("water_ms", 4000), c.get("air_ms", 8000), c.get("why", "command from API"))
            if now - t_sim >= 1.0:                                  # demo controls relayed through the API
                t_sim = now; c = http(self.api, "/api/simcmd")
                for cmd in (c or {}).get("cmds", []): self.do(cmd)
                http(self.api, "/api/simstate", self.state())
            if now - t_wx >= 5.0:
                t_wx = now; http(self.api, "/api/weather", self.weather_feed())
            time.sleep(0.1)
    def state(self):
        w0 = self.worlds[0]
        return {"clock": f"Day {w0.day()} {int(w0.hour()):02d}:{int(w0.hour() % 1 * 60):02d}", "speed": self.speed, "link": self.link, "api": self.api,
                "sun_wm2": round(w0.irradiance()), "ambient_c": round(w0.ambient(), 1), "cloud": round(w0.cloud, 2), "raining": w0.raining,
                "forecast_rain": w0.forecast_rain, "storm": w0.t < w0.storm_until, "timer": self.nodes[0].timer_on, "sel": self.sel,
                "now": time.time(), "activity": self.act, "cfg": {"auto_s": self.nodes[0].c["AUTO_CLEAN_MS"] / 1000, "volt_div": self.nodes[0].c["VOLT_DIV"], "zero": self.nodes[0].c["CURR_ZERO_V"], "vpa": self.nodes[0].c["CURR_V_PER_A"], "mvc": self.nodes[0].c["TEMP_MV_PER_C"]},
                "panels": [{"id": n.pid, "soil_pct": round(w.mean_soil() * 100, 1), "tank": round(w.tank), "faults": w.faults, "node_state": n.cs,
                            "valve": n.valve, "blower": n.blower, "temps": [round(x, 1) for x in w.tcell], "sensors": [round(x, 1) for x in w.tback],
                            "soil": [round(w.soil(i), 2) for i in range(len(w.dust))], "stuck": [round(x, 2) for x in w.stuck],
                            "node": {"cs": n.cs, "elapsed_ms": round(time.time() * 1000 - n.cs_start) if n.cs != "IDLE" else 0, "total_ms": n.water_ms if n.cs == "WATER" else n.air_ms,
                                     "timer_on": n.timer_on, "timer_in_s": round(n.c["AUTO_CLEAN_MS"] / 1000 - (w.t - n.boot_sim - n.last_clean_sim)), "adc": n.adc, "last": n.last, "tank": round(w.tank)}} for w, n in zip(self.worlds, self.nodes)],
                "events": sorted(sum([[f"{n.pid} {e}" for e in n.events[-6:]] for n in self.nodes], []))[-12:]}
    def do(self, b):
        c, i = b.get("cmd"), int(b.get("panel", self.sel))
        w = self.worlds[i % len(self.worlds)]
        if c == "select": self.sel = i
        elif c == "storm": self.worlds[0].storm_until = self.worlds[0].t + 3600
        elif c == "bird": w.stuck[random.randrange(len(w.stuck))] = 0.5
        elif c in ("crack", "hotspot", "shade"): w.faults[c] = not w.faults[c]
        elif c == "repair": w.faults = {"crack": False, "hotspot": False, "shade": False}
        elif c == "rain_forecast": w0 = self.worlds[0]; w0.forecast_rain = not w0.forecast_rain; w0.rain_at = None
        elif c == "timer":
            for n in self.nodes: n.timer_on = not n.timer_on
        elif c == "speed": self.speed = max(0.0, min(3000.0, float(b.get("value", self.speed))))
        elif c == "dirty": w.dust = [random.uniform(0.07, 0.17) for _ in w.dust]

PAGE = (HERE / "console.html").read_text()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000"); ap.add_argument("--speed", type=float, default=120)
    ap.add_argument("--console-port", type=int, default=8100); ap.add_argument("--panels", type=int, default=3); a = ap.parse_args()
    sim = Sim(a.api.rstrip("/"), a.speed, a.panels)
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
