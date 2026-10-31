# Live demo on 3 laptops

```
 This Mac (Sanjay)                       Pratham's laptop                    Shashank's laptop / Cloudflare
 hardware: virtual panels + ESP32s  -->  ML program (ml_worker.py)           customer web app
 + the final API (hub)              <--  decisions + clean commands          reads the API
        ^                                 prints every decision in its
        |  all data and decisions         terminal and POSTs it to the API
        +--------------------------------------------------------------->  UI
```
**The Mac runs two programs:** the hardware (`virtual_node.py`: panels, ESP32 logic, cleaning machine) and the final API (`2-ml-ai/api/server.py`). Everything meets there.
**Pratham runs the ML program**, which streams readings from the API, decides, shows the output in his terminal and sends it back to the API. If it stops, the API's built-in rules take over.
**The UI** only talks to the API.

All on the same Wi-Fi (a phone hotspot works). Get the Mac's IP: `ipconfig getifaddr en0`.

1. **Mac** `python3 2-ml-ai/api/server.py` then `python3 3-hardware-sim/sim/virtual_node.py --api http://localhost:8000`  (hardware view: http://localhost:8100)
2. **Pratham** `git pull`, then `python ml_worker.py --api http://<MAC-IP>:8000`  (from the `2-ml-ai` folder, with its venv)
3. **Shashank** `cd 1-ui-design/webapp && python3 -m http.server 8200` then open `http://localhost:8200/?api=http://<MAC-IP>:8000`

The Mac needs no ML libraries. Put it on the internet for the web app: [CLOUDFLARE.md](CLOUDFLARE.md).

## Demo script (about 3 minutes)
1. Healthy panel. Customer sees clean heatmap, power, forecast. (C)
2. A: click **Dust storm**. Power drops, heatmap warms, decision turns "dusty". B decides washing is worth the money, sends a command. A: valve and blower turn on. C: wash animation, power recovers, dashed line on the chart.
3. A: click **Rain forecast**, then **Make dirty now**. B refuses to wash ("rain is coming"). Rain later cleans the panel for free.
4. A: click **Cracked cell**. Hot cell on the heatmap, state "cracked cell", no water used, technician advice. A fault is never washed.
5. A: **Shade**. State "shaded", no wash.
6. Optional: turn on the **2 h timer** on A to show the backup. Note it washes even when not needed, which is why AI-driven washing is better.

If B is not ready yet, run the whole thing alone on one laptop: start B's server, A's simulator and open C's page, all with `localhost`.
