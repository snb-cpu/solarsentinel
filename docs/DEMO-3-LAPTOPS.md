# Live demo on 3 laptops

```
 Laptop A (Sanjay)            Laptop B (Pratham)              Laptop C (Shashank)
 virtual panel + ESP32  --->  API + ML decision engine  --->  customer web app
 sun, weather, dust,    <---  clean commands                  what the customer sees
 faults, rain forecast
```
All three on the same Wi-Fi (phone hotspot works). Get laptop B's IP: `ipconfig getifaddr en0` (Mac) or `ipconfig` (Windows).

1. **B** `git pull` then `python 2-ml-ai/api/server.py`  (port 8000)
2. **A** `python3 3-hardware-sim/sim/virtual_node.py --api http://<B-IP>:8000`  (console on A at http://localhost:8100)
3. **C** `cd 1-ui-design/webapp && python3 -m http.server 8200` then open `http://localhost:8200/?api=http://<B-IP>:8000`

Everything is Python standard library, no installs. If a firewall blocks it, allow Python on port 8000 on laptop B.

## Demo script (about 3 minutes)
1. Healthy panel. Customer sees clean heatmap, power, forecast. (C)
2. A: click **Dust storm**. Power drops, heatmap warms, decision turns "dusty". B decides washing is worth the money, sends a command. A: valve and blower turn on. C: wash animation, power recovers, dashed line on the chart.
3. A: click **Rain forecast**, then **Make dirty now**. B refuses to wash ("rain is coming"). Rain later cleans the panel for free.
4. A: click **Cracked cell**. Hot cell on the heatmap, state "cracked cell", no water used, technician advice. A fault is never washed.
5. A: **Shade**. State "shaded", no wash.
6. Optional: turn on the **2 h timer** on A to show the backup. Note it washes even when not needed, which is why AI-driven washing is better.

If B is not ready yet, run the whole thing alone on one laptop: start B's server, A's simulator and open C's page, all with `localhost`.
