# Pocket Pivot Walk-Forward Hit-Rate Report Design

**Goal:** Give the Pocket Pivot module the same read-only calibration instrument its
siblings already have (`scripts/backtest_chart_patterns.py`, `scripts/backtest_wyckoff.py`):
a walk-forward hit-rate report a human reads to hand-tune the constants in
`pocket_pivot_signals.py` and `pocket_pivot_context.py`. It is **not** a trading backtest —
no position sizing, execution, or P&L — and it tunes nothing itself. This is item (3) of
the TA-module deferred-work sequencing; Wyckoff and O'Neil are complete.

**The question it answers:** when `analyze_pocket_pivots_from_data` reports a pocket pivot
event as of some historical date, how often does price rise over the next N trading days —
and how does each context flag (v-shape risk, extension, downtrend, MA position, gap-up)
shift that hit rate? Pocket pivots are always bullish point-events, so "hit" is simply
forward return > 0.

**Decision locked during brainstorming — report shape:** per-flag lift table (chosen over a
Wyckoff-style single cross-bucket, which examines only one flag, and over a full flag
cross-product, which yields ~100 sparse unreadable buckets).

## Files

New (each ≤150 lines):

- `tradingagents/dataflows/pocket_pivot_backtest.py` — the testable logic:
  - `collect_events(df, step, holding_days) -> list[dict]` — walk-forward event collection
    over one symbol's already-trimmed OHLCV frame (the CLI trims to `--start` before
    calling; see Collection below). Each returned
    record carries: `date`, `ma_period`, `context` (the event's flag dict), `gap_up`,
    `forward_return: float`, `hit: bool`.
  - `aggregate(records, stats) -> None` — folds records into two accumulator structures:
    baseline buckets keyed by `ma_period`, and per-flag lift buckets keyed by
    `(flag_name, flag_value)` where `flag_value` is `True`/`False`/`None`.
  - `format_report(stats) -> str` — renders the two report sections as aligned text.
  Splitting logic out of the script (which `backtest_wyckoff.py` did not do) is a
  deliberate small improvement: it is what lets collection/aggregation get real unit tests
  with synthetic frames. Not a rewrite of the Wyckoff script's pattern — that script stays
  as-is.
- `scripts/backtest_pocket_pivot.py` — thin argparse CLI mirroring `backtest_wyckoff.py`:
  positional `symbols` (one or more), `--start` (default `2022-01-01`), `--end` (default
  today), `--step` (default 5, business days between walk-forward checks),
  `--holding-days` (default 20). Per symbol: `load_ohlcv(symbol, end)`, trim to
  `--start`, delegate to `collect_events`/`aggregate`, then print via `format_report`.
  Module docstring carries the same framing as Wyckoff's: not a trading backtest; a human
  reads the report against `CROSS_BUFFER_ATR`/`DOWN_VOLUME_LOOKBACK` in
  `pocket_pivot_signals.py` and `V_SHAPE_*`/`EXTENSION_ATR_THRESHOLD`/
  `DOWNTREND_LOOKBACK_BARS` in `pocket_pivot_context.py`; the script tunes nothing.
- `tests/test_pocket_pivot_backtest.py` — unit tests (see Testing).

No existing file is modified.

## Collection — production-fidelity walk

`find_pocket_pivots` evaluates events using the ATR **as of the analysis date** (the end of
the frame passed in), not the event date. Since the goal is calibrating production
constants, the backtest must reproduce production behavior rather than scanning full
history once with a single final ATR:

- Walk analysis dates every `step` bars, skipping an initial warm-up of 60 bars (Wyckoff
  precedent; also covers `MIN_ROWS = 51`).
- At each walk date, call `analyze_pocket_pivots_from_data(window, as_of_str)` on the
  truncated frame (`Date <= as_of`). Catch `ValueError` (short window) and skip that date.
- Events repeat across walk dates while inside `EVENT_SCAN_WINDOW = 60`: dedupe by
  `(date, ma_period)`, keeping the **first** sighting — the walk date closest to the event
  date, whose as-of ATR best matches what production would have used live.
- Forward return is measured from the **event date's** bar (not the walk date):
  close-to-close from the event bar to `holding_days` bars later. Events whose forward
  window extends past the end of data are dropped (Wyckoff precedent).
- `hit = forward_return > 0`.

## Report — per-flag lift table

Section 1, baseline by MA period:

```
ma_period      n   hit_rate   avg_fwd_ret
10           124      58.9%         1.84%
50            41      63.4%         2.31%
```

Section 2, one row per context flag — `v_shape_risk`, `extended_from_ma`,
`multi_month_downtrend`, `above_sma200`, `gap_up` (the first four read from the event's
`context` dict; `gap_up` from the event itself):

```
flag                    n_true  hit_true  ret_true   n_false  hit_false  ret_false   n_na
v_shape_risk                18     44.4%    -0.52%       147      61.2%      2.10%      0
extended_from_ma            22     50.0%     0.31%        98      60.2%      2.05%     45
...
```

`None` flag values (insufficient history, or `extended_from_ma` on 50dma events) are
excluded from both the True and False sides and counted in `n_na`, so insufficient-history
cases can never masquerade as `False`. Buckets with `n = 0` on both sides are still
printed (flags are a fixed known set; an all-zero row is itself information). Percentages
formatted as in the Wyckoff report (`{:.1%}` / `{:.2%}`).

## Error handling

- A symbol whose trimmed history is shorter than ~80 bars prints
  `"{symbol}: not enough history in range, skipping"` and continues (Wyckoff precedent).
- Per-walk-date `ValueError` from `prepare_ohlcv` is caught and that date skipped.
- No other exception handling: a broken vendor or malformed frame should fail loudly —
  this is an offline research script, not a pipeline component.

## Testing (`tests/test_pocket_pivot_backtest.py`, `@pytest.mark.unit`, synthetic OHLCV, no network)

- **Dedupe:** a synthetic frame whose single pocket pivot is visible from multiple walk
  dates yields exactly one record, carrying the first sighting's values.
- **Forward-return anchor:** the return is computed from the event date's close, not the
  walk date's close (frame constructed so the two differ measurably).
- **Flag-lift aggregation:** hand-built records with known flag values land True/False/None
  in the right columns; `None` never counts as `False`.
- **End-to-end:** a fabricated frame with one known qualifying pocket pivot (rising close
  through the 10dma on volume exceeding the prior down-volume max) flows through
  `collect_events` → `aggregate` → `format_report` and appears in the correct baseline and
  flag buckets.
- **Edge:** an event too close to the end of data (no full forward window) produces no
  record.
- No integration test: running the CLI on real tickers is itself the manual integration
  path, exactly as with the two sibling scripts.

## Non-goals

- No auto-tuning, no persistence of results, no changes to any `pocket_pivot_*` module.
- No P&L, position sizing, slippage, or benchmark comparison.
- No multi-holding-period sweep in one run — rerun with a different `--holding-days`.
- No changes to `backtest_wyckoff.py`/`backtest_chart_patterns.py` (their inline style
  stays; only this new script gets the extracted-logic treatment).

## Codex model tier per plan task

Single feature, small: logic module + tests **terra**; CLI script + smoke wiring **luna**
(or fold into one terra task if the plan ends up with a single task). Always pass
`-m gpt-5.6-<tier>` explicitly.

## Acceptance criteria

- `pytest -q tests/test_pocket_pivot_backtest.py` passes; `ruff check` clean on the three
  new files; every new file ≤150 lines (tests included — split the test file if projected
  over).
- `python scripts/backtest_pocket_pivot.py AAPL --start 2024-01-01 --step 5` runs end to
  end against the cache/vendor and prints both report sections (manual check, real data).
- No modification to any existing file.

> Research/analysis support only; not investment advice; no trade execution.
