# Minervini Trend Template Walk-Forward Report Design

**Goal:** Give the Minervini trend-template module its calibration instrument — a
walk-forward hit-rate report bucketed by criteria-pass-count bands and rs_score bands —
completing item (4) of the TA-module deferred-work sequencing. It is read-only: no
position sizing, execution, P&L, or auto-tuning; a human reads it against
`trend_template.py`'s thresholds and `_QUARTER_WEIGHTS`.

**The two questions it answers:**
1. Does the template's pass-count gradient predict forward outcomes (is 8/8 stage-2
   actually better than 7, than 5–6, than 0–4)?
2. Does `rs_score` add lift **beyond** the pass count — i.e., within a pass band, do
   higher rs_score bands show better outcomes? This is the promised "rigorous
   relative-strength calibration" grounding: if rs bands separate outcomes, the current
   quarter-weighted proxy is vindicated; if they don't, that is the documented,
   data-driven case for redesigning the proxy as a separate follow-up.

**Decisions locked during brainstorming:**
- **Backtest only.** No `relative_strength_score` redesign in this round (chosen over
  bundling a redesign, which would be blind until this report exists).
- **Report shape: two sections** — pass-band baseline, then rs-band lift within each pass
  band (chosen over a full 9×3 exact cross-product, which goes sparse, and over a
  stage-2-only view, which throws away the gradient).

## Key structural difference from the pocket-pivot backtest

The trend template is a **state read** — every date yields `passed_count` (0–8),
`rs_score`, `stage_2_uptrend` — not a point event. So collection samples one record per
walk date with **no dedupe** (the pocket-pivot script dedupes events; the Wyckoff script
dedupes structures; here neither applies). Adjacent samples overlap and autocorrelate;
the module and script docstrings must say hit rates are tendencies over correlated
samples, not independent trials.

## Files

New (each ≤150 lines, tests included):

- `tradingagents/dataflows/trend_template_backtest.py` — testable logic:
  - `collect_readings(df, benchmark_df, step, holding_days) -> list[dict]` — walk-forward
    sampling over one symbol's already-trimmed OHLCV frame plus the benchmark frame.
    Each record: `date`, `passed_count`, `total_criteria`, `stage_2_uptrend`,
    `rs_score` (float | None), `forward_return`, `hit`.
  - `pass_band(passed_count) -> str` — `"0-4"`, `"5-6"`, `"7"`, `"8"`.
  - `rs_band(rs_score) -> str` — `"rs<0"`, `"0<=rs<=0.10"`, `"rs>0.10"`, `"n/a"` for None
    (band edges: 0 belongs to the middle band, 0.10 belongs to the middle band,
    i.e. `score < 0` / `0 <= score <= 0.10` / `score > 0.10`).
  - `new_stats() -> dict`, `aggregate(records, stats) -> None`,
    `format_report(stats) -> str` — same accumulator idiom as
    `pocket_pivot_backtest.py` (`{"count", "hits", "return_sum"}` buckets).
- `scripts/backtest_trend_template.py` — thin argparse CLI mirroring the sibling scripts:
  positional `symbols`, `--benchmark` (default `SPY`), `--start` (default `2022-01-01`),
  `--end` (default today), `--step` (default 5), `--holding-days` (default 20). Loads the
  benchmark frame once per run via `load_ohlcv(benchmark, end)`; per symbol loads the
  stock frame, trims both to `--start`, and delegates to
  `collect_readings`/`aggregate`/`format_report`.
- `tests/test_trend_template_backtest.py` — unit tests (see Testing).

No existing file is modified.

## Collection

- Walk analysis dates every `step` bars after a warm-up of `WARMUP_BARS = 260` (252 bars
  for the 52-week extremes and 200-SMA, and `relative_strength_score` needs 253 aligned
  stock/benchmark bars).
- At each walk date, truncate **both** frames to `Date <= as_of` and call the existing
  `evaluate_trend_template(window, benchmark_window)` — production-fidelity by
  construction, since the production tool passes cutoff-loaded frames the same way.
- Forward return: close-to-close from the walk date's bar to `holding_days` bars later on
  the stock frame; walk dates without a full forward window produce no record.
- `hit = forward_return > 0` (the template is a bullish stage-2 filter).

## Benchmark is required

Without a benchmark, `evaluate_trend_template` drops the RS criterion and
`passed_count`'s denominator silently changes from 8 to 7, corrupting the pass-band
semantics. The CLI therefore **skips a symbol with a printed message** when the benchmark
frame cannot be loaded or aligned, instead of degrading — a deliberate difference from the
production tool's lenient behavior, correct for a calibration instrument.
`collect_readings` itself asserts nothing about this; the CLI owns the guard (it simply
does not call collect without a benchmark frame).

## Report

Section 1 — baseline by pass band:

```
pass_band      n   hit_rate   avg_fwd_ret
0-4          312      48.7%         0.31%
5-6          140      55.0%         1.12%
7             66      59.1%         1.75%
8             98      63.3%         2.40%
```

Section 2 — rs_score lift within each pass band (one row per `(pass_band, rs_band)`,
bands in fixed order, `n/a` rows included):

```
pass_band  rs_band          n   hit_rate   avg_fwd_ret
8          rs<0            12      50.0%         0.80%
8          0<=rs<=0.10     51      62.7%         2.21%
8          rs>0.10         30      70.0%         3.44%
8          n/a              5      60.0%         1.90%
...
```

Rows with `n = 0` are printed anyway (fixed known band set; an empty cell is itself
information). Formatting matches the sibling scripts (`{:.1%}` / `{:.2%}`, aligned
columns).

## Error handling

- Symbol with insufficient trimmed history (< ~280 bars, warm-up + a forward window):
  print `"{symbol}: not enough history in range, skipping"` and continue.
- Benchmark load failure: print a message naming the benchmark and skip the affected
  symbol(s) as above.
- Nothing else is swallowed — offline research script, loud failures are correct.
  (`evaluate_trend_template` raises nothing on short frames; it returns falsy criteria,
  which the warm-up makes irrelevant.)

## Testing (`tests/test_trend_template_backtest.py`, `@pytest.mark.unit`, synthetic frames, no network)

- **Band edges:** `pass_band` at 4/5/6/7/8; `rs_band` at exactly 0 (middle), exactly 0.10
  (middle), just below 0, just above 0.10, and None (`n/a`).
- **Collection:** a synthetic strong-uptrend stock against a flat benchmark yields records
  whose `passed_count`/`stage_2_uptrend` match values prototyped against the live
  `evaluate_trend_template` before the plan locks them (per standing fixture practice);
  forward return anchored at the walk date; no records once the forward window runs out;
  warm-up respected (first record's date is at/after bar `WARMUP_BARS`).
- **Aggregation:** hand-built records land in the right `(pass_band, rs_band)` buckets;
  None rs_score lands in `n/a` and never in a numeric band.
- **End-to-end:** collect → aggregate → format on the synthetic pair; assert section
  headers and a known bucket row appear.
- No integration test; the CLI on real tickers is the manual path, run by the reviewer
  outside the Codex sandbox.

## Non-goals

- No change to `trend_template.py` or any existing file; no RS-proxy redesign (that is
  the potential follow-up this report informs).
- No auto-tuning, persistence, P&L, or multi-holding-period sweep (rerun with a different
  `--holding-days`).

## Codex model tier per plan task

Task 1 (logic module + tests): **terra**. Task 2 (CLI): **luna**. Always pass
`-m gpt-5.6-<tier>` explicitly. Codex prompts open with the "YOU are the implementer"
paragraph per feedback_codex_nested_delegation.

## Acceptance criteria

- `pytest -q tests/test_trend_template_backtest.py` passes; `ruff check` clean on the
  three new files; every new file ≤150 lines (tests included — pre-split in the plan if
  projected over).
- Manual reviewer smoke: `python scripts/backtest_trend_template.py AAPL NVDA --start
  2024-01-01 --step 5` prints both sections with plausible numbers.
- No modification to any existing file.

> Research/analysis support only; not investment advice; no trade execution.
