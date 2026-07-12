# False-Breakout State Machine (SP2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Note for this repo specifically:** execute each task through the `codex-delegate` skill. Codex prompts must open with the "YOU are the implementer" paragraph (feedback_codex_nested_delegation memory).

**Goal:** Turn every reversed parent breakout (triangles, rectangles, double top/bottom,
standalone S/R level breaks) into an actionable opposite-direction signal —
`false_breakout_short` after an upward false break, `false_breakdown_long` after a
downward one — via one generic state machine with thin per-pattern adapters, and mark the
failed parent `structure_may_be_expanding` with a voided target.

**Architecture:** A generic machine (`false_break_machine.py`) reuses SP1's
`find_reversal_index` as the universal Stage-1 re-entry detector, then dispatches to the
two direction-asymmetric Stage-2 confirmation builders (`false_break_confirm.py`). Pure
detectors live in `false_break_rules.py`, dataclasses/constants in `false_break_types.py`,
and PricePattern rendering + parent mutation in `false_break_patterns.py`.
`chart_patterns.py` wires the four failure sites; no upstream files are touched.

**Tech Stack:** Python 3.14, pandas, pytest (`@pytest.mark.unit`), ruff.

**Design source of truth:** `docs/superpowers/specs/2026-07-11-false-breakout-machine-design.md`.

**Planned deviation from the spec's file table:** the machine is split across TWO source
files — `false_break_machine.py` (Stage-1 + dispatch) and `false_break_confirm.py` (the
two Stage-2 builders + confidence helper) — because a single file holding the dispatcher
plus both `FalseBreakSignal` constructors is ~165 lines, over the 150 cap. This is a
responsibility split (orchestrator vs. per-direction behavior), exactly the decomposition
CLAUDE.md prescribes.

## Global Constraints

- **New files ≤150 lines each**, verified budgets: `false_break_types.py` ~66,
  `false_break_rules.py` ~95, `false_break_confirm.py` ~120, `false_break_machine.py` ~40,
  `false_break_patterns.py` ~100; tests ~25 / ~95 / ~110 / ~75 / ~70. `chart_patterns.py`
  is an existing grandfathered file (690 lines) — the wiring adds ~55 lines; that is
  acceptable (it is not a *new* file), but keep additions minimal and do not refactor it.
- **Constants, exact values and names** (all interim SP4 placeholders — say so in the
  `false_break_types.py` docstring): `REENTRY_WINDOW_BARS = 10`,
  `CONFIRM_WINDOW_BARS = 8`, `NO_NEW_LOW_GRACE_BARS = 2`, `VOLUME_MULTIPLE = 1.3`,
  `FORMING_CONFIDENCE = 0.45`, `CONFIRMED_STANDARD_CONFIDENCE = 0.60`,
  `CONFIRMED_AGGRESSIVE_CONFIDENCE = 0.55`, `VOLUME_CONFIDENCE_BONUS = 0.05`,
  `CONFIDENCE_FLOOR = 0.2`, `CONFIDENCE_CEILING = 0.9`. Retest tolerance is `1.0 × buffer`
  (the existing ATR buffer — no new constant).
- **No new schema:** signals are first-class `PricePattern` entries in the existing
  `patterns` list. Do NOT change `PricePattern`.
- **No import cycle:** `false_break_*` modules must NOT import `chart_patterns` at module
  top. `false_break_patterns.false_break_to_pattern` imports `PricePattern` lazily
  (function-local). `chart_patterns` imports `false_break_patterns`/`false_break_types` at
  top; that chain resolves without touching `chart_patterns` again.
- All tests `@pytest.mark.unit`, synthetic frames only, no network, no LLM calls.
- Do NOT `git add`/`git commit` — commits require separate explicit user approval
  (feedback_no_auto_commit_specs, feedback_user_pushes_himself).

**Empirically validated geometry (2026-07-12, prototyped against the live modules — the
tests below assert these exact numbers):**

- **Pipeline reversed-triangle** (`_triangle_breakout_data(53, reverse_after=True)`, the
  existing `test_late_triangle_breakout_that_reenters_is_failed` fixture): `len(df)=56`,
  `atr≈1.529`, `buffer≈0.306`, apex 60.5, `window_bars=8`, `start_index=5`. The triangle
  breaks **bullish at bar 53** with `risk_flags=['late_apex_breakout',
  'breakout_reversed_back_through_triangle']`; `find_reversal_index` returns **re-entry
  bar 55** (gap 2 ≤ 10). Because `late_apex_breakout ∈ ASYMMETRIC_REVERSAL_FLAGS`, the
  short confirms **aggressively at bar 55**: `false_breakout_short`, `bearish`,
  `confirmed`, `risk_flags=["aggressive_confirmation"]`.
- **Horizontal short (non-aggressive)** — resistance 100, buffer 0.3, bullish break bar 5,
  closes `[97,98,99,99.5,99.8,101.2,101.0,100.4,99.4,98.7,98.2]`, High/Low = Close±0.5:
  re-entry **bar 8** (close 99.4), pullback low **98.9**, confirms via a close below the
  pullback low at **bar 9**; extreme high 101.7 → invalidation 102.0. Confidence 0.6.
- **Horizontal long (standard)** — support 100, buffer 0.3, bearish break bar 5,
  closes `[103,102,101,100.6,100.3,98.8,98.0,99.0,100.1,101.1,101.4]`,
  lows `[102,101,101,100.5,100.2,98.5,97.8,98.4,99.6,100.9,101.2]`, High=Close+0.5:
  re-entry **bar 9**, trough bar 6 (guard ok: 6 ≤ 7), rebound high 101.6, upgrades to
  standard when the retest holds at **bar 10**. Confidence 0.6.
- **Long guard-fail** — closes `[103,102,101,100.5,100.2,99.0,98.5,98.2,97.5,100.6]`,
  lows `[102,101,101,100.5,100.2,98.5,98.0,97.9,97.2,100.3]`, support 100, bearish break
  bar 5: re-entry bar 9 but the trough is at **bar 8** (8 > 9−2) → guard fails →
  `detect_false_break` returns **None**.
- **Short window-expiry** — closes `[97,98,99,99.5,99.8] + [101.5]*12 + [99.0,98.0]`,
  resistance 100, bullish break bar 5: re-entry bar 17, gap 12 > 10 → returns **None**.

---

### Task 1: Signal dataclasses + calibration constants

**Files:**
- Create: `tradingagents/dataflows/false_break_types.py`
- Test: `tests/test_false_break_types.py`

**Interfaces:**
- Produces: constants named above; `FalseBreakContext` (frozen) with fields
  `breakout_index:int, direction:str, high_slope:float, high_intercept:float,
  low_slope:float, low_intercept:float, apex_index:float, buffer:float, window_bars:int,
  parent_pattern:str, parent_risk_flags:tuple[str,...]=(), target_price:float|None=None`;
  `FalseBreakSignal` (mutable) with fields `signal_type:str, direction:str, status:str,
  aggressive:bool, boundary_price:float, false_break_extreme:float, reentry_index:int,
  reentry_close:float, trigger_index:int|None, trigger_price:float|None,
  volume_expanded:bool, confidence:float, target_price:float|None,
  invalidation_price:float, start_index:int, end_index:int, parent_pattern:str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_false_break_types.py
"""Constants and dataclass defaults for the false-breakout machine (SP2)."""

from __future__ import annotations

import pytest

from tradingagents.dataflows import false_break_types as t


@pytest.mark.unit
def test_calibration_constants_have_exact_values():
    assert t.REENTRY_WINDOW_BARS == 10
    assert t.CONFIRM_WINDOW_BARS == 8
    assert t.NO_NEW_LOW_GRACE_BARS == 2
    assert t.VOLUME_MULTIPLE == 1.3
    assert t.FORMING_CONFIDENCE == 0.45
    assert t.CONFIRMED_STANDARD_CONFIDENCE == 0.60
    assert t.CONFIRMED_AGGRESSIVE_CONFIDENCE == 0.55
    assert (t.CONFIDENCE_FLOOR, t.CONFIDENCE_CEILING) == (0.2, 0.9)


@pytest.mark.unit
def test_context_defaults_are_empty_flags_and_no_target():
    ctx = t.FalseBreakContext(
        breakout_index=5, direction="bullish", high_slope=0.0, high_intercept=100.0,
        low_slope=0.0, low_intercept=100.0, apex_index=float("inf"), buffer=0.3,
        window_bars=0, parent_pattern="rectangle",
    )
    assert ctx.parent_risk_flags == ()
    assert ctx.target_price is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_false_break_types.py -q`
Expected: FAIL with `ModuleNotFoundError: ... false_break_types`.

- [ ] **Step 3: Write the module**

```python
# tradingagents/dataflows/false_break_types.py
"""Signal dataclasses and calibration constants for the false-breakout machine (SP2).

Every numeric constant here is an interim placeholder pending SP4 backtest calibration
(docs/superpowers/specs/2026-07-11-false-breakout-machine-design.md).
"""

from __future__ import annotations

from dataclasses import dataclass

REENTRY_WINDOW_BARS = 10
CONFIRM_WINDOW_BARS = 8
NO_NEW_LOW_GRACE_BARS = 2
VOLUME_MULTIPLE = 1.3

FORMING_CONFIDENCE = 0.45
CONFIRMED_STANDARD_CONFIDENCE = 0.60
CONFIRMED_AGGRESSIVE_CONFIDENCE = 0.55
VOLUME_CONFIDENCE_BONUS = 0.05
CONFIDENCE_FLOOR = 0.2
CONFIDENCE_CEILING = 0.9


@dataclass(frozen=True)
class FalseBreakContext:
    """One failed parent breakout described generically for the machine."""

    breakout_index: int
    direction: str  # original breakout direction: "bullish" | "bearish"
    high_slope: float
    high_intercept: float
    low_slope: float
    low_intercept: float
    apex_index: float
    buffer: float
    window_bars: int
    parent_pattern: str
    parent_risk_flags: tuple[str, ...] = ()
    target_price: float | None = None


@dataclass
class FalseBreakSignal:
    """The machine's verdict before it is rendered as a PricePattern."""

    signal_type: str  # "false_breakout_short" | "false_breakdown_long"
    direction: str  # "bearish" | "bullish"
    status: str  # "forming" | "confirmed"
    aggressive: bool
    boundary_price: float
    false_break_extreme: float
    reentry_index: int
    reentry_close: float
    trigger_index: int | None
    trigger_price: float | None
    volume_expanded: bool
    confidence: float
    target_price: float | None
    invalidation_price: float
    start_index: int
    end_index: int
    parent_pattern: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_false_break_types.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Ruff, then STOP for review** (do not commit)

Run: `ruff check tradingagents/dataflows/false_break_types.py tests/test_false_break_types.py`
Expected: `All checks passed!`

---

### Task 2: Pure false-break detectors

**Files:**
- Create: `tradingagents/dataflows/false_break_rules.py`
- Test: `tests/test_false_break_rules.py`

**Interfaces:**
- Consumes: `VOLUME_MULTIPLE` from `false_break_types`.
- Produces: `pullback_low(df, breakout_index, reentry_index) -> float`;
  `rebound_high(df, breakdown_index, reentry_index) -> float`;
  `false_break_extreme(df, breakout_index, reentry_index, direction) -> float`;
  `trough_index(df, breakdown_index, reentry_index) -> int`;
  `no_new_low_guard(df, *, breakdown_index, reentry_index, grace_bars) -> bool`;
  `short_trigger_index(df, *, reentry_index, boundary_price, pullback_low_price, buffer,
  confirm_window) -> int|None`;
  `long_upgrade_index(df, *, reentry_index, boundary_price, rebound_high_price, buffer)
  -> int|None`;
  `volume_expanded(df, index, multiple=VOLUME_MULTIPLE) -> bool`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_false_break_rules.py
"""Pure false-break detectors (SP2)."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows import false_break_rules as r


def _frame(closes, lows=None, highs=None, volume=None):
    lows = lows if lows is not None else [c - 0.5 for c in closes]
    highs = highs if highs is not None else [c + 0.5 for c in closes]
    volume = volume if volume is not None else [1_000_000.0] * len(closes)
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2026-01-02", periods=len(closes)),
            "Open": closes, "High": highs, "Low": lows, "Close": closes, "Volume": volume,
        }
    )


SHORT = _frame([97, 98, 99, 99.5, 99.8, 101.2, 101.0, 100.4, 99.4, 98.7, 98.2])
LONG = _frame(
    [103, 102, 101, 100.6, 100.3, 98.8, 98.0, 99.0, 100.1, 101.1, 101.4],
    lows=[102, 101, 101, 100.5, 100.2, 98.5, 97.8, 98.4, 99.6, 100.9, 101.2],
)


@pytest.mark.unit
def test_pullback_low_and_extreme_high_over_breakout_to_reentry():
    assert r.pullback_low(SHORT, 5, 8) == pytest.approx(98.9)
    assert r.false_break_extreme(SHORT, 5, 8, "bullish") == pytest.approx(101.7)


@pytest.mark.unit
def test_rebound_high_extreme_low_and_trough_over_breakdown_to_reentry():
    assert r.rebound_high(LONG, 5, 9) == pytest.approx(101.6)
    assert r.false_break_extreme(LONG, 5, 9, "bearish") == pytest.approx(97.8)
    assert r.trough_index(LONG, 5, 9) == 6


@pytest.mark.unit
def test_no_new_low_guard_passes_when_trough_is_early_fails_when_late():
    assert r.no_new_low_guard(LONG, breakdown_index=5, reentry_index=9, grace_bars=2) is True
    late = _frame(
        [103, 102, 101, 100.5, 100.2, 99.0, 98.5, 98.2, 97.5, 100.6],
        lows=[102, 101, 101, 100.5, 100.2, 98.5, 98.0, 97.9, 97.2, 100.3],
    )
    assert r.no_new_low_guard(late, breakdown_index=5, reentry_index=9, grace_bars=2) is False


@pytest.mark.unit
def test_short_trigger_fires_on_pullback_low_break():
    assert (
        r.short_trigger_index(
            SHORT, reentry_index=8, boundary_price=100.0, pullback_low_price=98.9,
            buffer=0.3, confirm_window=8,
        )
        == 9
    )


@pytest.mark.unit
def test_short_trigger_fires_on_failed_retest_before_pullback_break():
    # High tags 100-0.3 from below at bar 9 but Close stays below 100; pullback low far away.
    frame = _frame([97, 98, 99, 99.5, 99.8, 101.2, 100.9, 100.2, 99.4, 99.8, 99.5],
                   highs=[97.5, 98.5, 99.5, 100, 100.3, 101.7, 101.4, 100.7, 99.9, 100.5, 100])
    assert (
        r.short_trigger_index(
            frame, reentry_index=8, boundary_price=100.0, pullback_low_price=90.0,
            buffer=0.3, confirm_window=8,
        )
        == 9
    )


@pytest.mark.unit
def test_short_trigger_returns_none_when_no_confirmation_in_window():
    flat = _frame([97, 98, 99, 99.5, 99.8, 101.2, 100.9, 100.4, 99.4])  # ends at re-entry
    assert (
        r.short_trigger_index(
            flat, reentry_index=8, boundary_price=100.0, pullback_low_price=98.9,
            buffer=0.3, confirm_window=8,
        )
        is None
    )


@pytest.mark.unit
def test_long_upgrade_fires_when_retest_holds():
    assert (
        r.long_upgrade_index(
            LONG, reentry_index=9, boundary_price=100.0, rebound_high_price=101.6, buffer=0.3
        )
        == 10
    )


@pytest.mark.unit
def test_long_upgrade_returns_none_without_break_or_held_retest():
    stalled = _frame([103, 102, 101, 100.6, 100.3, 98.8, 98.0, 99.0, 100.1, 100.05],
                     lows=[102, 101, 101, 100.5, 100.2, 98.5, 97.8, 98.4, 99.6, 99.0])
    assert (
        r.long_upgrade_index(
            stalled, reentry_index=8, boundary_price=100.0, rebound_high_price=101.6, buffer=0.3
        )
        is None
    )


@pytest.mark.unit
def test_volume_expanded_true_on_spike_false_on_flat():
    spike = _frame([100] * 22, volume=[1_000_000.0] * 21 + [1_600_000.0])
    assert r.volume_expanded(spike, 21) is True
    assert r.volume_expanded(_frame([100] * 22), 21) is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_false_break_rules.py -q`
Expected: FAIL with `ModuleNotFoundError: ... false_break_rules`.

- [ ] **Step 3: Write the module**

```python
# tradingagents/dataflows/false_break_rules.py
"""Pure detectors for the false-breakout state machine (SP2).

Pullback-low / rebound-high extremes, the post-breakdown no-new-low guard, the short
confirmation trigger, the long standard-tier upgrade, and volume expansion. No dependency
on chart_patterns (kept import-cycle free).
"""

from __future__ import annotations

import pandas as pd

from tradingagents.dataflows.false_break_types import VOLUME_MULTIPLE


def pullback_low(df: pd.DataFrame, breakout_index: int, reentry_index: int) -> float:
    """Lowest Low from the breakout bar through the re-entry bar (inclusive)."""
    return float(df["Low"].iloc[breakout_index : reentry_index + 1].min())


def rebound_high(df: pd.DataFrame, breakdown_index: int, reentry_index: int) -> float:
    """Highest High from the breakdown bar through the re-entry bar (inclusive)."""
    return float(df["High"].iloc[breakdown_index : reentry_index + 1].max())


def false_break_extreme(
    df: pd.DataFrame, breakout_index: int, reentry_index: int, direction: str
) -> float:
    """Furthest excursion outside the boundary during the false break."""
    window = df.iloc[breakout_index : reentry_index + 1]
    if direction == "bullish":
        return float(window["High"].max())
    return float(window["Low"].min())


def trough_index(df: pd.DataFrame, breakdown_index: int, reentry_index: int) -> int:
    """Absolute index of the lowest Low between breakdown and re-entry (inclusive)."""
    return int(df["Low"].iloc[breakdown_index : reentry_index + 1].idxmin())


def no_new_low_guard(
    df: pd.DataFrame, *, breakdown_index: int, reentry_index: int, grace_bars: int
) -> bool:
    """True when the post-breakdown trough is at least grace_bars before re-entry."""
    return trough_index(df, breakdown_index, reentry_index) <= reentry_index - grace_bars


def short_trigger_index(
    df: pd.DataFrame,
    *,
    reentry_index: int,
    boundary_price: float,
    pullback_low_price: float,
    buffer: float,
    confirm_window: int,
) -> int | None:
    """First bar in the window confirming the short: pullback-low break or failed retest."""
    end = min(len(df), reentry_index + 1 + confirm_window)
    for index in range(reentry_index + 1, end):
        close = float(df.at[index, "Close"])
        high = float(df.at[index, "High"])
        if close < pullback_low_price:
            return index
        if high >= boundary_price - buffer and close < boundary_price:
            return index
    return None


def long_upgrade_index(
    df: pd.DataFrame,
    *,
    reentry_index: int,
    boundary_price: float,
    rebound_high_price: float,
    buffer: float,
) -> int | None:
    """First bar upgrading the long to standard tier: rebound-high break or a held retest."""
    for index in range(reentry_index + 1, len(df)):
        close = float(df.at[index, "Close"])
        low = float(df.at[index, "Low"])
        if close > rebound_high_price:
            return index
        if low >= boundary_price - buffer and close >= boundary_price:
            return index
    return None


def volume_expanded(df: pd.DataFrame, index: int, multiple: float = VOLUME_MULTIPLE) -> bool:
    """Bar volume vs. the trailing 20-bar average (same mechanism as _volume_confirmation)."""
    if index < 1 or pd.isna(df.at[index, "Volume"]):
        return False
    start = max(0, index - 20)
    baseline = pd.to_numeric(df["Volume"].iloc[start:index], errors="coerce").mean()
    return bool(baseline and float(df.at[index, "Volume"]) >= float(baseline) * multiple)
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_false_break_rules.py -q`
Expected: PASS (9 passed). If `test_short_trigger_fires_on_failed_retest_before_pullback_break`
fails, re-check that bar 9's High (100.5) ≥ 100−0.3 and Close (99.8) < 100 — adjust the
fixture, not the rule.

- [ ] **Step 5: Ruff, then STOP for review** (do not commit)

Run: `ruff check tradingagents/dataflows/false_break_rules.py tests/test_false_break_rules.py`
Expected: `All checks passed!`

---

### Task 3: The machine (Stage-1 dispatch + Stage-2 builders)

**Files:**
- Create: `tradingagents/dataflows/false_break_confirm.py`
- Create: `tradingagents/dataflows/false_break_machine.py`
- Test: `tests/test_false_break_machine.py`

**Interfaces:**
- Consumes: everything from Tasks 1–2; `find_reversal_index`, `line_before_apex`,
  `ASYMMETRIC_REVERSAL_FLAGS` from `triangle_post_apex`.
- Produces (confirm): `build_short(df, ctx, reentry, extreme) -> FalseBreakSignal`;
  `build_long(df, ctx, reentry, extreme) -> FalseBreakSignal | None`.
- Produces (machine): `detect_false_break(df, ctx: FalseBreakContext) ->
  FalseBreakSignal | None` — the only entry point adapters call.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_false_break_machine.py
"""End-to-end machine behavior for the false-breakout state machine (SP2)."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from tradingagents.dataflows.false_break_machine import detect_false_break
from tradingagents.dataflows.false_break_types import FalseBreakContext


def _frame(closes, lows=None, highs=None):
    lows = lows if lows is not None else [c - 0.5 for c in closes]
    highs = highs if highs is not None else [c + 0.5 for c in closes]
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2026-01-02", periods=len(closes)),
            "Open": closes, "High": highs, "Low": lows, "Close": closes,
            "Volume": [1_000_000.0] * len(closes),
        }
    )


def _ctx(direction, level=100.0, flags=()):
    return FalseBreakContext(
        breakout_index=5, direction=direction, high_slope=0.0, high_intercept=level,
        low_slope=0.0, low_intercept=level, apex_index=math.inf, buffer=0.3, window_bars=0,
        parent_pattern="rectangle", parent_risk_flags=flags,
        target_price=(level - 5 if direction == "bullish" else level + 5),
    )


SHORT = _frame([97, 98, 99, 99.5, 99.8, 101.2, 101.0, 100.4, 99.4, 98.7, 98.2])
LONG = _frame(
    [103, 102, 101, 100.6, 100.3, 98.8, 98.0, 99.0, 100.1, 101.1, 101.4],
    lows=[102, 101, 101, 100.5, 100.2, 98.5, 97.8, 98.4, 99.6, 100.9, 101.2],
)


@pytest.mark.unit
def test_upward_false_break_confirms_short_at_standard_tier():
    signal = detect_false_break(SHORT, _ctx("bullish"))
    assert signal is not None
    assert (signal.signal_type, signal.direction, signal.status) == (
        "false_breakout_short", "bearish", "confirmed",
    )
    assert signal.aggressive is False
    assert (signal.reentry_index, signal.trigger_index) == (8, 9)
    assert signal.confidence == 0.6
    assert signal.invalidation_price == pytest.approx(102.0)
    assert signal.target_price == pytest.approx(95.0)


@pytest.mark.unit
def test_short_stays_forming_when_window_has_no_confirmation():
    signal = detect_false_break(_frame([97, 98, 99, 99.5, 99.8, 101.2, 101.0, 100.4, 99.4]),
                                _ctx("bullish"))
    assert signal is not None
    assert signal.status == "forming"
    assert signal.trigger_index is None
    assert signal.confidence == 0.45


@pytest.mark.unit
def test_late_apex_parent_confirms_short_aggressively_at_reentry():
    signal = detect_false_break(SHORT, _ctx("bullish", flags=("late_apex_breakout",)))
    assert signal.status == "confirmed"
    assert signal.aggressive is True
    assert signal.trigger_index == signal.reentry_index == 8
    assert signal.confidence == 0.55


@pytest.mark.unit
def test_downward_false_break_confirms_long_and_upgrades_to_standard():
    signal = detect_false_break(LONG, _ctx("bearish"))
    assert signal is not None
    assert (signal.signal_type, signal.direction, signal.status) == (
        "false_breakdown_long", "bullish", "confirmed",
    )
    assert signal.aggressive is False  # upgraded at bar 10
    assert (signal.reentry_index, signal.trigger_index) == (9, 10)
    assert signal.confidence == 0.6


@pytest.mark.unit
def test_long_returns_none_when_new_low_guard_fails():
    guard_fail = _frame(
        [103, 102, 101, 100.5, 100.2, 99.0, 98.5, 98.2, 97.5, 100.6],
        lows=[102, 101, 101, 100.5, 100.2, 98.5, 98.0, 97.9, 97.2, 100.3],
    )
    assert detect_false_break(guard_fail, _ctx("bearish")) is None


@pytest.mark.unit
def test_reentry_beyond_window_emits_nothing():
    late = _frame([97, 98, 99, 99.5, 99.8] + [101.5] * 12 + [99.0, 98.0])
    assert detect_false_break(late, _ctx("bullish")) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_false_break_machine.py -q`
Expected: FAIL with `ModuleNotFoundError: ... false_break_machine`.

- [ ] **Step 3a: Write the confirmation builders**

```python
# tradingagents/dataflows/false_break_confirm.py
"""Stage-2 direction-asymmetric confirmation builders for false breakouts (SP2)."""

from __future__ import annotations

import pandas as pd

from tradingagents.dataflows.false_break_rules import (
    long_upgrade_index,
    no_new_low_guard,
    pullback_low,
    rebound_high,
    short_trigger_index,
    volume_expanded,
)
from tradingagents.dataflows.false_break_types import (
    CONFIDENCE_CEILING,
    CONFIDENCE_FLOOR,
    CONFIRM_WINDOW_BARS,
    CONFIRMED_AGGRESSIVE_CONFIDENCE,
    CONFIRMED_STANDARD_CONFIDENCE,
    FORMING_CONFIDENCE,
    NO_NEW_LOW_GRACE_BARS,
    VOLUME_CONFIDENCE_BONUS,
    FalseBreakContext,
    FalseBreakSignal,
)
from tradingagents.dataflows.triangle_post_apex import (
    ASYMMETRIC_REVERSAL_FLAGS,
    line_before_apex,
)


def _confidence(status: str, aggressive: bool, expanded: bool) -> float:
    if status == "forming":
        base = FORMING_CONFIDENCE
    else:
        base = CONFIRMED_AGGRESSIVE_CONFIDENCE if aggressive else CONFIRMED_STANDARD_CONFIDENCE
    if expanded:
        base += VOLUME_CONFIDENCE_BONUS
    return round(max(CONFIDENCE_FLOOR, min(CONFIDENCE_CEILING, base)), 2)


def build_short(
    df: pd.DataFrame, ctx: FalseBreakContext, reentry: int, extreme: float
) -> FalseBreakSignal:
    boundary = line_before_apex(ctx.high_slope, ctx.high_intercept, reentry, ctx.apex_index)
    pullback = pullback_low(df, ctx.breakout_index, reentry)
    trigger: int | None
    if ASYMMETRIC_REVERSAL_FLAGS & set(ctx.parent_risk_flags):
        status, aggressive, trigger = "confirmed", True, reentry
    else:
        trig = short_trigger_index(
            df, reentry_index=reentry, boundary_price=boundary,
            pullback_low_price=pullback, buffer=ctx.buffer, confirm_window=CONFIRM_WINDOW_BARS,
        )
        if trig is not None:
            status, aggressive, trigger = "confirmed", False, trig
        else:
            status, aggressive, trigger = "forming", False, None
    vol_index = trigger if trigger is not None else reentry
    expanded = volume_expanded(df, vol_index)
    return FalseBreakSignal(
        signal_type="false_breakout_short", direction="bearish", status=status,
        aggressive=aggressive, boundary_price=boundary, false_break_extreme=extreme,
        reentry_index=reentry, reentry_close=float(df.at[reentry, "Close"]),
        trigger_index=trigger, trigger_price=pullback, volume_expanded=expanded,
        confidence=_confidence(status, aggressive, expanded), target_price=ctx.target_price,
        invalidation_price=extreme + ctx.buffer, start_index=ctx.breakout_index,
        end_index=trigger if trigger is not None else reentry, parent_pattern=ctx.parent_pattern,
    )


def build_long(
    df: pd.DataFrame, ctx: FalseBreakContext, reentry: int, extreme: float
) -> FalseBreakSignal | None:
    if not no_new_low_guard(
        df, breakdown_index=ctx.breakout_index, reentry_index=reentry,
        grace_bars=NO_NEW_LOW_GRACE_BARS,
    ):
        return None
    boundary = line_before_apex(ctx.low_slope, ctx.low_intercept, reentry, ctx.apex_index)
    rebound = rebound_high(df, ctx.breakout_index, reentry)
    upgrade = long_upgrade_index(
        df, reentry_index=reentry, boundary_price=boundary,
        rebound_high_price=rebound, buffer=ctx.buffer,
    )
    aggressive, trigger = (False, upgrade) if upgrade is not None else (True, reentry)
    expanded = volume_expanded(df, trigger)
    return FalseBreakSignal(
        signal_type="false_breakdown_long", direction="bullish", status="confirmed",
        aggressive=aggressive, boundary_price=boundary, false_break_extreme=extreme,
        reentry_index=reentry, reentry_close=float(df.at[reentry, "Close"]),
        trigger_index=trigger, trigger_price=rebound, volume_expanded=expanded,
        confidence=_confidence("confirmed", aggressive, expanded), target_price=ctx.target_price,
        invalidation_price=extreme - ctx.buffer, start_index=ctx.breakout_index,
        end_index=trigger, parent_pattern=ctx.parent_pattern,
    )
```

- [ ] **Step 3b: Write the orchestrator**

```python
# tradingagents/dataflows/false_break_machine.py
"""Stage-1 re-entry detection + dispatch for the false-breakout state machine (SP2).

Reuses SP1's find_reversal_index as the universal re-entry detector, caps signal emission
at REENTRY_WINDOW_BARS, and dispatches to the Stage-2 builders in false_break_confirm.
"""

from __future__ import annotations

import pandas as pd

from tradingagents.dataflows.false_break_confirm import build_long, build_short
from tradingagents.dataflows.false_break_rules import false_break_extreme
from tradingagents.dataflows.false_break_types import (
    REENTRY_WINDOW_BARS,
    FalseBreakContext,
    FalseBreakSignal,
)
from tradingagents.dataflows.triangle_post_apex import find_reversal_index


def detect_false_break(df: pd.DataFrame, ctx: FalseBreakContext) -> FalseBreakSignal | None:
    """Return a false-break signal for a reversed parent breakout, or None."""
    reentry = find_reversal_index(
        df, high_slope=ctx.high_slope, high_intercept=ctx.high_intercept,
        low_slope=ctx.low_slope, low_intercept=ctx.low_intercept, apex_index=ctx.apex_index,
        breakout_index=ctx.breakout_index, breakout_direction=ctx.direction,
        risk_flags=list(ctx.parent_risk_flags), buffer=ctx.buffer, window_bars=ctx.window_bars,
    )
    if reentry is None or reentry - ctx.breakout_index > REENTRY_WINDOW_BARS:
        return None
    extreme = false_break_extreme(df, ctx.breakout_index, reentry, ctx.direction)
    if ctx.direction == "bullish":
        return build_short(df, ctx, reentry, extreme)
    return build_long(df, ctx, reentry, extreme)
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_false_break_machine.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Confirm both files fit budget + ruff, then STOP for review** (do not commit)

Run: `wc -l tradingagents/dataflows/false_break_confirm.py tradingagents/dataflows/false_break_machine.py`
Expected: both ≤150 (confirm ~120, machine ~40).
Run: `ruff check tradingagents/dataflows/false_break_confirm.py tradingagents/dataflows/false_break_machine.py tests/test_false_break_machine.py`
Expected: `All checks passed!`

---

### Task 4: Render signals as PricePatterns + mutate the parent

**Files:**
- Create: `tradingagents/dataflows/false_break_patterns.py`
- Test: `tests/test_false_break_patterns.py`

**Interfaces:**
- Consumes: `detect_false_break`; `FalseBreakContext`, `FalseBreakSignal`; `PricePattern`
  (lazy import inside `false_break_to_pattern`).
- Produces: `apply_parent_side_effects(parent) -> None` (sets `parent.target_price=None`,
  appends `"structure_may_be_expanding"` once); `false_break_to_pattern(df, signal) ->
  PricePattern`; `build_false_break_signal(df, ctx) -> PricePattern | None` (runs the
  machine, returns a rendered PricePattern or None). Adapters call
  `apply_parent_side_effects` **and** `build_false_break_signal`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_false_break_patterns.py
"""PricePattern rendering and parent mutation for the false-breakout machine (SP2)."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from tradingagents.dataflows.chart_patterns import PricePattern
from tradingagents.dataflows.false_break_patterns import (
    apply_parent_side_effects,
    build_false_break_signal,
)
from tradingagents.dataflows.false_break_types import FalseBreakContext


def _frame(closes, lows=None, highs=None):
    lows = lows if lows is not None else [c - 0.5 for c in closes]
    highs = highs if highs is not None else [c + 0.5 for c in closes]
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2026-01-02", periods=len(closes)),
            "Open": closes, "High": highs, "Low": lows, "Close": closes,
            "Volume": [1_000_000.0] * len(closes),
        }
    )


def _failed_parent():
    return PricePattern(
        pattern="rectangle", status="failed", direction="neutral", confidence=0.5,
        start_date="2026-01-02", end_date="2026-01-20", levels={}, target_price=123.0,
        invalidation_price=None, volume_confirmed=None, evidence=[],
        risk_flags=["some_existing_flag"],
    )


@pytest.mark.unit
def test_apply_parent_side_effects_voids_target_and_flags_expansion():
    parent = _failed_parent()
    apply_parent_side_effects(parent)
    assert parent.target_price is None
    assert "structure_may_be_expanding" in parent.risk_flags
    apply_parent_side_effects(parent)  # idempotent
    assert parent.risk_flags.count("structure_may_be_expanding") == 1


@pytest.mark.unit
def test_short_signal_renders_as_bearish_pricepattern():
    df = _frame([97, 98, 99, 99.5, 99.8, 101.2, 101.0, 100.4, 99.4, 98.7, 98.2])
    ctx = FalseBreakContext(
        breakout_index=5, direction="bullish", high_slope=0.0, high_intercept=100.0,
        low_slope=0.0, low_intercept=100.0, apex_index=math.inf, buffer=0.3, window_bars=0,
        parent_pattern="rectangle", target_price=95.0,
    )
    pattern = build_false_break_signal(df, ctx)
    assert isinstance(pattern, PricePattern)
    assert pattern.pattern == "false_breakout_short"
    assert pattern.direction == "bearish"
    assert pattern.status == "confirmed"
    assert pattern.target_price == pytest.approx(95.0)
    assert pattern.invalidation_price == pytest.approx(102.0)
    assert set(pattern.levels) == {
        "boundary_price", "false_break_extreme", "reentry_close", "trigger_price",
    }
    assert len(pattern.evidence) == 6
    assert pattern.risk_flags == []


@pytest.mark.unit
def test_aggressive_short_carries_the_aggressive_confirmation_flag():
    df = _frame([97, 98, 99, 99.5, 99.8, 101.2, 101.0, 100.4, 99.4, 98.7, 98.2])
    ctx = FalseBreakContext(
        breakout_index=5, direction="bullish", high_slope=0.0, high_intercept=100.0,
        low_slope=0.0, low_intercept=100.0, apex_index=math.inf, buffer=0.3, window_bars=0,
        parent_pattern="symmetrical_triangle", parent_risk_flags=("late_apex_breakout",),
    )
    pattern = build_false_break_signal(df, ctx)
    assert pattern.risk_flags == ["aggressive_confirmation"]


@pytest.mark.unit
def test_build_returns_none_when_machine_finds_no_signal():
    df = _frame([97, 98, 99, 99.5, 99.8] + [101.5] * 12 + [99.0, 98.0])
    ctx = FalseBreakContext(
        breakout_index=5, direction="bullish", high_slope=0.0, high_intercept=100.0,
        low_slope=0.0, low_intercept=100.0, apex_index=math.inf, buffer=0.3, window_bars=0,
        parent_pattern="rectangle",
    )
    assert build_false_break_signal(df, ctx) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_false_break_patterns.py -q`
Expected: FAIL with `ModuleNotFoundError: ... false_break_patterns`.

- [ ] **Step 3: Write the module**

```python
# tradingagents/dataflows/false_break_patterns.py
"""Render false-break signals as PricePattern entries and mutate the failed parent (SP2)."""

from __future__ import annotations

import math

import pandas as pd

from tradingagents.dataflows.false_break_machine import detect_false_break
from tradingagents.dataflows.false_break_types import FalseBreakContext, FalseBreakSignal


def _round(value: float | None) -> float | None:
    return None if value is None or not math.isfinite(value) else round(float(value), 4)


def _date(df: pd.DataFrame, index: int) -> str:
    return df.at[index, "Date"].strftime("%Y-%m-%d")


def apply_parent_side_effects(parent) -> None:
    """A reversed-breakout parent stays failed but its target is void and structure may expand."""
    parent.target_price = None
    if "structure_may_be_expanding" not in parent.risk_flags:
        parent.risk_flags.append("structure_may_be_expanding")


def _evidence(df: pd.DataFrame, signal: FalseBreakSignal) -> list[str]:
    short = signal.signal_type == "false_breakout_short"
    lines = [
        (
            f"The {signal.parent_pattern} broke {'out above' if short else 'down below'} "
            f"{_round(signal.boundary_price)} on {_date(df, signal.start_index)} then reversed."
        ),
        (
            f"The false break extended to {_round(signal.false_break_extreme)} "
            "before price closed back through the boundary."
        ),
        (
            f"Re-entry closed at {_round(signal.reentry_close)} on "
            f"{_date(df, signal.reentry_index)}, inside the re-entry window."
        ),
    ]
    if signal.aggressive:
        lines.append(
            "Confirmed aggressively at re-entry (aggressive_confirmation): less structural proof."
        )
    elif signal.trigger_index is not None:
        verb = "a close below the pullback low" if short else "price taking out the rebound high"
        lines.append(
            f"Confirmed by {verb} {_round(signal.trigger_price)} on "
            f"{_date(df, signal.trigger_index)}."
        )
    else:
        lines.append(
            f"Forming: awaiting a close below the pullback low {_round(signal.trigger_price)}."
        )
    if signal.volume_expanded:
        lines.append("Volume expanded on the confirming bar, strengthening the reversal.")
    elif short:
        lines.append("Volume did not expand; price structure alone carries the signal.")
    else:
        lines.append("Volume contracted, which may reflect exhausted selling pressure.")
    lines.append(
        f"Reverses the failed {signal.parent_pattern} breakout of {_date(df, signal.start_index)}."
    )
    return lines


def false_break_to_pattern(df: pd.DataFrame, signal: FalseBreakSignal):
    """Convert a FalseBreakSignal into a PricePattern (lazy import breaks the cycle)."""
    from tradingagents.dataflows.chart_patterns import PricePattern

    return PricePattern(
        pattern=signal.signal_type,
        status=signal.status,
        direction=signal.direction,
        confidence=signal.confidence,
        start_date=_date(df, signal.start_index),
        end_date=_date(df, signal.end_index),
        levels={
            "boundary_price": _round(signal.boundary_price),
            "false_break_extreme": _round(signal.false_break_extreme),
            "reentry_close": _round(signal.reentry_close),
            "trigger_price": _round(signal.trigger_price),
        },
        target_price=_round(signal.target_price),
        invalidation_price=_round(signal.invalidation_price),
        volume_confirmed=signal.volume_expanded,
        evidence=_evidence(df, signal),
        risk_flags=["aggressive_confirmation"] if signal.aggressive else [],
    )


def build_false_break_signal(df: pd.DataFrame, ctx: FalseBreakContext):
    """Run the machine and render a PricePattern, or return None."""
    signal = detect_false_break(df, ctx)
    if signal is None:
        return None
    return false_break_to_pattern(df, signal)
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_false_break_patterns.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Budget + ruff, then STOP for review** (do not commit)

Run: `wc -l tradingagents/dataflows/false_break_patterns.py` (expect ~100, ≤150)
Run: `ruff check tradingagents/dataflows/false_break_patterns.py tests/test_false_break_patterns.py`
Expected: `All checks passed!`

---

### Task 5: Wire the four failure sites in `chart_patterns.py`

**Files:**
- Modify: `tradingagents/dataflows/chart_patterns.py` (imports; `_level_breakout_patterns`;
  `_double_patterns`; `_rectangle_pattern`; `_triangle_pattern`;
  `analyze_chart_patterns_from_data` call sites)
- Test: `tests/test_false_break_pipeline.py`

**Interfaces:**
- Consumes: `apply_parent_side_effects`, `build_false_break_signal` from
  `false_break_patterns`; `FalseBreakContext` from `false_break_types`;
  `post_apex_window_bars` from `triangle_post_apex`.
- Produces: `analyze_chart_patterns_from_data(...)["patterns"]` now includes
  `false_breakout_short` / `false_breakdown_long` entries next to their failed parent,
  and failed reversed parents carry `structure_may_be_expanding` with `target_price=None`.

- [ ] **Step 1: Write the failing pipeline test**

```python
# tests/test_false_break_pipeline.py
"""End-to-end false-break wiring through analyze_chart_patterns_from_data (SP2)."""

from __future__ import annotations

import pandas as pd
import pytest

import tradingagents.dataflows.chart_patterns as patterns


def _interp(anchors):
    values = []
    for start, end in zip(anchors, anchors[1:]):
        (s, sv), (e, ev) = start, end
        values += [sv + (ev - sv) * o / (e - s) for o in range(e - s)]
    values.append(anchors[-1][1])
    return values


def _ohlcv(closes, bvi=None):
    volume = [1_000_000.0] * len(closes)
    if bvi is not None:
        volume[bvi] = 1_600_000.0
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2026-01-02", periods=len(closes)),
            "Open": closes, "High": [c + 0.6 for c in closes], "Low": [c - 0.6 for c in closes],
            "Close": closes, "Volume": volume,
        }
    )


def _reversed_triangle():
    bi = 53
    anchors = [
        (0, 100), (5, 110), (10, 90), (15, 108), (20, 92), (25, 106), (30, 94),
        (bi - 2, 99.5), (bi, 103), (bi + 2, 99.5),
    ]
    return _ohlcv(_interp(anchors), bvi=bi)


def _find(result, name):
    return next((p for p in result["patterns"] if p["pattern"] == name), None)


@pytest.mark.unit
def test_reversed_late_apex_triangle_emits_aggressive_short():
    data = _reversed_triangle()
    result = patterns.analyze_chart_patterns_from_data(
        data, data["Date"].iloc[-1].strftime("%Y-%m-%d"), pivot_span=3
    )
    short = _find(result, "false_breakout_short")
    assert short is not None
    assert short["status"] == "confirmed"
    assert short["direction"] == "bearish"
    assert "aggressive_confirmation" in short["risk_flags"]


@pytest.mark.unit
def test_reversed_triangle_parent_marked_expanding_with_void_target():
    data = _reversed_triangle()
    result = patterns.analyze_chart_patterns_from_data(
        data, data["Date"].iloc[-1].strftime("%Y-%m-%d"), pivot_span=3
    )
    parent = _find(result, "symmetrical_triangle")
    assert parent["status"] == "failed"
    assert "structure_may_be_expanding" in parent["risk_flags"]
    assert parent["target_price"] is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_false_break_pipeline.py -q`
Expected: FAIL — `false_breakout_short` not found / `structure_may_be_expanding` missing.

- [ ] **Step 3a: Add imports** near the top of `chart_patterns.py` (after the existing
  `from tradingagents.dataflows.triangle_breakout import classify_triangle_breakout` line):

```python
from tradingagents.dataflows.false_break_patterns import (
    apply_parent_side_effects,
    build_false_break_signal,
)
from tradingagents.dataflows.false_break_types import FalseBreakContext
from tradingagents.dataflows.triangle_post_apex import post_apex_window_bars
```

- [ ] **Step 3b: Wire `_level_breakout_patterns`.** Change the candidate list to carry a
  context, and emit on the selected failed parents.

Change the declaration:
```python
    candidates: list[tuple[int, PricePattern]] = []
```
to:
```python
    candidates: list[tuple[int, FalseBreakContext | None, PricePattern]] = []
```

Immediately BEFORE the `candidates.append((crossing_index, PricePattern(` call, insert:
```python
            false_break_ctx = None
            if status == "failed":
                false_break_ctx = FalseBreakContext(
                    breakout_index=crossing_index,
                    direction="bullish" if direction == "above" else "bearish",
                    high_slope=0.0, high_intercept=level, low_slope=0.0, low_intercept=level,
                    apex_index=math.inf, buffer=buffer, window_bars=0,
                    parent_pattern=pattern_name,
                )
```
and change the append from `candidates.append((crossing_index, PricePattern(` to
`candidates.append((crossing_index, false_break_ctx, PricePattern(`.

Replace the final output block:
```python
    if not candidates:
        return []
    # One most-recent signal in each direction is enough for the analyst.
    output = []
    for name in ("resistance_breakout", "support_breakdown"):
        matching = [item for item in candidates if item[1].pattern == name]
        if matching:
            output.append(max(matching, key=lambda item: item[0])[1])
    return output
```
with:
```python
    if not candidates:
        return []
    # One most-recent signal in each direction is enough for the analyst.
    output: list[PricePattern] = []
    for name in ("resistance_breakout", "support_breakdown"):
        matching = [item for item in candidates if item[2].pattern == name]
        if not matching:
            continue
        _, ctx, parent = max(matching, key=lambda item: item[0])
        output.append(parent)
        if ctx is not None:
            apply_parent_side_effects(parent)
            signal = build_false_break_signal(df, ctx)
            if signal is not None:
                output.append(signal)
    return output
```

- [ ] **Step 3c: Wire `_double_patterns`.** Void the target on every failed double and emit
  on reversed ones.

After the `target = neckline + depth if kind == "low" else neckline - depth` line, insert:
```python
                if status == "failed":
                    target = None
```

Add `best_ctx: FalseBreakContext | None = None` next to `best`/`best_second_index`
initialization (the `best: PricePattern | None = None` line). Immediately BEFORE the
`if second.index > best_second_index:` block, insert:
```python
                candidate_ctx = None
                if breakout_failed and breakout_index is not None:
                    candidate_ctx = FalseBreakContext(
                        breakout_index=breakout_index,
                        direction="bullish" if kind == "low" else "bearish",
                        high_slope=0.0, high_intercept=neckline,
                        low_slope=0.0, low_intercept=neckline,
                        apex_index=math.inf, buffer=buffer, window_bars=0, parent_pattern=name,
                        target_price=(
                            min(first.price, second.price)
                            if kind == "low"
                            else max(first.price, second.price)
                        ),
                    )
```
and inside the `if second.index > best_second_index:` block add `best_ctx = candidate_ctx`
alongside `best = pattern`.

Replace:
```python
        if best is not None:
            # At most one recent signal of each double-pattern type keeps the
            # tool output compact enough for downstream LLM context.
            patterns.append(best)
```
with:
```python
        if best is not None:
            # At most one recent signal of each double-pattern type keeps the
            # tool output compact enough for downstream LLM context.
            patterns.append(best)
            if best_ctx is not None:
                apply_parent_side_effects(best)
                signal = build_false_break_signal(df, best_ctx)
                if signal is not None:
                    patterns.append(signal)
```

- [ ] **Step 3d: Wire `_rectangle_pattern`.** Change its return type to a list and emit.

Change the signature return annotation `-> PricePattern | None:` to `-> list[PricePattern]:`.
Change every early `return None` in the function body to `return []`.
Replace the final `return PricePattern(` block by first binding it:
```python
    parent = PricePattern(
        ...  # unchanged existing keyword arguments
    )
    results = [parent]
    if breakout_index is not None and status == "failed":
        ctx = FalseBreakContext(
            breakout_index=breakout_index,
            direction="bullish" if breakout_index == up_break else "bearish",
            high_slope=0.0, high_intercept=upper, low_slope=0.0, low_intercept=lower,
            apex_index=math.inf, buffer=buffer, window_bars=0, parent_pattern="rectangle",
            target_price=lower if breakout_index == up_break else upper,
        )
        apply_parent_side_effects(parent)
        signal = build_false_break_signal(df, ctx)
        if signal is not None:
            results.append(signal)
    return results
```

- [ ] **Step 3e: Wire `_triangle_pattern`.** Change its return type to a list and emit on
  reversed triangles.

Change the signature return annotation `-> PricePattern | None:` to `-> list[PricePattern]:`.
Change every early `return None` in the function body to `return []`.
Replace the final `return PricePattern(` block by first binding it:
```python
    parent = PricePattern(
        ...  # unchanged existing keyword arguments
    )
    results = [parent]
    if "breakout_reversed_back_through_triangle" in risk_flags and breakout_index is not None:
        ctx = FalseBreakContext(
            breakout_index=breakout_index, direction=direction,
            high_slope=high_slope, high_intercept=high_intercept,
            low_slope=low_slope, low_intercept=low_intercept,
            apex_index=apex_index, buffer=buffer,
            window_bars=post_apex_window_bars(start_index, apex_index),
            parent_pattern=name, parent_risk_flags=tuple(risk_flags),
            target_price=lower_level if direction == "bullish" else upper_level,
        )
        apply_parent_side_effects(parent)
        signal = build_false_break_signal(df, ctx)
        if signal is not None:
            results.append(signal)
    return results
```

- [ ] **Step 3f: Update the two call sites** in `analyze_chart_patterns_from_data`.

Replace:
```python
    rectangle = _rectangle_pattern(df, pivots, atr_value)
    if rectangle is not None:
        patterns.append(rectangle)
    triangle = _triangle_pattern(df, pivots, atr_value)
    if triangle is not None:
        patterns.append(triangle)
```
with:
```python
    patterns.extend(_rectangle_pattern(df, pivots, atr_value))
    patterns.extend(_triangle_pattern(df, pivots, atr_value))
```

- [ ] **Step 4: Run the new pipeline test**

Run: `pytest tests/test_false_break_pipeline.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the full chart-pattern + triangle suite to confirm no regressions**

Run: `pytest tests/test_chart_patterns.py tests/test_triangle_breakout.py tests/test_triangle_breakout_window.py tests/test_triangle_post_apex.py -q`
Expected: all PASS. The existing `test_late_triangle_breakout_that_reenters_is_failed`
still passes — it uses `in`-style `risk_flags` assertions on the parent and the new
`structure_may_be_expanding` flag does not disturb them; `classify_triangle_breakout`
(and its tests) are untouched. If a *failed double/rectangle* target assertion breaks,
that is a genuinely intended change (targets on failed reversed parents are now voided) —
update that single assertion; do not weaken the wiring.

- [ ] **Step 6: Full sweep + ruff, then STOP for review** (do not commit)

Run: `pytest -q` and `ruff check .` (cross-cutting change to a shared dataflow module
warrants the full suite per CLAUDE.md).
Expected: all PASS, `All checks passed!`. Report line counts:
`wc -l tradingagents/dataflows/false_break_*.py tradingagents/dataflows/chart_patterns.py`.

---

## Self-Review

**Spec coverage:** ✔ four sites in one generic pass (Task 5); ✔ first-class PricePattern
entries, no schema change (Task 4); ✔ pending shorts as `forming` (Task 3, forming test);
✔ Architecture A — generic machine + `find_reversal_index` reuse (Task 3); ✔ Stage-1
window cap `REENTRY_WINDOW_BARS` (Task 3, window-expiry test); ✔ Stage-2 short triggers
(pullback-low + failed-retest), CONFIRM window, late/post-apex aggressive immediate
confirm (Tasks 2–3); ✔ Stage-2 long aggressive-at-re-entry, no-new-low guard, standard
upgrade, no forming state (Tasks 2–3); ✔ volume ±0.05 & always narrated (Tasks 3–4); ✔
output levels/target/invalidation/confidence table/evidence (Task 4); ✔ parent side
effects `structure_may_be_expanding` + voided target incl. the double-bottom path that
still carried one (Task 5, 3c); ✔ constants named exactly (Task 1).

**Placeholder scan:** no TBD/"handle edge cases"/"similar to Task N"; every code step is
complete and copy-pasteable.

**Type consistency:** `FalseBreakContext`/`FalseBreakSignal` field names are identical
across Tasks 1, 3, 4. `detect_false_break`, `build_short`, `build_long`,
`build_false_break_signal`, `apply_parent_side_effects` names match every call site.
`_round`/`_date` are local to `false_break_patterns` (no chart_patterns import at module
top — cycle avoided via the lazy `PricePattern` import).

**Non-goals honored:** no entry taxonomy (SP3), no larger-structure re-detection, no
threshold calibration (SP4). No upstream files touched; `triangle_post_apex` consumed only.
