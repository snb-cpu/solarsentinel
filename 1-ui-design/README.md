# 1-ui-design  (owner: Shashank)

The customer app is **`webapp/index.html`**: one HTML file, no build step. It uses the shared look in [`../shared/`](../shared/) (`ss.css` for styles, `ss.js` for the data connection, the heat map and the charts, and the Atkinson Hyperlegible fonts).

## What changed on October 31
`solarsentinel_enterprise_dashboard(1).html` (the first push) did not run: the opening lines of the panel-card template are missing (the code jumps from `const v = ...` straight into HTML), so the script has a syntax error and the page stays on "Connecting...". Its demo buttons also sent commands the simulator does not know (`set_fault`, `set_weather`, `set_speed`). `webapp/index.html` is rebuilt from the same sections and wording on a new look, and wired to the real API fields. The original file is still here, untouched, if you want to compare.

## Run it
It is served by the API itself (`http://<MAC-IP>:8000/`), or double-click the file and add the API address: `webapp/index.html?api=http://<MAC-IP>:8000`. The address is remembered. Exact commands for every way of running it: [`../docs/RUN.md`](../docs/RUN.md).

## Put it online
```
./cloud/deploy.sh app          # from the project folder, after a git pull
```
That uploads this folder plus `shared/` to `https://solarsentinel-app.pages.dev` (first time: `./cloud/deploy.sh`, see RUN.md). Ask Sanjay or run it yourself after `npx wrangler login`.

## Changing the design
Keep these things and change the rest freely:
- Colour, type and spacing are tokens at the top of [`../shared/ss.css`](../shared/ss.css). Change a token and all three pages follow. The five state colours (`--ok --dust --shade --hot --fault`) are checked to stay tell-apart-able; if you change one, check the others still look different, and keep the shape marks (circle, triangle, square, diamond, cross) because they carry the meaning for colour-blind viewers.
- No gradients, glows, glass or emoji icons (they were the part that made the first version look generated). Use the page's own words: plain, short, sentence case.
- Text never smaller than 13 px, no horizontal scrolling at 360 px wide. Open the page at phone width and at 1440 px before you push.
- Data: `draw(m)` receives one snapshot, shaped as in [`../docs/contract.md`](../docs/contract.md). Do not rename `SS.api`, `SS.feed` or the `/api/clean` and `/api/sim` calls.
- The customer must not see the problem buttons. They live in the drawer at the bottom, which `?demo=0` removes.

## Gemini
[`PROMPT.md`](PROMPT.md) still works for small changes, but give Gemini the whole of `webapp/index.html` **and** `shared/ss.css` and `shared/ss.js`, and always open the browser console after pasting its answer. Check the console for a syntax error every time: one missing line stops the whole page. `solarsentinel-ui-brief.zip` is the older brief, from before the shared files existed.

## Screens (fields from `../docs/contract.md`)
Plain-language headline for the whole plant, a smooth heat map for each panel with the four corner light sensors, the AI's reason, power and money lost, the power chart, the 7-day forecast, weather, power and water, what the system did, and the demo drawer.

## Shashank's notes on the first version
[README-first-version.md](README-first-version.md) keeps what he wrote about his first page, as he wrote it.
