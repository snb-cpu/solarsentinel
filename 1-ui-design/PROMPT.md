# Gemini prompts for the customer UI (Shashank)

> **Read first (Oct 31).** `webapp/index.html` was rebuilt by hand on the shared design in `../shared/` (see README.md). Use these prompts only for small changes, and give Gemini `webapp/index.html`, `../shared/ss.css` and `../shared/ss.js` together. The zip below is the older brief.

How to use:
1. Upload `solarsentinel-ui-brief.zip` (in this folder) to Gemini. It holds `index.html`, `contract.md` and `sample-snapshot.json`.
2. Paste Prompt 1. Then Prompt 2. Then any fine-tune prompts you need.
3. Save Gemini's file as `webapp/index.html`, run it (steps at the bottom), commit on branch `ui/shashank`, push.

Rule: never let Gemini rename or remove `API`, `connect()` or `draw(m)`. Everything else can change.

---

## Prompt 1: the main build

```
I'm uploading a zip with 3 files: index.html (a working but plain dashboard), contract.md (data formats) and sample-snapshot.json (one real live message).

PRODUCT: SolarSentinel, a smart solar panel monitor and auto-cleaner for homeowners and small plant operators in India. The customer opens this page to see how their panel is doing and whether it needs cleaning. The AI decides when to wash; the customer never sees engineering controls.

TASK: Redesign index.html into a polished, professional, customer-facing dashboard. Return ONE self-contained index.html (inline CSS and JS, no frameworks, no build step, no external libraries, system fonts or Google Fonts via link only). It must open by double-click and by python3 -m http.server.

DO NOT CHANGE THE DATA LOGIC:
- Keep the API connection code exactly: the `API` variable (from ?api= query, localStorage, or http://localhost:8000), `connect()` using EventSource(API + '/events'), `draw(m)` receiving one JSON snapshot per message, and the "Clean now" button doing fetch(API + '/api/clean', {method:'POST', body:'{}'}).
- Keep every field binding. Shape of m is in sample-snapshot.json: m.panels (array, one per solar panel: id, mode ("active" or "sleep": a sleeping panel is NOT offline, it is saving power at night or in rain; show it as asleep), sleep ({reason: "dark" or "rain"}), reading {voltage_v, current_a, ldr_lux (average light), ldr_corners_lux (4 numbers: top-left, top-right, bottom-left, bottom-right light sensors; if they differ by more than 25% the light is uneven, a shadow or cloud, not dirt), temps_c as a 2-row x 4-column grid of 8 sensor temperatures, tank_level_pct, clean_state 0/1/2, tap_open (1 while the tap-water inlet valve is refilling the tank), rain, node_mw, node_wh, tap_s, spray_s, sim_clock}, decision {state: ok|dust|shading|hotspot|fault, efficiency_loss_pct, loss_inr_per_day, clean_cost_inr, clean_now, reason}, history [{p: watts, c: true if a wash just finished}], age_s: seconds since last reading; over 8 means that panel is offline, unless its mode is "sleep"), m.site (power_w total, node_mw (what the node itself draws), asleep (how many panels sleep), node_wh, tap_l (litres of tap water used), spray_l, tap_open, loss_inr_per_day total, history, forecast_kwh_7d, forecast_clean_kwh_7d), m.weather (rain_48h, raining, ambient_c), m.log (array of {t, msg}), m.ml (who made the decisions: "ML model" or "built-in rules"), m.ml_connected, m.econ. Each panel also has source ("ml" or "rules"). Show a small line "Decisions by: <m.ml>". The per-panel "Clean now" button does fetch(API + '/api/clean', {method:'POST', body: JSON.stringify({panel_id: id})}).
- Keep the "Demo controls" drawer (id="demo"): it lets the presenter cause problems in the simulator during the live demo. It reads m.sim (panels[i].faults, forecast_rain, storm, timer, speed, clock) and sends POST API + '/api/sim' with body {cmd, panel (0-based index), value}. Keep it working, restyle it as a tidy collapsible panel, and hide it when the URL has ?demo=0 (that is the clean customer view).
- Keep the "Power and water" row: what the node itself draws, the node's energy, litres of tap water used, litres sprayed, and (when m.sim.today exists) energy recovered by cleaning. The message to land with customers: the device works only in daylight and dry weather and sleeps otherwise, so it never uses more energy than cleaning gives back; rainwater fills the tank first and the tap valve is only a back-up.
- Remove nothing that exists. You may restyle, rearrange and add.

DESIGN BRIEF:
- Look: clean, modern, trustworthy energy-tech product. Calm and premium, not a hacker dashboard. Palette: deep navy (#0B1D33), sun amber (#FFB703) as the single accent, soft off-white cards; light theme by default plus a dark-mode toggle.
- Top: product name with a small sun logo (inline SVG), a live status pill (green "Panel online" / red "Offline"), site time.
- Hero row: a big plain-English status card, e.g. "Your panel is healthy" / "Dust is costing you Rs 21 a day, cleaning now" / "Cracked cell detected, technician needed". Large number for power output in watts, with today's energy in kWh if you can estimate it from history.
- THERMAL HEATMAP PER PANEL (the centrepiece): for EACH panel draw a smooth, continuous thermal heatmap (like a thermal camera image, not coloured boxes) interpolated from the 2x4 temps_c sensor grid, for example with canvas and a Gaussian blend of the sensor points, colour scale blue to cyan to green to yellow to orange to red to white-hot, scaled to that panel's own min and max so a single hot cell stands out. Overlay the solar-cell grid lines, a dot and the temperature at each sensor, the four corner light levels in thousands of lux shown at the panel corners (orange when uneven), a pulsing ring on the hottest point when it is more than 4 degrees above the median, and a small colour legend. Show a water-drops animation over the panel when clean_state is 1 and a wind-streaks animation when it is 2. Panels sit side by side in a responsive grid, each with its state badge, power, power lost, rupees lost per day, water level, decision reason and its own Clean button.
- Decision card: state shown as a colored badge, the reason in plain language, and three numbers: power lost %, money lost per day (Rs), cost of one wash (Rs).
- Power chart: smooth area chart of m.history, with a blue marker where c is true labelled "washed". Pure SVG, no libraries.
- 7-day forecast: bar chart, solid bars from forecast_kwh_7d with dashed ghost bars from forecast_clean_kwh_7d, day labels Today, Tomorrow, then weekday names.
- Weather chip (rain soon / raining / clear, air temperature), water tank gauge, sunlight level.
- Activity feed from m.log, newest first, with small icons.
- Smooth transitions when numbers change, no layout jumping, skeleton shimmer while waiting for the first message.
- Fully responsive: great on a laptop projector (readable from 5 metres, minimum 16px body text) and on a phone.
- Accessible: good contrast, aria-labels, no color-only meaning.

Return the full file, no explanations, no placeholders, no "rest unchanged".
```

## Prompt 2: make it robust

```
Without changing the design, double check every m.* field in draw() against sample-snapshot.json (including panels that appear later and panels with age_s over 8) and make the page robust: if m.reading is null show the waiting skeleton, if forecast arrays are missing show empty bars, never throw an error. Also add a small footer line "Data: <m.ml>, updated <m.age_s> s ago". Return the full file.
```

## Fine-tune prompts (use as needed)

Bigger, more realistic panel:
```
Make the per-panel thermal heatmaps the visual centerpiece: bigger, smoother, more like a real thermal-camera image on a real solar panel (frame, glass reflection, silver busbars), with a clearer colour legend.
```

Match the Canva design (attach a screenshot):
```
Match my Canva design: here is the screenshot [attach]. Copy its colors, fonts, spacing, card style and icon style exactly. Keep all data bindings.
```

Friendlier headline text:
```
Write the plain-English status headline better for a non-technical homeowner in India: short, friendly, no jargon. Cover all five states (ok, dust, shading, hotspot, fault) plus washing and drying.
```

Explain the decision:
```
Add a "Why did the system do this?" expandable section under the decision card that explains the decision reason in two simple sentences.
```

Projector mode:
```
Make it look good on a projector across a hall: larger type, higher contrast, a presentation mode toggled with the key P.
```

If something breaks:
```
The page shows this error in the browser console: [paste error]. Fix it and return the full file.
```

---

## After Gemini gives you the file
1. Save it as `webapp/index.html` (replace the old one).
2. Run it:
   ```
   cd webapp
   python3 -m http.server 8200
   ```
   Open `http://localhost:8200/?api=http://<PRATHAM-IP>:8000`
3. No API yet? Run all three parts on your laptop: see `../docs/DEMO-3-LAPTOPS.md`.
4. Commit on branch `ui/shashank` and push.
