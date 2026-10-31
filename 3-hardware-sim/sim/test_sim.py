import sim
n = sim.Node("dust"); before = n.reading()["current_a"]; n.clean(); after = n.reading()["current_a"]
assert after > before + 0.3, (before, after)           # cleaning recovers dust loss
f = sim.Node("fault"); f.clean(); assert f.soil == 0.0 and f.reading()["current_a"] < 4.5   # fault never recovers
r = sim.Node("hotspot").reading(); flat = [x for row in r["temps_c"] for x in row]; assert max(flat) - sorted(flat)[2] > 5
print("sim ok")
