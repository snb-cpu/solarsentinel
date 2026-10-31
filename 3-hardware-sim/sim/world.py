"""The physical world around one panel: sun cycle, weather, dust, heat, faults, water.
Time is accelerated (World.step takes sim seconds). Used by virtual_node.py.
Layout: 8 sensor cells, 2 rows x 4 columns, index = row*4 + col.
"""
import math, random

ROWS, COLS = 2, 4
N = ROWS * COLS
HOT_CELL, CRACK_CELL = 5, 3     # where the hotspot and the cracked cell sit
ISC_A = 5.5            # panel current at 1000 W/m2, clean
VOC_V = 18.5
LUX_PER_WM2 = 100.0    # light the LDR sees per W/m2

class World:
    def __init__(self, start_hour=9.0, dust_mult=1.0):
        self.t = start_hour * 3600.0
        self.soil = [0.0] * N
        self.tcell = [32.0] * N
        self.offs = [random.uniform(-0.3, 0.3) for _ in range(N)]   # fixed cell-to-cell differences
        self.cloud = 0.1
        self.raining = False
        self.forecast_rain = False
        self.rain_at = None
        self.rain_until = 0.0
        self.dust_rate = 0.015 * dust_mult         # soil per sim hour (per cell, average)
        self.storm_until = 0.0
        self.faults = {"crack": False, "hotspot": False, "shade": False}
        self.tank = 70.0               # percent

    # ---- environment ----
    def hour(self): return (self.t / 3600) % 24
    def day(self): return int(self.t // 86400) + 1
    def clear_sky(self):
        h = self.hour()
        return 1000 * math.sin(math.pi * (h - 6) / 12) if 6 < h < 18 else 0.0
    def irradiance(self):
        return self.clear_sky() * (1 - 0.7 * self.cloud) * (0.25 if self.raining else 1)
    def ambient(self):
        return 27 + 7 * math.sin(math.pi * (self.hour() - 9) / 12) - (4 if self.raining else 0)
    def cell_irr(self, i):
        g = self.irradiance()
        if self.faults["shade"] and i % COLS == 0: g *= 0.4           # shadow on the left column
        return g * (1 - self.soil[i])

    # ---- one step: dt = sim seconds, real = real seconds, valve/blower = relay states ----
    def step(self, dt, real, valve, blower):
        self.t += dt
        # weather: slow cloud drift, scheduled rain
        if not self.raining:
            self.cloud = min(0.6, max(0.0, self.cloud + random.gauss(0, 0.02) * math.sqrt(dt / 60)))
            if self.forecast_rain and self.rain_at is None: self.rain_at = self.t + 5 * 3600
            if self.rain_at and self.t >= self.rain_at:
                self.raining, self.rain_until, self.rain_at, self.forecast_rain = True, self.t + 1.5 * 3600, None, False
        elif self.t >= self.rain_until:
            self.raining = False
        if self.raining:
            self.cloud = 0.9
            self.soil = [s * math.exp(-dt / 3600 * 1.2) for s in self.soil]   # rain washes ~70% per hour
            self.tank = min(100.0, self.tank + dt / 3600 * 15)                # and fills the tank
        # dust builds up, faster in a storm
        rate = self.dust_rate * (8 if self.t < self.storm_until else 1)
        self.soil = [min(0.4, s + dt / 3600 * rate * random.uniform(0.4, 1.6)) for s in self.soil]
        # wash: water strips dirt quickly, air only dries (no extra cleaning)
        if valve and self.tank > 0:
            self.soil = [s * math.exp(-real / 1.5) for s in self.soil]
            self.tank = max(0.0, self.tank - 1.0 * real)
        # heat: lagging toward the target, per cell
        g0 = self.irradiance()
        for i in range(N):
            gi = self.cell_irr(i)
            hot = 8 * self.soil[i] * g0 / 1000
            if self.faults["hotspot"] and i == HOT_CELL: hot += 12 * g0 / 1000
            if self.faults["crack"] and i == CRACK_CELL: hot += 10 * g0 / 1000
            target = self.ambient() + 0.025 * (g0 if not (self.faults["shade"] and i % COLS == 0) else g0 * 0.4) + hot + (-0.8 if i < COLS else 0.0) + self.offs[i]
            self.tcell[i] += (target - self.tcell[i]) * (1 - math.exp(-dt / 600))

    # ---- electrical ----
    def electrical(self):
        gc = [self.cell_irr(i) for i in range(N)]
        eff = 0.75 * sum(gc) / N + 0.25 * min(gc)
        i_a = ISC_A * eff / 1000 * (0.8 if self.faults["crack"] else 1.0)
        g = self.irradiance()
        v = VOC_V * (1 - 0.004 * (sum(self.tcell) / N - 25)) * (0.85 + 0.15 * min(1.0, g / 200)) if g > 1 else 0.0
        return max(v, 0.0), max(i_a, 0.0)
    def lux(self): return self.irradiance() * LUX_PER_WM2
