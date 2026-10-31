"""Physics of one solar panel and the world around it. Used by virtual_node.py.

Layout: 8 temperature sensors, 2 rows x 4 columns, index = row*4 + col.
Time is accelerated by the caller: step(dt_sim_seconds, real_seconds, spray, blower, tap). Big steps are split
into sub-steps of at most MAX_SUB seconds, so the thermal physics stays correct at any speed (1x to 3000x).

What is modelled (per cell, in W/m2 of panel area):
  heat in    = absorbed sunlight (dirt absorbs differently from glass)
  heat out   = electricity made (ETA of the light the cell passes on, limited by the weakest cell in the string)
  extra heat = MISMATCH heating: a cell that makes less current than the string forces through is driven in
               reverse and dissipates the difference. This is what turns a bird dropping into a real hotspot.
               Heavy shade (cell below 45% light) trips the bypass diode instead, so shaded cells run cooler.
  loss       = convection (wind) + radiation, h = H_BASE + H_WIND*wind; much larger while water or air is on the glass
  conduction = to the 4 neighbouring cells (K_LAT) and nothing else; the thermal mass C_TH gives a ~6 min time constant
The sensors sit on the back sheet: they follow the cell with an extra 2 minute lag and read ~1.5 C lower.
Dust builds up slowly and is washed off quickly; bird droppings are stuck on and need more water; rain washes both slowly.

Water: a 20 L tank per panel with two inlets, rain (gutter, passive) and tap (solenoid valve), and one outlet (the spray valve).
Energy ledger: how much power dirt cost, and what it WOULD have cost with no cleaning at all (a shadow copy of the dirt that is
never washed), so the dashboard can show what cleaning recovered against what the node itself used.
"""
import math, random

ROWS, COLS = 2, 4
N = ROWS * COLS
HOT_CELL, CRACK_CELL = 5, 3          # where the hotspot fault and the cracked cell sit
ISC_A, VOC_V, LUX_PER_WM2 = 5.5, 18.5, 100.0
CLOUD_W, CLOUD_DEPTH = 1.3, 0.65    # width (in panel widths) and darkness of a passing cloud's shadow; it sweeps left to right
LDR_CORNERS = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)]   # top-left, top-right, bottom-left, bottom-right
C_TH = 9000.0                        # J/m2K thermal mass of a cell patch
H_BASE, H_WIND = 16.0, 5.0           # W/m2K, plus per m/s of wind
K_LAT = 6.0                          # W/m2K cell-to-cell conduction
ETA = 0.18                           # cell efficiency
MAX_SUB = 20.0                       # s, largest physics step (stable: h*MAX_SUB/C_TH << 1)
TANK_L = 20.0                        # litres
SPRAY_L_S = 0.2                      # litres per second through the spray pipe (4 nozzles)
TAP_L_S = 0.17                       # litres per second through the tap inlet valve (about 10 L/min)
RAIN_FILL_PCT_H = 30.0               # tank percent per hour gained from the gutter while it rains

def _neighbours(i):
    r, c = divmod(i, COLS)
    return [r * COLS + c + dc for dc in (-1, 1) if 0 <= c + dc < COLS] + [(r + dr) * COLS + c for dr in (-1, 1) if 0 <= r + dr < ROWS]
NB = [_neighbours(i) for i in range(N)]

class World:
    def __init__(self, start_hour=9.0, dust_mult=1.0):
        self.t = start_hour * 3600.0
        self.dust = [0.0] * N              # loose dust on each cell (0..0.4)
        self.stuck = [0.0] * N             # bird droppings: stuck on
        self.dust_nc, self.stuck_nc = [0.0] * N, [0.0] * N     # the same dirt in a world where nobody ever cleans (for the ledger)
        self.hvar = [random.uniform(0.94, 1.06) for _ in range(N)]   # cell-to-cell cooling differences
        self.wind = 2.0
        self.cloud, self.raining, self.forecast_rain = 0.1, False, False
        self.rain_at, self.rain_until, self.storm_until = None, 0.0, 0.0
        self.dust_rate = 0.015 * dust_mult   # dust per sim hour
        self.faults = {"crack": False, "hotspot": False, "shade": False}
        self.cloud_x = None                # a passing cloud: x position (0 = left edge of the panel, 1 = right) of a shadow band, or None
        self.tank = 70.0                   # percent of TANK_L
        self.tap_used_l = self.rain_in_l = self.spray_used_l = 0.0       # litres in and out, since the start
        self.yield_wh = self.lost_wh = self.lost_nc_wh = 0.0             # panel output, loss to dirt, loss to dirt with no cleaning
        self.tcell = [self.ambient() + 12.0] * N
        self.tback = list(self.tcell)

    # ---- dirt helpers (keep the no-cleaning shadow copy in step) ----
    def add_bird(self, i, amount=0.5): self.stuck[i] = amount; self.stuck_nc[i] = amount
    def set_dust(self, levels): self.dust = list(levels); self.dust_nc = list(levels)

    # ---- environment ----
    def hour(self): return (self.t / 3600) % 24
    def day(self): return int(self.t // 86400) + 1
    def clear_sky(self):
        h = self.hour()
        return 1000 * math.sin(math.pi * (h - 6) / 12) if 6 < h < 18 else 0.0
    def irradiance(self): return self.clear_sky() * (1 - 0.7 * self.cloud) * (0.25 if self.raining else 1)
    def ambient(self): return 27 + 7 * math.sin(math.pi * (self.hour() - 9) / 12) - (4 if self.raining else 0)
    def soil(self, i): return min(0.7, self.dust[i] + self.stuck[i])
    def mean_soil(self): return sum(self.soil(i) for i in range(N)) / N
    def cloud_factor(self, x):                              # a moving shadow band across the panel
        if self.cloud_x is None: return 1.0
        sig = lambda z: 1 / (1 + math.exp(-max(-30.0, min(30.0, z))))
        return 1.0 - CLOUD_DEPTH * (sig((self.cloud_x - x) / 0.05) - sig((self.cloud_x - CLOUD_W - x) / 0.05))   # shadow covers [cloud_x - W, cloud_x]
    def light_factor_at(self, x):                           # how much sun reaches a point at horizontal position x (0..1)
        return (0.4 if self.faults["shade"] and x < 0.5 else 1.0) * self.cloud_factor(x)
    def light_factor(self, i): return self.light_factor_at(((i % COLS) + 0.5) / COLS)
    def transmit(self, i, soil=None):                       # fraction of sunlight the cell actually gets (dirt x shade x cloud)
        s = self.soil(i) if soil is None else soil[i]
        return (1 - s) * self.light_factor(i)
    def string_factor(self, soil=None):                     # series string: the weak cells drag the rest down
        tr = [self.transmit(i, soil) for i in range(N)]
        return 0.75 * sum(tr) / N + 0.25 * min(tr), tr

    # ---- time stepping ----
    def step(self, dt, real, spray, blower, tap=False):
        n = max(1, math.ceil(dt / MAX_SUB)) if dt > 0 else 1
        for _ in range(n): self._sub(dt / n, real / n, spray, blower, tap)

    def _sub(self, dt, real, spray, blower, tap):
        self.t += dt
        # weather
        if not self.raining:
            self.cloud = min(0.6, max(0.0, self.cloud + random.gauss(0, 0.02) * math.sqrt(dt / 60)))
            if self.forecast_rain and self.rain_at is None: self.rain_at = self.t + 5 * 3600
            if self.rain_at and self.t >= self.rain_at:
                self.raining, self.rain_until, self.rain_at, self.forecast_rain = True, self.t + 1.5 * 3600, None, False
        elif self.t >= self.rain_until:
            self.raining = False
        if self.cloud_x is not None:
            self.cloud_x += dt / 600                            # crosses the panel in 10 simulated minutes
            if self.cloud_x > 2.4: self.cloud_x = None
        storm = self.t < self.storm_until
        target_wind = 8.0 if storm else 2.0
        self.wind = min(10.0, max(0.0, self.wind + (target_wind - self.wind) * dt / 1800 + 0.5 * math.sqrt(dt / 60) * random.gauss(0, 1)))
        if self.raining:
            self.cloud = 0.9
            k = math.exp(-dt / 3600 * 1.2); self.dust = [d * k for d in self.dust]; self.dust_nc = [d * k for d in self.dust_nc]
            k = math.exp(-dt / 3600 * 0.3); self.stuck = [s * k for s in self.stuck]; self.stuck_nc = [s * k for s in self.stuck_nc]
            add = min(100.0 - self.tank, dt / 3600 * RAIN_FILL_PCT_H)       # the gutter fills the tank
            self.tank += add; self.rain_in_l += add * TANK_L / 100
        # dust deposition (wind helps), identical in the no-cleaning copy
        rate = self.dust_rate * (1 + 0.15 * self.wind) * (8 if storm else 1)
        draws = [random.uniform(0.4, 1.6) for _ in range(N)]
        self.dust = [min(0.4, d + dt / 3600 * rate * r) for d, r in zip(self.dust, draws)]
        self.dust_nc = [min(0.4, d + dt / 3600 * rate * r) for d, r in zip(self.dust_nc, draws)]
        # water out: the spray valve strips dirt quickly and drains the tank
        wet = spray and self.tank > 0
        if wet:
            self.dust = [d * math.exp(-real / 1.5) for d in self.dust]
            self.stuck = [s * math.exp(-real / 3.0) for s in self.stuck]
            use = min(self.tank, SPRAY_L_S * real / TANK_L * 100)
            self.tank -= use; self.spray_used_l += use * TANK_L / 100
        # water in: the tap inlet valve (whatever does not fit overflows, but it is still tap water drawn)
        if tap:
            litres = TAP_L_S * real
            self.tap_used_l += litres; self.tank = min(100.0, self.tank + litres / TANK_L * 100)
        # heat balance
        g0, tamb = self.irradiance(), self.ambient()
        tref = tamb - 2.0 if g0 < 1 else tamb
        isf, tr = self.string_factor()
        new = []
        for i in range(N):
            inc = g0 * self.light_factor(i)
            dirt = self.soil(i)
            absorbed = inc * (0.80 * (1 - dirt) + 0.35 * dirt)
            elec = ETA * g0 * min(tr[i], isf)
            m = max(0.0, isf - tr[i])
            mism = 2.5 * m * g0 if tr[i] >= 0.45 else 0.0               # mismatch heating; below 45% the bypass diode takes over
            fault = (0.30 * g0 if self.faults["hotspot"] and i == HOT_CELL else 0.0) + (0.24 * g0 if self.faults["crack"] and i == CRACK_CELL else 0.0)
            h = (H_BASE + H_WIND * self.wind) * self.hvar[i] + (60 if self.raining else 0) + (500 if wet else 0) + (40 if blower else 0)
            lat = sum(K_LAT * (self.tcell[j] - self.tcell[i]) for j in NB[i])
            new.append(self.tcell[i] + dt * (absorbed - elec + mism + fault - h * (self.tcell[i] - tref) + lat) / C_TH)
        self.tcell = new
        a = 1 - math.exp(-dt / 120)                                     # back-sheet sensor lag
        self.tback = [b + (t - 1.5 - b) * a for b, t in zip(self.tback, self.tcell)]
        # energy ledger: what the panel made, what dirt cost, and what dirt would have cost with no cleaning at all
        if g0 > 1:
            v, i_act = self.electrical()
            i_clean = self.electrical([0.0] * N)[1]
            i_nc = self.electrical([min(0.7, self.dust_nc[i] + self.stuck_nc[i]) for i in range(N)])[1]
            hr = dt / 3600
            self.yield_wh += v * i_act * hr
            self.lost_wh += max(0.0, v * (i_clean - i_act)) * hr
            self.lost_nc_wh += max(0.0, v * (i_clean - i_nc)) * hr

    # ---- electrical ----
    def electrical(self, soil=None):
        isf, _ = self.string_factor(soil); g = self.irradiance(); tavg = sum(self.tcell) / N
        i_a = ISC_A * g * isf / 1000 * (1 + 0.0005 * (tavg - 25)) * (0.8 if self.faults["crack"] else 1.0)
        v = VOC_V * (1 - 0.004 * (tavg - 25)) * (0.85 + 0.15 * min(1.0, g / 200)) if g > 1 else 0.0
        return max(v, 0.0), max(i_a, 0.0)
    def lux_corners(self):                                  # what the four LDRs see (they sit beside the panel, so no dirt, but the same shadows)
        return [self.irradiance() * LUX_PER_WM2 * self.light_factor_at(x) for x, _ in LDR_CORNERS]
    def lux(self): return sum(self.lux_corners()) / len(LDR_CORNERS)
    def ledger(self):
        return {"yield_wh": self.yield_wh, "lost_wh": self.lost_wh, "lost_nc_wh": self.lost_nc_wh,
                "recovered_wh": max(0.0, self.lost_nc_wh - self.lost_wh),
                "tap_l": self.tap_used_l, "rain_l": self.rain_in_l, "spray_l": self.spray_used_l}
