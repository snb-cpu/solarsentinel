"""SolarSentinel ML program. Runs on Pratham's laptop, prints every decision in the terminal and sends it to the final API.

  python ml_worker.py --api http://<IP-OF-THE-MAC>:8000

It listens to the API's readings stream, runs decide.py (classifier, heatmap, forecast, weather rules) on every
reading and POSTs the decision back. If this program stops, the API falls back to its built-in rules after 8 seconds.
Wash handling: when a wash starts it remembers the "before" reading; when the panel has cooled after the wash
it builds a cleaning_result, so the after-cleaning model can tell dirt (gone after a wash) from a real fault (still there).
"""
import argparse, json, re, sys, time, urllib.request
from collections import deque
from datetime import datetime

import warnings; warnings.filterwarnings("ignore")
from decide import decide

COL = {"ok": "32", "dust": "33", "shading": "34", "hotspot": "35", "fault": "31"}
TTY = sys.stdout.isatty()
paint = lambda t, c: f"\033[{c}m{t}\033[0m" if TTY else t

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
    d["model_ms"] = round((time.time() - t0) * 1000)
    p.ok_streak = p.ok_streak + 1 if d["state"] == "ok" else 0
    if p.ok_streak >= 15: p.washed_at = p.cleaning_result = None      # healthy again: forget the wash
    return d

def show(d, last, a):
    key = (d["panel_id"], d["state"], d["clean_now"])
    if a.quiet and last.get(d["panel_id"]) == key: return
    last[d["panel_id"]] = key
    st = paint(f"{d['state']:<8}", COL.get(d["state"], "0"))
    go = paint("WASH NOW", "1;36") if d["clean_now"] else "        "
    stage = {"after_cleaning": "after-wash model", "before_cleaning": "before-wash model"}.get(d.get("diagnosis_stage"), "no analysis")
    print(f"{datetime.now():%H:%M:%S}  {d['panel_id']}  {st}  loss {d['efficiency_loss_pct']:5.1f}%  Rs {d['loss_inr_per_day']:5.1f}/day  {go}  "
          f"[{stage}, {d.get('model_score_pct', 0):.0f}% sure, {d['model_ms']} ms]  {d['reason']}", flush=True)

def post(api, path, body):
    req = urllib.request.Request(api + path, data=json.dumps(body).encode(), headers={"Content-Type": "text/plain"}, method="POST")
    urllib.request.urlopen(req, timeout=3).read()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000"); ap.add_argument("--quiet", action="store_true", help="only print when something changes")
    ap.add_argument("--history-s", type=float, default=3.0, help="how old the comparison reading is, real seconds")
    ap.add_argument("--settle-sim-min", type=float, default=15.0, help="simulated minutes to let a washed panel cool before judging")
    ap.add_argument("--settle-real-s", type=float, default=20.0, help="same, in real seconds, when there is no simulated clock (real hardware)")
    a = ap.parse_args(); a.api = a.api.rstrip("/")
    print(paint("SolarSentinel ML program", "1"), f"-> {a.api}\nStates: " + "  ".join(paint(s, c) for s, c in COL.items()) + "\n", flush=True)
    panels, last = {}, {}
    while True:
        try:
            with urllib.request.urlopen(a.api + "/api/ml/stream", timeout=30) as stream:
                print(paint("connected to the API, waiting for readings...", "2"), flush=True)
                for raw in stream:
                    line = raw.decode().strip()
                    if not line.startswith("data:"): continue
                    try:
                        d = handle(json.loads(line[5:]), panels, a)
                        post(a.api, "/api/decision", d); show(d, last, a)
                    except Exception as e:
                        print(paint(f"skipped a reading: {e}", "31"), flush=True)
        except Exception as e:
            print(paint(f"cannot reach {a.api} ({e}). Retrying in 3 s...", "31"), flush=True); time.sleep(3)

if __name__ == "__main__":
    main()
