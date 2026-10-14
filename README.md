# Price Alert Tool

Command-line tool that reads daily prices (CSV) and alert rules (JSON),
and prints which alerts fired on which day.

## How to run

Python 3.8+. No dependencies - standard library only.

    python alerts.py prices.csv rules.json

Run tests:

    python -m unittest test_alerts.py -v

## Input formats

Prices CSV - one row per instrument per trading day (dates may be out of order):

    date,instrument,close
    2026-09-01,INFY,1520.50
    2026-09-01,TCS,3890.00
    2026-09-02,INFY,1534.10
    2026-09-02,TCS,3902.25
    2026-09-03,INFY,1498.00

Rules JSON - any number of rules:

    [
      {"id":"r1","instrument":"INFY","type":"level","direction":"below","level":1500},
      {"id":"r2","instrument":"TCS","type":"ma_cross","short":5,"long":20,"direction":"above"}
    ]

## Rule semantics

- **level** - fires on the first day `close` crosses `level` in the given
  direction. "Crosses" means yesterday's close was on the other side
  (`>= level` for below, `<= level` for above) and today's close is
  strictly past it. Touching the level exactly does not count as
  having crossed; it counts as the "before" state.
- **ma_cross** - fires on the day the short moving average crosses the
  long moving average in the given direction. Both MAs must be defined
  today *and* yesterday. Only the crossing day fires, not every day
  the short is above or below the long.

Rows are sorted per instrument by ISO date before evaluation, so
out-of-order input is handled. Output is sorted by date, then rule id:

    <date> <rule_id> <instrument> <type> <direction> <value>

## Verification

Sample run:

    $ python alerts.py prices.csv rules.json
    2026-09-03 r1 INFY level below 1500

Harder run - out-of-order dates, MA cross, multiple level recrossings:

    $ python make_hard_data.py
    $ python alerts.py prices_hard.csv rules_hard.json
    2026-09-04 r1 INFY level below 1500
    2026-09-09 r1 INFY level below 1500
    2026-09-22 r2 TCS ma_cross above 5/20

I hand-checked the TCS alert. On 2026-09-21, MA5 = 3820.0 and
MA20 = 3822.5 (short below long). On 2026-09-22, MA5 = 3850.0 and
MA20 = 3820.0 (short above long). The rule fires on 09-22 only. On
09-23 the short is still above the long but no alert fires, which is
correct - it is a state, not a crossing.

Unit tests (13) cover: rolling-mean windowing, level cross in both
directions, first-day non-firing, touch-at-level, MA-not-ready window,
cross-day-only firing, and end-to-end ordering with out-of-order dates.

## How I used the AI assistant

Prompts in brief:

1. "Given this problem statement, propose the smallest correct algorithm
   for level and MA-cross rules, and list edge cases that break naive
   implementations."
2. "Draft unittest cases for those edge cases."
3. "Review rolling_mean for off-by-one errors in the windowing logic."

## What the assistant got wrong

- **`rolling_mean` off-by-one.** The first draft subtracted the
  outgoing value *before* checking `i >= window - 1`, so the first
  defined MA was wrong. I caught it by writing
  `test_window_equals_length`, which expected `[None, None, 2.0]` for
  `[1, 2, 3]` with window 3. The test failed. I rewrote the loop so the
  subtraction happens only when `i >= window`, and the test passed.

- **MA-cross fired every day after the cross.** The first draft
  checked `short_ma[i] > long_ma[i]` alone, which fires on every day
  the short is above the long, not only the crossing day. I changed it
  to compare today's and yesterday's differences
  (`prev_diff <= 0 and cur_diff > 0`) and added
  `test_ma_cross_fires_only_on_cross_day`.

- **Level rule treated touching as crossed.** The first draft used
  `prev > level` (strict) for the below case, which meant a touch at
  exactly the level did not count as being on the "before" side. I
  changed it to `prev >= level` and added a test to pin the behaviour.

## What I changed and why

- **Pure standard library.** No `pip install` step means no install
  risk at evaluation time.
- **Sort per instrument by ISO date string.** ISO dates sort
  lexicographically, so no date parsing needed.
- **Alerts collected as dicts, then sorted by `(date, rule id)`.** The
  output ordering is explicit, not incidental to evaluation order.
- **Warn to stderr on missing instrument or unknown rule type, then
  continue.** One bad rule does not kill the run for all the others.
- **Debugged the harder dataset by inspecting intermediate values.**
  My first attempt at `make_hard_data.py` produced no TCS alert.
  Instead of changing code, I dumped the MA series and saw the V-shape
  was too shallow for MA5 to overtake MA20 within 30 days. I
  regenerated with a sharper V; the cross appeared exactly where I
  predicted. This is why I trust the tests - I verified the numbers,
  not just the pass/fail.

## Known limitations

- Dates are compared as strings; the code assumes ISO `YYYY-MM-DD`.
- Duplicate `(date, instrument)` rows: last one wins after a stable
  sort. In production I would deduplicate upstream or raise.
- No calendar awareness - rows are treated as consecutive
  observations, not as a fixed trading calendar.
- Float equality on the level has no epsilon tolerance.

## Files

- `alerts.py` - the tool
- `test_alerts.py` - 13 unit and end-to-end tests
- `prices.csv`, `rules.json` - sample inputs
- `prices_hard.csv`, `rules_hard.json`, `make_hard_data.py` - harder
  dataset with a golden cross and multiple level recrossings