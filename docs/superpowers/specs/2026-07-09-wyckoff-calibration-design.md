# Wyckoff Walk-Forward Calibration Report

Date: 2026-07-09

## Purpose

Per `WYCKOFF_ANALYSIS_PLAN.md`'s "后续迭代" item 2: build a read-only
walk-forward hit-rate report for the Wyckoff structure module, analogous to
`scripts/backtest_chart_patterns.py`. It answers "when the tool reports a
confirmed Phase D/E directional read, how often does price actually move
that way over the following N days" — evidence for a human to later hand-tune
`DOMINANT_WEIGHT`, the confidence formula, and the VSA constants. This script
does not tune anything itself.

## Scope

- Applies to: a small additive edit to the existing
  `tradingagents/dataflows/wyckoff_bias.py` (one new field on the result
  dict), and a new `scripts/backtest_wyckoff.py`.
- Does not apply to: `wyckoff_range.py`, `wyckoff_events.py`,
  `wyckoff_accumulation.py`, `wyckoff_distribution.py`, `wyckoff_vsa*.py`,
  `market_analyst.py`, `trading_graph.py` — no detection logic, tool
  signature, or prompt wiring changes. `wyckoff_bias.py` is project-custom
  (not upstream), so no upstream-approval gate applies.
- Out of scope (not part of this design): auto-tuning/parameter sweeps (a
  human reads the report and edits constants by hand, same as the
  chart-pattern script); complex/multi-range structure handling (plan item
  3); extending Wyckoff weighting into bull/bear/risk-debate agents (plan
  item 4 — requires separate upstream-file approval).

## Approaches considered

1. **Read-only hit-rate report, mirroring `backtest_chart_patterns.py`**
   (chosen). Reuses the exact walk-forward/bucket/print shape already
   established and already understood by whoever reads these reports.
2. Report + parameter sweep (re-run across a grid of candidate VSA
   thresholds). Rejected for this pass: bigger surface, and the plan
   explicitly treats `DOMINANT_WEIGHT` as a policy constant "not a backtest
   artifact" — a sweep implies auto-optimization the plan doesn't ask for.

## Design

### Additive field on `wyckoff_bias.py`

`analyze_vsa` already returns `(vsa_signals, delta)`, but
`analyze_wyckoff_structure_from_data` only keeps the post-adjustment
`confidence` — the signed `delta` itself is discarded. Add
`result["vsa_confidence_delta"] = round(delta, 4)` next to `vsa_signals`
(same condition: only present on a non-neutral read). This is additive only;
existing tests assert key presence, not full-dict equality, so no existing
test changes are required beyond adding coverage for the new field.

### `scripts/backtest_wyckoff.py`

Mirrors `backtest_chart_patterns.py`'s structure and helpers (each script is
self-contained; no cross-import of another script's private functions):

- CLI: `symbols` (nargs+), `--start` (default `2022-01-01`), `--end` (default
  today), `--step` (default 5 — business days between walk-forward checks),
  `--holding-days` (default **20**, vs. the chart-pattern script's 10 —
  Wyckoff markup/markdown moves following a Phase D/E read play out slower
  than a chart-pattern breakout).
- `_walk_dates`, `_forward_return`, `_direction_hit`: same logic as the
  chart-pattern script (`_direction_hit` treats `"bullish"`/`"bearish"`
  identically to that script's `phase_bias` values).
- `backtest_symbol(symbol, start, end, step, holding_days, stats)`:
  - Loads full history via `load_ohlcv`, filters to `[start, end]`, skips
    symbols with under 80 rows (same guard as the chart script).
  - For each walk-forward `as_of`: build `window = full[full["Date"] <=
    as_of]`, call `analyze_wyckoff_structure_from_data(window, as_of_str)`,
    catching `ValueError` (insufficient history for `MIN_ROWS`) and
    continuing.
  - Skip unless `result["trading_range"]["status"] == "confirmed"` (Phase
    D/E) and `result["phase_bias"] != "neutral"` — only score reads the tool
    would present to the LLM as a firm directional call, matching the
    chart-pattern script only scoring `status == "confirmed"` patterns.
  - **Dedup key**: `(phase_bias, current_phase, trading_range["start_date"])`.
    A trading range can stay in Phase D for many consecutive walk-forward
    samples before a breakout resolves it; without dedup the same call would
    be counted (and its forward return re-measured from a later, already-
    moved price) on every step. Only a phase advance (D → E) or a new range
    (`start_date` changes) counts as a fresh call. This differs from the
    chart-pattern script's key (which includes `end_date`, fixed once
    confirmed) because Wyckoff phases have no analogous fixed end marker.
  - Compute `forward = _forward_return(...)`; skip if `None`.
  - `hit = _direction_hit(result["phase_bias"], forward)`.
  - `vsa_effect`: `"none"` if `vsa_confidence_delta` is absent or `0`,
    `"positive"` if `> 0`, `"negative"` if `< 0`.
  - Bucket key: `(current_phase, vsa_effect)`. Accumulate `count`, `hits`,
    `confidence_sum`, `return_sum` — same accumulator shape as the
    chart-pattern script.
- `print_report(stats)`: same table shape — `phase`, `vsa_effect`, `n`,
  `hit_rate`, `avg_conf`, `avg_fwd_ret` columns, sorted by key.
- `main()`: argparse wiring identical in spirit to the chart-pattern script.

Target: keep the file at or under 150 lines (the chart-pattern script is
128). If the dedup/bucketing logic pushes it over, split bucket/report
printing into a second file rather than compressing past readability.

## Testing plan

This is a manual research script (the chart-pattern script has no test
file), so no new test file is planned. Verification is a smoke run instead:

- `python scripts/backtest_wyckoff.py AAPL MSFT --start 2023-01-01 --end
  2026-01-01` completes without error and prints a non-empty report table
  (or a clear "not enough history" / "no confirmed reads" message) for at
  least one symbol.
- `ruff check scripts/backtest_wyckoff.py tradingagents/dataflows/wyckoff_bias.py`
  passes.
- Add one small unit-test addition to the existing
  `tests/test_wyckoff_bias.py`: a synthetic accumulation read's payload
  includes `vsa_confidence_delta` as a float, and a neutral read still has
  no such key.

## Acceptance criteria

- `scripts/backtest_wyckoff.py` runs end-to-end against real tickers and
  produces a hit-rate table bucketed by `(current_phase, vsa_effect)`.
- No detection/scoring logic in `wyckoff_range.py`/`wyckoff_accumulation.py`/
  `wyckoff_distribution.py`/`wyckoff_vsa*.py` changes — this is observation
  only.
- `wyckoff_bias.py`'s new field is additive; existing Wyckoff/market-analyst
  tests still pass unmodified.
- No future-data leakage: each walk-forward window only includes bars up to
  `as_of`.

> This module is for research and analysis support only; it does not
> constitute investment advice and does not place trades.
