"""SolarSentinel API + brain. Laptop B (Pratham). Standard library only.

  python3 2-ml-ai/api/server.py               # listens on :8000
Node (laptop A) -> POST /api/reading, POST /api/weather, GET /api/command
UI   (laptop C) -> GET /events (live stream), POST /api/clean (customer's manual wash)
Decision: uses 2-ml-ai/decide.py `decide(reading, weather) -> dict` if it imports and works, else the built-in rules below.
Replace builtin_decide with real ML step by step; the contract in docs/contract.md must keep holding.
"""
import argparse, json, queue, statistics, sys, threading, time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))          # 2-ml-ai/ so `from decide import decide` works
try:
    from decide import decide as ml_decide
except Exception:
    ml_decide = None

# Money maths, modelled for a small rooftop array and shown on the dashboard.
ARRAY_KW, PEAK_SUN_H, TARIFF_INR, CLEAN_COST_INR = 5.0, 4.8, 8.0, 5.0
ISC_A = 5.5                   # panel current at 100,000 lux, clean. Calibrate on the real rig.
MIN_LUX = 20000               # below this, analysis is paused (night / heavy cloud)
CMD_COOLDOWN_S = 30

def builtin_decide(r, rain):
    t = r["temps_c"]; flat = [x for row in t for x in row]
    med = sorted(flat)[len(flat) // 2]; spread = max(flat) - med
    base = {"panel_id": r["panel_id"], "heatmap": [[round(min(1, max(0, (x - med) / 12)), 2) for x in row] for row in t], "clean_cost_inr": CLEAN_COST_INR}
    if r["ldr_lux"] < MIN_LUX:
        return {**base, "state": "ok", "efficiency_loss_pct": 0.0, "clean_now": False, "loss_inr_per_day": 0.0, "reason": "Low sunlight (night or heavy cloud). Analysis paused."}
    exp_i = ISC_A * r["ldr_lux"] / 100000
    loss = max(0.0, (1 - r["current_a"] / exp_i) * 100)
    cols = [statistics.mean(row[c] for row in t) for c in range(len(t[0]))]
    thr = 3 + 3 * min(1, r["ldr_lux"] / 80000)
    if spread > thr: state = "fault" if loss > 12 else "hotspot"
    elif min(cols) < statistics.mean(flat) - 2 and loss > 20: state = "shading"
    elif loss > 3: state = "dust"
    else: state = "ok"
    inr = loss / 100 * ARRAY_KW * PEAK_SUN_H * TARIFF_INR
    if state in ("fault", "hotspot"): go, why = False, "A cell is overheating and washing will not fix it. No water used. Send a technician."
    elif state == "shading": go, why = False, "Part of the panel is in shade, not dirt. Washing will not help."
    elif state == "ok": go, why = False, "Panel is clean and producing as expected."
    elif rain: go, why = False, "Dust detected, but rain is forecast within 48 h. Letting the rain clean it."
    elif inr > CLEAN_COST_INR: go, why = True, f"Dust is costing Rs {inr:.0f}/day, more than the Rs {CLEAN_COST_INR:.0f} wash. Cleaning now."
    else: go, why = False, "Dust loss is still smaller than the cost of a wash."
    return {**base, "state": state, "efficiency_loss_pct": round(loss, 1), "clean_now": go, "reason": why, "loss_inr_per_day": round(inr, 1)}

class App:
    def __init__(self):
        self.reading = None; self.decision = None; self.rx = 0.0
        self.weather = {"rain_48h": False, "day_factor": [1, .95, .9, 1, 1, .9, 1], "ambient_c": None, "raining": False}
        self.history, self.log, self.clients = [], [], []
        self.pending = None; self.last_cmd = 0.0; self.prev_cs = 0
        self.lock = threading.Lock(); self.say("API started. Waiting for the node.")
    def say(self, m):
        self.log.append({"t": datetime.now().strftime("%H:%M:%S"), "msg": m}); self.log = self.log[-30:]
    def queue_clean(self, why):
        self.pending = {"action": "clean", "water_ms": 4000, "air_ms": 8000, "why": why}; self.last_cmd = time.time()
        self.say(f"Command sent to node: clean ({why})")
    def on_reading(self, r):
        with self.lock:
            r["ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"); self.rx = time.time()
            if self.reading is None: self.say("Node connected.")
            d = None
            if ml_decide:
                try: d = ml_decide(r, self.weather)
                except Exception: d = None
            d = d if d and "state" in d else builtin_decide(r, self.weather["rain_48h"])
            f = self.weather["day_factor"]; loss = d["efficiency_loss_pct"]
            d["forecast_clean_kwh_7d"] = [round(ARRAY_KW * PEAK_SUN_H * x, 1) for x in f]
            d["forecast_kwh_7d"] = [round(c * (1 - loss / 100), 1) for c in d["forecast_clean_kwh_7d"]]
            cs = r.get("clean_state", 0)
            if d["clean_now"] and cs == 0 and not self.pending and time.time() - self.last_cmd > CMD_COOLDOWN_S:
                self.queue_clean("AI decision: " + d["reason"])
            done = self.prev_cs == 2 and cs == 0
            if done: self.say("Node finished cleaning.")
            if cs != self.prev_cs and cs == 1: self.say("Node: water flush")
            if cs != self.prev_cs and cs == 2: self.say("Node: air dry")
            self.prev_cs = cs
            self.reading, self.decision = r, d
            self.history.append({"p": round(r["voltage_v"] * r["current_a"], 1), "c": done}); self.history = self.history[-90:]
        self.push()
    def snapshot(self):
        with self.lock:
            return {"reading": self.reading, "decision": self.decision, "weather": self.weather, "history": self.history, "log": self.log,
                    "age_s": round(time.time() - self.rx, 1) if self.rx else None, "ml": "ML model" if ml_decide else "rules",
                    "econ": {"array_kw": ARRAY_KW, "tariff": TARIFF_INR, "clean_cost": CLEAN_COST_INR}}
    def push(self):
        data = f"data: {json.dumps(self.snapshot())}\n\n".encode()
        for q in list(self.clients): q.put(data)

app = App()

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def reply(self, body=b"{}", ctype="application/json", code=200):
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_OPTIONS(self):
        self.send_response(204); self.send_header("Access-Control-Allow-Origin", "*"); self.send_header("Access-Control-Allow-Headers", "*"); self.end_headers()
    def do_GET(self):
        if self.path.startswith("/events"):
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers()
            q = queue.Queue(); app.clients.append(q); q.put(f"data: {json.dumps(app.snapshot())}\n\n".encode())
            try:
                while True: self.wfile.write(q.get()); self.wfile.flush()
            except Exception: pass
            finally: app.clients.remove(q)
        elif self.path.startswith("/api/command"):
            with app.lock: c, app.pending = app.pending or {}, None
            self.reply(json.dumps(c).encode())
        elif self.path.startswith("/api/state"): self.reply(json.dumps(app.snapshot()).encode())
        else: self.reply((HERE.parent.parent / "1-ui-design" / "webapp" / "index.html").read_bytes(), "text/html; charset=utf-8")
    def do_POST(self):
        try: body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except Exception: return self.reply(code=400)
        if self.path == "/api/reading": app.on_reading(body)
        elif self.path == "/api/weather":
            with app.lock:
                if body.get("rain_48h") != app.weather["rain_48h"]: app.say("Weather feed: rain expected within 48 h" if body.get("rain_48h") else "Weather feed: no rain expected")
                app.weather = body
        elif self.path == "/api/clean":
            with app.lock:
                if app.reading and not app.pending and app.prev_cs == 0: app.queue_clean("customer pressed Clean now")
        else: return self.reply(code=404)
        self.reply()

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8000); a = ap.parse_args()
    threading.Thread(target=lambda: [(app.push(), time.sleep(1.0)) for _ in iter(int, 1)], daemon=True).start()
    print(f"API on http://0.0.0.0:{a.port}  decision: {'Pratham decide.py' if ml_decide else 'built-in rules'}")
    ThreadingHTTPServer(("0.0.0.0", a.port), H).serve_forever()
