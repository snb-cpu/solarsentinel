# 2-ml-ai  (owner: Pratham)

The brain. Runs on **your laptop (laptop B)**, shows every decision in your terminal, and sends it to the final API (on the Mac, which handles all the hardware).

## Run it
```
python3 -m venv venv && source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt                         # Mac also needs: brew install libomp (for lightgbm)
python ml_worker.py --api http://<IP-OF-THE-MAC>:8000
```
You will see one line per panel per reading: state, power lost, rupees lost per day, WASH NOW, which model decided and how sure it is, and why. `--quiet` prints only changes.
If you stop it, the API switches to its built-in rules after 8 seconds and switches back when you restart.

## How a decision is made (`decide.py`)
1. `classify.py` RandomForest, two models: **before-wash** and **after-wash**. The after-wash model sees what the wash changed (power recovered, temperature dropped, hot spot left) and is what separates dirt from a real fault.
2. `heatmap.py` heat of each cell above the median (any grid size).
3. `forecast.py` LightGBM 7-day energy forecast, with today's dirt and as if clean.
4. Weather comes from the feed the Mac sends with every reading (no internet needed). `weather.py` (Open-Meteo) is only the fallback when no feed is given.
5. Rules: fault or hotspot never gets water; shading never gets water; dust gets a wash only if no rain is forecast and the money lost per day is more than the Rs 2 wash; a hot patch with dirt-like signs is washed once to find out; low tank defers the wash.
6. `ml_worker.py` remembers the reading before a wash, waits for the panel to cool (15 simulated minutes), then asks the after-wash model.

## Training data (important)
`data/make_physics.py` makes the training data from the **physics simulator** (3-hardware-sim/sim/world.py), the same one the demo runs, with real sensor noise. Re-make and retrain:
```
python data/make_physics.py 4000     # about 3 minutes
python classify.py                   # writes model.pkl, prints accuracy and confusion matrices
python -m pytest -q                  # 15 tests
```
Accuracy is about 99.8% on held-out episodes from the same simulator. That number is on simulated data. Real accuracy comes from Sanjay's rig. Say that to the judges.
Your original hand-made generator is still in `data/make_synthetic.py`; `classify.py` uses `data/physics.csv` when it exists.

## Changes made when merging your branch (so you know)
- `classify.py` / `heatmap.py`: any grid size (the rig is 2x4, the Wokwi node 1x3); light is in lux (0 to 100,000) not 0-4095; expected power now corrects for panel temperature; model loaded once.
- `decide.py`: new `weather=` argument, forecasts always computed and scaled to a 1.5 kW string, returns `forecast_clean_kwh_7d`, pauses at night, hot-patch rule.
- `ml_worker.py` is new. `serve.py` (MQTT) is kept but not used: the system talks HTTP.
- `api/server.py` is the final API. It does not need your libraries.

## Rules
- Push only inside this folder, on branch `ml/pratham`.
- Keep files under 20 MB. Do not change `../docs/contract.md` without telling Sanjay.
