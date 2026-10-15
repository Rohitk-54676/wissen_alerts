"""Generate hard test data.

Every run:
- random seed (fresh dataset each time)
- CSV has between 50 and 200 rows
- prices between 50 and 200
- mix of level and ma_cross rules
- tuned to produce between 1 and 7 alerts

Outputs prices_hard.csv and rules_hard.json, so the existing command
    python alerts.py prices_hard.csv rules_hard.json
keeps working.
"""
import csv
import json
import random
import sys
from datetime import date, timedelta


MIN_ALERTS = 1
MAX_ALERTS = 7
MIN_ROWS = 50
MAX_ROWS = 200
PRICE_LO = 50.0
PRICE_HI = 200.0


# ---------- helpers ----------

def rolling_mean(vals, w):
    out = []
    for i in range(len(vals)):
        if i < w - 1:
            out.append(None)
        else:
            out.append(sum(vals[i - w + 1:i + 1]) / w)
    return out


def count_alerts(prices_by_inst, rules):
    """Independent reference count. Used to keep the dataset in the
    1..MAX_ALERTS band."""
    total = 0
    for r in rules:
        s = prices_by_inst.get(r["instrument"], [])
        if not s:
            continue
        if r["type"] == "level":
            for i in range(1, len(s)):
                prev = s[i - 1][1]
                cur = s[i][1]
                if r["direction"] == "below" and prev >= r["level"] and cur < r["level"]:
                    total += 1
                elif r["direction"] == "above" and prev <= r["level"] and cur > r["level"]:
                    total += 1
        else:
            closes = [c for _, c in s]
            sm = rolling_mean(closes, r["short"])
            lm = rolling_mean(closes, r["long"])
            for i in range(1, len(s)):
                if None in (sm[i], lm[i], sm[i - 1], lm[i - 1]):
                    continue
                pd = sm[i - 1] - lm[i - 1]
                cd = sm[i] - lm[i]
                if r["direction"] == "above" and pd <= 0 and cd > 0:
                    total += 1
                elif r["direction"] == "below" and pd >= 0 and cd < 0:
                    total += 1
    return total


def gen_series_bounded(rng, n, lo, hi, vol, trend):
    """Price walk that stays roughly within [lo, hi] via soft mean reversion."""
    mid = (lo + hi) / 2
    p = rng.uniform(lo + 10, hi - 10)
    out = []
    for _ in range(n):
        pull = (mid - p) * 0.02
        p += pull + trend + rng.uniform(-vol, vol)
        p = max(lo, min(hi, p))
        out.append(round(p, 2))
    return out


# ---------- main ----------

def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else random.randint(1, 10**9)
    rng = random.Random(seed)
    print(f"seed = {seed} (run `python make_hard_data.py {seed}` to reproduce)")

    # Pick instrument count and days so rows land in [MIN_ROWS, MAX_ROWS].
    # Try a few (n_instruments, n_days) combos and pick one that fits.
    best = None
    for _ in range(50):
        n_instruments = rng.randint(3, 6)
        target_rows = rng.randint(MIN_ROWS, MAX_ROWS)
        n_days = max(20, target_rows // n_instruments)
        rows = n_instruments * n_days
        if MIN_ROWS <= rows <= MAX_ROWS:
            best = (n_instruments, n_days, rows)
            break
    if best is None:
        # fallback: force a fit
        n_instruments = 4
        n_days = rng.randint(MIN_ROWS // n_instruments,
                             MAX_ROWS // n_instruments)
        rows = n_instruments * n_days
        best = (n_instruments, n_days, rows)
    n_instruments, n_days, planned_rows = best

    start_date = date(2026, 1, 1)
    instruments = [f"INST{i+1:02d}" for i in range(n_instruments)]

    # --- price series, all within [50, 200] ---
    prices_by_inst = {}
    all_rows = []
    for inst in instruments:
        vol = rng.uniform(0.8, 2.5)
        trend = rng.uniform(-0.15, 0.15)
        closes = gen_series_bounded(rng, n_days, PRICE_LO, PRICE_HI, vol, trend)
        series = []
        for i, c in enumerate(closes):
            d = (start_date + timedelta(days=i)).isoformat()
            series.append((d, c))
            all_rows.append((d, inst, c))
        prices_by_inst[inst] = series

    # --- rules: mostly near edges, so most do NOT fire ---
    rules = []
    rule_id = 1
    for inst in instruments:
        closes = [c for _, c in prices_by_inst[inst]]
        lo, hi = min(closes), max(closes)
        n_rules = rng.randint(2, 4)
        for _ in range(n_rules):
            kind = rng.choice(["level", "ma_cross"])
            if kind == "level":
                if rng.random() < 0.5:
                    level = round(lo + rng.uniform(0.02, 0.12) * (hi - lo), 2)
                    direction = "below"
                else:
                    level = round(hi - rng.uniform(0.02, 0.12) * (hi - lo), 2)
                    direction = "above"
                rules.append({
                    "id": f"r{rule_id}",
                    "instrument": inst,
                    "type": "level",
                    "direction": direction,
                    "level": level,
                })
            else:
                # keep windows small so the cross has room to happen
                short = rng.choice([3, 5])
                long_ = short + rng.choice([3, 5, 7])
                direction = rng.choice(["above", "below"])
                rules.append({
                    "id": f"r{rule_id}",
                    "instrument": inst,
                    "type": "ma_cross",
                    "short": short,
                    "long": long_,
                    "direction": direction,
                })
            rule_id += 1

    n_alerts = count_alerts(prices_by_inst, rules)

    # --- trim if too many ---
    attempts = 0
    while n_alerts > MAX_ALERTS and attempts < 500:
        attempts += 1
        removed = False
        for r in list(rules):
            trial = [x for x in rules if x is not r]
            if count_alerts(prices_by_inst, trial) < n_alerts:
                rules.remove(r)
                n_alerts = count_alerts(prices_by_inst, rules)
                removed = True
                break
        if not removed:
            break

    # --- top up if too few ---
    attempts = 0
    while n_alerts < MIN_ALERTS and attempts < 200:
        attempts += 1
        inst = rng.choice(instruments)
        closes = [c for _, c in prices_by_inst[inst]]
        lo, hi = min(closes), max(closes)
        mid = (lo + hi) / 2
        band = rng.uniform(0.02, 0.10)
        level = round(mid + rng.uniform(-band, band) * (hi - lo), 2)
        direction = rng.choice(["above", "below"])
        rules.append({
            "id": f"r{rule_id}",
            "instrument": inst,
            "type": "level",
            "direction": direction,
            "level": level,
        })
        rule_id += 1
        n_alerts = count_alerts(prices_by_inst, rules)

    # --- write prices (shuffled) ---
    rng.shuffle(all_rows)
    with open("prices_hard.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "instrument", "close"])
        w.writerows(all_rows)

    # --- write rules ---
    with open("rules_hard.json", "w") as f:
        json.dump(rules, f, indent=2)

    # --- report ---
    lo_written = min(r[2] for r in all_rows)
    hi_written = max(r[2] for r in all_rows)
    print(f"instruments : {n_instruments}")
    print(f"days        : {n_days}")
    print(f"rows        : {len(all_rows)}  (target {MIN_ROWS}-{MAX_ROWS})")
    print(f"price range : {lo_written:.2f} .. {hi_written:.2f}  (target {PRICE_LO:.0f}-{PRICE_HI:.0f})")
    print(f"rules       : {len(rules)}")
    print(f"expected    : {n_alerts} alerts  (target {MIN_ALERTS}-{MAX_ALERTS})")
    print("wrote prices_hard.csv and rules_hard.json")


if __name__ == "__main__":
    main()