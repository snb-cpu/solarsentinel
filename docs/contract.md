# Shared data contract

The three parts talk through these JSON shapes. Change them only after telling the team.

## 1. Sensor reading (hardware -> ml, ui)  every 60 s
```json
{
  "ts": "2026-10-31T10:00:00Z",
  "panel_id": "P1",
  "voltage_v": 18.2,
  "current_a": 4.1,
  "ldr_lux": 54000,
  "ldr_corners_lux": [53000, 55000, 54000, 54500],
  "temps_c": [[41.2, 41.5, 41.0, 41.4], [41.3, 47.9, 41.1, 41.2]],
  "tank_level_pct": 70,
  "clean_state": 0,
  "tap_open": 0,
  "rain": 0,
  "node_mw": 250,
  "node_wh": 2.41,
  "tap_s": 0,
  "spray_s": 8,
  "sim_clock": "Day 1 14:20"
}
```
`temps_c` is the thermal grid: 2 rows x 4 columns = 8 analog temperature sensors under each panel (one CD4051 mux). Several panels (P1, P2, P3) each have their own node.
`ldr_lux` is the average of the four corner light sensors (top-left, top-right, bottom-left, bottom-right). If they disagree by more than 25% the light is uneven: a shadow or passing cloud, never call that dirt.
`tank_level_pct` comes from the JSN-SR04T ultrasonic sensor and two float switches (-1 = unknown). `tap_open` is 1 while the tap inlet valve is refilling the tank. `rain` is 1 when the FC-37 sensor is wet. `node_mw` is what the node itself draws right now and `node_wh` the energy it has used since power-on (INA219 on the battery rail). `tap_s` and `spray_s` are the total seconds the tap valve and the spray valve have been open (litres = seconds x flow).
`clean_state`: 0 idle, 1 water flush, 2 air dry. `sim_clock` exists only in the simulator (the real ESP32 has no clock; the API stamps `ts`).

## 2. Decision (ml -> hardware, ui)
```json
{
  "ts": "2026-10-31T10:00:02Z",
  "panel_id": "P1",
  "state": "dust",
  "efficiency_loss_pct": 8.4,
  "clean_now": true,
  "reason": "uniform heat rise, no rain forecast in 48h",
  "heatmap": [[0.1, 0.2, 0.1, 0.1], [0.2, 0.9, 0.1, 0.1]],
  "forecast_kwh_7d": [3.1, 3.4, 2.9, 3.3, 3.5, 3.2, 3.0],
  "loss_inr_per_day": 12.5,
  "clean_cost_inr": 2.0
}
```
`state` is one of: `ok`, `dust`, `shading`, `hotspot`, `fault`.
`fault` = permanent damage, needs a human. Never trigger cleaning for it.

## 3. Command (hardware listens)
```json
{ "panel_id": "P1", "action": "clean", "water_ms": 4000, "air_ms": 8000 }
```
Cycle: solenoid water pulse first, then blower/air dry. Hardware also has its own 2-hour timer as backup.

## Transport (plain HTTP, no broker)
| Who | Call | What |
|---|---|---|
| Node -> API | `POST /api/reading` | the reading above, every 2 s |
| Node -> API | `GET /api/command?panel=P1` | polled every 1 s; returns the command above if there is one, and always `"tap_hold":true/false` (true = rain is forecast, so do not buy tap water unless the tank is critical) |
| Node -> API | `POST /api/status` | `{"panel_id":"P1","mode":"sleep","reason":"dark"/"rain","wake_s":1200}`, sent just before deep sleep so the dashboard shows "asleep" and not "offline". Waking is announced by the next reading |
| Weather feed -> API | `POST /api/weather` | `{"rain_48h":bool,"day_factor":[7],"ambient_c":27.0,"raining":false}` (in the demo, laptop A plays the weather service) |
| ML program -> API | `GET /api/ml/stream` | live stream of `{"reading": {...}, "weather": {...}}` for every reading |
| ML program -> API | `POST /api/decision` | the decision for one panel (shape above, plus optional `model_score_pct`, `diagnosis_stage`). The API uses it, and falls back to built-in rules if it goes quiet for 8 s |
| UI -> API | `GET /events` | live stream (server-sent events) of reading + decision + weather + history + log |
| UI -> API | `POST /api/sim` | demo controls: `{"cmd":"bird","panel":1}` (cmd: dirty, bird, shade, hotspot, crack, repair, storm, rain_forecast, timer, speed+value). The API relays to the simulator, which polls `GET /api/simcmd` and posts its state to `POST /api/simstate` (shown to the UI as `sim`) |
| UI -> API | `POST /api/clean` | customer's manual "Clean now" |

The decision also carries `forecast_kwh_7d` (with current dirt) and `forecast_clean_kwh_7d` (if the panel were clean).

## What the UI receives (`GET /events`, one JSON per message)
```json
{
  "panels": [ { "id": "P1", "mode": "active", "sleep": null, "reading": {..}, "decision": {..}, "history": [{"p": 71.0, "c": false}], "age_s": 0.8 } ],
  "site":   { "power_w": 198.0, "node_mw": 750.0, "asleep": 0, "node_wh": 7.2, "tap_l": 0.0, "spray_l": 2.4, "tap_open": 0, "loss_inr_per_day": 17.4, "history": [{"p": 198.0, "c": false}],
              "forecast_kwh_7d": [..7..], "forecast_clean_kwh_7d": [..7..] },
  "weather": { "rain_48h": false, "raining": false, "ambient_c": 31.9, "day_factor": [..7..] },
  "log": [{"t": "12:07:01", "msg": "P2: cleaning finished."}],
  "ml": "rules", "econ": { "panel_kw": 1.5, "tariff": 8.0, "clean_cost": 2.0 }
}
```
`POST /api/clean` body `{"panel_id":"P2"}` washes one panel, `{}` washes all.
