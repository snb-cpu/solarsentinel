"""Checks that an API keeps the contract in docs/contract.md. Run it against the Python hub and the Cloudflare one.

  python3 2-ml-ai/api/server.py --port 8001 &            # a spare copy, so the real demo is not disturbed
  python3 cloud/contract_test.py http://localhost:8001
  python3 cloud/contract_test.py https://solarsentinel-api.pages.dev --room test        # --room keeps the test away from the real demo
  python3 cloud/contract_test.py https://solarsentinel-api.pages.dev --room test --key SECRET

It plays a panel called T9: node, ML program, web page and simulator, in the order they would talk. Standard library only.
"""
import argparse, json, sys, time, urllib.error, urllib.request

ap = argparse.ArgumentParser(); ap.add_argument("base"); ap.add_argument("--key", default=""); ap.add_argument("--room", default="")
A = ap.parse_args(); BASE = A.base.rstrip("/")
fails = []

def call(path, body=None, key=True, method=None, timeout=30, raw=False):
    if A.room: path += ("&" if "?" in path else "?") + "room=" + A.room
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(), method=method or ("GET" if body is None else "POST"),
                                 headers={"Content-Type": "text/plain", "User-Agent": "SolarSentinel-test/1.0", **({"X-Key": A.key} if A.key and key else {})})
    if raw: return urllib.request.urlopen(req, timeout=timeout)       # a stream the caller reads and closes
    with urllib.request.urlopen(req, timeout=timeout) as r: return json.loads(r.read() or b"{}")

def check(name, cond, extra=""):
    print(("  ok    " if cond else "  FAIL  ") + name + (f"   {extra}" if extra and not cond else ""), flush=True)
    if not cond: fails.append(name)

def reading(current=2.0, clean_state=0):                     # a clearly dusty panel at midday
    return {"panel_id": "T9", "voltage_v": 17.5, "current_a": current, "ldr_lux": 80000, "ldr_corners_lux": [80000] * 4, "temps_c": [[44.0, 44.2, 44.1, 44.3], [44.1, 44.4, 44.0, 44.2]],
            "tank_level_pct": 70, "clean_state": clean_state, "tap_open": 0, "rain": 0, "node_mw": 250, "node_wh": 1.0, "tap_s": 0, "spray_s": 0, "sim_clock": "Day 1 12:00"}
SIMSTATE = {"clock": "Day 1 12:00", "speed": 120, "panels": [{"id": "T9", "faults": {}}], "today": {}}
WEATHER = {"rain_48h": False, "day_factor": [1] * 7, "ambient_c": 30.0, "raining": False}
def sync(readings=(), panels=("T9",), **kw): return call("/api/sync", {"readings": list(readings), "panels": list(panels), "simstate": SIMSTATE, "weather": WEATHER, **kw})
def panel(): return next((p for p in call("/api/state")["panels"] if p["id"] == "T9"), None)

print(f"contract test against {BASE}" + (f" (room {A.room})" if A.room else ""))
r = sync([reading()])
check("sync answers with commands and simcmds", set(r) >= {"commands", "simcmds"} and "T9" in r["commands"])
check("tap_hold is a boolean and false with no rain forecast", r["commands"]["T9"].get("tap_hold") is False)
p = panel()
check("the panel appears with its reading and a decision", bool(p and p["reading"]["panel_id"] == "T9" and p["decision"] and p["decision"]["state"] in ("ok", "dust", "shading", "hotspot", "fault")))
check("a reading gets a server timestamp", bool(p and p["reading"].get("ts")))
st = call("/api/state")
check("state carries site totals, weather, log, feed, econ and the simulator state", all(k in st for k in ("site", "weather", "log", "feed", "econ")) and st["sim"]["clock"] == "Day 1 12:00")
check("site has a power history and a 7-day forecast", isinstance(st["site"]["history"], list) and len(st["site"]["forecast_kwh_7d"]) == 7 and len(st["site"]["forecast_clean_kwh_7d"]) == 7)
if p["source"] == "rules":
    check("a dusty panel decided by the rules gets a clean order", r["commands"]["T9"].get("action") == "clean" and r["commands"]["T9"].get("water_ms") == 4000, str(r["commands"]["T9"]))
check("the decision feed has entries with a time, panel and state", bool(st["feed"]) and all({"ts", "panel", "state"} <= set(f) for f in st["feed"]))

call("/api/sim", {"cmd": "cloud", "panel": 0})
r = sync([])
check("a demo control from a web page reaches the simulator once", len(r["simcmds"]) == 1 and r["simcmds"][0]["cmd"] == "cloud")
check("...and is not delivered twice", sync([])["simcmds"] == [])

call("/api/clean", {"panel_id": "T9"})
check("the customer's Clean now becomes a clean order", sync([reading()])["commands"]["T9"].get("action") == "clean")

call("/api/status", {"panel_id": "T9", "mode": "sleep", "reason": "dark", "wake_s": 1200})
check("a sleep notice marks the panel asleep, not offline", panel()["mode"] == "sleep" and panel()["sleep"]["reason"] == "dark")
sync([reading()])
check("the next reading wakes it", panel()["mode"] == "active")

cur = call("/api/ml/poll?since=-1")["seq"]
sync([reading()])
got = call(f"/api/ml/poll?since={cur}&wait=5", timeout=15)
check("the ML program's long poll returns the new reading and the weather", len(got["msgs"]) >= 1 and got["msgs"][0]["reading"]["panel_id"] == "T9" and "weather" in got["msgs"][0] and got["seq"] > cur)
t0 = time.time(); empty = call(f"/api/ml/poll?since={got['seq']}&wait=1", timeout=10)
check("an idle long poll waits, then returns nothing", empty["msgs"] == [] and time.time() - t0 >= 0.8)

verdict = {"panel_id": "T9", "state": "ok", "efficiency_loss_pct": 0.0, "clean_now": False, "loss_inr_per_day": 0.0, "clean_cost_inr": 2.0, "reason": "test verdict", "heatmap": [[0.0] * 4] * 2,
           "forecast_kwh_7d": [3.0] * 7, "forecast_clean_kwh_7d": [3.0] * 7, "model_ms": 3, "trace": [{"step": "Light", "ok": True, "text": "even"}]}
call("/api/decision", [verdict])
p = panel()
check("a batch of ML verdicts is accepted and takes over from the rules", p["source"] == "ml" and p["decision"]["reason"] == "test verdict" and p["decision"]["trace"][0]["step"] == "Light" and p["ml_age_s"] is not None)
check("the state says the ML program is connected", call("/api/state")["ml_connected"] is True)

c = call("/api/command?panel=T9")
check("the single-panel command call (real firmware) answers with tap_hold", "tap_hold" in c)

try:
    resp = call("/events", raw=True, timeout=10)
    first = resp.readline().decode()
    check("the live stream (/events) starts with a snapshot", first.startswith("data:") and "panels" in json.loads(first[5:]), repr(first[:100]))
    resp.close()
except Exception as e:
    check("the live stream (/events) starts with a snapshot", False, str(e))

req = urllib.request.Request(BASE + "/api/state" + (f"?room={A.room}" if A.room else ""), method="OPTIONS", headers={"User-Agent": "SolarSentinel-test/1.0", "Origin": "https://example.org", "Access-Control-Request-Method": "POST"})
try:
    with urllib.request.urlopen(req, timeout=10) as o: check("web pages on other addresses may call it (CORS)", o.headers.get("Access-Control-Allow-Origin") == "*")
except Exception as e: check("web pages on other addresses may call it (CORS)", False, str(e))

if A.key:
    try: call("/api/sync", {"readings": []}, key=False); check("without the key the machine endpoints are refused", False)
    except urllib.error.HTTPError as e: check("without the key the machine endpoints are refused", e.code == 401)
    check("the public endpoints still work without the key", "panels" in call("/api/state", key=False))

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
