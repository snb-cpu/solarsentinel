# 1-ui-design  (owner: Shashank)

Canva designs plus the customer web app (`webapp/`). Branch: `ui/shashank`.

**Start here: [PROMPT.md](PROMPT.md)** has the exact Gemini prompts. Upload `solarsentinel-ui-brief.zip` to Gemini and paste them.

## Laptop C (you) in the live demo
`webapp/index.html` is a working customer dashboard (Sanjay's reference). It connects to the API on Pratham's laptop and shows live data.
```
cd webapp
python3 -m http.server 8200                    # then open http://localhost:8200/?api=http://<PRATHAM-IP>:8000
```
(It also works when served by the API itself at http://<PRATHAM-IP>:8000.) The `?api=` address is remembered by the browser.

## Your job
1. Do the Canva design for the customer app (screens below), then restyle `webapp/index.html` to match it. Keep the data bindings (`draw(m)` function); change layout, colours, fonts, icons.
2. The customer must NOT see problem-injection buttons. Those live on Sanjay's console. The only customer action is "Clean now".
3. Export the Canva designs to `exports/` and paste the share link here: (paste link)
4. Own the pitch deck and demo script too.

## Screens (fields from `../docs/contract.md`)
Live panel + thermal heatmap, power chart, AI decision card (state, loss, rupees lost, clean yes/no, reason), 7-day forecast, weather, activity log.
