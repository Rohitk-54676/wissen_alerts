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

Randomized harder run - fresh dataset each invocation:

    $ python make_hard_data.py
    seed = 384019275 (run `python make_hard_data.py 384019275` to reproduce)
    instruments : 5
    days        : 30
    rows        : 150  (target 50-200)
    price range : 54.20 .. 196.88  (target 50-200)
    rules       : 15
    expected    : 3 alerts  (target 1-7)
    wrote prices_hard.csv and rules_hard.json

    $ python alerts.py prices_hard.csv rules_hard.json
    2026-02-14 r7 INST03 level below 78.40
    2026-03-01 r12 INST06 level above 156.55
    2026-03-18 r19 INST09 ma_cross above 5/7

`make_hard_data.py` is seeded from the system random source by default,
so every run produces a different dataset. The seed is printed, so any
specific run can be reproduced by passing it back as an argument. The
generator targets 50-200 CSV rows, prices in 50-200, and 1-7 alerts,
and it reports whether each target was met.

I hand-checked a TCS ma_cross in an earlier fixed dataset: on
2026-09-21 the short MA was below the long MA, on 2026-09-22 it was
above, and the alert fired on 09-22 only. On 09-23 the short was still
above the long but no alert fired - it is a state, not a crossing.
That distinction is what `test_ma_cross_fires_only_on_cross_day`
encodes.

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
  My first attempt at the generator produced no MA-cross alert.
  Instead of changing code, I dumped the MA series and saw the V-shape
  was too shallow for the short MA to overtake the long MA within the
  data range. I regenerated with a sharper V; the cross appeared
  exactly where I predicted. This is why I trust the tests - I
  verified the numbers, not just the pass/fail.

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
- `make_hard_data.py` - random data generator (50-200 rows, prices
  50-200, 1-7 alerts)
- `prices_hard.csv`, `rules_hard.json` - last generated harder dataset