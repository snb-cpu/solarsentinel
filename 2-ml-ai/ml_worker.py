"""SolarSentinel ML program. Runs on Pratham's laptop, prints every decision in the terminal and sends it to the API.

  ./run.sh http://<IP-OF-THE-MAC>:8000 --no-sim          # same Wi-Fi (from the project folder; run.bat on Windows)
  ./run.sh https://solarsentinel-api.pages.dev --no-sim  # through Cloudflare, works from anywhere
(run.sh builds the Python environment the first time and then runs:  2-ml-ai/venv/bin/python ml_worker.py --api <address>)

It long-polls the API for readings, runs decide.py (classifier, heatmap, forecast, weather rules) on each one
and POSTs the verdicts back. If this program stops, the API falls back to its built-in rules after 8 seconds.
Wash handling: when a wash starts it remembers the "before" reading; when the panel has cooled after the wash
it builds a cleaning_result, so the after-cleaning model can tell dirt (gone after a wash) from a real fault.
"""
import argparse, json, os, re, shutil, sys, time, urllib.request
from collections import deque
from datetime import datetime

print("SolarSentinel ML program: loading the models (the first start after installing can take a minute)...", flush=True)
import warnings; warnings.filterwarnings("ignore")
from decide import decide

if os.name == "nt": os.system("")                         # lets the Windows console understand colours
COL = {"ok": "32", "dust": "33", "shading": "34", "hotspot": "35", "fault": "31"}
NAME = {"ok": "healthy", "dust": "dusty", "shading": "shaded", "hotspot": "hot cell", "fault": "cracked cell"}
TTY = sys.stdout.isatty()
paint = lambda t, c: f"\033[{c}m{t}\033[0m" if TTY and c else t

def sim_minutes(clock):                                   # "Day 1 10:15" -> minutes since day 1 00:00, or None on real hardware
    m = re.match(r"Day (\d+) (\d+):(\d+)", clock or "")
    return (int(m[1]) - 1) * 1440 + int(m[2]) * 60 + int(m[3]) if m else None

class Panel:
    def __init__(self):
        self.hist = deque(maxlen=60); self.cs = 0; self.before = None
        self.washed_at = None; self.cleaning_result = None; self.ok_streak = 0
    def settled(self, r, a):
        now_sim, then_sim = sim_minutes(r.get("sim_clock")), self.washed_at["sim"]
        if now_sim is not None and then_sim is not None: return now_sim - then_sim >= a.settle_sim_min
        return time.time() - self.washed_at["real"] >= a.settle_real_s

def history_for(p, a):                                    # a reading about history_s seconds old
    cutoff = time.time() - a.history_s
    old = [r for t, r in p.hist if t <= cutoff]
    return [old[-1]] if old else None

def handle(msg, panels, a):
    r, weather = msg["reading"], msg["weather"]
    p = panels.setdefault(r["panel_id"], Panel())
    cs = r.get("clean_state", 0)
    if p.cs == 0 and cs == 1:                              # a wash is starting: keep the last reading from before it
        p.before = p.hist[-1][1] if p.hist else r; p.washed_at = None; p.cleaning_result = None
    if p.cs != 0 and cs == 0:                              # wash finished: start the cool-down clock
        p.washed_at = {"sim": sim_minutes(r.get("sim_clock")), "real": time.time()}
    p.cs = cs
    note = None
    if p.washed_at and p.cleaning_result is None:
        if p.settled(r, a) and p.before:
            b = p.before
            p.cleaning_result = {"power_before_w": max(b["voltage_v"] * b["current_a"], 0.01), "power_after_w": r["voltage_v"] * r["current_a"],
                                 "temps_before_c": b["temps_c"], "temps_after_c": r["temps_c"]}
            p.ok_streak = 0
        else:
            note = "Washed. Waiting for the panel to cool, then checking again."
    if cs != 0: note = "Cleaning in progress."
    use_cr = p.cleaning_result                              # sticky: a fault confirmed after a wash stays confirmed
    t0 = time.time()
    d = decide(r, history=history_for(p, a), cleaning_result=use_cr, weather=weather)
    p.hist.append((time.time(), r))
    if note:                                               # do not judge or re-wash a panel that is wet or still hot from the wash
        d["clean_now"] = False; d["reason"] = note
        if d["state"] in ("hotspot", "fault"): d["state"] = "dust"
        for t in d.get("trace", []):
            if t["step"] == "Decision": t.update(ok=False, text=note)
    d["model_ms"] = round((time.time() - t0) * 1000)
    p.ok_streak = p.ok_streak + 1 if d["state"] == "ok" else 0
    if p.ok_streak >= 15: p.washed_at = p.cleaning_result = None      # healthy again: forget the wash
    return d

# ---- the terminal view: one aligned line per verdict ----
HEAD = f"{'time':<8}  {'panel':<5}  {'verdict':<12}  {'loss':>6}  {'per day':>8}  {'action':<8}  {'model':<15}  {'ms':>4}  why"
FIXED = len(HEAD) - 3
class Screen:
    def __init__(self): self.lines = 0; self.last = {}
    def header(self):
        print(paint(HEAD, "1") + "\n" + "-" * min(shutil.get_terminal_size((120, 30)).columns, 140), flush=True); self.lines = 0
    def show(self, d, a):
        key = (d["panel_id"], d["state"], d["clean_now"])
        if a.quiet and self.last.get(d["panel_id"]) == key: return
        self.last[d["panel_id"]] = key
        if self.lines % 20 == 0: self.header()
        self.lines += 1
        stage = {"after_cleaning": "after-wash", "before_cleaning": "before-wash"}.get(d.get("diagnosis_stage"), "no analysis")
        model = f"{stage} {d.get('model_score_pct', 0):.0f}%" if d.get("model_score_pct") else stage
        room = max(20, shutil.get_terminal_size((120, 30)).columns - FIXED) if TTY else 10 ** 6    # cut the reason to fit a terminal, never in a log file
        why = d["reason"] if len(d["reason"]) <= room else d["reason"][:room - 1] + "…"
        verdict = paint(f"{NAME.get(d['state'], d['state']):<12}", COL.get(d["state"]))
        action = paint("WASH NOW", "1;36") if d["clean_now"] else "-       "
        cost = "Rs " + format(d["loss_inr_per_day"], ".0f")
        print(f"{datetime.now():%H:%M:%S}  {d['panel_id']:<5}  {verdict}  {d['efficiency_loss_pct']:>5.1f}%  {cost:>8}  {action}  {model:<15}  {d['model_ms']:>4}  {why}", flush=True)

def call(a, path, body=None, timeout=30):
    req = urllib.request.Request(a.api + path, data=None if body is None else json.dumps(body).encode(), method="GET" if body is None else "POST",
                                 headers={"Content-Type": "text/plain", "User-Agent": "SolarSentinel-ml/1.0", **({"X-Key": a.key} if a.key else {})})
    with urllib.request.urlopen(req, timeout=timeout) as r: return json.loads(r.read() or b"{}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000"); ap.add_argument("--quiet", action="store_true", help="only print when something changes")
    ap.add_argument("--key", default=os.environ.get("SS_KEY", ""), help="the API's access key, if it has one (also SS_KEY)")
    ap.add_argument("--history-s", type=float, default=3.0, help="how old the comparison reading is, real seconds")
    ap.add_argument("--settle-sim-min", type=float, default=15.0, help="simulated minutes to let a washed panel cool before judging")
    ap.add_argument("--settle-real-s", type=float, default=20.0, help="same, in real seconds, when there is no simulated clock (real hardware)")
    a = ap.parse_args(); a.api = a.api.rstrip("/")
    print(paint("SolarSentinel ML program", "1") + f"   API {a.api}" + ("" if a.api.startswith("https://") else f"   web view {a.api}/ml/"))
    print("verdicts: " + "  ".join(paint(n, COL[s]) for s, n in NAME.items()) + "\n", flush=True)
    panels, screen, cursor = {}, Screen(), -1
    while True:
        try:
            r = call(a, f"/api/ml/poll?since={cursor}&wait=20", timeout=35)
        except Exception as e:
            print(paint(f"cannot reach {a.api} ({e}). Retrying in 3 s...", "31"), flush=True); cursor = -1; time.sleep(3); continue
        if cursor < 0: print(paint("connected to the API, waiting for readings...", "2"), flush=True)
        cursor, out = r["seq"], []
        for msg in r["msgs"]:
            try:
                d = handle(msg, panels, a); out.append(d); screen.show(d, a)
            except Exception as e:
                print(paint(f"skipped a reading: {e}", "31"), flush=True)
        if out:
            try: call(a, "/api/decision", out, timeout=10)
            except Exception as e: print(paint(f"could not send the verdicts: {e}", "31"), flush=True)

if __name__ == "__main__":
    main()
