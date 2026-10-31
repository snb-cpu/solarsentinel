#!/usr/bin/env bash
# Puts SolarSentinel on Cloudflare: the hub (a Durable Object, no public address) and four Pages projects.
#
#   ./cloud/deploy.sh              everything
#   ./cloud/deploy.sh app          only the customer app (do this each time Shashank changes 1-ui-design/webapp)
#   ./cloud/deploy.sh hw ml        any mix of: hub api app hw ml
#   ./cloud/deploy.sh --dry-run    build into cloud/.build and print the commands, deploy nothing
#   SS_PREFIX=trueno ./cloud/deploy.sh      use other names if "solarsentinel-app.pages.dev" is taken
#
# Needs Node.js and a Cloudflare login (npx wrangler login). Nothing here touches the workers.dev address of your account.
set -euo pipefail
cd "$(dirname "$0")/.."
P="${SS_PREFIX:-solarsentinel}"
B="$PWD/cloud/.build"
WR="npx --yes wrangler@4"
DRY=0; TARGETS=()
for a in "$@"; do case "$a" in --dry-run) DRY=1;; hub|api|app|hw|ml) TARGETS+=("$a");; all) ;; *) echo "unknown argument: $a"; sed -n 2,9p "$0"; exit 2;; esac; done
[ ${#TARGETS[@]} -eq 0 ] && TARGETS=(hub api app hw ml)
want() { for t in "${TARGETS[@]}"; do [ "$t" = "$1" ] && return 0; done; return 1; }
run() { echo "+ $*"; if [ "$DRY" = 0 ]; then "$@"; fi; }
mkdir -p "$B"

command -v node >/dev/null || { echo "Node.js is needed: https://nodejs.org"; exit 1; }
if [ "$DRY" = 0 ]; then
  echo "Checking the Cloudflare login..."
  WHO="$($WR whoami 2>&1 || true)"; echo "$WHO" | tail -n 6
  echo "$WHO" | grep -qi "logged in" || { echo; echo "Not logged in. Run:  npx wrangler login   then run this script again."; exit 1; }
fi

# The API address: remembered from the last API deploy (Cloudflare adds letters to a name that is already taken), else the plain name.
API_HOST="${P}-api.pages.dev"; [ -f "$B/api-host" ] && API_HOST="$(cat "$B/api-host")"
api_url() { echo "https://${API_HOST}"; }

pages() {   # pages <project> <folder>: create it if new, then upload; remembers the address Cloudflare gave it
  run $WR pages project create "$1" --production-branch main --force > "$B/create.log" 2>&1 || true     # --force: make it a classic Pages project (new wrangler would otherwise send a static site down its Workers path, to a workers.dev address). Fails harmlessly if it exists; the deploy below says so if it really is missing
  run $WR pages deploy "$2" --project-name "$1" --branch main --commit-dirty=true 2>&1 | tee "$B/last-deploy.log"
  grep -oE 'https://[a-z0-9-]+\.[a-z0-9-]+\.pages\.dev' "$B/last-deploy.log" | head -n1 | sed -E 's#https://[^.]+\.##' > "$B/last-host" || true
  if [ "$DRY" = 0 ] && [ -s "$B/last-host" ]; then cp "$B/last-host" "$B/host-$1"; fi
}
host() { if [ -s "$B/host-${P}-$1" ]; then cat "$B/host-${P}-$1"; else echo "${P}-$1.pages.dev"; fi; }   # the real address of a project (Cloudflare adds letters to a name that is taken)
site() {    # site <folder> <page or directory>: a file becomes index.html, a directory is copied whole; then the shared folder and the API address
  local d="$B/$1"; rm -rf "$d"; mkdir -p "$d/public/shared"
  if [ -d "$2" ]; then cp -R "$2/." "$d/public/"; else cp "$2" "$d/public/index.html"; fi
  cp -R shared/fonts "$d/public/shared/"; cp shared/ss.css shared/ss.js "$d/public/shared/"
  printf 'window.SS_API = "%s";\n' "$(api_url)" > "$d/public/shared/config.js"
  printf '/*\n  X-Content-Type-Options: nosniff\n/shared/fonts/*\n  Cache-Control: public, max-age=31536000, immutable\n' > "$d/public/_headers"
  # a Pages config next to the files: without one, new wrangler versions send the command down their Workers path (which would use a workers.dev address)
  printf 'name = "%s-%s"\npages_build_output_dir = "./public"\ncompatibility_date = "2025-10-01"\n' "$P" "$1" > "$d/wrangler.toml"
}

# 1. the hub, 2. the public API address in front of it
if want hub; then (cd cloud/hub && run $WR deploy --name "${P}-hub"); fi
if want api; then
  rm -rf "$B/api"; cp -R cloud/api "$B/api"
  sed -i.bak -e "s/solarsentinel-hub/${P}-hub/g" -e "s/solarsentinel-api/${P}-api/g" "$B/api/wrangler.toml"; rm -f "$B/api/wrangler.toml.bak"
  (cd "$B/api" && pages "${P}-api" public)            # run inside the folder so wrangler finds functions/ and wrangler.toml
  if [ "$DRY" = 0 ] && [ -s "$B/last-host" ]; then cp "$B/last-host" "$B/api-host"; API_HOST="$(cat "$B/api-host")"; fi
fi
# 3. the three web sites, each told where the API is
want app && { site app 1-ui-design/webapp; (cd "$B/app" && pages "${P}-app" public); }
want hw  && { site hw  3-hardware-sim/sim/console.html; (cd "$B/hw" && pages "${P}-hw" public); }
want ml  && { site ml  2-ml-ai/console/index.html; (cd "$B/ml" && pages "${P}-ml" public); }

[ "$DRY" = 1 ] && { echo; echo "Dry run: built into $B, deployed nothing."; exit 0; }
if want hub && want api; then
  echo; echo "Checking the API end to end (uses a separate test room, so the demo is untouched)..."
  sleep 5; python3 cloud/contract_test.py "$(api_url)" --room test | tail -n 4 || echo "Not answering yet. Wait a minute, then run: python3 cloud/contract_test.py $(api_url) --room test"
fi
cat <<EOF

Done. Your three links (each one is its own site, with no way to switch between them):
  customer app      https://$(host app)
  hardware view     https://$(host hw)
  ML console        https://$(host ml)
  API (machines)    $(api_url)

Point the machines at the API (from the project folder on each machine; run.bat on Windows):
  Mac, simulated panels:   ./run.sh $(api_url) --no-ml
  Pratham, ML program:     ./run.sh $(api_url) --no-sim
  Or both on one always-on Ubuntu machine: ./cloud/ubuntu-setup.sh $(api_url)
Who runs what: docs/WHO-RUNS-WHAT.md
EOF
