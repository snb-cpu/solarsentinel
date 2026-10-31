"""SolarSentinel API + brain (the "hub"). Standard library only.

  python3 2-ml-ai/api/server.py               # listens on :8000, also serves the web pages
Node (the Mac's virtual panels, or a real ESP32) -> POST /api/sync (virtual node: everything in one call each second)
                                                    or POST /api/reading, POST /api/status, GET /api/command (real firmware)
ML program (Pratham)  -> GET /api/ml/poll (readings), POST /api/decision (verdicts)
Web pages             -> GET /events (live stream) or GET /api/state, POST /api/clean, POST /api/sim (demo controls)
Decision: the ML program's if it answered in the last 8 s, else the built-in rules below.
The same contract is implemented by the Cloudflare version in cloud/hub/ (docs/contract.md). Keep them in step.
"""
import argparse, json, mimetypes, os, queue, statistics, threading, time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
SHARED = ROOT / "shared"
SITES = {"app": ROOT / "1-ui-design" / "webapp", "ml": ROOT / "2-ml-ai" / "console"}
mimetypes.add_type("font/woff2", ".woff2"); mimetypes.add_type("text/javascript", ".js")
KEY = os.environ.get("SS_KEY", "")   # optional: when set, the machine endpoints need the header X-Key

# Money maths, per panel (one node = one 1.5 kW string), shown on the dashboard.
ARRAY_KW, PEAK_SUN_H, TARIFF_INR, CLEAN_COST_INR = 1.5, 4.8, 8.0, 2.0   # per panel: each node watches a 1.5 kW string
ISC_A = 5.5                   # panel current at 100,000 lux, clean. Calibrate on the real rig.
MIN_LUX = 20000               # below this, analysis is paused (night / heavy cloud)
CMD_COOLDOWN_S = 30
TANK_L, SPRAY_L_S, TAP_L_S = 20.0, 0.2, 0.17      # litres, and litres per second through the spray valve and the tap inlet valve (same as the firmware and the simulator)
MIN_TANK_PCT = 20             # below this a wash is put off until the tap inlet has refilled the tank
ML_STALE_S = 8                # if the ML program (Pratham's laptop) has not answered for a panel in this long, fall back to the built-in rules
ML_POLL_GRACE_S = 25          # the ML program counts as connected this long after its last poll
SETTLE_S = 25                 # real seconds to let a washed panel cool before judging a hot spot (assumes demo speed of 60x or more)

def builtin_decide(r, rain, ctx=None):
    ctx = ctx or {}
    t = r["temps_c"]; flat = [x for row in t for x in row]
    med = sorted(flat)[len(flat) // 2]; spread = max(flat) - med
    base = {"panel_id": r["panel_id"], "heatmap": [[round(min(1, max(0, (x - med) / 12)), 2) for x in row] for row in t], "clean_cost_inr": CLEAN_COST_INR}
    if r["ldr_lux"] < MIN_LUX:
        return {**base, "state": "ok", "efficiency_loss_pct": 0.0, "clean_now": False, "loss_inr_per_day": 0.0, "reason": "Low sunlight (night or heavy cloud). Analysis paused."}
    exp_i = ISC_A * r["ldr_lux"] / 100000
    corners = r.get("ldr_corners_lux") or []
    uneven = len(corners) > 1 and (max(corners) - min(corners)) / max(sum(corners) / len(corners), 1) > 0.25   # corner light sensors disagree: a shadow or cloud
    loss = max(0.0, (1 - r["current_a"] / exp_i) * 100)
    cols = [statistics.mean(row[c] for row in t) for c in range(len(t[0]))]
    thr = 3 + 3 * min(1, r["ldr_lux"] / 80000)
    hot = spread > thr
    if hot and not ctx.get("washed_hot"): state = "dust"                 # first assume dirt (a dropping): wash once and see if it clears
    elif hot and time.time() < ctx.get("settle_until", 0): state = "dust"   # washed, give the panel time to cool before judging
    elif hot: state = "fault" if loss > 12 else "hotspot"
    elif uneven and loss > 3: state = "shading"
    elif min(cols) < statistics.mean(flat) - 2 and loss > 20: state = "shading"
    elif loss > 3: state = "dust"
    else: state = "ok"
    inr = loss / 100 * ARRAY_KW * PEAK_SUN_H * TARIFF_INR
    if state == "dust" and hot:
        go = not ctx.get("washed_hot")
        why = "Local hot patch, probably a bird dropping or dirt. Washing first to find out." if go else "Washed. Waiting for the panel to cool, then checking if the hot spot is gone."
        return {**base, "state": state, "efficiency_loss_pct": round(loss, 1), "clean_now": go, "reason": why, "loss_inr_per_day": round(inr, 1), "hot": True}
    if state in ("fault", "hotspot"): go, why = False, "A cell is overheating and washing will not fix it. No water used. Send a technician."
    elif state == "shading": go, why = False, ("Uneven light across the panel (a shadow or passing cloud), not dirt. No wash." if uneven else "Part of the panel is in shade, not dirt. Washing will not help.")
    elif state == "ok": go, why = False, "Panel is clean and producing as expected."
    elif rain: go, why = False, "Dust detected, but rain is forecast within 48 h. Letting the rain clean it."
    elif 0 <= r.get("tank_level_pct", 100) < MIN_TANK_PCT: go, why = False, "Dust detected, but the water tank is low. Refilling it from the tap first."
    elif inr > CLEAN_COST_INR: go, why = True, f"Dust is costing Rs {inr:.0f}/day, more than the Rs {CLEAN_COST_INR:.0f} wash. Cleaning now."
    else: go, why = False, "Dust loss is still smaller than the cost of a wash."
    return {**base, "state": state, "efficiency_loss_pct": round(loss, 1), "clean_now": go, "reason": why, "loss_inr_per_day": round(inr, 1), "hot": hot}

class App:
    def __init__(self):
        self.p = {}                       # panel_id -> {reading, decision, rx, history, pending, last_cmd, prev_cs}
        self.weather = {"rain_48h": False, "day_factor": [1, .95, .9, 1, 1, .9, 1], "ambient_c": None, "raining": False}
        self.site_hist, self.washed, self.log, self.clients, self.feed = [], False, [], [], []
        self.simq, self.sim = [], None    # demo controls: web page -> API -> simulator, and the simulator's state back to the page
        self.ml_clients = []              # ML programs on the older /api/ml/stream
        self.mlcv, self.mlseq, self.mlbuf, self.ml_poll_at = threading.Condition(), 0, [], 0.0   # ...or long-polling /api/ml/poll
        self.lock = threading.Lock(); self.say("API started. Waiting for the panel nodes.")
    def say(self, m):
        self.log.append({"t": datetime.now().strftime("%H:%M:%S"), "ts": round(time.time(), 1), "msg": m}); self.log = self.log[-40:]
    def ml_connected(self): return bool(self.ml_clients) or time.time() - self.ml_poll_at < ML_POLL_GRACE_S
    def queue_clean(self, pid, why):
        st = self.p[pid]; st["pending"] = {"action": "clean", "water_ms": 4000, "air_ms": 8000, "why": why}; st["last_cmd"] = time.time()
        self.say(f"{pid}: clean command sent ({why})")
    def on_reading(self, r):
        with self.lock:
            pid = r.get("panel_id", "P1"); r["ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if pid not in self.p:
                self.p[pid] = {"washed_hot": False, "settle_until": 0.0, "reading": None, "decision": None, "source": "rules", "ml_at": 0.0, "mode": "active", "sleep": None,
                               "rx": 0.0, "history": [], "pending": None, "last_cmd": 0.0, "prev_cs": 0}
                self.say(f"{pid}: node connected.")
            st = self.p[pid]; st["rx"] = time.time(); st["reading"] = r
            if st["mode"] == "sleep": self.say(f"{pid}: woke up (daylight and dry)."); st["mode"], st["sleep"] = "active", None
            cs = r.get("clean_state", 0)
            done = st["prev_cs"] == 2 and cs == 0
            if done:
                self.say(f"{pid}: cleaning finished."); self.washed = True
                if st.get("was_hot"): st["washed_hot"], st["settle_until"] = True, time.time() + SETTLE_S
            if cs != st["prev_cs"] and cs == 1: self.say(f"{pid}: water flush")
            if cs != st["prev_cs"] and cs == 2: self.say(f"{pid}: air dry")
            st["prev_cs"] = cs
            st["history"].append({"p": round(r["voltage_v"] * r["current_a"], 1), "c": done}); st["history"] = st["history"][-90:]
            if pid == min(self.p):                                  # one site-power point per round of readings
                self.site_hist.append({"p": round(sum((x["history"][-1]["p"] if x["history"] else 0) for x in self.p.values()), 1), "c": self.washed})
                self.site_hist, self.washed = self.site_hist[-90:], False
            ml = self.ml_connected()
            if ml: self.ml_send({"reading": r, "weather": self.weather})                  # the ML program decides...
            if not (ml and time.time() - st["ml_at"] < ML_STALE_S):                       # ...unless it is offline or silent
                if st["source"] == "ml": self.say(f"{pid}: ML program not answering, using built-in rules."); st["source"] = "rules"
                d = builtin_decide(r, self.weather["rain_48h"], st); st["was_hot"] = bool(d.get("hot"))
                if not d.get("hot") and time.time() > st["settle_until"]: st["washed_hot"] = False
                self.apply(pid, st, d)
        self.push()
    def apply(self, pid, st, d):
        """Common path for a decision from the ML program or the built-in rules."""
        f, loss = self.weather["day_factor"], d["efficiency_loss_pct"]
        if len(d.get("forecast_kwh_7d") or []) != 7 or not any(d["forecast_kwh_7d"]):
            d["forecast_clean_kwh_7d"] = [round(ARRAY_KW * PEAK_SUN_H * x, 2) for x in f]
            d["forecast_kwh_7d"] = [round(c * (1 - loss / 100), 2) for c in d["forecast_clean_kwh_7d"]]
        prev = st["decision"]; st["decision"] = d
        if not prev or (prev["state"], prev["clean_now"]) != (d["state"], d["clean_now"]):      # the feed shows changes, not every reading
            self.feed.append({"ts": round(time.time(), 1), "panel": pid, "state": d["state"], "clean_now": d["clean_now"], "loss": d["efficiency_loss_pct"],
                              "inr": d["loss_inr_per_day"], "reason": d["reason"], "source": st["source"]})
            self.feed = self.feed[-60:]
        if d["clean_now"] and st["prev_cs"] == 0 and not st["pending"] and time.time() - st["last_cmd"] > CMD_COOLDOWN_S:
            self.queue_clean(pid, "AI decision: " + d["reason"])
    def on_status(self, b):                                         # the node says it is going to sleep (so it is not 'offline')
        with self.lock:
            pid = b.get("panel_id"); st = self.p.get(pid)
            if not st or b.get("mode") != "sleep": return
            why = {"dark": "it is dark or heavily overcast", "rain": "it is raining"}.get(b.get("reason"), b.get("reason"))
            self.say(f"{pid}: going to sleep because {why}. Radio and sensors off; it looks at the sun every {int(b.get('wake_s', 0)) // 60} min.")
            st["mode"], st["sleep"] = "sleep", {"reason": b.get("reason"), "wake_s": b.get("wake_s"), "since": time.time()}
        self.push()
    def on_decision(self, d):                                       # from the ML program
        with self.lock:
            st = self.p.get(d.get("panel_id"))
            if not st or "state" not in d: return
            if st["source"] != "ml": self.say(f"{d['panel_id']}: decisions now come from the ML program."); st["source"] = "ml"
            st["ml_at"] = time.time(); self.apply(d["panel_id"], st, d)
        self.push()
    def set_weather(self, body):
        with self.lock:
            if body.get("rain_48h") != self.weather["rain_48h"]: self.say("Weather feed: rain expected within 48 h" if body.get("rain_48h") else "Weather feed: no rain expected")
            self.weather = body
    def take_command(self, pid):                                    # what a node should do now (a clean order, at most one) plus the tap policy
        with self.lock:
            st = self.p.get(pid); c = (st["pending"] or {}) if st else {}
            if st: st["pending"] = None
            hold = bool(self.weather.get("rain_48h"))               # rain is coming: do not buy tap water unless the tank is critical
        return {**c, "tap_hold": hold}
    def on_sync(self, b):
        """Everything the virtual node says in one second, and everything it needs back."""
        for s in b.get("status") or []: self.on_status(s)
        if b.get("weather"): self.set_weather(b["weather"])
        if b.get("simstate") is not None: self.sim = b["simstate"]
        for r in b.get("readings") or []: self.on_reading(r)
        cmds = {pid: self.take_command(pid) for pid in (b.get("panels") or [])}
        with self.lock: q, self.simq = self.simq, []
        return {"commands": cmds, "simcmds": q}
    def on_sim(self, body):
        with self.lock: self.simq.append(body)
        self.say(f"Demo control: {body.get('cmd')}" + (f" on panel {int(body.get('panel', 0)) + 1}" if body.get("cmd") in ("bird", "dirty", "shade", "hotspot", "crack", "repair") else ""))
    def on_clean(self, body):
        with self.lock:
            for pid in ([body["panel_id"]] if body.get("panel_id") in self.p else list(self.p)):
                st = self.p[pid]
                if not st["pending"] and st["prev_cs"] == 0: self.queue_clean(pid, "customer pressed Clean now")
    def ml_send(self, msg):
        data = f"data: {json.dumps(msg)}\n\n".encode()
        for q in list(self.ml_clients): q.put(data)
        with self.mlcv:
            self.mlseq += 1; self.mlbuf = (self.mlbuf + [(self.mlseq, msg)])[-200:]; self.mlcv.notify_all()
    def ml_poll(self, since, wait):
        """Long poll for the ML program: waits up to `wait` s for readings newer than `since`. since < 0 only returns the cursor."""
        self.ml_poll_at = time.time()
        with self.mlcv:
            if since < 0: return {"seq": self.mlseq, "msgs": []}
            if self.mlseq <= since: self.mlcv.wait(wait)
            self.ml_poll_at = time.time()
            return {"seq": self.mlseq, "msgs": [m for s, m in self.mlbuf if s > since]}
    def snapshot(self):
        with self.lock:
            now, panels = time.time(), []
            for pid in sorted(self.p):
                x = self.p[pid]; panels.append({"id": pid, "mode": x["mode"], "sleep": x["sleep"], "source": x["source"], "reading": x["reading"], "decision": x["decision"], "history": x["history"],
                                                "age_s": round(now - x["rx"], 1), "ml_age_s": round(now - x["ml_at"], 1) if x["ml_at"] else None})
            ds = [x["decision"] for x in self.p.values() if x["decision"]]
            rd = [x["reading"] for x in self.p.values() if x["reading"]]
            site = {"power_w": round(sum(x["history"][-1]["p"] for x in self.p.values() if x["history"] and x["mode"] == "active"), 1),
                    "node_mw": round(sum(x["reading"].get("node_mw", 0) for x in self.p.values() if x["reading"] and x["mode"] == "active"), 1),
                    "asleep": sum(1 for x in self.p.values() if x["mode"] == "sleep"),
                    "node_wh": round(sum(r.get("node_wh", 0) for r in rd), 3),
                    "tap_l": round(sum(r.get("tap_s", 0) for r in rd) * TAP_L_S, 1), "spray_l": round(sum(r.get("spray_s", 0) for r in rd) * SPRAY_L_S, 1),
                    "tap_open": sum(1 for r in rd if r.get("tap_open")),
                    "loss_inr_per_day": round(sum(d["loss_inr_per_day"] for d in ds), 1), "history": self.site_hist,
                    "forecast_kwh_7d": [round(sum(d["forecast_kwh_7d"][i] for d in ds), 1) for i in range(7)] if ds else [],
                    "forecast_clean_kwh_7d": [round(sum(d["forecast_clean_kwh_7d"][i] for d in ds), 1) for i in range(7)] if ds else []}
            return {"panels": panels, "site": site, "weather": self.weather, "log": self.log, "feed": self.feed[-30:], "ml": ("ML model" if any(x["source"] == "ml" for x in self.p.values()) else "built-in rules"),
                    "ml_connected": self.ml_connected(), "sim": self.sim, "now": round(now, 1),
                    "econ": {"panel_kw": ARRAY_KW, "tariff": TARIFF_INR, "clean_cost": CLEAN_COST_INR, "tank_l": TANK_L, "tap_l_s": TAP_L_S, "spray_l_s": SPRAY_L_S}}
    def push(self):
        data = f"data: {json.dumps(self.snapshot())}\n\n".encode()
        for q in list(self.clients): q.put(data)

app = App()

def static_file(path):
    """The web pages: / = customer app, /ml = ML console, /shared = fonts, styles, scripts. Nothing outside those folders."""
    path = unquote(path)
    if path.startswith("/shared/"): root, rel = SHARED, path[len("/shared/"):]
    elif path == "/ml" or path.startswith("/ml/"): root, rel = SITES["ml"], path[3:].lstrip("/")
    else: root, rel = SITES["app"], path.lstrip("/")
    f = (root / (rel or "index.html")).resolve()
    return f if f.is_file() and root.resolve() in f.parents else None

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def reply(self, body=b"{}", ctype="application/json", code=200, cache="no-store"):
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Access-Control-Allow-Origin", "*"); self.send_header("Cache-Control", cache)
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def stream(self):
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-cache"); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers()
    def authorized(self, qs): return not KEY or self.headers.get("X-Key") == KEY or qs.get("key") == KEY
    def do_OPTIONS(self):
        self.send_response(204); self.send_header("Access-Control-Allow-Origin", "*"); self.send_header("Access-Control-Allow-Headers", "*"); self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS"); self.end_headers()
    def do_GET(self):
        u = urlsplit(self.path); path, qs = u.path, {k: v[0] for k, v in parse_qs(u.query).items()}
        machine = path in ("/api/command", "/api/ml/poll", "/api/ml/stream", "/api/simcmd")
        if machine and not self.authorized(qs): return self.reply(b'{"error":"key"}', code=401)
        if path == "/events":
            self.stream(); q = queue.Queue(); app.clients.append(q); q.put(f"data: {json.dumps(app.snapshot())}\n\n".encode())
            try:
                while True: self.wfile.write(q.get()); self.wfile.flush()
            except Exception: pass
            finally: app.clients.remove(q)
        elif path == "/api/command": self.reply(json.dumps(app.take_command(qs.get("panel", "P1")), separators=(",", ":")).encode())
        elif path == "/api/ml/poll":
            try: since, wait = int(qs.get("since", -1)), min(float(qs.get("wait", 20)), 25)
            except ValueError: return self.reply(code=400)
            self.reply(json.dumps(app.ml_poll(since, wait)).encode())
        elif path == "/api/ml/stream":
            self.stream(); q = queue.Queue(); app.ml_clients.append(q); app.say("ML program connected.")
            try:
                while True: self.wfile.write(q.get()); self.wfile.flush()
            except Exception: pass
            finally: app.ml_clients.remove(q); app.say("ML program disconnected.")
        elif path == "/api/simcmd":
            with app.lock: c, app.simq = app.simq, []
            self.reply(json.dumps({"cmds": c}).encode())
        elif path == "/api/state": self.reply(json.dumps(app.snapshot()).encode())
        else:
            f = static_file(path)
            if not f: return self.reply(b"Not found", "text/plain", 404)
            ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
            self.reply(f.read_bytes(), ctype + ("; charset=utf-8" if ctype.startswith("text/") else ""), cache="no-store" if f.suffix in (".html", ".js", ".css") else "max-age=3600")
    def do_POST(self):
        u = urlsplit(self.path); path, qs = u.path, {k: v[0] for k, v in parse_qs(u.query).items()}
        try: body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except Exception: return self.reply(code=400)
        if path in ("/api/reading", "/api/status", "/api/weather", "/api/decision", "/api/simstate", "/api/sync") and not self.authorized(qs): return self.reply(b'{"error":"key"}', code=401)
        out = {}
        if path == "/api/reading": app.on_reading(body)
        elif path == "/api/sync": out = app.on_sync(body)
        elif path == "/api/weather": app.set_weather(body)
        elif path == "/api/decision":
            for d in (body if isinstance(body, list) else [body]): app.on_decision(d)       # one verdict, or a batch
        elif path == "/api/status": app.on_status(body)
        elif path == "/api/sim": app.on_sim(body)
        elif path == "/api/simstate": app.sim = body
        elif path == "/api/clean": app.on_clean(body)
        else: return self.reply(code=404)
        self.reply(json.dumps(out).encode())

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8000); ap.add_argument("--key", default=KEY, help="require this key (header X-Key) from the machines; also SS_KEY")
    a = ap.parse_args(); KEY = a.key
    try: httpd = ThreadingHTTPServer(("0.0.0.0", a.port), H)
    except OSError: raise SystemExit(f"Port {a.port} is already in use, so the API is probably already running.\nStop it with:  pkill -f api/server.py     or run this one on another port with:  --port {a.port + 1}")
    threading.Thread(target=lambda: [(app.push(), time.sleep(1.0)) for _ in iter(int, 1)], daemon=True).start()
    print(f"API on http://0.0.0.0:{a.port}   customer app: /   ML console: /ml/   {'(machines need X-Key)' if KEY else ''}")
    print(f"decisions: the ML program if it is connected (on its machine, from the project folder:  ./run.sh http://THIS-IP:{a.port} --no-sim), else built-in rules")
    httpd.serve_forever()
