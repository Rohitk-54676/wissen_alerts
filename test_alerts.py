import unittest
import tempfile, os, json, csv, io
import contextlib
from alerts import run, rolling_mean, eval_level_rule, eval_ma_cross_rule, load_prices


def write_tmp(content, suffix):
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, newline="")
    f.write(content)
    f.close()
    return f.name


class TestRollingMean(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(rolling_mean([1, 2, 3, 4, 5], 3),
                         [None, None, 2.0, 3.0, 4.0])

    def test_window_equals_length(self):
        self.assertEqual(rolling_mean([1, 2, 3], 3), [None, None, 2.0])

    def test_window_larger_than_data(self):
        self.assertEqual(rolling_mean([1, 2], 5), [None, None])


class TestLevelRule(unittest.TestCase):
    def test_cross_below(self):
        series = [("2026-09-01", 1520.0), ("2026-09-02", 1498.0)]
        rule = {"id": "r1", "instrument": "X", "type": "level",
                "direction": "below", "level": 1500}
        alerts = eval_level_rule(series, rule)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["date"], "2026-09-02")

    def test_no_fire_if_already_below(self):
        series = [("2026-09-01", 1490.0), ("2026-09-02", 1480.0)]
        rule = {"id": "r1", "instrument": "X", "type": "level",
                "direction": "below", "level": 1500}
        self.assertEqual(eval_level_rule(series, rule), [])

    def test_touch_exactly_level_fires_next_day(self):
        # prev == level (1500.0) counts as "not yet crossed below"
        # because the rule tests prev >= level. So the next day (1499.0)
        # does fire. This is a deliberate design choice: touching the
        # level is treated as the "before" state, not the "after" state.
        series = [("2026-09-01", 1500.0), ("2026-09-02", 1499.0)]
        rule = {"id": "r1", "instrument": "X", "type": "level",
                "direction": "below", "level": 1500}
        alerts = eval_level_rule(series, rule)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["date"], "2026-09-02")

    def test_cross_above(self):
        series = [("2026-09-01", 1490.0), ("2026-09-02", 1510.0)]
        rule = {"id": "r2", "instrument": "X", "type": "level",
                "direction": "above", "level": 1500}
        alerts = eval_level_rule(series, rule)
        self.assertEqual(len(alerts), 1)

    def test_first_day_never_fires(self):
        series = [("2026-09-01", 1400.0)]
        rule = {"id": "r1", "instrument": "X", "type": "level",
                "direction": "below", "level": 1500}
        self.assertEqual(eval_level_rule(series, rule), [])


class TestMaCrossRule(unittest.TestCase):
    def test_golden_cross(self):
        # falling then rising -> short crosses above long
        closes = [10, 9, 8, 7, 6, 5, 6, 7, 8, 9, 10, 11]
        series = [(f"2026-09-{i+1:02d}", c) for i, c in enumerate(closes)]
        rule = {"id": "r1", "instrument": "X", "type": "ma_cross",
                "short": 3, "long": 5, "direction": "above"}
        alerts = eval_ma_cross_rule(series, rule)
        self.assertGreaterEqual(len(alerts), 1)

    def test_no_cross_when_short_window_not_ready(self):
        # only 3 days, short=5 long=10 -> no MA defined, no alerts
        closes = [1, 2, 3]
        series = [(f"2026-09-{i+1:02d}", c) for i, c in enumerate(closes)]
        rule = {"id": "r1", "instrument": "X", "type": "ma_cross",
                "short": 5, "long": 10, "direction": "above"}
        self.assertEqual(eval_ma_cross_rule(series, rule), [])

    def test_ma_cross_fires_only_on_cross_day(self):
        """After the cross, subsequent days where short > long must NOT fire."""
        # 15 down, 15 up - same shape as make_hard_data.py, deterministic.
        closes = [4000 - 20 * i for i in range(15)] + \
                 [3700 + 30 * i for i in range(1, 16)]
        series = [(f"2026-09-{i+1:02d}", c) for i, c in enumerate(closes)]
        rule = {"id": "r2", "instrument": "TCS", "type": "ma_cross",
                "short": 5, "long": 20, "direction": "above"}
        alerts = eval_ma_cross_rule(series, rule)
        # exactly one cross should fire, not many
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["date"], "2026-09-22")


class TestEndToEnd(unittest.TestCase):
    def test_sorts_out_of_order_dates(self):
        prices = (
            "date,instrument,close\n"
            "2026-09-03,X,1498.0\n"
            "2026-09-01,X,1520.0\n"
            "2026-09-02,X,1530.0\n"
        )
        rules = json.dumps([{"id": "r1", "instrument": "X", "type": "level",
                             "direction": "below", "level": 1500}])
        pp = write_tmp(prices, ".csv")
        rp = write_tmp(rules, ".json")
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                run(pp, rp)
            out = buf.getvalue().strip().splitlines()
            self.assertEqual(len(out), 1)
            self.assertTrue(out[0].startswith("2026-09-03 r1 X"))
        finally:
            os.unlink(pp); os.unlink(rp)

    def test_orders_by_date_then_rule_id(self):
        # two instruments forced to cross on the same day.
        prices = (
            "date,instrument,close\n"
            "2026-09-01,A,1520.0\n"
            "2026-09-01,B,1520.0\n"
            "2026-09-02,A,1498.0\n"
            "2026-09-02,B,1498.0\n"
        )
        rules = json.dumps([
            {"id": "r2", "instrument": "B", "type": "level", "direction": "below", "level": 1500},
            {"id": "r1", "instrument": "A", "type": "level", "direction": "below", "level": 1500},
        ])
        pp = write_tmp(prices, ".csv"); rp = write_tmp(rules, ".json")
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                run(pp, rp)
            lines = buf.getvalue().strip().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertTrue(lines[0].startswith("2026-09-02 r1 A"))
            self.assertTrue(lines[1].startswith("2026-09-02 r2 B"))
        finally:
            os.unlink(pp); os.unlink(rp)


if __name__ == "__main__":
    unittest.main()