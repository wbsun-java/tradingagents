# Chart-Pattern Calibration Backtest (SP4) — Design Spec

Date: 2026-07-12
Status: approved design, pre-implementation
Parent: `CHART_PATTERN_ANALYSIS_PLAN.md` (backtest calibration, "具体阈值后续通过回测校准");
extends the pre-SP1 `scripts/backtest_chart_patterns.py`.
Sub-project: SP4 of 4. Consumes the flags/states introduced by SP1 (post-apex), SP2
(false-break machine), and SP3 (entry taxonomy). SP3b (emerging second-bottom stage) is
separately deferred and out of scope here.

## Problem

SP1–SP3 introduced ~13 interim constants (window bars, timing adjustments, confidence
tiers, proximity fractions) all marked "pending SP4 backtest calibration." Nothing has
checked whether the flags and states those constants produce actually carry the edge they
assume. SP4 answers that with a read-only walk-forward report — like the Wyckoff,
pocket-pivot, and trend-template backtests — that buckets forward returns so a human can
decide, per constant, whether to change it. SP4 tunes nothing itself.

## Scope decisions (user-approved 2026-07-12)

1. **Three lift tables in one report**: entry_state (SP3), apex-timing (SP1), SP2 tier.
2. **State-sampled, no dedupe**: at every walk-forward date, record every pattern's
   current state/flags + forward return. Overlapping windows autocorrelate — carry the
   same explicit caveat the trend-template report uses. (Matches that precedent; the
   natural fit for calibrating a signal read fresh each day.)
3. **Refactor to module + thin script** (matches `pocket_pivot_backtest.py` /
   `trend_template_backtest.py`): report logic in a new dataflow module; the existing
   script becomes a thin CLI. No new detection; nothing is auto-tuned.

## Scoring — directional edge

The taxonomy mixes long and short verdicts, so raw forward return is not comparable across
states. Every table scores a sample through one shared helper:

```
_edge(forward_return, direction):
    return forward_return  if direction in ("long", "none")   # none = long-reference
    return -forward_return if direction == "short"
hit = _edge(...) > 0
```

A positive `edge` always means the tested bet worked. **Which `direction` feeds `_edge`
depends on the table**, because a pattern's entry verdict and its breakout direction can
differ (a confirmed `descending_triangle` is `avoid`/`none` as an entry but a short as a
breakout). So each record stores the raw `forward_return` plus BOTH directions
(`entry_direction` = `entry_assessment.direction`, `pattern_direction` from the pattern's
`direction`), and: Table 1 uses `entry_direction`; Tables 2 and 3 use `pattern_direction`
(for the two false-break signals these coincide). `observe`/`avoid` (entry_direction
`none`) are scored as a long-reference; the validation is that they should show *lower*
edge than the actionable long entries. `forward_return = (close[t+H] - close[t]) /
close[t]`, dropped when `t+H` is beyond the frame. Warm-up: skip the first 60 bars.

## The three tables

Every table reports `n`, `hit_rate` (share with `edge > 0`), and `avg_edge`.

**Table 1 — entry_state lift (SP3):** one row per `entry_assessment.state`
(`predictive_bottom`, `breakout_entry`, `breakout_retest_entry`, `observe`, `avoid`,
`false_breakout_short`, `false_breakdown_long`). Read: do the three long entries beat
`observe`, does `avoid` trail both, do the two false-break states carry positive edge? A
flat gradient means `ENTRY_PROXIMITY_ATR` / `RETEST_WINDOW_BARS` / `PREDICTIVE_UNDERSHOOT
_ATR` need tightening.

**Table 2 — apex-timing lift (SP1):** confirmed triangle patterns
(`symmetrical/ascending/descending_triangle`, `status == "confirmed"`) bucketed
`post_apex_breakout` (if flagged) → else `late_apex_breakout` (if flagged) → else
`normal`. Read: late/post-apex breakouts should show lower edge, justifying the
`POST_APEX_TIMING_ADJUSTMENT` and easier-reversal asymmetry; if not, those adjustments are
unjustified.

**Table 3 — SP2 tier lift (SP2):** the two false-break signals only, bucketed by whether
`aggressive_confirmation` is in `risk_flags` (true / false / n_a columns, like the
pocket-pivot flag table — None never folds into False). Read: does the aggressive tier
underperform standard, justifying the 0.55 vs 0.60 confidence gap? If not, the tier split
adds no information.

## Data flow

`collect_samples(df, step, holding_days) -> list[dict]`: for each `as_of` in
`df["Date"].iloc[60::step]`, run `analyze_chart_patterns_from_data(window, as_of)` on
`df[df.Date <= as_of]`; for every pattern, compute `forward_return` from the full `df` and
append a record `{state, entry_direction, pattern, pattern_direction, status, risk_flags,
forward_return}`. Skip records whose forward window runs off the frame.

`new_stats()` / `aggregate(records, stats)`: fold each record into the three bucket
families (`entry_state`, `apex`, `tier`); a record contributes to Table 2 only when it is
a confirmed triangle, to Table 3 only when it is a false-break signal.

`format_report(stats) -> str`: render the three tables under a header that states the
symbol set, `holding_days`, total `n`, and the autocorrelation caveat.

## Files

| File | Change |
|---|---|
| `tradingagents/dataflows/chart_patterns_backtest.py` | NEW: `collect_samples`, `new_stats`, `aggregate`, `format_report`, `_forward_return`, `_edge` |
| `scripts/backtest_chart_patterns.py` | MOD (refactor): thin CLI over the module — argparse, per-symbol `load_ohlcv` + collect + aggregate, print |
| `tests/test_chart_patterns_backtest.py` | NEW: `_edge`/`hit` sign rules, `aggregate` bucket routing (incl. None n_a), `format_report` structure, a synthetic end-to-end `collect_samples` |

Every new file ≤150 lines; budgets fixed at plan time (module may split its table
renderers if `format_report` pushes it past the cap). `chart_patterns_backtest.py` imports
only `analyze_chart_patterns_from_data` + pandas — it does NOT modify detection.

## CLI

```
python scripts/backtest_chart_patterns.py AAPL MSFT NVDA \
    --start 2022-01-01 --end 2026-01-01 --step 5 --holding-days 10
```

Defaults mirror the existing script (`--start 2022-01-01`, `--step 5`, `--holding-days
10`); the operator reruns with `--holding-days 20` for the second horizon, as done for the
pocket-pivot and trend-template sweeps.

## Non-goals

- **No parameter sweep**: SP4 does not re-run detection with varied constant values; it
  buckets the outcomes the current constants produce. Re-detection sweeps are a separate
  effort if a table shows a constant is wrong.
- No auto-tuning, no P&L / position sizing / execution modeling, no new detection logic.
- No dedupe (state-sampling is deliberate; the autocorrelation caveat stands in for it).
- SP3b (emerging second-bottom stage) is out of scope.
