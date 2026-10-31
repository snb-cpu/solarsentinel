"""Virtual ESP32 + the world around it. Run this on the Mac (laptop A).

  python3 sim/virtual_node.py --api http://<laptop-B-ip>:8000
  open http://localhost:8100            # hardware view + operator console: dust storm, cracked cell, rain, drain the tank...

It is a line-for-line port of firmware/solarsentinel/solarsentinel.ino, using the same constants
(parsed from config.h) and the same math, including the ADS1115 16-bit I2C ADC (its gain steps and counts), the two CD74HC4051E
multiplexers, the JSN-SR04T ultrasonic tank sensor and the INA219 power monitor. The "hardware" in front of it differs slightly from the
constants (divider error, current-sensor zero offset, per-sensor temperature error, ADC noise), exactly like a real build before calibration.
Two deliberate differences: AUTO_CLEAN_MS and the sleep timers run on simulated time (so they are visible in a demo), and the debounce
before sleeping is counted in simulated seconds, as on a real device reporting once a minute. Valves and the blower run in real time.
"""
import argparse, json, math, random, re, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from world import World, TANK_L, SPRAY_L_S, TAP_L_S

HERE = Path(__file__).parent
CFG_PATH = HERE.parent / "firmware" / "solarsentinel" / "config.h"

# What the real parts draw (datasheet typicals), used for the energy bill. Milliwatts at the 12 V battery rail.
P_ACTIVE_MW = 250.0                 # ESP32 awake in modem sleep, ACS712 + JSN-SR04T + LM35s + FC-37 + relay module logic, buck losses
P_SPRAY_MW, P_TAP_MW, P_BLOWER_MW = 4800.0, 4800.0, 2400.0   # 12 V solenoid valves ~0.4 A each, 5015 blower ~0.2 A
SKIP_SPEED = 6000.0                 # "skip to" runs the normal logic at this speed until the target hour

def load_cfg():
    src = CFG_PATH.read_text().split("// ---- WOKWI")[0]      # the Wokwi overrides are not the real hardware
    cfg = {m[0]: float(m[1]) for m in re.findall(r"#define\s+(\w+)\s+(-?[0-9.]+)(?:f|UL)?\b", src)}
    cfg["TEMP_OFFSET_C"] = [float(x) for x in re.search(r"TEMP_OFFSET_C\[8\]\s*=\s*\{([^}]*)\}", src).group(1).split(",")]
    cfg["RELAY_ON_LOW"] = "#define RELAY_ON  LOW" in src
    return cfg

class Node:
    def __init__(self, world, cfg, pid="P1"):
        self.w, self.c, self.pid = world, cfg, pid
        self.on_status = lambda body: None                    # set by Sim: tells the API when the node goes to sleep
        # the imperfect real hardware in front of the ADS1115 (what calibration is for)
        self.div_real = cfg["VOLT_DIV"] * 1.01
        self.zero_real = cfg["CURR_ZERO_V"] + 0.005
        self.t_err = [random.uniform(-0.6, 0.6) for _ in range(8)]
        # outputs and cleaning state machine
        self.cs, self.cs_start, self.water_ms, self.air_ms = "IDLE", 0, 0, 0
        self.spray = self.blower = False
        self.boot_sim = world.t
        self.last_clean_sim = 0.0
        self.timer_on = False        # off by default so the demo shows the AI deciding; toggle in the console
        # tank and tap refill
        self.tank_pct, self.last_tank = -1.0, 0.0
        self.tap_open, self.tap_hold = False, False
        self.tap_start, self.tap_lock_until = 0.0, 0.0
        self.tap_open_s = self.spray_s = 0.0
        # day-only power management
        self.mode, self.sleep_reason, self.wake_at = "active", "", 0.0
        self.was_day, self.dark_for = True, 0.0
        self.node_wh = self.always_on_wh = self.actuator_wh = 0.0
        self.events = []
        self.adc = {"volt": [0, 0], "curr": [0, 0], "ldr": [[0, 0]] * 4, "temp": [[0, 0]] * 8}   # [ADS1115 counts, millivolts at the input]
        self.last = {}
        self.sleeps = 0
        self.tank_pct = self.read_tank()                       # first look at the tank at power-on

    # ---- ADS1115: 16-bit, single-shot at 860 SPS, a few counts of noise, inputs limited to GND-0.3 .. VDD+0.3 ----
    def ads(self, true_v, pga, record=None):
        lsb = (187.5e-6, 125e-6, 62.5e-6)[int(pga)]
        n = int(self.c["ADS_SAMPLES"]); total = 0
        for _ in range(n):
            v = min(max(true_v, -0.3), 3.6)
            total += max(-32768, min(32767, round(v / lsb + random.gauss(0, 3))))
        counts = total / n
        if record is not None: record[:] = [round(counts, 1), round(counts * lsb * 1000, 2)]
        return counts * lsb
    # ---- sensors, same formulas as the .ino ----
    def read_temp(self, ch):                                   # CD74HC4051E #1 channel ch -> LM35DZ -> ADS1115 A0
        true_v = (self.w.tback[ch] + self.t_err[ch]) * 0.010
        rec = [0, 0]; v = self.ads(true_v, self.c["ADS_PGA_TEMP"], rec); self.adc["temp"][ch] = rec
        return v * 1000.0 / self.c["TEMP_MV_PER_C"] + self.c["TEMP_OFFSET_C"][ch]
    def read_ldr(self, k, true_lux, record=True):              # CD74HC4051E #2 channel k -> GL5528 divider -> ADS1115 A1
        rec = [0, 0]; v = self.ads(true_lux / self.c["LDR_MAX_LUX"] * 3.3, self.c["ADS_PGA_WIDE"], rec)
        if record: self.adc["ldr"][k] = rec
        return v / 3.3 * self.c["LDR_MAX_LUX"]
    def lux_now(self):                                         # what the node sees when it just looks at the sun
        return sum(self.read_ldr(k, l, False) for k, l in enumerate(self.w.lux_corners())) / 4
    def read_tank(self):                                       # JSN-SR04T: median of three pings, corrected by the float switches
        empty, full = self.c["TANK_EMPTY_CM"], self.c["TANK_FULL_CM"]
        d_true = empty - self.w.tank / 100 * (empty - full)
        pings = sorted(max(0.0, random.gauss(d_true, 0.4)) for _ in range(3))
        pct = max(0.0, min(100.0, (empty - pings[1]) / (empty - full) * 100))
        if self.w.tank <= 6: pct = min(pct, 5.0)               # low float open: water is below it
        if self.w.tank >= 95: pct = max(pct, 95.0)             # high float closed: water is above it
        return pct
    def power_mw(self):                                        # what the INA219 would read on the battery rail
        if self.mode == "sleep": return self.c["SLEEP_POWER_MW"]
        return P_ACTIVE_MW + (P_SPRAY_MW if self.spray else 0) + (P_TAP_MW if self.tap_open else 0) + (P_BLOWER_MW if self.blower else 0)
    def reading(self):
        v_true, i_true = self.w.electrical()
        rec = [0, 0]; v = self.ads(v_true / self.div_real, self.c["ADS_PGA_WIDE"], rec) * self.c["VOLT_DIV"]; self.adc["volt"] = rec
        rec = [0, 0]; vi = self.ads(self.zero_real + 0.100 * i_true, self.c["ADS_PGA_WIDE"], rec); self.adc["curr"] = rec
        a = max((vi - self.c["CURR_ZERO_V"]) / self.c["CURR_V_PER_A"], 0.0)
        corners = [self.read_ldr(k, l) for k, l in enumerate(self.w.lux_corners())]   # four LDRs through the second multiplexer
        lux = sum(corners) / len(corners)
        R, C = int(self.c["GRID_ROWS"]), int(self.c["GRID_COLS"])
        grid = [[round(self.read_temp(r * C + k), 1) for k in range(C)] for r in range(R)]
        mw = self.power_mw() * random.gauss(1, 0.02)
        tap_s = self.tap_open_s + ((time.time() * 1000 - self.tap_start) / 1000 if self.tap_open else 0)
        self.last = {"v": round(v, 2), "a": round(a, 2), "lux": round(lux), "corners": [round(x) for x in corners], "mw": round(mw)}
        return {"panel_id": self.pid, "voltage_v": round(v, 2), "current_a": round(a, 2), "ldr_lux": round(lux), "ldr_corners_lux": [round(x) for x in corners],
                "temps_c": grid, "tank_level_pct": round(self.tank_pct) if self.tank_pct >= 0 else -1,
                "clean_state": {"IDLE": 0, "WATER": 1, "AIR": 2}[self.cs], "tap_open": int(self.tap_open), "rain": int(self.w.raining),
                "node_mw": round(mw), "node_wh": round(self.node_wh, 4), "tap_s": round(tap_s), "spray_s": round(self.spray_s),
                "sim_clock": f"Day {self.w.day()} {int(self.w.hour()):02d}:{int(self.w.hour() % 1 * 60):02d}"}

    # ---- cleaning state machine, same as the .ino ----
    def start_clean(self, water, air, why):
        if self.cs != "IDLE": return
        if 0 <= self.tank_pct < self.c["MIN_WASH_PCT"]: self.log("clean skipped: tank too low, waiting for the refill"); return
        self.water_ms, self.air_ms = min(water, self.c["MAX_WATER_MS"]), min(air, self.c["MAX_AIR_MS"])
        self.cs, self.cs_start = "WATER", time.time() * 1000
        self.last_clean_sim = self.w.t - self.boot_sim
        self.spray = True
        self.log(f"clean start ({why}) water={int(self.water_ms)}ms air={int(self.air_ms)}ms")
    def clean_loop(self):
        t = time.time() * 1000 - self.cs_start
        if self.cs == "WATER" and t >= self.water_ms:
            self.cs, self.cs_start = "AIR", time.time() * 1000; self.spray, self.blower = False, True; self.spray_s += self.water_ms / 1000
        elif self.cs == "AIR" and t >= self.air_ms: self.cs = "IDLE"; self.blower = False; self.log("clean done")
    def timer_check(self):
        sim_ms = (self.w.t - self.boot_sim) * 1000
        if self.timer_on and self.cs == "IDLE" and sim_ms - self.last_clean_sim * 1000 >= self.c["AUTO_CLEAN_MS"]:
            self.start_clean(4000, 8000, "2-hour backup timer")

    # ---- tap-water back-up for the rainwater tank, same as tapLoop() ----
    def tap_loop(self):
        now = time.time() * 1000
        if now - self.last_tank >= 1000: self.last_tank = now; self.tank_pct = self.read_tank()
        if not self.tap_open:
            low = 0 <= self.tank_pct < self.c["TANK_LOW_PCT"]; critical = 0 <= self.tank_pct < self.c["TANK_CRITICAL_PCT"]
            if ((low and not self.tap_hold) or critical) and now > self.tap_lock_until:
                self.tap_open, self.tap_start = True, now
                self.log(f"tap refill start (tank {self.tank_pct:.0f}%{', rain expected but tank is critical' if self.tap_hold else ''})")
        else:
            full = self.tank_pct >= self.c["TANK_FULL_PCT"] or self.w.tank >= 95
            timeout = now - self.tap_start > self.c["TAP_MAX_MS"]
            if full or timeout:
                self.tap_open = False; self.tap_open_s += (now - self.tap_start) / 1000
                if timeout: self.tap_lock_until = now + self.c["TAP_LOCKOUT_MS"]; self.log("tap refill TIMED OUT: check the level sensor and the valve")
                else: self.log(f"tap refill done (tank {self.tank_pct:.0f}%)")

    # ---- day-only power management, same as sleepNow() / setup() / loop() ----
    def is_daylight(self, lux): return lux >= (self.c["DAY_LUX_OFF"] if self.was_day else self.c["DAY_LUX_ON"])
    def sleep_now(self, reason, seconds, tell_api):
        if tell_api: self.on_status({"panel_id": self.pid, "mode": "sleep", "reason": reason, "wake_s": seconds})
        self.log(f"sleeping ({reason}): sensors off, radio off, wakes every {int(seconds // 60)} min to look at the sun")
        self.spray = self.blower = False; self.tap_open = False
        self.mode, self.sleep_reason, self.wake_at, self.was_day, self.dark_for = "sleep", reason, self.w.t + seconds, False, 0.0
        self.sleeps += 1
    def check_wake(self):                                       # the deep-sleep timer fired: take a quick look, no Wi-Fi
        if self.w.t < self.wake_at: return
        lux, wet = self.lux_now(), self.w.raining
        if not self.is_daylight(lux) or wet:
            reason = "rain" if wet else "dark"
            if reason != self.sleep_reason: self.log(f"still asleep ({reason})"); self.sleep_reason = reason
            self.wake_at = self.w.t + (self.c["SLEEP_RAIN_S"] if wet else self.c["SLEEP_NIGHT_S"])
            return
        self.mode, self.was_day, self.dark_for, self.last_clean_sim = "active", True, 0.0, self.w.t - self.boot_sim
        self.last_tank = 0.0
        self.log("waking up: daylight and dry")
    def watch_the_sun(self, dt_sim):                            # awake: go back to sleep when it is dark or wet for long enough
        lux, wet = self.lux_now(), self.w.raining
        dark = (not self.is_daylight(lux)) or wet
        self.dark_for = self.dark_for + dt_sim if dark else 0.0
        if self.dark_for >= self.c["SLEEP_AFTER_REPORTS"] * 60 and self.cs == "IDLE" and not self.tap_open:   # 3 reports at one a minute
            why = "rain" if wet else "dark"
            self.sleep_now(why, self.c["SLEEP_RAIN_S"] if wet else self.c["SLEEP_NIGHT_S"], True)
    def account(self, dt_sim, real):                            # the node's own energy bill (what the INA219 integrates)
        base = self.c["SLEEP_POWER_MW"] if self.mode == "sleep" else P_ACTIVE_MW
        act = ((P_SPRAY_MW if self.spray else 0) + (P_TAP_MW if self.tap_open else 0) + (P_BLOWER_MW if self.blower else 0)) * real / 3.6e6
        self.node_wh += base * dt_sim / 3.6e6 + act
        self.always_on_wh += P_ACTIVE_MW * dt_sim / 3.6e6 + act      # the same device that never sleeps
        self.actuator_wh += act
    def log(self, m):
        self.events.append(f"{time.strftime('%H:%M:%S')}  {m}"); self.events = self.events[-40:]; print(self.pid, m, flush=True)

def http(api, path, body=None):
    try:
        req = urllib.request.Request(api + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "text/plain"}, method="POST" if body is not None else "GET")
        with urllib.request.urlopen(req, timeout=2) as r: return json.loads(r.read() or b"{}")
    except Exception: return None

class Sim:
    def __init__(self, api, speed, n_panels=3):
        self.api, self.speed, self.link, self.sel = api, speed, False, 0
        self.skip_to, self.saved_speed = None, speed
        self.act = {"poll": 0.0, "report": 0.0, "weather": 0.0}
        cfg = load_cfg()
        self.worlds = [World(dust_mult=[1.0, 1.4, 0.8][i % 3]) for i in range(n_panels)]   # panels collect dust at different rates
        self.nodes = [Node(w, cfg, f"P{i + 1}") for i, w in enumerate(self.worlds)]       # each panel has its own ESP32, valves, blower, tank
        for n in self.nodes: n.on_status = lambda body: http(self.api, "/api/status", body)
        self.marks = {}                                                                     # start-of-day ledger snapshots, for "today" numbers
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
    def snapshot_marks(self):
        for w, n in zip(self.worlds, self.nodes):
            m = self.marks.get(n.pid)
            if m is None or m["day"] != w.day():
                L = w.ledger(); self.marks[n.pid] = {"day": w.day(), **L, "node_wh": n.node_wh, "always_on_wh": n.always_on_wh}
    def run(self):
        last, t_rep, t_cmd, t_wx, t_sim = time.time(), 0, 0, 0, 0
        while True:
            now = time.time(); real = now - last; last = now
            if self.skip_to is not None:                         # fast-forward with all the normal logic running
                h = self.worlds[0].hour()
                if abs((h - self.skip_to + 12) % 24 - 12) < 0.1: self.skip_to, self.speed = None, self.saved_speed
                else: self.speed = SKIP_SPEED
            dt_sim = real * self.speed
            for k, (w, n) in enumerate(zip(self.worlds, self.nodes)):
                if k: w.t = self.worlds[0].t - dt_sim
                w.step(dt_sim, real, n.spray, n.blower, n.tap_open)
                if k == 0: self.sync_env()
                n.account(dt_sim, real)
                if n.mode == "active":
                    n.clean_loop(); n.tap_loop(); n.timer_check(); n.watch_the_sun(dt_sim)
                else:
                    n.check_wake()
            self.snapshot_marks()
            if now - t_rep >= 2.0:
                t_rep = now; self.act["report"] = now
                results = [http(self.api, "/api/reading", n.reading()) is not None for n in self.nodes if n.mode == "active"]
                if results: self.link = all(results)
            if now - t_cmd >= 1.0:
                t_cmd = now; self.act["poll"] = now
                for n in self.nodes:
                    if n.mode != "active": continue
                    c = http(self.api, f"/api/command?panel={n.pid}")
                    if c is None: continue
                    n.tap_hold = bool(c.get("tap_hold"))
                    if c.get("action") == "clean": n.start_clean(c.get("water_ms", 4000), c.get("air_ms", 8000), c.get("why", "command from API"))
            if now - t_sim >= 1.0:                                  # demo controls relayed through the API
                t_sim = now; c = http(self.api, "/api/simcmd")
                for cmd in (c or {}).get("cmds", []): self.do(cmd)
                http(self.api, "/api/simstate", self.state())
            if now - t_wx >= 5.0:
                t_wx = now; self.act["weather"] = now; http(self.api, "/api/weather", self.weather_feed())
            time.sleep(0.1)
    def today(self):                                             # this simulated day so far, all panels
        tot = {"node_wh": 0.0, "always_on_wh": 0.0, "recovered_wh": 0.0, "lost_wh": 0.0, "yield_wh": 0.0, "tap_l": 0.0, "rain_l": 0.0, "spray_l": 0.0}
        for w, n in zip(self.worlds, self.nodes):
            m, L = self.marks.get(n.pid), w.ledger()
            if not m: continue
            rec = max(0.0, (L["lost_nc_wh"] - m["lost_nc_wh"]) - (L["lost_wh"] - m["lost_wh"]))
            tot["node_wh"] += n.node_wh - m["node_wh"]; tot["always_on_wh"] += n.always_on_wh - m["always_on_wh"]; tot["recovered_wh"] += rec
            for key in ("lost_wh", "yield_wh", "tap_l", "rain_l", "spray_l"): tot[key] += L[key] - m[key]
        return {k: round(v, 3) for k, v in tot.items()}
    def state(self):
        w0 = self.worlds[0]
        return {"clock": f"Day {w0.day()} {int(w0.hour()):02d}:{int(w0.hour() % 1 * 60):02d}", "speed": self.speed if self.skip_to is None else self.saved_speed, "skipping": self.skip_to is not None,
                "link": self.link, "api": self.api,
                "sun_wm2": round(w0.irradiance()), "ambient_c": round(w0.ambient(), 1), "cloud": round(w0.cloud, 2), "raining": w0.raining,
                "forecast_rain": w0.forecast_rain, "storm": w0.t < w0.storm_until, "timer": self.nodes[0].timer_on, "sel": self.sel,
                "now": time.time(), "activity": self.act, "today": self.today(),
                "cfg": {"auto_s": self.nodes[0].c["AUTO_CLEAN_MS"] / 1000, "volt_div": self.nodes[0].c["VOLT_DIV"], "zero": self.nodes[0].c["CURR_ZERO_V"], "vpa": self.nodes[0].c["CURR_V_PER_A"],
                        "mvc": self.nodes[0].c["TEMP_MV_PER_C"], "tank_l": TANK_L, "spray_l_s": SPRAY_L_S, "tap_l_s": TAP_L_S,
                        "p_active_mw": P_ACTIVE_MW, "p_sleep_mw": self.nodes[0].c["SLEEP_POWER_MW"]},
                "panels": [{"id": n.pid, "soil_pct": round(w.mean_soil() * 100, 1), "tank": round(w.tank), "faults": w.faults, "node_state": n.cs,
                            "mode": n.mode, "sleep_reason": n.sleep_reason, "wake_in_s": max(0, round(n.wake_at - w.t)) if n.mode == "sleep" else 0,
                            "spray": n.spray, "blower": n.blower, "tap": n.tap_open, "tap_hold": n.tap_hold, "raining": w.raining,
                            "temps": [round(x, 1) for x in w.tcell], "sensors": [round(x, 1) for x in w.tback],
                            "cloud_x": None if w.cloud_x is None else round(w.cloud_x, 2), "soil": [round(w.soil(i), 2) for i in range(len(w.dust))], "stuck": [round(x, 2) for x in w.stuck],
                            "node": {"cs": n.cs, "elapsed_ms": round(time.time() * 1000 - n.cs_start) if n.cs != "IDLE" else 0, "total_ms": n.water_ms if n.cs == "WATER" else n.air_ms,
                                     "timer_on": n.timer_on, "timer_in_s": round(n.c["AUTO_CLEAN_MS"] / 1000 - (w.t - n.boot_sim - n.last_clean_sim)), "adc": n.adc, "last": n.last,
                                     "tank": round(w.tank), "tank_sensor": round(n.tank_pct), "mw": round(n.power_mw(), 1),
                                     "node_wh": round(n.node_wh, 3), "always_on_wh": round(n.always_on_wh, 3), "actuator_wh": round(n.actuator_wh, 4),
                                     "tap_s": round(n.tap_open_s), "spray_s": round(n.spray_s), "sleeps": n.sleeps}}
                           for w, n in zip(self.worlds, self.nodes)],
                "events": sorted(sum([[f"{n.pid} {e}" for e in n.events[-6:]] for n in self.nodes], []))[-14:]}
    def do(self, b):
        c, i = b.get("cmd"), int(b.get("panel", self.sel))
        w, n = self.worlds[i % len(self.worlds)], self.nodes[i % len(self.nodes)]
        w0 = self.worlds[0]
        if c == "select": self.sel = i
        elif c == "storm": w0.storm_until = w0.t + 3600
        elif c == "bird": w.add_bird(random.randrange(len(w.stuck)))
        elif c in ("crack", "hotspot", "shade"): w.faults[c] = not w.faults[c]
        elif c == "cloud": w.cloud_x = 0.0
        elif c == "repair": w.faults = {"crack": False, "hotspot": False, "shade": False}
        elif c == "rain_forecast": w0.forecast_rain = not w0.forecast_rain; w0.rain_at = None
        elif c == "rain_now":
            w0.raining, w0.rain_until, w0.forecast_rain, w0.rain_at = True, w0.t + 5400, False, None
        elif c == "drain": w.tank = 12.0
        elif c == "timer":
            for nn in self.nodes: nn.timer_on = not nn.timer_on
        elif c == "speed": self.speed = self.saved_speed = max(0.0, min(3000.0, float(b.get("value", self.speed))))
        elif c == "skip":                                        # fast-forward to an hour of the day, e.g. 5.5 = 05:30, with all the logic running
            self.skip_to = float(b.get("value", 6)) % 24
        elif c == "dirty": w.set_dust([random.uniform(0.07, 0.17) for _ in w.dust])

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
    print(f"Virtual node sending to {a.api}. Hardware view and operator console: http://localhost:{a.console_port}")
    ThreadingHTTPServer(("0.0.0.0", a.console_port), H).serve_forever()

if __name__ == "__main__":
    main()
