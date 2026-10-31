# Wokwi: the real firmware, with relays and LEDs (connected to our API)

What it shows: the same `solarsentinel.ino` that goes on the real ESP32, running inside Wokwi. Dials replace the sensors, two relay modules click when the valve and blower switch on, LEDs light. It talks to laptop B's API, so it appears as a 4th panel, "W1", on the customer dashboard, and the dashboard's "Clean this panel now" button makes the relays click in Wokwi.

## Setup (once)
1. Laptop B (or this laptop, until B is ready) is running the API: `python3 2-ml-ai/api/server.py`.
2. Make the API reachable from the internet with a tunnel (Wokwi's Wi-Fi cannot see your LAN):
   ```
   cloudflared tunnel --url http://localhost:8000
   ```
   It prints an address like `https://random-words.trycloudflare.com`. Anyone with that address can reach the API while the tunnel runs, so close it after the demo (Ctrl+C).
3. `python3 wokwi/make_wokwi.py` (regenerates `wokwi/project/` from the real firmware).
4. On wokwi.com: New Project, ESP32, Arduino. Replace/add four files with the ones in `wokwi/project/`: `sketch.ino`, `config.h`, `secrets.h`, `diagram.json`.
5. In `secrets.h` set `API_URL` to the tunnel address. Press Start.

## Wiring (diagram.json does this; if a wire is missing, connect by hand)
| Part | Wokwi pin | GPIO |
|---|---|---|
| Pot V (panel voltage) | D34 | 34 |
| Pot I (current) | D35 | 35 |
| Pot L (light) | VN | 39 (one dial stands for all four corner LDRs; Wokwi has no spare pins for four) |
| NTC 1, 2, 3 | D32, D33, VP | 32, 33, 36 |
| Relay 1 (spray valve) IN | RX2 | 16 |
| Relay 2 (tap inlet valve) IN | TX2 | 17 |
| Relay 3 (blower) IN | D18 | 18 |
| Slide switch: rain (slid to GND = raining) | D25 | 25 |
| Slide switch: float low (slid to GND = water above it) | D26 | 26 |
| Slide switch: float high (slid to GND = water above it) | D27 | 27 |
Relays: VCC to VIN, GND to GND, COM to 3V3, NO to resistor to LED to GND (blue = spray valve, purple = tap valve, green = blower).

## Dial settings for the demo
The firmware turns the pot voltage into the reading. Pot value is a fraction of 3.3 V.
| Reading | Set the pot to | Result |
|---|---|---|
| Healthy: 17 V | V pot about 86% | voltage 17.0 V |
| Sunlight 70,000 lux | L pot about 70% | light 70k lux |
| Healthy current 3.85 A | I pot about 62% | AI says healthy |
| Dusty: current drops to about 3.2 A | I pot about 59% | AI says dust, orders a wash, relays click |
| No current | I pot 50% | 0 A |
Temperatures: click each NTC and set about 45 C. Set one to 60 C to make a hot spot.

## What is different from the real node
Wokwi has no ADS1115 or INA219 part that I could rely on, so here the sensors go to the ESP32's own pins (dials, thermistors, slide switches), the three relays are the same, and the node stays awake so the demo keeps running (the serial log says when it would sleep). Everything else, the wash, the tap refill rule (flip the float switches: both open = nearly empty, so the tap valve LED lights; close the high one = full, so it goes off) and the commands from the API, is the real firmware.

## Notes
- If the relay LEDs look inverted, swap HIGH and LOW for `RELAY_ON` in the WOKWI block at the bottom of `config.h`.
- The first run of `diagram.json` was written from memory of Wokwi's part and pin names and has not been opened in Wokwi yet. If a part or wire is rejected, fix it by eye using the table above.
- Wokwi sometimes runs slower than real time. Readings may arrive less often than every 2 seconds.
