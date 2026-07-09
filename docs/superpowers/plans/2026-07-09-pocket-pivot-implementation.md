# Pocket Pivot Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standalone, deterministic Pocket Pivot detector (Kacher & Morales) as an independent LangChain tool the Market Analyst can call, per `docs/superpowers/specs/2026-07-09-pocket-pivot-design.md`.

**Architecture:** Three new dataflow modules — `pocket_pivot_signals.py` (the two hard rules: ATR-adaptive MA cross-up + volume signature), `pocket_pivot_context.py` (four qualitative buyability flags), `pocket_pivot_bias.py` (thin orchestrator, tool-facing JSON) — plus a new tool file `pocket_pivot_tools.py`, and mechanical registration edits to three existing files so the tool is reachable.

**Tech Stack:** Python, pandas (existing project stack — no new dependencies).

## Global Constraints

- Every newly created file is at most 150 lines (CLAUDE.md). If a test file would exceed this, split it by responsibility rather than growing past the cap.
- This feature is fully decoupled from the Wyckoff → O'Neil precedence chain: no changes to `wyckoff_bias.py` or `oneil_bias.py`, no prefetch wiring, no precedence prose. A pocket pivot event must never be suppressed by its context flags — code reports structure, the LLM/user judges buyability.
- No signal may be computed from data after `curr_date` (existing project principle, matches Wyckoff/O'Neil).
- Every emitted pocket pivot event must carry an auditable date, volume figures, and an evidence string.
- Per CLAUDE.md's "put customization in newly added files" rule, and the user's explicit approval for this exact scope (see spec's "`market_analyst.py` scope" section): Task 5 makes minimal, mechanical registration edits to `tradingagents/agents/utils/agent_utils.py`, `tradingagents/agents/analysts/market_analyst.py`, and `tradingagents/graph/trading_graph.py` — import + list registration + one prompt paragraph, matching the exact pattern already used for `get_chart_patterns`/`get_trend_template`/`get_wyckoff_structure`/`get_oneil_setup`. No other prose in those files is touched.
- Per CLAUDE.md's default verification policy: this is an isolated additive change, so run `pytest -q tests/test_pocket_pivot_signals.py tests/test_pocket_pivot_context.py tests/test_pocket_pivot_bias.py tests/test_market_toolnode.py` and `ruff check` on the touched/created files — not the full suite (Task 5 touches shared registration files, so also run `ruff check` on those three).

---

### Task 1: Core detector — `pocket_pivot_signals.py`

**Files:**
- Create: `tradingagents/dataflows/pocket_pivot_signals.py`
- Test: `tests/test_pocket_pivot_signals.py`

**Interfaces:**
- Produces: `PocketPivotEvent` dataclass (`index: int`, `date: str`, `ma_period: Literal[10, 50]`, `close: float`, `ma_value: float`, `volume: float`, `highest_down_volume_10d: float`, `gap_up: bool`, `evidence: list[str]`); `prepare_ohlcv(data, curr_date, look_back_days) -> pd.DataFrame`; `atr(df, period=14) -> pd.Series`; `sma(series, period) -> pd.Series`; `find_pocket_pivots(df, atr_value, ma_periods=(10, 50)) -> list[PocketPivotEvent]`; module constants `CROSS_BUFFER_ATR = 0.1`, `DOWN_VOLUME_LOOKBACK = 10`, `EVENT_SCAN_WINDOW = 60`, `MA_PERIODS = (10, 50)`.
- Consumes: nothing project-specific (self-contained, following the same per-module `prepare_ohlcv`/`atr` duplication convention as `wyckoff_range.py` and `oneil_cup.py`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pocket_pivot_signals.py`:

```python
"""Unit tests for the core Pocket Pivot detector: ATR-adaptive MA cross-up
plus the volume-signature rule."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.pocket_pivot_signals import find_pocket_pivots

ATR = 2.0


def _decline_then_bounce(
    decline_days: int,
    start_price: float,
    end_price: float,
    bounce_close: float,
    bounce_volume: float,
    down_volume: float = 1_000_000.0,
) -> pd.DataFrame:
    """`decline_days` bars linearly declining from start_price to end_price
    (each a down day on `down_volume`), followed by one bounce bar closing
    at `bounce_close` on `bounce_volume`."""
    dates = pd.date_range("2020-01-01", periods=decline_days + 1, freq="D")
    step = (start_price - end_price) / (decline_days - 1)
    closes = [start_price - step * k for k in range(decline_days)]
    closes.append(bounce_close)
    volumes = [down_volume] * decline_days + [bounce_volume]
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": closes,
            "High": [c + 0.5 for c in closes],
            "Low": [c - 0.5 for c in closes],
            "Close": closes,
            "Volume": volumes,
        }
    )


@pytest.mark.unit
def test_10dma_pocket_pivot_fires_on_bounce_with_strong_volume():
    df = _decline_then_bounce(
        decline_days=15, start_price=110.0, end_price=90.0,
        bounce_close=101.0, bounce_volume=5_000_000.0,
    )
    events = find_pocket_pivots(df, ATR, ma_periods=(10,))
    assert len(events) == 1
    assert events[0].ma_period == 10
    assert events[0].volume == 5_000_000.0
    assert events[0].highest_down_volume_10d == 1_000_000.0


@pytest.mark.unit
def test_50dma_pocket_pivot_fires_on_deep_bounce_with_strong_volume():
    df = _decline_then_bounce(
        decline_days=70, start_price=150.0, end_price=50.0,
        bounce_close=90.0, bounce_volume=8_000_000.0,
    )
    events = find_pocket_pivots(df, ATR, ma_periods=(50,))
    assert len(events) == 1
    assert events[0].ma_period == 50


@pytest.mark.unit
def test_silent_when_volume_does_not_exceed_highest_down_volume():
    df = _decline_then_bounce(
        decline_days=15, start_price=110.0, end_price=90.0,
        bounce_close=101.0, bounce_volume=500_000.0, down_volume=1_000_000.0,
    )
    assert find_pocket_pivots(df, ATR, ma_periods=(10,)) == []


@pytest.mark.unit
def test_silent_when_bounce_does_not_clear_the_ma():
    df = _decline_then_bounce(
        decline_days=15, start_price=110.0, end_price=90.0,
        bounce_close=90.5, bounce_volume=5_000_000.0,
    )
    assert find_pocket_pivots(df, ATR, ma_periods=(10,)) == []


@pytest.mark.unit
def test_gap_up_flag_reflects_open_vs_prior_close():
    df = _decline_then_bounce(
        decline_days=15, start_price=110.0, end_price=90.0,
        bounce_close=101.0, bounce_volume=5_000_000.0,
    )
    df.loc[df.index[-1], "Open"] = 100.5
    events = find_pocket_pivots(df, ATR, ma_periods=(10,))
    assert len(events) == 1
    assert events[0].gap_up is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pocket_pivot_signals.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'tradingagents.dataflows.pocket_pivot_signals'`

- [ ] **Step 3: Implement the module**

Create `tradingagents/dataflows/pocket_pivot_signals.py`:

```python
"""Pocket Pivot core detection: Kacher & Morales's two-rule definition -- an
ATR-adaptive cross back above the 10-day or 50-day moving average on an up
day, confirmed by volume exceeding the highest down-volume day of the prior
10 sessions. See docs/superpowers/specs/2026-07-09-pocket-pivot-design.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

CROSS_BUFFER_ATR = 0.1
DOWN_VOLUME_LOOKBACK = 10
EVENT_SCAN_WINDOW = 60
MA_PERIODS: tuple[int, ...] = (10, 50)


def prepare_ohlcv(data: pd.DataFrame, curr_date: str, look_back_days: int) -> pd.DataFrame:
    required = {"Date", "Open", "High", "Low", "Close", "Volume"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"OHLCV data is missing required columns: {sorted(missing)}")
    df = data.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    for column in required - {"Date"}:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = (
        df.dropna(subset=["Date"])
        .sort_values("Date")
        .drop_duplicates(subset="Date", keep="last")
    )
    cutoff = pd.to_datetime(curr_date)
    df = df[df["Date"] <= cutoff]
    if look_back_days:
        df = df.tail(look_back_days)
    return df.reset_index(drop=True)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()


def _highest_down_volume(df: pd.DataFrame, i: int, window: int = DOWN_VOLUME_LOOKBACK) -> float:
    lo = max(1, i - window)
    down_volumes = [
        float(df.at[j, "Volume"])
        for j in range(lo, i)
        if float(df.at[j, "Close"]) < float(df.at[j - 1, "Close"])
    ]
    return max(down_volumes) if down_volumes else 0.0


@dataclass
class PocketPivotEvent:
    index: int
    date: str
    ma_period: Literal[10, 50]
    close: float
    ma_value: float
    volume: float
    highest_down_volume_10d: float
    gap_up: bool
    evidence: list[str] = field(default_factory=list)


def _qualifies(
    df: pd.DataFrame, i: int, period: int, ma_series: pd.Series, atr_value: float
) -> PocketPivotEvent | None:
    if i < 1 or pd.isna(ma_series.iloc[i]) or pd.isna(ma_series.iloc[i - 1]):
        return None
    close, prior_close = float(df.at[i, "Close"]), float(df.at[i - 1, "Close"])
    if close <= prior_close:
        return None
    buffer = CROSS_BUFFER_ATR * atr_value
    ma_value, prior_ma = float(ma_series.iloc[i]), float(ma_series.iloc[i - 1])
    if not (prior_close <= prior_ma + buffer and close > ma_value + buffer):
        return None
    volume = float(df.at[i, "Volume"])
    highest_down = _highest_down_volume(df, i)
    if volume <= highest_down:
        return None
    gap_up = float(df.at[i, "Open"]) > prior_close
    evidence = [
        f"Closed at {close:.2f}, above the {period}dma ({ma_value:.2f}) after being at/below "
        f"it the prior day, on {volume:,.0f} volume vs. {highest_down:,.0f} highest down-volume "
        f"day in the prior {DOWN_VOLUME_LOOKBACK} sessions."
    ]
    return PocketPivotEvent(
        i, df.at[i, "Date"].strftime("%Y-%m-%d"), period, close, ma_value,
        volume, highest_down, gap_up, evidence,
    )


def find_pocket_pivots(
    df: pd.DataFrame, atr_value: float, ma_periods: tuple[int, ...] = MA_PERIODS
) -> list[PocketPivotEvent]:
    """Scan the last EVENT_SCAN_WINDOW bars for qualifying pocket pivots."""
    start = max(0, len(df) - EVENT_SCAN_WINDOW)
    ma_series_by_period = {period: sma(df["Close"], period) for period in ma_periods}
    events: list[PocketPivotEvent] = []
    for i in range(start, len(df)):
        for period in ma_periods:
            hit = _qualifies(df, i, period, ma_series_by_period[period], atr_value)
            if hit is not None:
                events.append(hit)
    return sorted(events, key=lambda e: (e.index, e.ma_period))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pocket_pivot_signals.py -v`
Expected: PASS (5 passed). If a fixture's margin turns out too tight (e.g. a boundary condition doesn't land as expected), adjust that test's numeric constants — not the detector logic — and re-run.

- [ ] **Step 5: Run ruff and commit**

```bash
ruff check tradingagents/dataflows/pocket_pivot_signals.py tests/test_pocket_pivot_signals.py
wc -l tradingagents/dataflows/pocket_pivot_signals.py tests/test_pocket_pivot_signals.py
git add tradingagents/dataflows/pocket_pivot_signals.py tests/test_pocket_pivot_signals.py
git commit -m "feat(pocket-pivot): add core MA cross-up + volume signature detector"
```

---

### Task 2: Context flags — `pocket_pivot_context.py`

**Files:**
- Create: `tradingagents/dataflows/pocket_pivot_context.py`
- Test: `tests/test_pocket_pivot_context.py`

**Interfaces:**
- Consumes: `sma` from `tradingagents.dataflows.pocket_pivot_signals` (Task 1).
- Produces: `multi_month_downtrend(df, i) -> bool | None`; `ma_position(df, i) -> dict[str, Any]` (`above_sma50`, `above_sma200`, `sma50`, `sma200`); `v_shape_risk(df, i, ma_period, atr_value) -> bool`; `extended_from_ma(df, i, ma_period, atr_value) -> bool | None`; `build_context(df, i, ma_period, atr_value) -> dict[str, Any]` (assembles all four); module constants `DOWNTREND_LOOKBACK_BARS = 105`, `V_SHAPE_LOOKBACK = 10`, `V_SHAPE_UNDERCUT_ATR = 1.0`, `V_SHAPE_REVERSAL_BARS = 3`, `EXTENSION_ATR_THRESHOLD = 1.5`. This is what Task 3 (`pocket_pivot_bias.py`) calls.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pocket_pivot_context.py`:

```python
"""Unit tests for Pocket Pivot context flags: downtrend, MA position,
V-shape risk, and extension from the 10dma."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.pocket_pivot_context import (
    extended_from_ma,
    ma_position,
    multi_month_downtrend,
    v_shape_risk,
)

ATR = 2.0


def _flat(n: int, price: float = 100.0, volume: float = 1_000_000.0) -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    closes = [price] * n
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": closes,
            "High": [c + 0.5 for c in closes],
            "Low": [c - 0.5 for c in closes],
            "Close": closes,
            "Volume": [volume] * n,
        }
    )


@pytest.mark.unit
def test_multi_month_downtrend_true_when_price_fell_over_105_bars():
    df = _flat(200)
    df.loc[df.index[-1], "Close"] = 80.0
    assert multi_month_downtrend(df, len(df) - 1) is True


@pytest.mark.unit
def test_multi_month_downtrend_false_when_price_rose_over_105_bars():
    df = _flat(200)
    df.loc[df.index[-1], "Close"] = 120.0
    assert multi_month_downtrend(df, len(df) - 1) is False


@pytest.mark.unit
def test_multi_month_downtrend_none_with_insufficient_history():
    df = _flat(50)
    assert multi_month_downtrend(df, len(df) - 1) is None


@pytest.mark.unit
def test_ma_position_flags_above_both_smas():
    df = _flat(250)
    df.loc[df.index[-1], "Close"] = 150.0
    ctx = ma_position(df, len(df) - 1)
    assert ctx["above_sma50"] is True
    assert ctx["above_sma200"] is True


@pytest.mark.unit
def test_ma_position_sma200_none_with_insufficient_history():
    df = _flat(100)
    ctx = ma_position(df, len(df) - 1)
    assert ctx["sma200"] is None
    assert ctx["above_sma200"] is None


@pytest.mark.unit
def test_v_shape_risk_true_on_deep_undercut_and_fast_reversal():
    df = _flat(60)
    i = len(df) - 1
    df.loc[df.index[i - 2], "Close"] = 80.0
    df.loc[df.index[i - 1], "Close"] = 90.0
    df.loc[df.index[i], "Close"] = 101.0
    assert v_shape_risk(df, i, 10, ATR) is True


@pytest.mark.unit
def test_v_shape_risk_false_on_shallow_undercut():
    df = _flat(60)
    i = len(df) - 1
    df.loc[df.index[i - 2], "Close"] = 99.5
    df.loc[df.index[i - 1], "Close"] = 99.8
    df.loc[df.index[i], "Close"] = 101.0
    assert v_shape_risk(df, i, 10, ATR) is False


@pytest.mark.unit
def test_extended_from_ma_true_when_far_above_10dma():
    df = _flat(60)
    i = len(df) - 1
    df.loc[df.index[i], "Close"] = 110.0
    assert extended_from_ma(df, i, 10, ATR) is True


@pytest.mark.unit
def test_extended_from_ma_none_for_50dma():
    df = _flat(60)
    i = len(df) - 1
    assert extended_from_ma(df, i, 50, ATR) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pocket_pivot_context.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tradingagents.dataflows.pocket_pivot_context'`

- [ ] **Step 3: Implement the module**

Create `tradingagents/dataflows/pocket_pivot_context.py`:

```python
"""Pocket Pivot qualitative context flags, per Kacher & Morales's buyability
guidelines. These never suppress a detected event -- code reports structure,
the LLM/user judges buyability. See
docs/superpowers/specs/2026-07-09-pocket-pivot-design.md.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from tradingagents.dataflows.pocket_pivot_signals import sma

DOWNTREND_LOOKBACK_BARS = 105
V_SHAPE_LOOKBACK = 10
V_SHAPE_UNDERCUT_ATR = 1.0
V_SHAPE_REVERSAL_BARS = 3
EXTENSION_ATR_THRESHOLD = 1.5


def multi_month_downtrend(df: pd.DataFrame, i: int) -> bool | None:
    if i < DOWNTREND_LOOKBACK_BARS:
        return None
    return float(df.at[i, "Close"]) < float(df.at[i - DOWNTREND_LOOKBACK_BARS, "Close"])


def ma_position(df: pd.DataFrame, i: int) -> dict[str, Any]:
    close = float(df.at[i, "Close"])
    sma50, sma200 = sma(df["Close"], 50), sma(df["Close"], 200)
    sma50_now = float(sma50.iloc[i]) if not pd.isna(sma50.iloc[i]) else None
    sma200_now = float(sma200.iloc[i]) if not pd.isna(sma200.iloc[i]) else None
    return {
        "above_sma50": close > sma50_now if sma50_now is not None else None,
        "above_sma200": close > sma200_now if sma200_now is not None else None,
        "sma50": sma50_now,
        "sma200": sma200_now,
    }


def v_shape_risk(df: pd.DataFrame, i: int, ma_period: int, atr_value: float) -> bool:
    ma_series = sma(df["Close"], ma_period)
    lo = max(0, i - V_SHAPE_LOOKBACK)
    trough_idx, trough_close = None, None
    for j in range(lo, i):
        if pd.isna(ma_series.iloc[j]):
            continue
        close = float(df.at[j, "Close"])
        if trough_close is None or close < trough_close:
            trough_close, trough_idx = close, j
    if trough_idx is None:
        return False
    undercut = float(ma_series.iloc[trough_idx]) - trough_close
    reversal_bars = i - trough_idx
    return undercut > V_SHAPE_UNDERCUT_ATR * atr_value and reversal_bars <= V_SHAPE_REVERSAL_BARS


def extended_from_ma(df: pd.DataFrame, i: int, ma_period: int, atr_value: float) -> bool | None:
    if ma_period != 10:
        return None
    sma10 = sma(df["Close"], 10)
    if pd.isna(sma10.iloc[i]) or atr_value == 0:
        return None
    close = float(df.at[i, "Close"])
    return (close - float(sma10.iloc[i])) / atr_value > EXTENSION_ATR_THRESHOLD


def build_context(df: pd.DataFrame, i: int, ma_period: int, atr_value: float) -> dict[str, Any]:
    context: dict[str, Any] = {"multi_month_downtrend": multi_month_downtrend(df, i)}
    context.update(ma_position(df, i))
    context["v_shape_risk"] = v_shape_risk(df, i, ma_period, atr_value)
    context["extended_from_ma"] = extended_from_ma(df, i, ma_period, atr_value)
    return context
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pocket_pivot_context.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Run ruff and commit**

```bash
ruff check tradingagents/dataflows/pocket_pivot_context.py tests/test_pocket_pivot_context.py
wc -l tradingagents/dataflows/pocket_pivot_context.py tests/test_pocket_pivot_context.py
git add tradingagents/dataflows/pocket_pivot_context.py tests/test_pocket_pivot_context.py
git commit -m "feat(pocket-pivot): add downtrend/MA-position/V-shape/extension context flags"
```

---

### Task 3: Orchestrator — `pocket_pivot_bias.py`

**Files:**
- Create: `tradingagents/dataflows/pocket_pivot_bias.py`
- Test: `tests/test_pocket_pivot_bias.py`

**Interfaces:**
- Consumes: `PocketPivotEvent`, `MA_PERIODS`, `atr`, `find_pocket_pivots`, `prepare_ohlcv` from `pocket_pivot_signals.py` (Task 1); `build_context` from `pocket_pivot_context.py` (Task 2); `load_ohlcv` from `tradingagents.dataflows.stockstats_utils`.
- Produces: `analyze_pocket_pivots_from_data(data, curr_date, look_back_days=320) -> dict[str, Any]`; `analyze_pocket_pivots(symbol, curr_date, look_back_days=320) -> str`; module constants `ACTIVE_WINDOW_DAYS = 10`, `LIMITATIONS`. This is what Task 4 (`pocket_pivot_tools.py`) calls.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pocket_pivot_bias.py`:

```python
"""Unit tests for the Pocket Pivot orchestrator: JSON shape and the
active-window computation."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.pocket_pivot_bias import analyze_pocket_pivots_from_data


def _decline_then_bounce(
    decline_days: int,
    start_price: float,
    end_price: float,
    bounce_close: float,
    bounce_volume: float,
    trailing_flat_days: int = 0,
    down_volume: float = 1_000_000.0,
) -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=decline_days + 1 + trailing_flat_days, freq="D")
    step = (start_price - end_price) / (decline_days - 1)
    closes = [start_price - step * k for k in range(decline_days)]
    closes.append(bounce_close)
    closes.extend([bounce_close] * trailing_flat_days)
    volumes = [down_volume] * decline_days + [bounce_volume] + [1_000_000.0] * trailing_flat_days
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": closes,
            "High": [c + 0.5 for c in closes],
            "Low": [c - 0.5 for c in closes],
            "Close": closes,
            "Volume": volumes,
        }
    )


@pytest.mark.unit
def test_analyze_returns_event_and_marks_it_active_near_curr_date():
    # decline_days=50 -> 51 total rows, meeting pocket_pivot_signals.py's
    # MIN_ROWS=51 floor (added during Task 1's review to guard against
    # atr()/sma() silently returning NaN on too-short data). bounce_close=95
    # is calibrated to clear only the 10dma (sma10 ~= 91.97 + ATR buffer)
    # and NOT the 50dma (sma50 ~= 99.7 + buffer), so exactly one event
    # fires -- a bounce large enough to also clear the 50dma would produce
    # two events and break the len(...) == 1 assertions below.
    df = _decline_then_bounce(
        decline_days=50, start_price=110.0, end_price=90.0,
        bounce_close=95.0, bounce_volume=5_000_000.0,
    )
    curr_date = df["Date"].iloc[-1].strftime("%Y-%m-%d")
    result = analyze_pocket_pivots_from_data(df, curr_date)
    assert len(result["events"]) == 1
    assert result["active"] is True
    assert result["most_recent_event_date"] == curr_date
    assert "limitations" in result


@pytest.mark.unit
def test_analyze_marks_event_inactive_once_curr_date_moves_past_window():
    df = _decline_then_bounce(
        decline_days=50, start_price=110.0, end_price=90.0,
        bounce_close=95.0, bounce_volume=5_000_000.0, trailing_flat_days=15,
    )
    curr_date = df["Date"].iloc[-1].strftime("%Y-%m-%d")
    result = analyze_pocket_pivots_from_data(df, curr_date)
    assert len(result["events"]) == 1
    assert result["active"] is False


@pytest.mark.unit
def test_analyze_returns_empty_events_when_no_pivot_present():
    dates = pd.date_range("2020-01-01", periods=60, freq="D")
    closes = [100.0] * 60
    df = pd.DataFrame(
        {
            "Date": dates,
            "Open": closes,
            "High": [c + 0.5 for c in closes],
            "Low": [c - 0.5 for c in closes],
            "Close": closes,
            "Volume": [1_000_000.0] * 60,
        }
    )
    curr_date = df["Date"].iloc[-1].strftime("%Y-%m-%d")
    result = analyze_pocket_pivots_from_data(df, curr_date)
    assert result["events"] == []
    assert result["active"] is False
    assert result["most_recent_event_date"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pocket_pivot_bias.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tradingagents.dataflows.pocket_pivot_bias'`

- [ ] **Step 3: Implement the orchestrator**

Create `tradingagents/dataflows/pocket_pivot_bias.py`:

```python
"""Pocket Pivot orchestrator: assembles the tool-facing JSON from the core
detector and context flags. Standalone from Wyckoff/O'Neil -- no precedence
wiring. See docs/superpowers/specs/2026-07-09-pocket-pivot-design.md.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from tradingagents.dataflows.pocket_pivot_context import build_context
from tradingagents.dataflows.pocket_pivot_signals import (
    MA_PERIODS,
    PocketPivotEvent,
    atr,
    find_pocket_pivots,
    prepare_ohlcv,
)
from tradingagents.dataflows.stockstats_utils import load_ohlcv

ACTIVE_WINDOW_DAYS = 10
LIMITATIONS = (
    "Fundamentals strength and wedge-pattern geometry are not evaluated by "
    "this tool; combine with the Fundamentals Analyst's read and visual "
    "chart review."
)


def _event_dict(df: pd.DataFrame, event: PocketPivotEvent, atr_value: float) -> dict[str, Any]:
    return {
        "date": event.date,
        "ma_period": event.ma_period,
        "close": round(event.close, 4),
        "ma_value": round(event.ma_value, 4),
        "volume": event.volume,
        "highest_down_volume_10d": event.highest_down_volume_10d,
        "gap_up": event.gap_up,
        "context": build_context(df, event.index, event.ma_period, atr_value),
        "evidence": event.evidence,
    }


def analyze_pocket_pivots_from_data(
    data: pd.DataFrame, curr_date: str, look_back_days: int = 320
) -> dict[str, Any]:
    """Analyze an OHLCV frame and return a JSON-serializable pocket pivot read."""
    df = prepare_ohlcv(data, curr_date, look_back_days)
    atr_value = float(atr(df).iloc[-1])
    events = find_pocket_pivots(df, atr_value, MA_PERIODS)
    event_dicts = [_event_dict(df, e, atr_value) for e in events]
    most_recent = event_dicts[-1]["date"] if event_dicts else None
    active = bool(events) and (len(df) - 1 - events[-1].index) <= ACTIVE_WINDOW_DAYS
    return {
        "analysis_date": curr_date,
        "events": event_dicts,
        "active": active,
        "most_recent_event_date": most_recent,
        "limitations": LIMITATIONS,
    }


def analyze_pocket_pivots(symbol: str, curr_date: str, look_back_days: int = 320) -> str:
    """Load cutoff-safe OHLCV and return a formatted JSON pocket pivot report."""
    data = load_ohlcv(symbol, curr_date)
    result = analyze_pocket_pivots_from_data(data, curr_date, look_back_days)
    result["symbol"] = symbol.upper()
    return json.dumps(result, indent=2, ensure_ascii=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pocket_pivot_bias.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run ruff and commit**

```bash
ruff check tradingagents/dataflows/pocket_pivot_bias.py tests/test_pocket_pivot_bias.py
wc -l tradingagents/dataflows/pocket_pivot_bias.py tests/test_pocket_pivot_bias.py
git add tradingagents/dataflows/pocket_pivot_bias.py tests/test_pocket_pivot_bias.py
git commit -m "feat(pocket-pivot): add orchestrator with tool-facing JSON output"
```

---

### Task 4: LangChain tool — `pocket_pivot_tools.py`

**Files:**
- Create: `tradingagents/agents/utils/pocket_pivot_tools.py`

**Interfaces:**
- Consumes: `analyze_pocket_pivots` from `pocket_pivot_bias.py` (Task 3).
- Produces: `get_pocket_pivot` (a `@tool`-decorated LangChain tool). This is what Task 5 registers into `agent_utils.py`, `market_analyst.py`, and `trading_graph.py`.

No dedicated test file for this task — `oneil_tools.py` (the closest precedent) has none either; Task 5's `test_market_toolnode.py` update is the wiring regression guard for this tool.

- [ ] **Step 1: Implement the tool**

Create `tradingagents/agents/utils/pocket_pivot_tools.py`:

```python
from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.pocket_pivot_bias import analyze_pocket_pivots


@tool
def get_pocket_pivot(
    symbol: Annotated[str, "ticker symbol of the instrument"],
    curr_date: Annotated[str, "current analysis date in YYYY-mm-dd format"],
    look_back_days: Annotated[int, "lookback window in trading days"] = 320,
) -> str:
    """Deterministically read the stock's Pocket Pivot signals (Kacher & Morales).

    A pocket pivot fires when price closes decisively back above its 10-day
    or 50-day moving average on an up day, with volume exceeding the highest
    down-volume day of the prior 10 sessions. This is an independent
    volume/accumulation signal -- it is NOT part of the Wyckoff/O'Neil
    precedence chain used elsewhere in this report, and a pocket pivot can
    fire outside a cup-with-handle base. Each event includes contextual
    guideline flags (multi-month downtrend, position vs. 50/200dma, V-shape
    reversal risk, extension from the 10dma) that inform buyability but never
    suppress a detected event -- code reports structure, you judge
    buyability. Fundamentals strength and wedge-pattern geometry are NOT
    evaluated here; combine with the Fundamentals Analyst's read and visual
    chart review. Returns `events: []` and `active: false` when no pocket
    pivot fired within the scan window.
    """
    return analyze_pocket_pivots(symbol, curr_date, look_back_days)
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `python -c "from tradingagents.agents.utils.pocket_pivot_tools import get_pocket_pivot; print(get_pocket_pivot.name)"`
Expected: prints `get_pocket_pivot`

- [ ] **Step 3: Run ruff and commit**

```bash
ruff check tradingagents/agents/utils/pocket_pivot_tools.py
wc -l tradingagents/agents/utils/pocket_pivot_tools.py
git add tradingagents/agents/utils/pocket_pivot_tools.py
git commit -m "feat(pocket-pivot): add get_pocket_pivot LangChain tool"
```

---

### Task 5: Register the tool (`agent_utils.py`, `market_analyst.py`, `trading_graph.py`)

**Files:**
- Modify: `tradingagents/agents/utils/agent_utils.py` (import + `__all__`)
- Modify: `tradingagents/agents/analysts/market_analyst.py` (import, `tools = [...]`, one prompt paragraph)
- Modify: `tradingagents/graph/trading_graph.py` (import, `"market"` `ToolNode([...])`)
- Modify: `tests/test_market_toolnode.py` (regression assertion)

**Interfaces:**
- Consumes: `get_pocket_pivot` from `pocket_pivot_tools.py` (Task 4).
- Produces: nothing new — this task only makes `get_pocket_pivot` reachable by the Market Analyst LLM and executable by its `ToolNode`. No precedence prose, no prefetch, no changes to Wyckoff/O'Neil wiring in any of these files.

- [ ] **Step 1: Write the failing regression test**

In `tests/test_market_toolnode.py`, replace the final assertion block:

```python
    assert {
        "get_stock_data", "get_indicators", "get_chart_patterns", "get_trend_template",
        "get_wyckoff_structure", "get_oneil_setup",
    } <= market_tools
```

with:

```python
    assert {
        "get_stock_data", "get_indicators", "get_chart_patterns", "get_trend_template",
        "get_wyckoff_structure", "get_oneil_setup", "get_pocket_pivot",
    } <= market_tools
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_market_toolnode.py -v`
Expected: FAIL — `AssertionError` (`get_pocket_pivot` not yet in `market_tools`)

- [ ] **Step 3: Register in `agent_utils.py`**

In `tradingagents/agents/utils/agent_utils.py`, add the import in alphabetical (isort) order, between the `pattern_analysis_tools` and `prediction_markets_tools` imports:

```python
from tradingagents.agents.utils.oneil_tools import get_oneil_setup
from tradingagents.agents.utils.pattern_analysis_tools import get_chart_patterns
from tradingagents.agents.utils.pocket_pivot_tools import get_pocket_pivot
from tradingagents.agents.utils.prediction_markets_tools import get_prediction_markets
```

Then add `"get_pocket_pivot",` to `__all__`, immediately after `"get_oneil_setup",`:

```python
    "get_wyckoff_structure",
    "get_oneil_setup",
    "get_pocket_pivot",
    "build_instrument_context",
```

- [ ] **Step 4: Register in `market_analyst.py`**

In `tradingagents/agents/analysts/market_analyst.py`, add `get_pocket_pivot` to the existing `agent_utils` import (alphabetical order, between `get_language_instruction` and `get_stock_data`):

```python
from tradingagents.agents.utils.agent_utils import (
    get_chart_patterns,
    get_indicators,
    get_instrument_context_from_state,
    get_language_instruction,
    get_pocket_pivot,
    get_stock_data,
    get_trend_template,
    get_verified_market_snapshot,
)
```

Add it to the `tools = [...]` list:

```python
        tools = [
            get_stock_data,
            get_indicators,
            get_verified_market_snapshot,
            get_chart_patterns,
            get_trend_template,
            get_pocket_pivot,
        ]
```

Insert a new prompt paragraph directly after the existing `"Also call get_trend_template..."` paragraph and before the `"The stock's Wyckoff accumulation/distribution..."` paragraph (both are in the same f-string literal):

```python
Also call get_pocket_pivot for the ticker and current date. It deterministically detects Pocket Pivots (Kacher & Morales): a price close back above the 10-day or 50-day moving average on an up day, confirmed by volume exceeding the highest down-volume day of the prior 10 sessions. This is an independent volume/accumulation signal, separate from the Wyckoff and O'Neil precedence chain described below -- it does not participate in and must not override the Wyckoff phase_bias or O'Neil setup_bias direction; report it as supplementary color alongside a `context` block of buyability flags (multi-month downtrend, position vs. 50/200dma, V-shape reversal risk, extension from the 10dma). These flags are informational, not automatic disqualifiers -- weigh them when discussing the signal's strength. Do not evaluate fundamentals or wedge-pattern geometry from this tool; it does not compute them. Only mention a pocket pivot if `events` is non-empty, and note whether `active` is true.
```

- [ ] **Step 5: Register in `trading_graph.py`**

In `tradingagents/graph/trading_graph.py`, add the import in alphabetical order, between `get_oneil_setup` and `get_prediction_markets`:

```python
    get_news,
    get_oneil_setup,
    get_pocket_pivot,
    get_prediction_markets,
    get_stock_data,
```

Add it to the `"market"` `ToolNode` list:

```python
                    # Wyckoff accumulation/distribution structure read.
                    get_wyckoff_structure,
                    # O'Neil cup-with-handle setup read.
                    get_oneil_setup,
                    # Pocket Pivot volume/accumulation signal (independent of
                    # the Wyckoff/O'Neil precedence chain above).
                    get_pocket_pivot,
                ]
            ),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_market_toolnode.py -v`
Expected: PASS (1 passed)

- [ ] **Step 7: Run ruff and commit**

```bash
ruff check tradingagents/agents/utils/agent_utils.py tradingagents/agents/analysts/market_analyst.py tradingagents/graph/trading_graph.py tests/test_market_toolnode.py
git add tradingagents/agents/utils/agent_utils.py tradingagents/agents/analysts/market_analyst.py tradingagents/graph/trading_graph.py tests/test_market_toolnode.py
git commit -m "feat(pocket-pivot): register get_pocket_pivot with the Market Analyst"
```

---

### Task 6: Isolated verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full set of directly-affected tests**

Run:
```bash
pytest -q tests/test_pocket_pivot_signals.py tests/test_pocket_pivot_context.py tests/test_pocket_pivot_bias.py tests/test_market_toolnode.py
```
Expected: all pass, no regressions.

- [ ] **Step 2: Run ruff on every touched/created file**

Run:
```bash
ruff check tradingagents/dataflows/pocket_pivot_signals.py tradingagents/dataflows/pocket_pivot_context.py tradingagents/dataflows/pocket_pivot_bias.py tradingagents/agents/utils/pocket_pivot_tools.py tradingagents/agents/utils/agent_utils.py tradingagents/agents/analysts/market_analyst.py tradingagents/graph/trading_graph.py tests/test_pocket_pivot_signals.py tests/test_pocket_pivot_context.py tests/test_pocket_pivot_bias.py tests/test_market_toolnode.py
```
Expected: `All checks passed!`

- [ ] **Step 3: Confirm every new file is at or under 150 lines**

Run:
```bash
wc -l tradingagents/dataflows/pocket_pivot_signals.py tradingagents/dataflows/pocket_pivot_context.py tradingagents/dataflows/pocket_pivot_bias.py tradingagents/agents/utils/pocket_pivot_tools.py tests/test_pocket_pivot_signals.py tests/test_pocket_pivot_context.py tests/test_pocket_pivot_bias.py
```
Expected: every file ≤150. If any test file exceeds it, split by responsibility (e.g. separate the MA-cross cases from the volume-signature/gap-up cases into a sibling test file) before proceeding.

- [ ] **Step 4: Smoke test through the tool-facing entry point**

Run:
```bash
python -c "
from tradingagents.dataflows.pocket_pivot_bias import analyze_pocket_pivots
print(analyze_pocket_pivots('AAPL', '2026-07-01')[:500])
"
```
Expected: valid JSON printed, no traceback (network/cache access required — this hits `load_ohlcv`, matching how the Wyckoff/O'Neil plans smoke-test their own tool-facing entry points).

- [ ] **Step 5: Update `ONEIL_CANSLIM_ANALYSIS_PLAN.md` with a note pointing to this standalone addition**

Add a short section near the end of `ONEIL_CANSLIM_ANALYSIS_PLAN.md` (do not touch its CANSLIM/cup-handle sections) noting that Pocket Pivot detection was added as a deliberately standalone, non-precedence-chain signal, with a pointer to the spec and plan file paths. Keep it to a few lines, matching the tone of `WYCKOFF_ANALYSIS_PLAN.md`'s "Stage 2 实施状态" addition.

- [ ] **Step 6: Commit**

```bash
git add ONEIL_CANSLIM_ANALYSIS_PLAN.md
git commit -m "docs(pocket-pivot): note standalone pocket pivot addition"
```
