# Gemini prompts for the customer UI (Shashank)

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
- Keep every field binding. Shape of m is in sample-snapshot.json: m.reading (voltage_v, current_a, ldr_lux, temps_c as a 2x3 grid, tank_level_pct, clean_state 0/1/2, sim_clock), m.decision (state: ok|dust|shading|hotspot|fault, efficiency_loss_pct, loss_inr_per_day, clean_cost_inr, clean_now, reason, forecast_kwh_7d, forecast_clean_kwh_7d), m.weather (rain_48h, raining, ambient_c), m.history (array of {p: watts, c: true if a wash just finished}), m.log (array of {t, msg}), m.age_s (seconds since last reading; over 8 means panel offline), m.econ, m.ml.
- Remove nothing that exists. You may restyle, rearrange and add.

DESIGN BRIEF:
- Look: clean, modern, trustworthy energy-tech product. Calm and premium, not a hacker dashboard. Palette: deep navy (#0B1D33), sun amber (#FFB703) as the single accent, soft off-white cards; light theme by default plus a dark-mode toggle.
- Top: product name with a small sun logo (inline SVG), a live status pill (green "Panel online" / red "Offline"), site time.
- Hero row: a big plain-English status card, e.g. "Your panel is healthy" / "Dust is costing you Rs 21 a day, cleaning now" / "Cracked cell detected, technician needed". Large number for power output in watts, with today's energy in kWh if you can estimate it from history.
- Panel thermal map: draw the panel as a realistic solar panel (2 rows x 3 columns of cells with a frame and grid lines), each cell colored by its temperature from temps_c (cool blue to hot red) with the temperature written on it. Show a water-drops animation when clean_state is 1 and a wind-streaks animation when it is 2. Highlight an overheating cell with a pulsing outline.
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
Without changing the design, double check every m.* field in draw() against sample-snapshot.json and make the page robust: if m.reading is null show the waiting skeleton, if forecast arrays are missing show empty bars, never throw an error. Also add a small footer line "Data: <m.ml>, updated <m.age_s> s ago". Return the full file.
```

## Fine-tune prompts (use as needed)

Bigger, more realistic panel:
```
Make the panel thermal map the visual centerpiece: bigger, more realistic (glass reflection, silver busbars, frame), and make the color scale legend clearer.
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
