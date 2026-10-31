# Run SolarSentinel: reference

**Per person and per system (Mac, Windows, Ubuntu), with every command: [WHO-RUNS-WHAT.md](WHO-RUNS-WHAT.md).** This page explains the three ways to connect the machines, what the launcher does, the limits, and what to do when something is wrong.

The folder name differs per machine: `~/Downloads/solarsentinel-project` on Sanjay's Mac, `solarsentinel` on a laptop that cloned from GitHub. Always `cd` into your own.

| Way | What runs where | Needs |
|---|---|---|
| **A. Cloudflare** (use this at the event) | The API and the three pages live on Cloudflare. The simulated panels and the ML program run on any computers, or both on one Ubuntu machine, and talk to the API over the internet. Anyone with a link can open the pages. | Internet on the machines that run the two programs |
| **B. Same Wi-Fi** | The Mac runs the API and the simulator. Pratham's laptop reaches the Mac by its address. | One Wi-Fi where laptops can see each other |
| **C. One laptop** | Everything on one machine. | Nothing |

| Page | For | A. Cloudflare | B and C. local |
|---|---|---|---|
| **Hardware view** (the machine, the ESP32, the trouble buttons) | Sanjay | `https://solarsentinel-hw.pages.dev` | `http://localhost:8100` (on the Mac) |
| **ML console** (verdicts, why, forecast) | Pratham | `https://solarsentinel-ml.pages.dev` | `http://<MAC-IP>:8000/ml/` |
| **Customer app** | Shashank, judges, phones | `https://solarsentinel-app.pages.dev` | `http://<MAC-IP>:8000/` |

Add `?demo=0` to the customer app to hide the demo controls, `?demo=open` to start with them open.

## The launcher: `./run.sh`
One script for a Mac or Ubuntu machine. It starts only the parts you ask for, builds the ML Python environment the first time, refuses to start a second copy of something already running, and stops everything it started on Ctrl+C.

| You want | Run, from the project folder |
|---|---|
| Everything on this machine (C) | `./run.sh` |
| The Mac's part with the Cloudflare API (A) | `./run.sh https://solarsentinel-api.pages.dev --no-ml` |
| Pratham's part with the Cloudflare API (A) | `./run.sh https://solarsentinel-api.pages.dev --no-sim` |
| The Mac's part for Way B | `./run.sh --no-ml` |
| Pratham's part for Way B | `./run.sh http://<MAC-IP>:8000 --no-sim` |
| Both programs on one machine with the Cloudflare API | `./run.sh https://solarsentinel-api.pages.dev` |

On Windows the ML program starts with `run.bat https://solarsentinel-api.pages.dev`. The programs write their logs to `logs/`; the ML program prints in the window.

What it does for you, if you ever want the long form:
```
python3 2-ml-ai/api/server.py                                                  # the API (only when no address is given)
python3 3-hardware-sim/sim/virtual_node.py --api <api>                          # the simulated panels
cd 2-ml-ai && ./venv/bin/python ml_worker.py --api <api>                        # the ML program (Windows: venv\Scripts\python)
```
The Mac has no `python` command and its system `python3` has no numpy, so the ML program always goes through `2-ml-ai/venv`.

## Put it on Cloudflare (Way A, once, on the Mac, about 3 minutes)
```
cd ~/Downloads/solarsentinel-project && npx wrangler login
./cloud/deploy.sh
```
`npx wrangler login` opens a browser to log in to Cloudflare. `deploy.sh` uploads the hub (a Durable Object with no public address of its own) and four Pages projects, then runs a self-test against the new API and prints your addresses. It never uses the workers.dev address of your account.

If a name such as `solarsentinel-app.pages.dev` is taken, pick your own prefix: `SS_PREFIX=trueno ./cloud/deploy.sh`. See what it would do without uploading anything: `./cloud/deploy.sh --dry-run`.

When a page changes, Shashank pushes and Sanjay runs `./cloud/deploy.sh app` (or `hw`, `ml`, `api`, `hub`, or several, for example `./cloud/deploy.sh hw ml`).

### Lock the machine endpoints (optional)
Anyone who knows the API address could post fake readings. To require a key from the two programs (web pages are unaffected):
```
cd cloud/hub && npx wrangler secret put KEY
```
It asks for a password. Then add `--key <password>` to the `./run.sh` commands. Leave the key off when testing the real ESP32, whose firmware does not send one yet.

### Limits to know about
The free plan allows 100,000 Cloudflare requests a day, counted from 05:30 India time. The simulator makes 1 request a second and the ML program 1 a second as well (it asks for readings and posts verdicts every 2 seconds), so running both costs about 7,200 an hour. **That is about 14 hours of running per day, not 24.** Start them for the demo and stop them (Ctrl+C) afterwards. Past the limit the API refuses requests until the next reset and the pages show their last data. Open pages cost almost nothing: each keeps one long-lived stream and closes it 20 seconds after its tab is hidden. The Workers Paid plan removes the limit.

## Same Wi-Fi (Way B)
Find the Mac's address with `ipconfig getifaddr en0`. If the ML program says "cannot reach", the venue Wi-Fi is probably stopping laptops from seeing each other: use Way A or a phone hotspot.

## What you should see
- Hardware view: the machine drawing, with a sentence on top saying what it is doing right now. Press **Cause trouble** to drop dust, a bird, shade or a cracked cell on a panel (on screens narrower than 1480 px the controls slide in from the right with the **Controls** button).
- Pratham's terminal: one aligned line for every verdict (time, panel, verdict, loss, rupees a day, WASH NOW, which model and how sure, milliseconds, and why).
- ML console: the same verdicts with the checks the program made, in order (light, diagnosis, rain, water, money, decision).
- If the ML program stops, the API falls back to its simple built-in rules after 8 seconds and the ML console says so. The demo keeps working.

## Self-checks
```
python3 3-hardware-sim/sim/test_node.py                                   # 10 checks of the ESP32 logic
cd 2-ml-ai && ./venv/bin/python -m unittest test_decide                   # 14 checks of the ML decisions
python3 cloud/contract_test.py http://localhost:8000                      # 20 checks that an API keeps the contract (run it on a spare API: it adds a panel T9)
python3 cloud/contract_test.py https://solarsentinel-api.pages.dev --room test      # on Cloudflare, --room test keeps it away from the live demo
```

## If something is wrong
| You see | Do this |
|---|---|
| "Port 8100 is already in use" (or 8000) | A copy is already running on this machine. Stop it with `pkill -f virtual_node.py` (the simulator) or `pkill -f api/server.py` (the API), then start again. |
| `cd: no such file or directory: solarsentinel/...` | You are on a machine where the folder has another name. On Sanjay's Mac it is `~/Downloads/solarsentinel-project`. |
| `command not found: python` | Mac and Ubuntu only have `python3`. Use `./run.sh`, which picks the right one. |
| Hardware view says "Cannot reach https://…pages.dev" | The API is not online yet. Open `https://solarsentinel-api.pages.dev/api/state` in a browser: JSON means it is live. If not, run `./cloud/deploy.sh` first. |
| Page says "Cannot reach the API" | The address is wrong or the API is not running. Open `<api>/api/state` in a browser: you should see JSON. |
| Hardware view says "The API is up, but the simulator is not sending" | Start the simulated panels with the same API address. |
| ML console says "ML program offline" | Start the ML program with the same API address as the simulator. |
| ML program prints only "loading the models" for a minute | Normal for the first start after installing. |
| `./run.sh`: "The ML libraries did not load" | Mac: `brew install libomp`. Ubuntu: `sudo apt-get install -y libgomp1`. |
| `deploy.sh`: "Not logged in" | `npx wrangler login`, then run it again. |
| `deploy.sh`: wrangler asks which account | `CLOUDFLARE_ACCOUNT_ID=<id> ./cloud/deploy.sh`. The id is on the Cloudflare dashboard. |
| `403` with `error code: 1010` from the Cloudflare address | Cloudflare blocks clients that call themselves `Python-urllib` or similar. The simulator, the ML program and the tests now send their own name (`SolarSentinel-…/1.0`). Any new script that talks to the API must do the same; browsers and curl are not affected. |
| Python: `CERTIFICATE_VERIFY_FAILED` | Run `/Applications/Python*/Install Certificates.command`, or `pip install certifi`. |
| Panels start "asleep" | The simulated clock reached night. Press **To morning** in the controls. |
