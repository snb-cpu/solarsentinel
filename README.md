# SolarSentinel

Smart solar monitoring + automated cleaning. Team TRUENO.

Sensors map a thermal grid under the panel -> ML finds dust vs real faults -> weather-aware decision -> forecast + ROI -> water flush + air dry only when worth it.

## Who works where

Each person pushes ONLY inside their own folder. No one edits another person's folder, so there are no merge conflicts.

| Folder | Owner | Job |
|---|---|---|
| `1-ui-design/` | Shashank | Canva designs, exported PNG/PDF, screen list, plus the pitch deck and other non-code items |
| `2-ml-ai/` | Pratham | Python. Thermal heatmap + anomaly model, weather-aware decision, 7-day forecast + ROI |
| `3-hardware-sim/` | Sanjay | ESP32 firmware, wiring, sensor + actuator simulation, final integration on the Mac |
| `docs/` | everyone | `contract.md` = shared data formats (read this first) |

Later everything is combined and run on the main Mac.

## Rules
1. Read `docs/contract.md`. Your output must match it, that is how the parts plug together.
2. Work on your own branch, e.g. `ui/yourname`, then open a pull request to `main` (steps in `docs/git-steps.md`).
3. Commit small and often. Put a short `README.md` in your folder saying how to run or view your work.
