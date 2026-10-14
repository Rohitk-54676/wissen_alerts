"""Generate hard test data: out-of-order dates, a golden cross, and level recrossing."""
import csv, json, random

random.seed(42)

# TCS: 30 days. 15 down, 15 up - sharp enough to force a golden cross.
tcs_prices = []
p = 4000.0
for i in range(15):
    p -= 20          # steeper downtrend
    tcs_prices.append(round(p, 2))
for i in range(15):
    p += 30          # steeper uptrend
    tcs_prices.append(round(p, 2))

# INFY: crosses 1500 three times -> three level alerts expected
infy_closes = [1520, 1510, 1505, 1498, 1495, 1502, 1510, 1508, 1499, 1490, 1510]
infy_prices = [round(c + random.uniform(-1, 1), 2) for c in infy_closes]

rows = []
for i, c in enumerate(infy_prices):
    rows.append((f"2026-09-{i+1:02d}", "INFY", c))
for i, c in enumerate(tcs_prices):
    rows.append((f"2026-09-{i+1:02d}", "TCS", c))

random.shuffle(rows)  # out-of-order input

with open("prices_hard.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["date", "instrument", "close"])
    w.writerows(rows)

rules = [
    {"id": "r1", "instrument": "INFY", "type": "level",
     "direction": "below", "level": 1500},
    {"id": "r2", "instrument": "TCS",  "type": "ma_cross",
     "short": 5, "long": 20, "direction": "above"},
]
with open("rules_hard.json", "w") as f:
    json.dump(rules, f, indent=2)

print("wrote prices_hard.csv and rules_hard.json")