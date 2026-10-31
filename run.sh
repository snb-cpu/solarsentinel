#!/usr/bin/env bash
# One command for a Mac or Ubuntu machine. Starts the parts of the demo that run on this machine, and stops them all on Ctrl+C.
#
#   ./run.sh                                          everything here: the API, the simulated panels and the ML program
#   ./run.sh https://solarsentinel-api.pages.dev      the simulated panels and the ML program, using the API on Cloudflare
#   ./run.sh https://solarsentinel-api.pages.dev --no-sim     only the ML program (Pratham's laptop)
#   ./run.sh https://solarsentinel-api.pages.dev --no-ml      only the simulated panels (the Mac, when Pratham runs the ML)
#   ./run.sh --no-ml                                  the API and the simulated panels here; Pratham connects from his laptop
#   ./run.sh http://192.168.1.23:8000 --no-sim        only the ML program, using the Mac on the same Wi-Fi
# Add  --key SECRET  if the API has a key. The first run that includes the ML program builds its Python environment (a few minutes).
# The API and simulator write to logs/. The ML program prints in this window.
set -o pipefail
cd "$(dirname "$0")" || exit 1
API=""; SIM=1; ML=1; KEY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --no-sim) SIM=0;;
    --no-ml) ML=0;;
    --key) KEY="${2:-}"; shift;;
    http://*|https://*) API="${1%/}";;
    -h|--help) sed -n 2,11p "$0"; exit 0;;
    *) echo "unknown argument: $1"; sed -n 2,11p "$0"; exit 2;;
  esac; shift
done
LOCAL_API=0; if [ -z "$API" ]; then LOCAL_API=1; API="http://localhost:8000"; fi
KEYARG=""; [ -n "$KEY" ] && KEYARG="--key $KEY"
mkdir -p logs; PIDS=""
stop() { for p in $PIDS; do kill "$p" 2>/dev/null; done; }
trap 'echo; echo "Stopping what this script started..."; stop; exit 0' INT TERM HUP
trap stop EXIT
# a laptop that falls asleep stops the demo: on a Mac, stay awake for as long as this script runs
if command -v caffeinate > /dev/null 2>&1; then caffeinate -is -w $$ > /dev/null 2>&1 & fi
busy() { python3 -c "import socket,sys; s=socket.socket(); s.settimeout(1); sys.exit(0 if s.connect_ex(('127.0.0.1', int(sys.argv[1]))) == 0 else 1)" "$1"; }

if [ "$LOCAL_API" = 1 ] && busy 8000; then echo "Port 8000 is already in use, so an API is already running here. Stop it with:  pkill -f api/server.py"; exit 1; fi
if [ "$SIM" = 1 ] && busy 8100; then echo "Port 8100 is already in use, so a simulator is already running here. Stop it with:  pkill -f virtual_node.py"; exit 1; fi

VPY="2-ml-ai/venv/bin/python"
if [ "$ML" = 1 ] && [ ! -x "$VPY" ]; then
  echo "Setting up the ML program's Python environment (first time only, a few minutes)..."
  { python3 -m venv 2-ml-ai/venv && 2-ml-ai/venv/bin/pip install --quiet --upgrade pip && 2-ml-ai/venv/bin/pip install --quiet -r 2-ml-ai/requirements.txt; } \
    || { echo "Could not set it up. On Ubuntu try:  sudo apt-get install -y python3-venv libgomp1"; rm -rf 2-ml-ai/venv; exit 1; }
fi
if [ "$ML" = 1 ] && ! "$VPY" -c "import numpy, sklearn, lightgbm" 2>/dev/null; then
  echo "The ML libraries did not load. On a Mac run:  brew install libomp     On Ubuntu run:  sudo apt-get install -y libgomp1"; exit 1
fi

if [ "$LOCAL_API" = 1 ]; then
  python3 2-ml-ai/api/server.py > logs/api.log 2>&1 &
  PIDS="$PIDS $!"
  for _ in 1 2 3 4 5 6 7 8 9 10; do busy 8000 && break; sleep 1; done
  busy 8000 || { echo "The API did not start. See logs/api.log"; exit 1; }
fi
if [ "$SIM" = 1 ]; then
  ( cd 3-hardware-sim/sim && exec python3 virtual_node.py --api "$API" $KEYARG ) > logs/sim.log 2>&1 &
  SIMPID=$!; PIDS="$PIDS $SIMPID"
  sleep 2; kill -0 "$SIMPID" 2>/dev/null || { echo "The simulator stopped at once:"; tail -n 5 logs/sim.log; exit 1; }
fi

echo "Running on this machine, using the API at $API:"
[ "$LOCAL_API" = 1 ] && echo "  API                  customer app http://localhost:8000/   ML console http://localhost:8000/ml/"
[ "$SIM" = 1 ] && echo "  simulated panels     hardware view http://localhost:8100/"
[ "$ML" = 1 ] && echo "  ML program           its verdicts print below"
if [ "$LOCAL_API" = 0 ]; then
  case "$API" in
    https://*-api.pages.dev)
      SITE="${API%-api.pages.dev}"
      echo "  your three links, each its own site, open them on any device:"
      echo "    customer app        $SITE-app.pages.dev"
      echo "    ESP32 / hardware    $SITE-hw.pages.dev"
      echo "    ML console          $SITE-ml.pages.dev";;
    https://*) echo "  (the three pages are on Cloudflare: see docs/WHO-RUNS-WHAT.md)";;
    *) echo "  (the pages are served by that API: $API/  and  $API/ml/)";;
  esac
fi
echo "Ctrl+C stops everything started here."; echo

if [ "$ML" = 1 ]; then      # in the background too, so that Ctrl+C, a closed terminal or kill all reach the trap above at once
  ( cd 2-ml-ai && exec ./venv/bin/python ml_worker.py --api "$API" $KEYARG ) &
  MLPID=$!; PIDS="$PIDS $MLPID"; wait "$MLPID"
else
  wait
fi
