# Power and water: the node must not eat what it saves, and must not run dry

Both rules are in the firmware (`3-hardware-sim/firmware/solarsentinel/solarsentinel.ino`, knobs in `config.h`) and are mirrored line for line by the simulator (`virtual_node.py`), so they can be watched at `http://localhost:8100`.

## 1. Day-only power

Cleaning only helps while the sun is up, and rain cleans the panel for free. So the node works only in daylight and dry weather. Otherwise it is in **deep sleep**: the radio is off, the 5 V sensor rail is off, every valve is shut, and the ESP32 itself draws about 10 microamps (a few hundredths of a milliwatt).

### What it does
| Situation | What the node does |
|---|---|
| Average of the four corner light sensors at or above **22,000 lux**, no rain | Awake: measures, reports, washes, refills the tank |
| Light below **18,000 lux** (dusk, night, heavy cloud) or the rain sensor wet, for 3 reports in a row | Tells the API it is going to sleep (so it is not shown as "offline"), then deep-sleeps |
| Asleep | Wakes on its own timer every **20 minutes** (dark) or **10 minutes** (rain), switches the sensor rail on for about 100 ms, reads the four light sensors and the rain sensor with no Wi-Fi, and goes straight back to sleep unless it is day and dry |
| Day and dry again | Wakes fully, switches on Wi-Fi and carries on |
| In the middle of a wash or a tap refill | Finishes first, then sleeps |

The two thresholds (22,000 up, 18,000 down) stop it flapping at dawn and dusk. They match the ML program, which pauses analysis below 20,000 lux anyway.

### What it saves
Power draws used (datasheet typicals; the INA219 on the battery rail replaces them with real measurements):

| State | Draw at the 12 V battery rail |
|---|---|
| Awake (ESP32 on Wi-Fi in modem sleep, ACS712, JSN-SR04T, LM35s, FC-37, relay module logic, buck losses) | about **250 mW** |
| Deep sleep (FireBeetle ESP32 + MP1584EN buck's own idle current) | about **1.3 mW** |
| Spray valve open | about 4.8 W, for 4 seconds per wash |
| Tap valve open | about 4.8 W, for about 75 seconds per refill |
| Blower | about 2.4 W, for 8 seconds per wash |

A simulated full day with the real logic (3 panels, dust, washes, nothing else): each node used about **2.4 Wh**, against about **6.0 Wh** if it never slept. That is 60% less. A 100 W-class panel makes roughly 500 Wh on a good day, so the node costs about **0.5% of the panel's output**. It pays for itself if cleaning recovers just half a percent.

Washes are almost free in energy terms: a wash is 4 s of valve (5 mWh) plus 8 s of blower (5 mWh). A tap refill is about 0.1 Wh. The big cost is staying awake, which is why it sleeps.

The dashboard's "Power and water" row shows the node's draw, its energy, and (in the simulator) what cleaning recovered. The simulator's recovered-energy figure compares the cleaned panel with a copy of the panel that is never cleaned. The simulator speeds dust build-up up a lot so that something happens during a demo, so **that recovered figure looks bigger than real life**. The break-even above (0.5%) is the number to quote.

### What makes it real and not just a line of code
- **The sensor rail switch (TPS22918).** The ACS712 alone draws about 10 mA at 5 V, which is 50 mW, 40 times the sleeping node. Everything on the 5 V rail is switched off through one load switch, held low through deep sleep.
- **A low-power board.** A generic ESP32 DevKit draws 5 to 10 mA asleep because of its USB-serial chip and regulator. Use a FireBeetle ESP32 (about 10 microamps) or a bare WROOM-32 module.
- **A low-quiescent buck converter** for 12 V to 5 V (MP1584EN, about 100 microamps), not a standard LM2596 module with a power LED.
- **The relay module's logic side is on the switched rail**, so its LEDs and optocouplers are off too.
- **Energy keeps counting through sleep:** the node keeps its running energy total in RTC memory (INA219 readings while awake plus the known sleep draw), so the count survives deep sleep.

## 2. Water: rain first, tap as the back-up

The tank (20 L per panel) has **two inlets and one outlet**:
- **Rain gutter** (passive, free): fills the tank whenever it rains. Needs no control.
- **Tap water through valve K2** (12 V normally-closed solenoid): only when the tank is low.
- **Spray valve K1** at the bottom takes water to the spray pipe on the panel.

### The refill rule (`tapLoop()`)
| Condition | Action |
|---|---|
| Tank below **25%** and the API is not holding it | Open the tap valve |
| Tank below **10%** (critical) | Open the tap valve even if rain is forecast |
| Tank at **85%** or above, or the high float switch closes | Close it |
| Open for **3 minutes** without reaching 85% | Close it, and lock out for 10 minutes (stuck level sensor, a leak, no mains pressure) |
| Rain forecast within 48 h (the API tells the node on every poll) | Hold: do not buy tap water, let the rain fill the tank, unless it is critical |
| Tank below **8%** | No wash starts; it waits for the refill |

The level comes from the JSN-SR04T ultrasonic sensor (median of three pings), corrected by two float switches: the low float overrides a sloshing echo to say "nearly empty", and the high float is an overflow stop that works even if the ultrasonic fails.

The ML program also knows: if the tank is under 20% it says "dust detected, the tank is low, refilling from the tap first" and does not order a wash until the refill has brought the level back up.

### The numbers
20 L tank, spray 0.2 L/s (a 4-second wash is 0.8 L, 4% of the tank), tap 0.17 L/s (about 10 L/min), so refilling from 25% to 85% takes about 70 seconds. The dashboard shows litres of tap water and litres sprayed since power-on, so the owner sees how much of the water is free rainwater.

### Plumbing rules that matter
- The tap pipe must end **above** the water level in the tank (an air gap). Never submerge it. That keeps tank water out of the mains.
- Mount the tank above the panel's top edge for gravity feed, or add a 12 V diaphragm pump after the spray valve.
- Fit an overflow pipe. The high float stops the tap valve, but the overflow protects against a failed valve.

## 3. Things to try in the simulator (http://localhost:8100)
1. **Drain the tank.** The tank drops to 12%, the tap valve opens (purple), the tank fills to 85% and the tap closes.
2. **Rain forecast, then drain the tank.** The API sends "hold": the tap stays shut at 12% (it only opens below 10%).
3. **Skip to dusk, then night.** The nodes finish what they are doing, tell the API, switch the sensor rail and radio off, and sleep. The node's draw drops from about 250 mW to 1.3 mW and the customer dashboard shows "asleep".
4. **Skip to morning.** The nodes wake on their timer, see the sun and carry on.
5. **Start rain now.** The nodes sleep with reason "rain"; the gutter fills the tank; after the rain they wake again.
