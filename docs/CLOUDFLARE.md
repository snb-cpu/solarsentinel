# SolarSentinel on Cloudflare

The commands are in [RUN.md](RUN.md). This page says what gets created and why.

```
 Mac: virtual_node.py ──┐                                     ┌── solarsentinel-hw.pages.dev   hardware view
                        ├──►  solarsentinel-api.pages.dev ◄───┼── solarsentinel-ml.pages.dev   ML console
 Pratham: ml_worker.py ─┘      (Pages project, one function)   └── solarsentinel-app.pages.dev  customer app
                                          │
                                          ▼ binding, no public address
                               solarsentinel-hub  (Worker with one Durable Object)
                               holds all the live state in memory and on disk
```

## The five pieces
| Name | What | Source |
|---|---|---|
| `solarsentinel-hub` | A Worker whose only content is one **Durable Object**. It is the API: the same logic and the same endpoints as `2-ml-ai/api/server.py` ([contract.md](contract.md)), so every machine and every page sees the same state. `workers.dev` and preview URLs are switched off. | `cloud/hub/` |
| `solarsentinel-api` | A **Pages** project with one function that hands every request to the hub. This gives the hub its public address. | `cloud/api/` |
| `solarsentinel-app` | Pages project: the customer app | `1-ui-design/webapp/` + `shared/` |
| `solarsentinel-hw` | Pages project: the hardware view and controls | `3-hardware-sim/sim/console.html` + `shared/` |
| `solarsentinel-ml` | Pages project: the ML console | `2-ml-ai/console/` + `shared/` |

The three sites are plain files. `cloud/deploy.sh` copies each page with `shared/` (fonts, styles, scripts) and writes `shared/config.js` with the API address, so a page knows where to talk. Locally `config.js` is empty and the page uses the address it was served from.

## Why a Durable Object and not a database or the Mac
- Everything has to agree, so one object holds the state and handles one request at a time. There are no races between the Mac, the ML program and the pages.
- The Mac and Pratham's laptop only make outgoing requests, so venue Wi-Fi that stops laptops seeing each other does not matter, and neither does the Mac going to sleep: the pages keep their last state.
- The Mac keeps working without internet: run the Python API (`2-ml-ai/api/server.py`) instead. It implements the same contract, and `cloud/contract_test.py` checks both against the same 20 tests.

## What the machines send
- The simulator makes **one request a second** (`POST /api/sync`) carrying its readings, sleep notices, weather and state, and gets back the clean orders and the demo-control presses.
- The ML program **long-polls** (`GET /api/ml/poll`): the call waits up to 20 seconds and returns as soon as readings arrive, then it posts all its verdicts in one request.
- Web pages hold one `/events` stream (server-sent events), with a plain `GET /api/state` poll as a fallback.
- A real ESP32 uses the single-purpose endpoints (`/api/reading`, `/api/command`, `/api/status`), which both versions still serve. Wokwi can use the same `https://…pages.dev` address instead of a tunnel.

## What is live (deployed 31 October 2026)
| Link | What |
|---|---|
| https://solarsentinel-app.pages.dev | customer app |
| https://solarsentinel-hw.pages.dev | hardware view and controls |
| https://solarsentinel-ml.pages.dev | ML console |
| https://solarsentinel-api.pages.dev | the API (for machines; `/api/state` shows the live JSON) |

Each site is its own project at its own `/`, and none of them links to another, so there is no way to switch between them from a page. `https://solarsentinel-app.pages.dev/?demo=0` is the customer view without the demo-controls drawer.

Two things to know if you deploy again from another machine:
- **Static sites need `--force` once.** Current wrangler (4.15x) sends a new static Pages project down its Workers path, which would publish it on a `workers.dev` address. `deploy.sh` creates each project with `pages project create --force`, which makes a normal Pages project; later deploys need no flag.
- **Cloudflare blocks Python's default client name** (`Python-urllib`, error 1010). The simulator, the ML program and the tests send their own `User-Agent`. If a real ESP32 gets a 403 from the Cloudflare address, give its HTTP client a `User-Agent` of its own too.

## Names, the account, and what it costs
- Only Pages addresses (`*.pages.dev`) are public. The hub Worker has no `workers.dev` route, so the account's own `workers.dev` name never appears anywhere.
- Free plan: 100,000 requests a day across the Worker and Pages Functions, and Durable Objects must be SQLite-backed (they are: `new_sqlite_classes` in `cloud/hub/wrangler.toml`). See the limits section of [RUN.md](RUN.md).
- To remove everything: delete the four Pages projects and the `solarsentinel-hub` Worker in the Cloudflare dashboard.

## Local test of the cloud version (no deployment, no login)
```
cd cloud/hub && npx wrangler@4 dev --port 8787                 # the hub
cd cloud/api && npx wrangler@4 pages dev --port 8788           # the public address in front of it
python3 cloud/contract_test.py http://localhost:8788 --room test
python3 3-hardware-sim/sim/virtual_node.py --api http://localhost:8788
```
