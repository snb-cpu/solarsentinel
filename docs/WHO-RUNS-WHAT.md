# Who runs what

Read the heading of each section: **the folder name is different on each machine**. On Sanjay's Mac the project is `~/Downloads/solarsentinel-project`. On a laptop that cloned it from GitHub it is `solarsentinel`. Every command below starts with a `cd` into the right one.

## Why isn't everything on Cloudflare?
These are, and they stay online with a link: **the customer app, the hardware view, the ML console, and the API** behind them. Nobody runs those.

Two things are not, because Cloudflare's free plan cannot run them:
- **The ML program** is Python with scikit-learn and LightGBM and a 7 MB model. Cloudflare Workers cannot run those libraries.
- **The simulator** (three virtual panels and the ESP32 logic) is a Python program that has to keep running. It could be moved into Cloudflare, but that is a rewrite, and the ML program would still need a computer.

So two Python programs run on some computer. The easiest way to get "just open a link" is **one always-on Ubuntu machine** that runs both (Way A). The next easiest is one command on each laptop (Way B).

## The links
After Sanjay's step 1 these stay up (replace `solarsentinel` if you used `SS_PREFIX`):

| What | Link |
|---|---|
| Customer app (judges, phones) | https://solarsentinel-app.pages.dev |
| Hardware view and controls | https://solarsentinel-hw.pages.dev |
| ML console | https://solarsentinel-ml.pages.dev |
| API (for the two programs) | https://solarsentinel-api.pages.dev |

With nothing running behind them the pages say they are waiting for the panels. They fill with live data as soon as the simulator and the ML program run, from anywhere.

---

## Step 1: Sanjay, once, on the Mac
Needs Node.js. `npx wrangler login` opens a browser to log in to Cloudflare.
```bash
cd ~/Downloads/solarsentinel-project && git pull && npx wrangler login
```
```bash
./cloud/deploy.sh
```
Check: open https://solarsentinel-api.pages.dev/api/state in a browser. JSON means it is live.

---

## Way A: one Ubuntu machine runs both programs (nobody else runs anything)
A machine that stays on and online: a spare Ubuntu laptop (turn off sleep) or a small cloud VM from any provider. Ubuntu 22.04 or 24.04, 1 GB of memory or more. Written for that; I have not run it on a real Ubuntu machine, so read the dry run first.

**On the Ubuntu machine**, once:
```bash
sudo apt-get update && sudo apt-get install -y git && git clone https://github.com/snb-cpu/solarsentinel.git && cd solarsentinel
```
```bash
./cloud/ubuntu-setup.sh https://solarsentinel-api.pages.dev --dry-run
```
That prints what it would do and changes nothing. Then for real (asks for the password once, a few minutes):
```bash
./cloud/ubuntu-setup.sh https://solarsentinel-api.pages.dev
```
It installs what is needed and starts two services that restart themselves and come back after a reboot. The four links then show live data.

**Free-plan limit:** the two programs together use about 7,200 Cloudflare requests an hour, and the free plan allows 100,000 a day, so about 14 hours. Stop them when the demo day is over and start them again in the morning:
```bash
sudo systemctl stop solarsentinel-sim solarsentinel-ml
```
```bash
sudo systemctl start solarsentinel-sim solarsentinel-ml
```

Watch the ML program: `journalctl -u solarsentinel-ml -f`. After someone pushes a change:
```bash
cd solarsentinel && git pull && sudo systemctl restart solarsentinel-sim solarsentinel-ml
```
Remove it again: `./cloud/ubuntu-setup.sh --remove`.

---

## Way B: each person runs their part on their own laptop

### On Sanjay's Mac: the simulated panels
```bash
cd ~/Downloads/solarsentinel-project && ./run.sh https://solarsentinel-api.pages.dev --no-ml
```
`./run.sh` starts only what you ask for and stops it all on Ctrl+C. If it says a port is in use, an old copy is running; it prints the command to stop it.

### On Pratham's laptop: the ML program
**Ubuntu or macOS** (Ubuntu once: `sudo apt-get install -y git python3-venv libgomp1`. Mac once: `brew install libomp`).

First time:
```bash
git clone https://github.com/snb-cpu/solarsentinel.git && cd solarsentinel && ./run.sh https://solarsentinel-api.pages.dev --no-sim
```
Every later time:
```bash
cd solarsentinel && git pull && ./run.sh https://solarsentinel-api.pages.dev --no-sim
```
The first run builds the Python environment (a few minutes), then the first start loads the models (up to a minute with only a "loading" line). After that it prints one line per verdict.

**Windows** (Python 3.9 to 3.13 from python.org with "Add python to PATH" ticked). In Command Prompt:
```bat
git clone https://github.com/snb-cpu/solarsentinel.git && cd solarsentinel && run.bat https://solarsentinel-api.pages.dev
```
Every later time: `cd solarsentinel && git pull && run.bat https://solarsentinel-api.pages.dev`. (I have not run `run.bat` on Windows.)

### Shashank: the customer app
Nothing to run at the demo; he opens https://solarsentinel-app.pages.dev. To work on his page against live data, in the project folder:
```bash
python3 -m http.server 8200
```
then open this in a browser (no Node, no Cloudflare login, nothing else running):
```
http://localhost:8200/1-ui-design/webapp/index.html?api=https://solarsentinel-api.pages.dev
```
To publish a change he pushes to GitHub, and Sanjay runs on the Mac:
```bash
cd ~/Downloads/solarsentinel-project && git pull && ./cloud/deploy.sh app
```

---

## Everything on one laptop, no internet (testing, or a demo without Wi-Fi)
```bash
cd ~/Downloads/solarsentinel-project && ./run.sh
```
That starts the API, the simulated panels and the ML program. Open `http://localhost:8000/` (customer app), `http://localhost:8000/ml/` (ML console) and `http://localhost:8100/` (hardware view). With Pratham on the same Wi-Fi instead: run `./run.sh --no-ml` on the Mac and, on his laptop, `./run.sh http://<MAC-IP>:8000 --no-sim` (the Mac's address: `ipconfig getifaddr en0`).

## Who needs what
| Person | Needs installed | Runs | When |
|---|---|---|---|
| Sanjay, Mac | Node.js, Python 3 | `./cloud/deploy.sh` | once, and after a page changes |
| Sanjay, Mac, Way B | Python 3 | `./run.sh <api> --no-ml` | each demo |
| The Ubuntu machine, Way A | git (the script installs the rest) | `./cloud/ubuntu-setup.sh <api>` | once |
| Pratham, Way B | Python 3.9 to 3.13, git | `./run.sh <api> --no-sim` (Windows: `run.bat <api>`) | each demo |
| Shashank | a browser; Python 3 only to preview | nothing at the demo | |

Use either Way A or Way B, not both, or the panels would be fed twice.

More detail, ports and error messages: [RUN.md](RUN.md). What gets created on Cloudflare: [CLOUDFLARE.md](CLOUDFLARE.md).
