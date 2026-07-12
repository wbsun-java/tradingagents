# Entry-State Taxonomy (SP3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Note for this repo specifically:** execute each task through the `codex-delegate` skill. Codex prompts must open with the "YOU are the implementer" paragraph (feedback_codex_nested_delegation memory).

**Goal:** Add a deterministic trading layer that attaches an `entry_assessment` (one of
seven states) to every chart PricePattern based on where current price sits in the
structure, and instruct the Market Analyst to treat that state as authoritative.

**Architecture:** A centralized post-pass in `analyze_chart_patterns_from_data` calls
`assess_entry(df, pattern, atr, current_close)` for each pattern. `assess_entry`
(entry_assessment.py) uses a per-type level extractor + position predicates
(entry_rules.py) and dataclass/constants (entry_types.py) to pick a state. The pattern
layer (SP1/SP2) is unchanged; SP2 signals pass through with their own name as the state.

**Tech Stack:** Python 3.14, pandas, pytest (`@pytest.mark.unit`), ruff.

**Design source of truth:** `docs/superpowers/specs/2026-07-12-entry-taxonomy-design.md`.

## Global Constraints

- **New files ≤150 lines each**, verified budgets: `entry_types.py` ~45,
  `entry_rules.py` ~55, `entry_assessment.py` ~80; tests ~30 / ~95 / ~110 / ~70.
  `chart_patterns.py` (existing, grandfathered, 783 lines) gains ~8 lines; the one
  prompt test is appended to the existing `tests/test_market_analyst_prefetch.py`.
- **Constants, exact names/values** (interim SP4 knobs — say so in `entry_types.py`):
  `ENTRY_PROXIMITY_ATR = 0.5`, `RETEST_WINDOW_BARS = 15`,
  `PREDICTIVE_UNDERSHOOT_ATR = 0.25`. Buffer reuses the existing `0.2 · ATR` (no new
  constant). Low-volume test reuses a trailing 20-bar volume baseline.
- **State names, verbatim:** `predictive_bottom`, `breakout_entry`,
  `breakout_retest_entry`, `observe`, `avoid`, `false_breakout_short`,
  `false_breakdown_long`.
- **No import cycle:** `entry_*` modules must NOT import `chart_patterns`. They duck-type
  the pattern object (`.pattern`, `.levels`, `.status`, `.direction`,
  `.invalidation_price`). `chart_patterns` imports `entry_assessment` + the
  `EntryAssessment` type at module top; that chain never re-enters `chart_patterns`.
- **Long-biased taxonomy:** a pattern is bearish-eligible (→ `avoid`) when it is in
  `BEARISH_TYPES` (`double_top`, `descending_triangle`, `support_breakdown`) OR its
  `direction == "bearish"`. Long-eligible types: `double_bottom`, `ascending_triangle`,
  `symmetrical_triangle`, `rectangle`, `resistance_breakout`. Anything else → `observe`
  (never a default buy).
- **Upstream edit is pre-approved for THIS feature only** (project_sp3_market_analyst
  _approval): only `market_analyst.py`'s existing chart-pattern paragraph, nothing else.
- All tests `@pytest.mark.unit`, synthetic frames only, no network/LLM calls.
- Do NOT `git add`/`git commit` — commits need separate explicit user approval.

**Validated geometry (2026-07-12, against the live pipeline):** the confirmed
`double_bottom` fixture `_interp([(0,108),(12,95),(24,108),(38,96),(50,111),(65,114)])`
(pivot_span 2, breakout volume bar 48) yields `neckline=108.6`, twin low `94.4`,
`invalidation 94.16`, latest close `114.0`, `atr 1.2` → `PROX=0.6`; close is `5.4`
above the neckline with no trailing dip to `[108.0,109.2]`, so its entry state is
`observe` (extended, no retest). Task 4's pipeline test asserts exactly this.

---

### Task 1: EntryAssessment dataclass + constants

**Files:**
- Create: `tradingagents/dataflows/entry_types.py`
- Test: `tests/test_entry_types.py`

**Interfaces:**
- Produces: state-name constants (`PREDICTIVE_BOTTOM`, `BREAKOUT_ENTRY`,
  `BREAKOUT_RETEST_ENTRY`, `OBSERVE`, `AVOID`, `FALSE_BREAKOUT_SHORT`,
  `FALSE_BREAKDOWN_LONG`); tuning constants (`ENTRY_PROXIMITY_ATR`, `RETEST_WINDOW_BARS`,
  `PREDICTIVE_UNDERSHOOT_ATR`); `LONG_ELIGIBLE`, `BEARISH_TYPES` frozensets;
  `EntryAssessment` dataclass with fields `state:str, direction:str,
  entry_zone_low:float|None, entry_zone_high:float|None, trigger_price:float|None,
  invalidation_price:float|None, confirmation:str, volume_role:str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_entry_types.py
"""Constants and dataclass for the entry-state trading layer (SP3)."""

from __future__ import annotations

import pytest

from tradingagents.dataflows import entry_types as t


@pytest.mark.unit
def test_state_names_and_tuning_constants():
    assert t.PREDICTIVE_BOTTOM == "predictive_bottom"
    assert t.BREAKOUT_RETEST_ENTRY == "breakout_retest_entry"
    assert t.FALSE_BREAKOUT_SHORT == "false_breakout_short"
    assert (t.ENTRY_PROXIMITY_ATR, t.RETEST_WINDOW_BARS, t.PREDICTIVE_UNDERSHOOT_ATR) == (
        0.5, 15, 0.25,
    )


@pytest.mark.unit
def test_eligibility_sets():
    assert "double_bottom" in t.LONG_ELIGIBLE
    assert "resistance_breakout" in t.LONG_ELIGIBLE
    assert t.BEARISH_TYPES == frozenset(
        {"double_top", "descending_triangle", "support_breakdown"}
    )


@pytest.mark.unit
def test_entry_assessment_holds_all_fields():
    a = t.EntryAssessment(
        state="observe", direction="none", entry_zone_low=None, entry_zone_high=None,
        trigger_price=None, invalidation_price=None, confirmation="x", volume_role="not_applicable",
    )
    assert a.state == "observe" and a.direction == "none"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest -q tests/test_entry_types.py`
Expected: FAIL with `ModuleNotFoundError: ... entry_types`.

- [ ] **Step 3: Write the module**

```python
# tradingagents/dataflows/entry_types.py
"""EntryAssessment dataclass, state names, and tuning constants for the entry layer (SP3).

Every numeric constant is an interim placeholder pending SP4 backtest calibration
(docs/superpowers/specs/2026-07-12-entry-taxonomy-design.md).
"""

from __future__ import annotations

from dataclasses import dataclass

PREDICTIVE_BOTTOM = "predictive_bottom"
BREAKOUT_ENTRY = "breakout_entry"
BREAKOUT_RETEST_ENTRY = "breakout_retest_entry"
OBSERVE = "observe"
AVOID = "avoid"
FALSE_BREAKOUT_SHORT = "false_breakout_short"
FALSE_BREAKDOWN_LONG = "false_breakdown_long"

ENTRY_PROXIMITY_ATR = 0.5
RETEST_WINDOW_BARS = 15
PREDICTIVE_UNDERSHOOT_ATR = 0.25

LONG_ELIGIBLE = frozenset(
    {
        "double_bottom",
        "ascending_triangle",
        "symmetrical_triangle",
        "rectangle",
        "resistance_breakout",
    }
)
BEARISH_TYPES = frozenset({"double_top", "descending_triangle", "support_breakdown"})


@dataclass
class EntryAssessment:
    state: str
    direction: str  # "long" | "short" | "none"
    entry_zone_low: float | None
    entry_zone_high: float | None
    trigger_price: float | None
    invalidation_price: float | None
    confirmation: str
    volume_role: str
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest -q tests/test_entry_types.py`
Expected: PASS (3 passed).

- [ ] **Step 5: Ruff, then STOP for review** (do not commit)

Run: `ruff check tradingagents/dataflows/entry_types.py tests/test_entry_types.py`
Expected: `All checks passed!`

---

### Task 2: Level extractor + position predicates

**Files:**
- Create: `tradingagents/dataflows/entry_rules.py`
- Test: `tests/test_entry_rules.py`

**Interfaces:**
- Consumes: nothing from `entry_types` (kept dependency-light; only `pandas`).
- Produces: `extract_levels(pattern, atr) -> dict[str,float] | None` returning
  `{"bottom_boundary", "breakout_level", "failure_level"}` for long-eligible types else
  `None`; `near(value, target, tolerance) -> bool`;
  `retest_hold(df, breakout_level, prox, window) -> bool`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_entry_rules.py
"""Level extraction and position predicates for the entry layer (SP3)."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from tradingagents.dataflows import entry_rules as r


def _pat(pattern, levels, invalidation=None):
    return SimpleNamespace(pattern=pattern, levels=levels, invalidation_price=invalidation)


def _df(closes, lows=None, vols=None):
    lows = lows if lows is not None else [c - 0.5 for c in closes]
    vols = vols if vols is not None else [1_000_000.0] * len(closes)
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2026-01-02", periods=len(closes)),
            "Open": closes, "High": [c + 0.5 for c in closes], "Low": lows,
            "Close": closes, "Volume": vols,
        }
    )


@pytest.mark.unit
def test_extract_levels_double_bottom_uses_twin_low_and_neckline():
    p = _pat("double_bottom", {"first_extreme": 94.4, "second_extreme": 95.4, "neckline": 108.6},
             invalidation=94.16)
    assert r.extract_levels(p, 1.2) == {
        "bottom_boundary": 94.4, "breakout_level": 108.6, "failure_level": 94.16,
    }


@pytest.mark.unit
def test_extract_levels_triangle_failure_is_lower_trendline_minus_buffer():
    p = _pat("ascending_triangle", {"lower_trendline": 95.0, "upper_trendline": 100.0})
    levels = r.extract_levels(p, 1.0)  # buffer = 0.2
    assert levels["bottom_boundary"] == 95.0
    assert levels["breakout_level"] == 100.0
    assert levels["failure_level"] == pytest.approx(94.8)


@pytest.mark.unit
def test_extract_levels_returns_none_for_unknown_pattern():
    assert r.extract_levels(_pat("head_shoulders", {}), 1.0) is None


@pytest.mark.unit
def test_near_within_tolerance():
    assert r.near(96.4, 96.0, 0.5) is True
    assert r.near(97.0, 96.0, 0.5) is False


@pytest.mark.unit
def test_retest_hold_true_on_low_volume_dip_to_boundary():
    closes = [100.0] * 18 + [102.0, 100.2, 101.0]
    lows = [99.5] * 18 + [101.5, 99.8, 100.5]
    vols = [1_000_000.0] * 18 + [1_000_000.0, 300_000.0, 1_000_000.0]
    assert r.retest_hold(_df(closes, lows, vols), 100.0, 0.5, 15) is True


@pytest.mark.unit
def test_retest_hold_false_when_price_below_boundary():
    closes = [100.0] * 18 + [102.0, 100.2, 99.0]
    assert r.retest_hold(_df(closes), 100.0, 0.5, 15) is False


@pytest.mark.unit
def test_retest_hold_false_when_no_low_volume_dip():
    closes = [100.0] * 18 + [102.0, 102.5, 103.0]
    lows = [101.5] * 21
    assert r.retest_hold(_df(closes, lows), 100.0, 0.5, 15) is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest -q tests/test_entry_rules.py`
Expected: FAIL with `ModuleNotFoundError: ... entry_rules`.

- [ ] **Step 3: Write the module**

```python
# tradingagents/dataflows/entry_rules.py
"""Level extraction + position predicates for the entry layer (SP3).

Duck-types the pattern object (no chart_patterns import → import-cycle free).
"""

from __future__ import annotations

import pandas as pd


def extract_levels(pattern, atr: float) -> dict[str, float] | None:
    """Return {bottom_boundary, breakout_level, failure_level} for a long-eligible pattern."""
    name = pattern.pattern
    lv = pattern.levels
    buffer = 0.2 * atr
    if name == "double_bottom":
        bottom = min(lv["first_extreme"], lv["second_extreme"])
        return {
            "bottom_boundary": bottom,
            "breakout_level": lv["neckline"],
            "failure_level": pattern.invalidation_price,
        }
    if name in ("ascending_triangle", "symmetrical_triangle"):
        bottom = lv["lower_trendline"]
        return {
            "bottom_boundary": bottom,
            "breakout_level": lv["upper_trendline"],
            "failure_level": bottom - buffer,
        }
    if name == "rectangle":
        bottom = lv["support"]
        return {
            "bottom_boundary": bottom,
            "breakout_level": lv["resistance"],
            "failure_level": bottom - buffer,
        }
    if name == "resistance_breakout":
        level = lv["broken_level"]
        return {
            "bottom_boundary": level,
            "breakout_level": level,
            "failure_level": pattern.invalidation_price,
        }
    return None


def near(value: float, target: float, tolerance: float) -> bool:
    return abs(value - target) <= tolerance


def retest_hold(df: pd.DataFrame, breakout_level: float, prox: float, window: int) -> bool:
    """A trailing bar dipped to the breakout level on below-average volume, price still above."""
    if float(df["Close"].iloc[-1]) < breakout_level:
        return False
    baseline = pd.to_numeric(df["Volume"].tail(20), errors="coerce").mean()
    start = max(1, len(df) - window)
    for index in range(start, len(df)):
        low = float(df.at[index, "Low"])
        volume = float(df.at[index, "Volume"])
        if breakout_level - prox <= low <= breakout_level + prox and (not baseline or volume < baseline):
            return True
    return False
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest -q tests/test_entry_rules.py`
Expected: PASS (7 passed).

- [ ] **Step 5: Ruff, then STOP for review** (do not commit)

Run: `ruff check tradingagents/dataflows/entry_rules.py tests/test_entry_rules.py`
Expected: `All checks passed!`

---

### Task 3: The assess_entry orchestrator

**Files:**
- Create: `tradingagents/dataflows/entry_assessment.py`
- Test: `tests/test_entry_assessment.py`

**Interfaces:**
- Consumes: `extract_levels`, `near`, `retest_hold` from `entry_rules`; all constants +
  `EntryAssessment` from `entry_types`.
- Produces: `assess_entry(df, pattern, atr, current_close) -> EntryAssessment`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_entry_assessment.py
"""State classification for the entry layer (SP3)."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from tradingagents.dataflows.entry_assessment import assess_entry

ATR = 1.0  # PROX = 0.5


def _df(closes, lows=None, vols=None):
    lows = lows if lows is not None else [c - 0.5 for c in closes]
    vols = vols if vols is not None else [1_000_000.0] * len(closes)
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2026-01-02", periods=len(closes)),
            "Open": closes, "High": [c + 0.5 for c in closes], "Low": lows,
            "Close": closes, "Volume": vols,
        }
    )


def _pat(pattern, status, direction, levels, invalidation=None):
    return SimpleNamespace(
        pattern=pattern, status=status, direction=direction, levels=levels,
        invalidation_price=invalidation, volume_confirmed=None,
    )


def _rect(status, direction="bullish"):
    return _pat("rectangle", status, direction, {"support": 96.0, "resistance": 100.0})


@pytest.mark.unit
def test_confirmed_fresh_break_is_breakout_entry():
    a = assess_entry(_df([100.0] * 21), _rect("confirmed"), ATR, 100.4)
    assert (a.state, a.direction, a.trigger_price) == ("breakout_entry", "long", 100.0)
    assert a.volume_role == "expansion_preferred"


@pytest.mark.unit
def test_confirmed_extended_is_observe():
    a = assess_entry(_df([100.0] * 21), _rect("confirmed"), ATR, 103.0)
    assert a.state == "observe" and a.direction == "none"


@pytest.mark.unit
def test_confirmed_low_volume_retest_is_retest_entry():
    closes = [100.0] * 18 + [102.0, 100.2, 101.0]
    lows = [99.5] * 18 + [101.5, 99.8, 100.5]
    vols = [1_000_000.0] * 18 + [1_000_000.0, 300_000.0, 1_000_000.0]
    a = assess_entry(_df(closes, lows, vols), _rect("confirmed"), ATR, 101.0)
    assert a.state == "breakout_retest_entry"
    assert a.volume_role == "low_volume_preferred"


@pytest.mark.unit
def test_forming_near_bottom_is_predictive_bottom():
    a = assess_entry(_df([96.4] * 21), _rect("forming", "neutral"), ATR, 96.4)
    assert (a.state, a.trigger_price) == ("predictive_bottom", 96.0)
    assert a.invalidation_price == pytest.approx(95.8)
    assert a.entry_zone_low == pytest.approx(95.75)


@pytest.mark.unit
def test_forming_mid_structure_is_observe():
    a = assess_entry(_df([100.0] * 21), _rect("forming", "neutral"), ATR, 100.0)
    assert a.state == "observe"


@pytest.mark.unit
def test_failed_long_pattern_is_avoid():
    p = _pat("ascending_triangle", "failed", "bullish",
             {"lower_trendline": 95.0, "upper_trendline": 100.0}, invalidation=94.8)
    assert assess_entry(_df([98.0] * 21), p, ATR, 98.0).state == "avoid"


@pytest.mark.unit
def test_bearish_pattern_is_avoid():
    p = _pat("double_top", "confirmed", "bearish",
             {"first_extreme": 110.0, "second_extreme": 111.0, "neckline": 100.0})
    a = assess_entry(_df([95.0] * 21), p, ATR, 95.0)
    assert (a.state, a.direction) == ("avoid", "none")


@pytest.mark.unit
def test_unknown_bullish_pattern_falls_back_to_observe():
    p = _pat("head_shoulders", "confirmed", "bullish", {})
    assert assess_entry(_df([100.0] * 21), p, ATR, 100.0).state == "observe"


@pytest.mark.unit
def test_sp2_short_signal_passthrough():
    p = _pat("false_breakout_short", "confirmed", "bearish",
             {"boundary_price": 100.6, "false_break_extreme": 103.6, "reentry_close": 99.5,
              "trigger_price": 98.9}, invalidation=103.9)
    a = assess_entry(_df([99.0] * 21), p, ATR, 99.0)
    assert (a.state, a.direction, a.trigger_price, a.invalidation_price) == (
        "false_breakout_short", "short", 98.9, 103.9,
    )
    assert (a.entry_zone_low, a.entry_zone_high) == (99.5, 100.6)


@pytest.mark.unit
def test_sp2_long_signal_passthrough():
    p = _pat("false_breakdown_long", "confirmed", "bullish",
             {"boundary_price": 100.0, "false_break_extreme": 97.8, "reentry_close": 100.1,
              "trigger_price": 101.6}, invalidation=97.5)
    a = assess_entry(_df([101.0] * 21), p, ATR, 101.0)
    assert (a.state, a.direction) == ("false_breakdown_long", "long")
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest -q tests/test_entry_assessment.py`
Expected: FAIL with `ModuleNotFoundError: ... entry_assessment`.

- [ ] **Step 3: Write the module**

```python
# tradingagents/dataflows/entry_assessment.py
"""Entry-state trading layer (SP3): classify one pattern into an EntryAssessment.

Runs as a post-pass over already-detected patterns. Deterministic; the LLM only explains
the resulting state (see market_analyst.py). Import-cycle free (duck-types the pattern).
"""

from __future__ import annotations

import math

import pandas as pd

from tradingagents.dataflows.entry_rules import extract_levels, near, retest_hold
from tradingagents.dataflows.entry_types import (
    AVOID,
    BEARISH_TYPES,
    BREAKOUT_ENTRY,
    BREAKOUT_RETEST_ENTRY,
    ENTRY_PROXIMITY_ATR,
    FALSE_BREAKDOWN_LONG,
    FALSE_BREAKOUT_SHORT,
    OBSERVE,
    PREDICTIVE_BOTTOM,
    PREDICTIVE_UNDERSHOOT_ATR,
    RETEST_WINDOW_BARS,
    EntryAssessment,
)


def _round(value):
    return None if value is None or not math.isfinite(value) else round(float(value), 4)


def _make(state, direction, low, high, trigger, invalidation, confirmation, volume_role):
    return EntryAssessment(
        state=state, direction=direction, entry_zone_low=_round(low), entry_zone_high=_round(high),
        trigger_price=_round(trigger), invalidation_price=_round(invalidation),
        confirmation=confirmation, volume_role=volume_role,
    )


def _from_signal(pattern) -> EntryAssessment:
    lv = pattern.levels
    short = pattern.pattern == FALSE_BREAKOUT_SHORT
    bounds = sorted(x for x in (lv.get("boundary_price"), lv.get("reentry_close")) if x is not None)
    return _make(
        pattern.pattern, "short" if short else "long",
        bounds[0] if bounds else None, bounds[-1] if bounds else None,
        lv.get("trigger_price"), pattern.invalidation_price,
        f"SP2 {pattern.pattern} reversal signal at the failed boundary.",
        "supporting_not_required",
    )


def assess_entry(df: pd.DataFrame, pattern, atr: float, current_close: float) -> EntryAssessment:
    """Classify one PricePattern into an entry state based on price position."""
    name = pattern.pattern
    if name in (FALSE_BREAKOUT_SHORT, FALSE_BREAKDOWN_LONG):
        return _from_signal(pattern)
    if name in BEARISH_TYPES or pattern.direction == "bearish":
        return _make(AVOID, "none", None, None, None, None, f"{name} offers no long entry.", "not_applicable")
    levels = extract_levels(pattern, atr)
    if levels is None:
        return _make(OBSERVE, "none", None, None, None, None, "No long-eligible structure.", "not_applicable")
    prox = ENTRY_PROXIMITY_ATR * atr
    if pattern.status == "failed":
        return _make(AVOID, "none", None, None, None, None,
                     f"{name} breakout failed; former boundary no longer reliable.", "not_applicable")
    if pattern.status == "confirmed":
        level = levels["breakout_level"]
        if retest_hold(df, level, prox, RETEST_WINDOW_BARS):
            return _make(BREAKOUT_RETEST_ENTRY, "long", level, level + prox, level,
                         levels["failure_level"], "Low-volume retest held above the former resistance.",
                         "low_volume_preferred")
        if current_close <= level + prox:
            return _make(BREAKOUT_ENTRY, "long", level, level + prox, level, levels["failure_level"],
                         "Price sits at a fresh valid breakout of the boundary.", "expansion_preferred")
        return _make(OBSERVE, "none", None, None, None, None,
                     f"{name} confirmed but price is extended above the breakout with no retest.",
                     "not_applicable")
    if pattern.status == "forming":
        bottom = levels["bottom_boundary"]
        failure = levels["failure_level"]
        if near(current_close, bottom, prox) and (failure is None or current_close > failure):
            return _make(PREDICTIVE_BOTTOM, "long", bottom - PREDICTIVE_UNDERSHOOT_ATR * atr,
                         bottom + prox, bottom, failure,
                         "Price sits at the confirmed bottom boundary of a forming structure.",
                         "supporting_not_required")
        return _make(OBSERVE, "none", None, None, None, None,
                     f"{name} forming; price is mid-structure with no positional edge.", "not_applicable")
    return _make(OBSERVE, "none", None, None, None, None, "No actionable position.", "not_applicable")
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest -q tests/test_entry_assessment.py`
Expected: PASS (10 passed).

- [ ] **Step 5: Budget + ruff, then STOP for review** (do not commit)

Run: `wc -l tradingagents/dataflows/entry_assessment.py` (expect ~80, ≤150)
Run: `ruff check tradingagents/dataflows/entry_assessment.py tests/test_entry_assessment.py`
Expected: `All checks passed!`

---

### Task 4: Wire the field + post-pass into `chart_patterns.py`

**Files:**
- Modify: `tradingagents/dataflows/chart_patterns.py` (imports; `PricePattern` field;
  post-pass loop in `analyze_chart_patterns_from_data`)
- Test: `tests/test_entry_pipeline.py`

**Interfaces:**
- Consumes: `assess_entry`, `EntryAssessment` from the SP3 modules.
- Produces: every pattern dict in `analyze_chart_patterns_from_data(...)["patterns"]` now
  carries a non-null nested `entry_assessment` object with a `state`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_entry_pipeline.py
"""End-to-end entry_assessment wiring through analyze_chart_patterns_from_data (SP3)."""

from __future__ import annotations

import pandas as pd
import pytest

import tradingagents.dataflows.chart_patterns as patterns


def _interp(anchors):
    values = []
    for (s, sv), (e, ev) in zip(anchors, anchors[1:]):
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


def _result():
    closes = _interp([(0, 108), (12, 95), (24, 108), (38, 96), (50, 111), (65, 114)])
    data = _ohlcv(closes, bvi=48)
    return patterns.analyze_chart_patterns_from_data(
        data, data["Date"].iloc[-1].strftime("%Y-%m-%d"), pivot_span=2
    )


@pytest.mark.unit
def test_extended_confirmed_double_bottom_is_observe():
    db = next(p for p in _result()["patterns"] if p["pattern"] == "double_bottom")
    assert db["entry_assessment"]["state"] == "observe"
    assert db["entry_assessment"]["direction"] == "none"


@pytest.mark.unit
def test_every_pattern_carries_an_entry_assessment():
    result = _result()
    assert result["patterns"]
    for p in result["patterns"]:
        assert p["entry_assessment"] is not None
        assert p["entry_assessment"]["state"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest -q tests/test_entry_pipeline.py`
Expected: FAIL — `entry_assessment` key missing / is `None`.

- [ ] **Step 3a: Add imports** after the existing
  `from tradingagents.dataflows.false_break_types import FalseBreakContext` line:

```python
from tradingagents.dataflows.entry_assessment import assess_entry
from tradingagents.dataflows.entry_types import EntryAssessment
```

- [ ] **Step 3b: Add the field to `PricePattern`.** After the existing last field
  `risk_flags: list[str] = field(default_factory=list)`, add:

```python
    entry_assessment: EntryAssessment | None = None
```

- [ ] **Step 3c: Add the post-pass** in `analyze_chart_patterns_from_data`, immediately
  before the `# Keep current/recent setups first` comment and its `patterns.sort(...)`:

```python
    for pattern in patterns:
        pattern.entry_assessment = assess_entry(df, pattern, atr_value, current)
```

- [ ] **Step 4: Run the pipeline test**

Run: `pytest -q tests/test_entry_pipeline.py`
Expected: PASS (2 passed).

- [ ] **Step 5: Regression — chart + false-break suites**

Run: `pytest -q tests/test_chart_patterns.py tests/test_false_break_pipeline.py tests/test_false_break_patterns.py`
Expected: all PASS. `entry_assessment` is additive (default `None`, filled by the
post-pass); existing field-access and `_find` assertions are unaffected. If any test does
a whole-dict equality on a pattern and now breaks on the new key, add
`entry_assessment` to that expected dict — do not remove the field.

- [ ] **Step 6: Ruff, then STOP for review** (do not commit)

Run: `ruff check tradingagents/dataflows/chart_patterns.py tests/test_entry_pipeline.py`
Expected: `All checks passed!`

---

### Task 5: Market Analyst prompt wiring (upstream, approved)

**Files:**
- Modify: `tradingagents/agents/analysts/market_analyst.py` (extend the existing
  chart-pattern paragraph only)
- Test: `tests/test_market_analyst_prefetch.py` (append one test, reusing the file's
  existing `_fake_llm` / `_make_state` / `_system_content` helpers)

**Interfaces:**
- Consumes: nothing new.
- Produces: the analyst system prompt now instructs the LLM to obey
  `entry_assessment.state`.

- [ ] **Step 1: Write the failing test** — append to `tests/test_market_analyst_prefetch.py`:

```python
@pytest.mark.unit
def test_entry_assessment_guidance_reaches_the_prompt(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.agents.analysts.market_analyst.analyze_wyckoff_structure",
        lambda *_args: '{"phase_bias":"neutral"}',
    )
    monkeypatch.setattr(
        "tradingagents.agents.analysts.market_analyst.analyze_oneil_setup",
        lambda *_args: '{"primary_pattern":null,"setup_bias":"neutral","other_detections":[]}',
    )

    create_market_analyst(_fake_llm())(_make_state())

    content = _system_content()
    assert "entry_assessment.state" in content
    assert "never upgrade an `observe`" in content
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest -q tests/test_market_analyst_prefetch.py::test_entry_assessment_guidance_reaches_the_prompt`
Expected: FAIL (`assert "entry_assessment.state" in content`).

- [ ] **Step 3: Extend the chart-pattern paragraph.** In
  `tradingagents/agents/analysts/market_analyst.py`, find the paragraph beginning
  `Also call get_chart_patterns for the ticker` and ending
  `...substitutes for geometric confirmation.` Append this sentence to the SAME paragraph
  string (a space then the new text, before the closing newline/quote):

```
 Each pattern also carries an `entry_assessment` with a deterministic `state` (one of `predictive_bottom`, `breakout_entry`, `breakout_retest_entry`, `observe`, `avoid`, `false_breakout_short`, `false_breakdown_long`) plus `direction`, entry zone, `trigger_price`, `invalidation_price`, and `volume_role`. Treat `entry_assessment.state` as the authoritative trade-layer verdict and only explain it: never upgrade an `observe` or `avoid` into a buy. `observe` means no positional edge; `avoid` means no long opportunity (a failed structure or a bearish direction); `false_breakout_short` and `false_breakdown_long` are contrarian reversal signals, not continuation entries.
```

- [ ] **Step 4: Run the prompt test**

Run: `pytest -q tests/test_market_analyst_prefetch.py::test_entry_assessment_guidance_reaches_the_prompt`
Expected: PASS.

- [ ] **Step 5: Full local suite + ruff, then STOP for review** (do not commit)

Run: `pytest -q -m 'not integration'` and `ruff check .` (cross-cutting: shared dataflow
output shape + an upstream prompt). Expected: all PASS (the one live-yfinance
`@pytest.mark.integration` test is excluded), `All checks passed!`. Report:
`wc -l tradingagents/dataflows/entry_*.py`.

---

## Self-Review

**Spec coverage:** ✔ two-layer separation + centralized post-pass (Task 4); ✔ per-type
level extractor (Task 2); ✔ full decision tree incl. eligibility keyed off direction,
failed→avoid, confirmed retest/fresh/extended, forming predictive/observe (Task 3); ✔ SP2
signal pass-through (Task 3, two tests); ✔ `entry_assessment` nested field on every
PricePattern (Task 4); ✔ EntryAssessment fields incl. zones/trigger/invalidation/
confirmation/volume_role (Tasks 1,3); ✔ constants named as SP4 knobs (Task 1); ✔ prompt
wiring, LLM may only explain the state (Task 5); ✔ non-goals untouched (no emerging stage,
no short trend states, no calibration).

**Placeholder scan:** no TBD/"handle edge cases"/"similar to Task N"; every code step is
complete and copy-pasteable.

**Conscious deviation from the spec:** the spec calls `confirmation` a "dated/priced
sentence." This plan emits a plain explanatory sentence and lets the structured fields
(`trigger_price`, `entry_zone_low/high`, `invalidation_price`) carry the numbers — a DRY
choice that avoids duplicating prices into prose the LLM already receives as data. Tests
assert `state`/`direction`/`trigger_price`/`volume_role`, not the confirmation wording, so
this stays flexible for SP4.

**Type consistency:** `EntryAssessment` field names identical across Tasks 1/3;
`assess_entry`, `extract_levels`, `near`, `retest_hold` signatures match their call sites;
state-name constants used consistently; `entry_assessment` field name matches between the
dataclass (Task 4), the post-pass, and every test. No `chart_patterns` import inside the
`entry_*` modules (cycle avoided; they duck-type the pattern object).
