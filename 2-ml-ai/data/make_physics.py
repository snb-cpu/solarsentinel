"""Training data from the physics simulator (the digital twin), not hand-made numbers.

  python data/make_physics.py [episodes]      # default 4000, writes data/physics.csv (about 2 minutes)

Each episode: build a panel with one known condition, let it settle, take a reading and an earlier reading,
run a real wash cycle (4 s water, 8 s air), wait 15 simulated minutes, take the after-wash reading.
The rows use the same feature code the live system uses (classify.build_prediction_features), so training
and prediction cannot drift apart. Sensor noise, ADC quantisation and sensor lag come from the virtual node.
"""
import random, sys
from pathlib import Path
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent / "3-hardware-sim" / "sim"))
from world import World, N
from virtual_node import Node, load_cfg
from classify import build_prediction_features, CLASSES

CFG = load_cfg()

def episode(label, rng):
    w = World(start_hour=rng.uniform(9.0, 14.5), dust_mult=rng.uniform(0.7, 1.4))
    w.cloud = rng.uniform(0.0, 0.35); w.wind = rng.uniform(0.5, 5.0)
    if label == "ok":
        w.dust = [rng.uniform(0.0, 0.015) for _ in range(N)]
    elif label == "dust":
        level = rng.uniform(0.05, 0.25)
        w.dust = [min(0.4, level * rng.uniform(0.6, 1.4)) for _ in range(N)]
        if rng.random() < 0.4: w.stuck[rng.randrange(N)] = rng.uniform(0.3, 0.6)      # a bird dropping: hot patch that washes off
    elif label == "shading":
        w.faults["shade"] = True; w.dust = [rng.uniform(0, 0.04) for _ in range(N)]
    elif label == "hotspot":
        w.faults["hotspot"] = True; w.dust = [rng.uniform(0, 0.03) for _ in range(N)]
    elif label == "fault":
        w.faults["crack"] = True; w.dust = [rng.uniform(0, 0.05) for _ in range(N)]
    w.step(2400, 0, False, False)                        # settle thermally
    n = Node(w, CFG, "P1")
    stamp = lambda r: {**r, "ts": "2026-01-01T00:00:00Z"}
    old = stamp(n.reading()); w.step(360, 0, False, False); cur = stamp(n.reading())
    before_p = cur["voltage_v"] * cur["current_a"]
    w.step(4, 4, True, False); w.step(8, 8, False, True); w.step(900, 0, False, False)      # wash, dry, cool down
    after = stamp(n.reading())
    result = {"power_before_w": max(before_p, 0.01), "power_after_w": after["voltage_v"] * after["current_a"],
              "temps_before_c": cur["temps_c"], "temps_after_c": after["temps_c"]}
    row, _ = build_prediction_features(cur, history=[old], cleaning_result=result)
    out = row.iloc[0].to_dict(); out["state"] = label
    return out

if __name__ == "__main__":
    total = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    rng = random.Random(7); random.seed(7)
    rows = []
    for i in range(total):
        label = CLASSES[i % len(CLASSES)]
        try: rows.append(episode(label, rng))
        except ValueError: continue                       # e.g. too little light for a valid reading
        if (i + 1) % 500 == 0: print(f"{i + 1}/{total}", flush=True)
    pd.DataFrame(rows).to_csv(HERE / "physics.csv", index=False)
    print("wrote", HERE / "physics.csv", len(rows), "rows")
