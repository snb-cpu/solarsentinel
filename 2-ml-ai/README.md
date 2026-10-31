# 2-ml-ai  (owner: Pratham)

Language: **Python 3.11+**. Libraries: numpy, pandas, scikit-learn, lightgbm, requests, paho-mqtt.
Input and output formats are in `../docs/contract.md`. Match them exactly.

```
pip install -r requirements.txt
python decide.py data/sample_reading.json     # prints a decision JSON
```

## What to build (in this order)

1. `data/make_synthetic.py`  Generate fake readings, since no hardware exists yet. Make 5 kinds, label each:
   `ok`, `dust` (whole grid warms evenly, power drops 5-15%), `shading` (one side cooler, sharp power drop),
   `hotspot` (one cell 6-15 C above the rest), `fault` (one cell stays hot all day and the power never recovers after a wash).
   Save thousands of rows to `data/synthetic.csv`.
2. `heatmap.py`  `make_heatmap(temps_c) -> 2D list in 0..1`. Use each cell's difference from the grid median, normalized.
3. `classify.py`  Train a RandomForest that outputs `state` (ok/dust/shading/hotspot/fault).
   Features: grid mean minus ambient, grid std, max minus median, left/right and top/bottom gradient,
   power loss vs expected (expected power comes from `ldr_lux`). Save the model to `model.pkl`. Print a confusion matrix.
   Key point to show judges: dust vs `fault` is told apart by whether the pattern is even and goes away after cleaning.
4. `weather.py`  `rain_expected(lat, lon, hours=48) -> bool`. Use the free Open-Meteo API, no key needed
   (`https://api.open-meteo.com/v1/forecast`, ask for `precipitation_probability`, `shortwave_radiation`, `temperature_2m`). Cache the result, never call more than once an hour.
5. `forecast.py`  LightGBM regressor for daily kWh over 7 days. Inputs: forecast irradiance, temperature, current soiling loss.
   Train on synthetic data for now. Output feeds `forecast_kwh_7d`.
6. `decide.py`  `decide(reading) -> decision dict` (see contract). Rule order:
   - state `fault` or `hotspot`: `clean_now=false`, reason says manual repair.
   - state `dust` and rain expected in 48h: `clean_now=false`, reason says rain will clean it.
   - state `dust` and `loss_inr_per_day` greater than `clean_cost_inr`: `clean_now=true`.
   - else `clean_now=false`.
   Use 8 INR per kWh for the money maths, and make it a constant at the top.
7. `serve.py`  Subscribe to MQTT `solar/+/reading`, call `decide`, publish to `solar/<id>/decision`. Do this last. Sanjay will run it on the Mac.
8. `test_decide.py`  A few asserts for the rules in step 6.

## Rules for you
- Push only inside this folder, on your branch `ml/pratham`.
- Commit `model.pkl` and `data/synthetic.csv` only if each is under 20 MB.
- Do not change `../docs/contract.md` without telling Sanjay.
- Keep the demo number honest: report accuracy on synthetic data as synthetic. Real data comes from Sanjay's rig later.
