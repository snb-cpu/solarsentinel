#!/usr/bin/env bash
# Turns one Ubuntu machine (22.04 or 24.04) into the always-on engine of the demo. It runs the simulated panels and the ML
# program all day as services, talking to the API on Cloudflare. After this nobody has to start anything: the three Cloudflare
# links just show live data. Needs sudo. Written for Ubuntu but not run by me on one: use --dry-run first and read what it does.
#
#   git clone https://github.com/snb-cpu/solarsentinel.git && cd solarsentinel
#   ./cloud/ubuntu-setup.sh https://solarsentinel-api.pages.dev
#   ./cloud/ubuntu-setup.sh https://solarsentinel-api.pages.dev --key SECRET     if you gave the API a key
#   ./cloud/ubuntu-setup.sh --remove                                             stop and delete the two services
# Add --dry-run to any of them to print what would happen and change nothing.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"; ME="$(id -un)"; API=""; KEY=""; REMOVE=0; DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1;;
    --remove) REMOVE=1;;
    --key) KEY="${2:?--key needs a value}"; shift;;
    http://*|https://*) API="${1%/}";;
    *) echo "unknown argument: $1"; sed -n 2,10p "$0"; exit 2;;
  esac; shift
done
run() { echo "+ $*"; if [ "$DRY" = 0 ]; then "$@"; fi; }

if [ "$REMOVE" = 1 ]; then
  run sudo systemctl disable --now solarsentinel-sim solarsentinel-ml || true
  run sudo rm -f /etc/systemd/system/solarsentinel-sim.service /etc/systemd/system/solarsentinel-ml.service
  run sudo systemctl daemon-reload
  echo "Removed."; exit 0
fi
[ -n "$API" ] || { echo "Give the API address, for example:  ./cloud/ubuntu-setup.sh https://solarsentinel-api.pages.dev"; exit 2; }
if [ "$DRY" = 0 ] && ! grep -qiE "ubuntu|debian" /etc/os-release 2>/dev/null; then echo "This script is for Ubuntu (it uses apt and systemd)."; exit 1; fi

echo "1. Programs the two services need (python3, its venv module, git, the OpenMP library LightGBM uses)"
run sudo apt-get update
run sudo apt-get install -y git python3 python3-venv python3-pip libgomp1

echo "2. A private Python environment for the ML program (about 250 MB of downloads, a few minutes)"
run python3 -m venv 2-ml-ai/venv
run 2-ml-ai/venv/bin/pip install --quiet --upgrade pip
run 2-ml-ai/venv/bin/pip install --quiet -r 2-ml-ai/requirements.txt

echo "3. The two services (start on boot, restart if they stop)"
KEYLINE=""; [ -n "$KEY" ] && KEYLINE="Environment=SS_KEY=$KEY"
unit() {   # unit <name> <description> <folder to run in> <command>
  local f="/etc/systemd/system/$1.service" text
  text="[Unit]
Description=$2
After=network-online.target
Wants=network-online.target

[Service]
User=$ME
WorkingDirectory=$3
Environment=PYTHONUNBUFFERED=1
$KEYLINE
ExecStart=$4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"
  echo "--- $f"; echo "$text" | sed "s/SS_KEY=.*/SS_KEY=(hidden)/"
  if [ "$DRY" = 0 ]; then printf '%s' "$text" | sudo tee "$f" > /dev/null; sudo chmod 600 "$f"; fi
}
unit solarsentinel-sim "SolarSentinel simulated panels" "$ROOT/3-hardware-sim/sim" "$(command -v python3) $ROOT/3-hardware-sim/sim/virtual_node.py --api $API --console-host 127.0.0.1"
unit solarsentinel-ml  "SolarSentinel ML program"       "$ROOT/2-ml-ai"            "$ROOT/2-ml-ai/venv/bin/python $ROOT/2-ml-ai/ml_worker.py --api $API --quiet"
run sudo systemctl daemon-reload
run sudo systemctl enable --now solarsentinel-sim solarsentinel-ml

if [ "$DRY" = 1 ]; then echo; echo "Dry run: nothing was changed."; exit 0; fi
echo; echo "Checking that the API answers..."
sleep 8
python3 -c "import sys, urllib.request as u; u.urlopen(u.Request(sys.argv[1] + '/api/state', headers={'User-Agent': 'SolarSentinel-setup/1.0'}), timeout=15); print('the API answers')" "$API" || echo "The API did not answer. Open $API/api/state in a browser; if it is not JSON, run ./cloud/deploy.sh on the Mac first."
cat <<EOF

Both services are running and will start again after a reboot.
  See the ML program's verdicts   journalctl -u solarsentinel-ml -f
  See the simulator               journalctl -u solarsentinel-sim -f
  Status                          systemctl status solarsentinel-sim solarsentinel-ml --no-pager
  Restart both                    sudo systemctl restart solarsentinel-sim solarsentinel-ml
The first ML start after installing can take a minute with no output.
EOF
