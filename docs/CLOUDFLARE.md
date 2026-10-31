# Putting the web app on Cloudflare (once Shashank's UI is done)

Two parts, same API for both:

## 1. The API (stays on the Mac) behind a Cloudflare Tunnel
```
brew install cloudflared
cloudflared tunnel --url http://localhost:8000          # quick tunnel: prints https://random-words.trycloudflare.com
```
That address is the API for the web app and for Wokwi. It changes every time you start the quick tunnel. For a fixed address, make a named tunnel on a domain in your Cloudflare account:
```
cloudflared tunnel login
cloudflared tunnel create solarsentinel
cloudflared tunnel route dns solarsentinel api.<your-domain>
cloudflared tunnel run --url http://localhost:8000 solarsentinel
```
While a tunnel runs, anyone with the address can read the dashboard data and use the demo-control endpoints. Close it after the demo, or ask for an access key to be added to the API first.

## 2. The web app on Cloudflare Pages
`1-ui-design/webapp/` is plain static files (no build step).
```
npm i -g wrangler
wrangler login
wrangler pages deploy 1-ui-design/webapp --project-name solarsentinel
```
It gives you `https://solarsentinel.pages.dev`. Open it as `https://solarsentinel.pages.dev/?api=https://<your-api-address>`; the page remembers the address. The API already allows requests from any website (CORS), so nothing else is needed. Add `&demo=0` to hide the demo controls for judges.

Pratham's ML program keeps talking to the Mac over the Wi-Fi, or through the same tunnel address with `--api https://<your-api-address>`.
