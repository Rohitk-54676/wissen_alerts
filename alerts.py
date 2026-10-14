#!/usr/bin/env python3
"""Price Alert Tool - reads prices CSV + rules JSON, prints fired alerts."""
import sys
import json
import csv
from datetime import datetime
from collections import defaultdict


# ---------- Loading ----------

def load_prices(path):
    """Return dict: instrument -> list of (date, close) sorted by date ascending."""
    by_instrument = defaultdict(list)
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            inst = row["instrument"].strip()
            date = row["date"].strip()
            close = float(row["close"])
            by_instrument[inst].append((date, close))
    # sort each instrument's series by date
    for inst in by_instrument:
        by_instrument[inst].sort(key=lambda x: x[0])
    return by_instrument


def load_rules(path):
    with open(path) as f:
        return json.load(f)


# ---------- Moving average ----------

def rolling_mean(values, window):
    """Return list same length as values; entry i = mean of values[i-window+1..i]
    or None if not enough data yet."""
    out = [None] * len(values)
    running = 0.0
    for i, v in enumerate(values):
        running += v
        if i >= window:
            running -= values[i - window]
        if i >= window - 1:
            out[i] = running / window
    return out


# ---------- Rule evaluation ----------

def eval_level_rule(series, rule):
    """series = list of (date, close) sorted ascending. Returns list of alert dicts."""
    alerts = []
    level = rule["level"]
    direction = rule["direction"]  # "below" or "above"
    for i in range(1, len(series)):
        prev_close = series[i - 1][1]
        cur_date, cur_close = series[i]

        if direction == "below":
            # crossed below: prev was >= level, now < level
            if prev_close >= level and cur_close < level:
                alerts.append({
                    "date": cur_date,
                    "id": rule["id"],
                    "instrument": rule["instrument"],
                    "type": "level",
                    "direction": "below",
                    "value": level,
                })
        elif direction == "above":
            if prev_close <= level and cur_close > level:
                alerts.append({
                    "date": cur_date,
                    "id": rule["id"],
                    "instrument": rule["instrument"],
                    "type": "level",
                    "direction": "above",
                    "value": level,
                })
    return alerts


def eval_ma_cross_rule(series, rule):
    alerts = []
    short_w = rule["short"]
    long_w = rule["long"]
    direction = rule["direction"]  # "above" or "below"

    closes = [c for _, c in series]
    short_ma = rolling_mean(closes, short_w)
    long_ma = rolling_mean(closes, long_w)

    for i in range(1, len(series)):
        # both MAs must be defined today AND yesterday
        if None in (short_ma[i], long_ma[i], short_ma[i - 1], long_ma[i - 1]):
            continue
        prev_diff = short_ma[i - 1] - long_ma[i - 1]
        cur_diff = short_ma[i] - long_ma[i]

        if direction == "above" and prev_diff <= 0 and cur_diff > 0:
            alerts.append({
                "date": series[i][0],
                "id": rule["id"],
                "instrument": rule["instrument"],
                "type": "ma_cross",
                "direction": "above",
                "value": f"{short_w}/{long_w}",
            })
        elif direction == "below" and prev_diff >= 0 and cur_diff < 0:
            alerts.append({
                "date": series[i][0],
                "id": rule["id"],
                "instrument": rule["instrument"],
                "type": "ma_cross",
                "direction": "below",
                "value": f"{short_w}/{long_w}",
            })
    return alerts


# ---------- Main ----------

def run(prices_path, rules_path):
    prices = load_prices(prices_path)
    rules = load_rules(rules_path)

    all_alerts = []
    for rule in rules:
        inst = rule["instrument"]
        series = prices.get(inst, [])
        if not series:
            # no prices for this instrument - skip (or warn on stderr)
            print(f"warning: no prices for {inst}", file=sys.stderr)
            continue

        if rule["type"] == "level":
            all_alerts.extend(eval_level_rule(series, rule))
        elif rule["type"] == "ma_cross":
            all_alerts.extend(eval_ma_cross_rule(series, rule))
        else:
            print(f"warning: unknown rule type {rule['type']}", file=sys.stderr)

    # sort by date, then rule id
    all_alerts.sort(key=lambda a: (a["date"], a["id"]))

    for a in all_alerts:
        print(f"{a['date']} {a['id']} {a['instrument']} {a['type']} {a['direction']} {a['value']}")

    return all_alerts


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python alerts.py prices.csv rules.json", file=sys.stderr)
        sys.exit(1)
    run(sys.argv[1], sys.argv[2])