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
  "temps_c": [[41.2, 41.5, 41.0], [41.3, 47.9, 41.1]],
  "tank_level_pct": 70
}
```
`temps_c` is the thermal grid, rows x columns of analog temperature sensors under the panel.

## 2. Decision (ml -> hardware, ui)
```json
{
  "ts": "2026-10-31T10:00:02Z",
  "panel_id": "P1",
  "state": "dust",
  "efficiency_loss_pct": 8.4,
  "clean_now": true,
  "reason": "uniform heat rise, no rain forecast in 48h",
  "heatmap": [[0.1, 0.2, 0.1], [0.2, 0.9, 0.1]],
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

## Transport
MQTT topics: `solar/<panel_id>/reading`, `solar/<panel_id>/decision`, `solar/<panel_id>/command`.
Until hardware exists, use the sample files in each folder to fake these messages.
