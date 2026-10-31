"""Checks on the virtual node's logic (a port of the firmware): tap refill, day-only sleep, energy bill. No network, fake clock.
   python3 test_node.py"""
import random, unittest
import virtual_node as vn
from world import World

class FakeTime:                                           # the node counts milliseconds with time.time(); here we control it
    def __init__(self): self.now = 1000.0
    def time(self): return self.now
    def strftime(self, fmt): return "00:00:00"
    def sleep(self, s): self.now += s

def make(hour=10.0):
    random.seed(1); vn.time = FakeTime()
    w = World(start_hour=hour); n = vn.Node(w, vn.load_cfg(), "P1")
    return w, n

def tick(w, n, seconds=1.0, steps=1, water=True):         # real time passes: the world and the node both move
    for _ in range(steps):
        vn.time.now += seconds
        w.step(seconds, seconds, n.spray, n.blower, n.tap_open and water)
        n.account(seconds, seconds)
        if n.mode == "active": n.clean_loop(); n.tap_loop(); n.watch_the_sun(seconds)
        else: n.check_wake()

class TapRefill(unittest.TestCase):
    def test_opens_below_25_and_closes_at_85(self):
        w, n = make(); w.tank = 20; opened = closed = False
        for _ in range(200):
            tick(w, n)
            opened = opened or n.tap_open
            if opened and not n.tap_open: closed = True; break
        self.assertTrue(opened and closed)
        self.assertGreaterEqual(w.tank, 84); self.assertLess(w.tank, 95)
        self.assertGreater(w.tap_used_l, 8)

    def test_rain_hold_keeps_the_tap_shut_until_critical(self):
        w, n = make(); n.tap_hold = True; w.tank = 20
        for _ in range(10): tick(w, n)
        self.assertFalse(n.tap_open)
        w.tank = 8                                         # nearly empty: open anyway
        for _ in range(3): tick(w, n)
        self.assertTrue(n.tap_open)

    def test_stuck_sensor_cannot_flood_the_tank(self):
        w, n = make(); n.read_tank = lambda: 10.0           # a level sensor that never sees the water rise
        w.tank = 10
        for _ in range(200): tick(w, n, water=False)        # no water arrives (closed supply tap): 200 s > TAP_MAX_MS (180 s)
        self.assertFalse(n.tap_open)
        self.assertGreater(n.tap_lock_until, vn.time.now * 1000)

    def test_wash_waits_for_water(self):
        w, n = make(); n.tank_pct = 5.0
        n.start_clean(4000, 8000, "test")
        self.assertEqual(n.cs, "IDLE")

class DayOnly(unittest.TestCase):
    def test_sleeps_after_dark_and_wakes_at_sunrise(self):
        w, n = make(hour=17.0)
        tick(w, n, 60, 150)                                 # 17:00 to 19:30
        self.assertEqual(n.mode, "sleep"); self.assertEqual(n.sleep_reason, "dark")
        self.assertFalse(n.spray or n.blower or n.tap_open)
        w.t += 11 * 3600                                    # morning
        tick(w, n, 60, 70)
        self.assertEqual(n.mode, "active")

    def test_sleeps_in_rain_and_wakes_when_dry(self):
        w, n = make(hour=11.0)
        w.raining, w.rain_until = True, w.t + 3 * 3600
        tick(w, n, 60, 6)
        self.assertEqual((n.mode, n.sleep_reason), ("sleep", "rain"))
        w.raining = False
        tick(w, n, 60, 15)
        self.assertEqual(n.mode, "active")

    def test_does_not_go_to_sleep_in_the_middle_of_a_wash_or_refill(self):
        w, n = make(hour=18.5)
        n.cs = "WATER"; n.cs_start = vn.time.now * 1000 + 10 ** 9      # a wash that will not finish
        for _ in range(60): vn.time.now += 60; w.step(60, 0, False, False, False); n.watch_the_sun(60)
        self.assertEqual(n.mode, "active")

    def test_sleeping_costs_a_fraction_of_being_awake(self):
        w, n = make(hour=10.0)
        tick(w, n, 60, 60); awake_wh_per_h = n.node_wh                      # one hour awake in daylight
        n.mode, n.wake_at = "sleep", w.t + 10 ** 7                         # then one hour asleep
        before = n.node_wh; tick(w, n, 60, 60)
        asleep_wh_per_h = n.node_wh - before
        self.assertLess(asleep_wh_per_h, 0.01 * awake_wh_per_h)
        self.assertGreater(n.always_on_wh, n.node_wh)

class Hardware(unittest.TestCase):
    def test_ads1115_lsb_and_gain(self):
        w, n = make()
        counts, mv = [0, 0], 0
        v = n.ads(1.0, 2, counts)                          # +-2.048 V range: 62.5 uV per count
        self.assertAlmostEqual(v, 1.0, delta=0.001); self.assertAlmostEqual(counts[0], 16000, delta=10)

    def test_the_four_light_sensors_and_temperatures_come_through(self):
        w, n = make(); r = n.reading()
        self.assertEqual(len(r["ldr_corners_lux"]), 4); self.assertEqual(len(r["temps_c"]), 2); self.assertEqual(len(r["temps_c"][0]), 4)
        self.assertIn("node_mw", r); self.assertIn("tap_open", r)

if __name__ == "__main__":
    unittest.main(verbosity=2)
