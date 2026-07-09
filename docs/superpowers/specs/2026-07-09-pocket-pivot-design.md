# Pocket Pivot Detection — Design Spec

**Goal:** Add a standalone, deterministic Pocket Pivot detector per Kacher &
Morales's *Trade Like an O'Neil Disciple* / *Trading in the Cockpit*
definition, exposed as an independent LangChain tool the Market Analyst may
call. This is intentionally decoupled from the existing Wyckoff → O'Neil
precedence chain: a pocket pivot can fire outside a cup-with-handle base and
should not be forced into that ranking, nor should it complicate
`oneil_bias.py`'s CANSLIM confidence math.

**Non-goals:** No changes to the Wyckoff/O'Neil precedence prose, no changes
to `wyckoff_bias.py` or `oneil_bias.py`, no prefetch wiring for this signal.
No fundamentals check (belongs to the Fundamentals Analyst). No wedge-pattern
detector (none exists in this codebase; out of scope here).

**`market_analyst.py` scope (user-approved):** unlike Wyckoff/O'Neil (which
are prefetch-only and never appear in the callable `tools=[...]` list), the
only way the Market Analyst LLM can invoke any tool is via that list, and
each tool there gets a short prompt paragraph telling the LLM to call it
(see `get_chart_patterns`/`get_trend_template`'s treatment). So making
`get_pocket_pivot` reachable requires: (1) importing it and adding it to
`tools = [...]`, and (2) one new prompt paragraph introducing it — explicitly
*not* part of the Wyckoff/O'Neil precedence chain, no prefetch, no directive
about overriding other evidence. This is the only edit this feature makes to
`market_analyst.py`.

## Core definition (the two hard rules)

A pocket pivot fires on day `i` for a given MA period (10 or 50) when **all**
of the following hold:

1. **Cross-up, ATR-adaptive:** yesterday's close was at/below its same-period
   MA (`prior_close <= prior_ma + CROSS_BUFFER_ATR * atr_value`), and today's
   close is decisively above its MA
   (`close > ma_value + CROSS_BUFFER_ATR * atr_value`). `CROSS_BUFFER_ATR =
   0.1`, matching `oneil_breakout.py`'s `BREAKOUT_BUFFER_ATR` convention.
2. **Up day:** `close > prior_close` (the "coming up" requirement — excludes
   the rare case where the MA itself falls faster than price).
3. **Volume signature:** `volume > highest_down_volume_10d`, where
   `highest_down_volume_10d` is the max volume among the `DOWN_VOLUME_LOOKBACK
   = 10` trading days immediately preceding `i` on which `close < prior_close`.
   If no down day exists in that window, this rule auto-passes (nothing to
   exceed) — recorded in evidence.

A single day can independently qualify against the 10dma, the 50dma, or
both — each qualifying `(day, ma_period)` pair emits its own event.

Only days within the most recent `EVENT_SCAN_WINDOW = 60` trading days
(relative to `curr_date`) are scanned; older pivots aren't actionable trade
signals.

## Context flags (informational only — never suppress a detected event)

Attached to every event. Code reports structure; the LLM/user judges
buyability, consistent with this project's core principle (see
`WYCKOFF_ANALYSIS_PLAN.md` principle 1).

- **`multi_month_downtrend`** (bool | null): `close[i] < close[i - 105]`
  (~5 months of trading days). `null` if fewer than 105 prior bars exist.
- **`above_sma50`, `above_sma200`** (bool | null) + **`sma50`, `sma200`**
  (float | null): price vs. each SMA, reusing the SMA-relationship pattern
  from `trend_template.py`. `null`/`None` when insufficient history (<50 or
  <200 bars respectively) rather than a false negative.
- **`v_shape_risk`** (bool): within the `V_SHAPE_LOOKBACK = 10` bars before
  `i` (excluding `i`), find the lowest close and its own MA at that index. If
  that trough closed more than `V_SHAPE_UNDERCUT_ATR = 1.0` ATR below its
  MA, **and** the bars from that trough to `i` number
  `<= V_SHAPE_REVERSAL_BARS = 3`, flag `true` (deep undercut + fast snapback
  — failure-prone per the guidelines). Otherwise `false`. Only evaluated
  against the same `ma_period` as the event.
- **`extended_from_ma`** (bool | null, 10dma events only): `(close - sma10) /
  atr_value > EXTENSION_ATR_THRESHOLD (1.5)`. `null` for 50dma events (the
  guideline specifically concerns the 10dma).

Plus, on every event regardless of context checks selected:
- **`gap_up`** (bool): `open[i] > prior_close` — self-contained, no
  cross-module coupling to O'Neil's breakout detector.

## Files

```
tradingagents/dataflows/pocket_pivot_signals.py   (~140 lines)
tradingagents/dataflows/pocket_pivot_context.py   (~140 lines)
tradingagents/dataflows/pocket_pivot_bias.py       (~110 lines)
tradingagents/agents/utils/pocket_pivot_tools.py  (~30 lines)
tests/test_pocket_pivot_signals.py
tests/test_pocket_pivot_context.py
tests/test_pocket_pivot_bias.py
```

Every file must stay ≤150 lines (CLAUDE.md); if a test file would exceed
this, split by responsibility (mirrors the `wyckoff_vsa_signals.py` /
`wyckoff_vsa_range_signals.py` split).

### `pocket_pivot_signals.py`

- `prepare_ohlcv`, `atr()` — small local copies of the existing
  clip-to-curr_date / ATR(14) helpers, following the same
  self-contained-per-module convention as `wyckoff_range.py` and
  `oneil_cup.py` (each duplicates rather than sharing, so this module has no
  cross-feature dependency).
- `_sma(series, period)` — rolling mean, `min_periods=period` (matches
  `trend_template.py`'s `_sma`).
- `_highest_down_volume(df, i, window=10) -> float` — as defined above.
- `@dataclass PocketPivotEvent`: `index: int`, `date: str`, `ma_period:
  Literal[10, 50]`, `close: float`, `ma_value: float`, `volume: float`,
  `highest_down_volume_10d: float`, `gap_up: bool`, `evidence: list[str]`.
- `find_pocket_pivots(df: pd.DataFrame, atr_value: float, ma_periods:
  tuple[int, ...] = (10, 50)) -> list[PocketPivotEvent]` — scans the last
  `EVENT_SCAN_WINDOW` bars, returns qualifying events sorted by `(index,
  ma_period)`.
- Constants: `CROSS_BUFFER_ATR = 0.1`, `DOWN_VOLUME_LOOKBACK = 10`,
  `EVENT_SCAN_WINDOW = 60`.

### `pocket_pivot_context.py`

- `multi_month_downtrend(df, i, months_bars=105) -> bool | None`
- `ma_position(df, i) -> dict` → `{"above_sma50": ..., "above_sma200": ...,
  "sma50": ..., "sma200": ...}`
- `v_shape_risk(df, i, ma_period, atr_value) -> bool`
- `extended_from_ma(df, i, ma_period, atr_value) -> bool | None`
- `build_context(df, i, ma_period, atr_value) -> dict` — calls the four above
  and assembles the `context` dict used in the output schema.
- Constants: `DOWNTREND_LOOKBACK_BARS = 105`, `V_SHAPE_LOOKBACK = 10`,
  `V_SHAPE_UNDERCUT_ATR = 1.0`, `V_SHAPE_REVERSAL_BARS = 3`,
  `EXTENSION_ATR_THRESHOLD = 1.5`.

### `pocket_pivot_bias.py`

- `analyze_pocket_pivots_from_data(data: pd.DataFrame, curr_date: str,
  look_back_days: int = 320) -> dict[str, Any]` — `prepare_ohlcv`, `atr()`,
  `find_pocket_pivots`, attach `build_context` per event, determine
  `active` (`True` if the most recent event's date is within
  `ACTIVE_WINDOW_DAYS = 10` trading days of `curr_date`), assemble the JSON
  payload below.
- `analyze_pocket_pivots(symbol: str, curr_date: str, look_back_days: int =
  320) -> str` — tool-facing entry point: `load_ohlcv` + JSON-dump the above.
  `look_back_days=320` covers, for an event at the *start* of the 60-bar scan
  window, the 200-bar SMA200 warmup needed as of that event's own date, plus
  the 60-bar scan window itself (`200 + 60 = 260`) with a margin. Events
  closer to `curr_date` get progressively more warmup; only the oldest
  events in the scan window are near this floor, and insufficient history
  still degrades to `None` rather than an error (see Error handling).

**Output schema:**

```json
{
  "symbol": "AAPL",
  "analysis_date": "2026-07-09",
  "events": [
    {
      "date": "2026-06-20",
      "ma_period": 10,
      "close": 195.32,
      "ma_value": 193.10,
      "volume": 62000000,
      "highest_down_volume_10d": 48000000,
      "gap_up": false,
      "context": {
        "multi_month_downtrend": false,
        "above_sma50": true,
        "above_sma200": true,
        "sma50": 188.4,
        "sma200": 175.2,
        "v_shape_risk": false,
        "extended_from_ma": false
      },
      "evidence": [
        "Closed above the 10dma (193.10) after being at/below it the prior day, on 62.0M volume vs. 48.0M highest down-volume day in the prior 10 sessions."
      ]
    }
  ],
  "active": true,
  "most_recent_event_date": "2026-06-20",
  "limitations": "Fundamentals strength and wedge-pattern geometry are not evaluated by this tool; combine with the Fundamentals Analyst's read and visual chart review."
}
```

### `pocket_pivot_tools.py`

- `get_pocket_pivot(symbol, curr_date, look_back_days=320) -> str` —
  `@tool`-decorated, calls `analyze_pocket_pivots`. Docstring states this is
  an independent volume/accumulation signal, not part of the Wyckoff/O'Neil
  precedence chain, and that fundamentals + wedge geometry are unevaluated
  (mirrors the `limitations` field). **Not wired into
  `market_analyst.py`** — the Market Analyst may call it like any other
  technical tool, but it is not prefetched or given precedence text.

## Error handling

- Empty/malformed OHLCV: `prepare_ohlcv` raises `ValueError` for missing
  required columns, same as `wyckoff_range.py`/`oneil_cup.py` — propagates to
  the tool caller (no silent fallback; matches existing convention where
  `market_analyst.py`'s `_fetch_*_block` wrappers are the only place errors
  are caught, and this tool isn't wired there).
- Too-short cutoff-safe OHLCV: after applying `curr_date` truncation,
  `prepare_ohlcv` also raises `ValueError` when fewer than `MIN_ROWS = 51`
  rows remain. This is a separate hard data-shape guard from missing columns;
  it does not change per-flag insufficient-history behavior below.
- Insufficient history for a given check (e.g. <200 bars for SMA200, <105
  bars for downtrend): that specific field is `None`/`null`, not an error —
  the rest of the analysis proceeds.
- No qualifying events in the scan window: `events: []`, `active: false`,
  `most_recent_event_date: null`.

## Testing

Synthetic OHLCV fixtures per file, mirroring the Wyckoff VSA test pattern
(`tests/test_wyckoff_vsa_bar_signals.py` style):

- `test_pocket_pivot_signals.py`: cross-up + volume-signature true/false
  cases for both MA periods, up-day requirement, gap-up flag, "no down day
  in window" edge case, `EVENT_SCAN_WINDOW` boundary.
- `test_pocket_pivot_context.py`: one true/false case per flag
  (`multi_month_downtrend`, `above_sma50`/`above_sma200`, `v_shape_risk`,
  `extended_from_ma`), plus the `None`-for-insufficient-history cases.
- `test_pocket_pivot_bias.py`: JSON shape, `active`/`most_recent_event_date`
  computation, empty-events case, `look_back_days` sizing.

Per CLAUDE.md's default verification policy: isolated additive change, so run
only `pytest -q tests/test_pocket_pivot_signals.py
tests/test_pocket_pivot_context.py tests/test_pocket_pivot_bias.py` and
`ruff check` on the touched/created files — not the full suite.

> This feature is for research and analysis assistance only; it does not
> constitute investment advice and does not execute trades.
