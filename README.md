# SolarSentinel

Autonomous solar panel monitoring and cleaning. Eight temperature sensors and four corner light sensors under each panel, an ESP32 that sleeps at night and in rain, an ML program that tells dust from shade from a cracked cell and washes only when the wash is worth the money. Team TRUENO: Shashank P, Pratham BR, Sanjay Niranjan Balaji.

**Run it:** `./run.sh` starts everything on one Mac or Ubuntu machine (`run.bat` for the ML program on Windows). **Who runs what, per person and per system: [docs/WHO-RUNS-WHAT.md](docs/WHO-RUNS-WHAT.md).** Reference and troubleshooting: [docs/RUN.md](docs/RUN.md).

| Folder | Owner | What |
|---|---|---|
| [`1-ui-design/`](1-ui-design/) | Shashank | The customer app (`webapp/index.html`) |
| [`2-ml-ai/`](2-ml-ai/) | Pratham | The ML program (`ml_worker.py`, `decide.py`), its console (`console/`) and the Python API (`api/server.py`) |
| [`3-hardware-sim/`](3-hardware-sim/) | Sanjay | ESP32 firmware, the physics simulator, the hardware view, Wokwi |
| [`shared/`](shared/) | all | One look for every page: styles, fonts, the data connection, the heat map and charts |
| [`cloud/`](cloud/) | Sanjay | The Cloudflare version of the API, and `deploy.sh` that puts the API and the three pages online |
| [`docs/`](docs/) | all | Problem and solution, exact parts, power and water design, the data contract, the demo script |

```
 virtual panels + ESP32 logic (Mac) ──►  API  ◄── ML program (Pratham)
                                          │
              hardware view · ML console · customer app
```
