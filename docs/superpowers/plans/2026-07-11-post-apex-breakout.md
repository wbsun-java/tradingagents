# Post-Apex Triangle Breakout (SP1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Note for this repo specifically:** execute each task through the `codex-delegate` skill. Codex prompts must open with the "YOU are the implementer" paragraph (feedback_codex_nested_delegation memory).

**Goal:** Report triangle breakouts that print after the theoretical apex as `confirmed`
with a `post_apex_breakout` risk flag inside a finite window, anchor their prices to the
apex value, and make late/post-apex breakouts easier to fail via a half-buffer reversal
check — per the approved SP1 spec.

**Architecture:** New module `tradingagents/dataflows/triangle_post_apex.py` owns the
post-apex regime (window sizing, apex-frozen line helpers, post-apex breakout search,
asymmetric reversal search, timing assessment). `triangle_breakout.py` becomes a thin
orchestrator that delegates to it; `chart_patterns.py` gains one branch that anchors the
measured-move target at the apex when the flag is present.

**Tech Stack:** Python 3.14, pandas, pytest (`@pytest.mark.unit`), ruff.

**Design source of truth:** `docs/superpowers/specs/2026-07-11-post-apex-breakout-design.md`.
One planned deviation from the spec's file table: the new tests are split across TWO new
test files (`test_triangle_post_apex.py` for pure functions,
`test_triangle_breakout_window.py` for classification behavior) because
`tests/test_triangle_breakout.py` is at 129 lines and a single new file would blow the
150-line cap.

## Global Constraints

- New files ≤150 lines each (verified budgets: module ~135, pure-function tests ~135,
  classification tests ~110). `triangle_breakout.py` is an existing file: after rewiring
  it must stay ≤150 lines (`wc -l`); if slightly over, compress its module docstring.
- Constants, exact values and names: `POST_APEX_WINDOW_FRACTION = 0.15`,
  `POST_APEX_WINDOW_MIN_BARS = 3`, `POST_APEX_WINDOW_MAX_BARS = 10`,
  `POST_APEX_TIMING_ADJUSTMENT = -0.4`, `REVERSAL_BUFFER_FRACTION = 0.5`. All are interim
  placeholders pending SP4 backtest calibration — say so in the module docstring.
- Existing evidence strings must be preserved verbatim (tests assert substrings):
  "This is in the preferred zone around two-thirds.", "do not penalize it, but
  re-evaluate whether price is evolving into a different structure.", "This is a late
  apex breakout with elevated false-break risk.", "Timing is acceptable but outside the
  preferred two-thirds zone.", "No confirmed trendline breakout yet."
- Pre-apex timing bands and adjustments are behavior-preserving: 0.55–0.75 → +0.1;
  <0.55 → 0.0; 0.75–0.85 → +0.02; >0.85 → −0.2 (≤0.97) / −0.3 (>0.97) + late flag.
- All tests `@pytest.mark.unit`, synthetic frames only, no network, no LLM calls.
- Do NOT `git add`/`git commit` — commits require separate explicit user approval.

**Empirically validated geometry (2026-07-11, prototyped against the live modules — do
not alter):**

- Unit fixture (`test_triangle_breakout.py` shared lines): `upper(x) = 111 − 0.2x`,
  `lower(x) = 88 + 0.2x`, apex index 57.5, apex price 99.5, `start_index = 5`,
  `formation_end = 30`. Window = `round(0.15 × 52.5)` = **8 bars**, so the post-apex
  search covers bars **58–65** and the final searchable bar (window-last index) is 65.
  A breakout at bar 60 has `breakout_progress = 55/52.5 ≈ 1.0476`.
- Pipeline fixture (`test_chart_patterns.py` anchors
  `[(0,100),(5,110),(10,90),(15,108),(20,92),(25,106),(30,94)]` + flat 99.5 run): fitted
  apex index **60.5**, apex price **99.5**, effective start index **5**, measured-move
  `start_gap ≈ 22.2` (recovered from a pre-apex-jump run: target 134.2 − close 112.0).
  Window = `round(0.15 × 55.5)` = **8 bars** → post-apex search bars **61–68**. A jump to
  112.0 at bar 65 is INSIDE the window → under the new code the current
  `test_post_apex_move_expires_triangle_through_full_pipeline` fixture becomes a
  confirmed `post_apex_breakout` (progress ≈ 1.0811, target ≈ 121.7, invalidation 99.5).
  A flat-99.5 run to 70+ bars still expires (`real_end ≥ 68`).

---

### Task 1: `triangle_post_apex.py` module + pure-function tests

**Files:**
- Create: `tradingagents/dataflows/triangle_post_apex.py`
- Test: `tests/test_triangle_post_apex.py`

**Interfaces:**
- Consumes: nothing project-specific (pandas only). No existing file changes.
- Produces (Task 2 imports these exact names):
  `line_value(slope: float, intercept: float, index: float) -> float`;
  `line_before_apex(slope: float, intercept: float, index: float, apex_index: float) -> float`;
  `post_apex_window_bars(start_index: int, apex_index: float) -> int`;
  `find_post_apex_breakout(df, *, formation_end: int, apex_index: float, apex_price: float, buffer: float, window_bars: int) -> tuple[int, str] | None`;
  `find_reversal_index(df, *, high_slope, high_intercept, low_slope, low_intercept, apex_index, breakout_index, breakout_direction, risk_flags, buffer, window_bars) -> int | None`;
  `timing_assessment(breakout_progress: float, *, post_apex: bool) -> tuple[str, float, list[str]]`;
  `post_apex_watch_evidence(window_bars: int) -> str`;
  constants listed in Global Constraints plus
  `ASYMMETRIC_REVERSAL_FLAGS = frozenset({"late_apex_breakout", "post_apex_breakout"})`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_triangle_post_apex.py
"""Unit tests for the post-apex triangle breakout rules (SP1)."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.triangle_post_apex import (
    POST_APEX_TIMING_ADJUSTMENT,
    POST_APEX_WINDOW_MAX_BARS,
    POST_APEX_WINDOW_MIN_BARS,
    find_post_apex_breakout,
    find_reversal_index,
    post_apex_watch_evidence,
    post_apex_window_bars,
    timing_assessment,
)

# Same geometry as test_triangle_breakout.py: upper(x) = 111 - 0.2x,
# lower(x) = 88 + 0.2x; they cross at index 57.5 where both equal 99.5.
_LINES = {
    "high_slope": -0.2, "high_intercept": 111.0, "low_slope": 0.2, "low_intercept": 88.0,
}
_APEX_INDEX = 57.5
_APEX_PRICE = 99.5


def _df(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"Close": closes})


@pytest.mark.unit
def test_window_scales_with_triangle_length_and_clamps():
    assert post_apex_window_bars(5, 57.5) == 8  # round(0.15 * 52.5)
    assert post_apex_window_bars(50, 55.0) == POST_APEX_WINDOW_MIN_BARS
    assert post_apex_window_bars(0, 300.0) == POST_APEX_WINDOW_MAX_BARS


@pytest.mark.unit
def test_post_apex_timing_flags_and_penalizes_beyond_late_apex():
    evidence, adjustment, flags = timing_assessment(1.05, post_apex=True)
    assert flags == ["post_apex_breakout"]
    assert adjustment == POST_APEX_TIMING_ADJUSTMENT
    assert adjustment < -0.3  # strictly worse than the worst late-apex penalty
    assert "past its theoretical apex" in evidence
    assert "false break" in evidence


@pytest.mark.unit
def test_pre_apex_timing_bands_are_preserved():
    assert timing_assessment(0.65, post_apex=False)[1:] == (0.1, [])
    assert timing_assessment(0.40, post_apex=False)[1:] == (0.0, [])
    assert timing_assessment(0.80, post_apex=False)[1:] == (0.02, [])
    assert timing_assessment(0.90, post_apex=False)[1:] == (-0.2, ["late_apex_breakout"])
    assert timing_assessment(0.99, post_apex=False)[1:] == (-0.3, ["late_apex_breakout"])


@pytest.mark.unit
def test_breakout_found_only_inside_the_post_apex_window():
    closes = [100.0] * 70
    closes[60] = 103.0
    hit = find_post_apex_breakout(
        _df(closes), formation_end=30, apex_index=_APEX_INDEX,
        apex_price=_APEX_PRICE, buffer=1.0, window_bars=8,
    )
    assert hit == (60, "bullish")

    late = [100.0] * 72
    late[66] = 103.0  # window covers bars 58-65 only
    assert find_post_apex_breakout(
        _df(late), formation_end=30, apex_index=_APEX_INDEX,
        apex_price=_APEX_PRICE, buffer=1.0, window_bars=8,
    ) is None


@pytest.mark.unit
def test_post_apex_breakdown_is_bearish():
    closes = [100.0] * 70
    closes[59] = 96.0
    hit = find_post_apex_breakout(
        _df(closes), formation_end=30, apex_index=_APEX_INDEX,
        apex_price=_APEX_PRICE, buffer=1.0, window_bars=8,
    )
    assert hit == (59, "bearish")


@pytest.mark.unit
def test_flagged_breakout_reverses_at_half_buffer_inside_reversal_window():
    closes = [100.0] * 70
    closes[60:63] = [103.0] * 3
    closes[63:] = [98.8] * (70 - 63)  # trips 99.0 (half buffer), not 98.5 (full)
    kwargs = dict(_LINES, apex_index=_APEX_INDEX, breakout_index=60,
                  breakout_direction="bullish", buffer=1.0, window_bars=8)
    assert find_reversal_index(_df(closes), risk_flags=["post_apex_breakout"], **kwargs) == 63
    assert find_reversal_index(_df(closes), risk_flags=[], **kwargs) is None


@pytest.mark.unit
def test_half_buffer_stops_applying_after_the_reversal_window():
    closes = [100.0] * 75
    closes[60:70] = [103.0] * 10
    closes[70:] = [98.8] * 5  # bar 70 is past breakout 60 + window 8
    assert find_reversal_index(
        _df(closes), risk_flags=["post_apex_breakout"],
        **dict(_LINES, apex_index=_APEX_INDEX, breakout_index=60,
               breakout_direction="bullish", buffer=1.0, window_bars=8),
    ) is None


@pytest.mark.unit
def test_late_apex_flag_uses_half_buffer_on_the_pre_apex_frozen_boundary():
    closes = [100.0] * 70
    closes[52:55] = [103.0] * 3
    closes[55:] = [99.2] * (70 - 55)  # upper(55)=100.0: trips 99.5, not 99.0
    kwargs = dict(_LINES, apex_index=_APEX_INDEX, breakout_index=52,
                  breakout_direction="bullish", buffer=1.0, window_bars=8)
    assert find_reversal_index(_df(closes), risk_flags=["late_apex_breakout"], **kwargs) == 55
    assert find_reversal_index(_df(closes), risk_flags=[], **kwargs) is None


@pytest.mark.unit
def test_watch_evidence_names_the_window_length():
    text = post_apex_watch_evidence(8)
    assert "8-bar" in text
    assert "apex" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_triangle_post_apex.py -q`
Expected: collection error — `ModuleNotFoundError: No module named
'tradingagents.dataflows.triangle_post_apex'`.

- [ ] **Step 3: Write the module**

```python
# tradingagents/dataflows/triangle_post_apex.py
"""Post-apex triangle breakout rules (SP1).

Once a triangle's trendlines cross at the theoretical apex the pattern no
longer exists geometrically, but a breakout can still print shortly after the
crossing.  This module owns that regime: the finite post-apex search window,
the apex-frozen boundary helpers, the breakout-timing assessment, and the
asymmetric (lower-threshold) reversal detection for late/post-apex breakouts.
Every constant here is an interim placeholder pending SP4 backtest calibration
(docs/superpowers/specs/2026-07-11-post-apex-breakout-design.md).
"""

from __future__ import annotations

import math

import pandas as pd

POST_APEX_WINDOW_FRACTION = 0.15
POST_APEX_WINDOW_MIN_BARS = 3
POST_APEX_WINDOW_MAX_BARS = 10
POST_APEX_TIMING_ADJUSTMENT = -0.4
REVERSAL_BUFFER_FRACTION = 0.5
ASYMMETRIC_REVERSAL_FLAGS = frozenset({"late_apex_breakout", "post_apex_breakout"})


def line_value(slope: float, intercept: float, index: float) -> float:
    return slope * index + intercept


def line_before_apex(slope: float, intercept: float, index: float, apex_index: float) -> float:
    """Evaluate a boundary without extrapolating beyond crossed trendlines."""
    return line_value(slope, intercept, min(index, apex_index))


def post_apex_window_bars(start_index: int, apex_index: float) -> int:
    """Finite bars after the apex in which a breakout may still be recognized."""
    scaled = round(POST_APEX_WINDOW_FRACTION * (apex_index - start_index))
    return int(min(POST_APEX_WINDOW_MAX_BARS, max(POST_APEX_WINDOW_MIN_BARS, scaled)))


def find_post_apex_breakout(
    df: pd.DataFrame,
    *,
    formation_end: int,
    apex_index: float,
    apex_price: float,
    buffer: float,
    window_bars: int,
) -> tuple[int, str] | None:
    """Search the finite post-apex window for a buffered close beyond the apex price."""
    begin = max(formation_end + 1, math.ceil(apex_index))
    end = min(len(df), math.ceil(apex_index) + window_bars)
    for index in range(begin, end):
        close = float(df.at[index, "Close"])
        if close > apex_price + buffer:
            return index, "bullish"
        if close < apex_price - buffer:
            return index, "bearish"
    return None


def find_reversal_index(
    df: pd.DataFrame,
    *,
    high_slope: float,
    high_intercept: float,
    low_slope: float,
    low_intercept: float,
    apex_index: float,
    breakout_index: int,
    breakout_direction: str,
    risk_flags: list[str],
    buffer: float,
    window_bars: int,
) -> int | None:
    """Find the bar where a confirmed breakout reverses back through the boundary.

    Late/post-apex breakouts reverse at half buffer inside the reversal window
    (reversal is their default expectation); the standard full-buffer check
    continues unbounded afterwards.
    """
    asymmetric = bool(ASYMMETRIC_REVERSAL_FLAGS & set(risk_flags))
    for index in range(breakout_index + 1, len(df)):
        upper = line_before_apex(high_slope, high_intercept, index, apex_index)
        lower = line_before_apex(low_slope, low_intercept, index, apex_index)
        close = float(df.at[index, "Close"])
        effective = buffer
        if asymmetric and index <= breakout_index + window_bars:
            effective = buffer * REVERSAL_BUFFER_FRACTION
        if breakout_direction == "bullish" and close < upper - effective:
            return index
        if breakout_direction == "bearish" and close > lower + effective:
            return index
    return None


def timing_assessment(breakout_progress: float, *, post_apex: bool) -> tuple[str, float, list[str]]:
    """Evidence text, confidence adjustment, and risk flags for a breakout's timing."""
    evidence = f"Breakout occurred at {breakout_progress:.1%} of the base-to-apex distance."
    if post_apex:
        evidence += (
            " The triangle is already past its theoretical apex, so this breakout is"
            " more likely a false break, with elevated odds of being pushed back inside"
            " the former triangle within a few sessions."
        )
        return evidence, POST_APEX_TIMING_ADJUSTMENT, ["post_apex_breakout"]
    if 0.55 <= breakout_progress <= 0.75:
        return evidence + " This is in the preferred zone around two-thirds.", 0.1, []
    if breakout_progress < 0.55:
        return (
            evidence + " This is before the preferred zone; do not penalize it, but"
            " re-evaluate whether price is evolving into a different structure.",
            0.0,
            [],
        )
    if breakout_progress > 0.85:
        return (
            evidence + " This is a late apex breakout with elevated false-break risk.",
            -0.2 if breakout_progress <= 0.97 else -0.3,
            ["late_apex_breakout"],
        )
    return (
        evidence + " Timing is acceptable but outside the preferred two-thirds zone.",
        0.02,
        [],
    )


def post_apex_watch_evidence(window_bars: int) -> str:
    return (
        "No confirmed trendline breakout yet; the triangle has passed its theoretical"
        f" apex and only a finite {window_bars}-bar post-apex window is being watched"
        " before the pattern expires."
    )
```

CRITICAL: the `< 0.55` evidence sentence must render exactly as today's string —
"This is before the preferred zone; do not penalize it, but re-evaluate whether price is
evolving into a different structure." (an existing pipeline test asserts the
"do not penalize it" substring).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_triangle_post_apex.py -q`
Expected: 9 passed.

- [ ] **Step 5: Lint and line-count check**

Run: `ruff check tradingagents/dataflows/triangle_post_apex.py tests/test_triangle_post_apex.py && wc -l tradingagents/dataflows/triangle_post_apex.py tests/test_triangle_post_apex.py`
Expected: no ruff errors; both files ≤150 lines.

---

### Task 2: Rewire `triangle_breakout.py` + classification tests

**Files:**
- Modify: `tradingagents/dataflows/triangle_breakout.py` (whole file shown below)
- Modify: `tests/test_triangle_breakout.py` (two tests replaced)
- Create: `tests/test_triangle_breakout_window.py`

**Interfaces:**
- Consumes: every name in Task 1's Produces list.
- Produces: `classify_triangle_breakout(...)` — signature and the `TriangleBreakout`
  dataclass are UNCHANGED (Task 3 and `chart_patterns.py` rely on that). New behavior:
  post-apex confirmations, `forming` inside the window, expiry only after the window,
  apex-frozen `upper_level`/`lower_level` for any post-apex `level_index`.

- [ ] **Step 1: Update the two behavior-change tests**

In `tests/test_triangle_breakout.py`, replace
`test_post_apex_move_does_not_confirm_an_expired_triangle` (entire function) with:

```python
@pytest.mark.unit
def test_post_apex_breakout_inside_window_is_confirmed_with_flag():
    closes = _flat(100.0, 70)
    closes[60:] = [103.0] * (70 - 60)

    result = _classify(closes)

    assert result.status == "confirmed"
    assert result.breakout_index == 60
    assert result.breakout_progress == pytest.approx((60 - 5) / 52.5)
    assert result.risk_flags == ["post_apex_breakout"]
    assert result.timing_adjustment == -0.4
    assert result.upper_level == pytest.approx(99.5)
    assert result.lower_level == pytest.approx(99.5)
```

and replace `test_no_breakout_at_apex_expires_the_triangle_immediately` (entire
function) with (same assertions — only the name and meaning change: expiry now happens
after the post-apex window, and 75 flat bars are well past window-last bar 65):

```python
@pytest.mark.unit
def test_no_breakout_through_the_post_apex_window_expires_the_triangle():
    closes = _flat(99.5, 75)

    result = _classify(closes, buffer=3.0)

    assert result.status == "failed"
    assert result.breakout_index is None
    assert result.risk_flags == ["triangle_expired_at_apex"]
```

- [ ] **Step 2: Write the new classification-level test file**

```python
# tests/test_triangle_breakout_window.py
"""Classification-level tests for the post-apex window and asymmetric reversal (SP1)."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.triangle_breakout import classify_triangle_breakout

# upper(x) = 111 - 0.2x, lower(x) = 88 + 0.2x, apex 57.5 at price 99.5.
# Window = round(0.15 * 52.5) = 8 bars: the post-apex search covers bars 58-65
# and flagged breakouts get the half-buffer reversal through breakout_index + 8.
_LINES = {
    "high_slope": -0.2, "high_intercept": 111.0, "low_slope": 0.2, "low_intercept": 88.0,
}


def _classify(closes: list[float], buffer: float = 1.0):
    return classify_triangle_breakout(
        pd.DataFrame({"Close": closes}),
        start_index=5, formation_end=30, apex_index=57.5,
        bias="neutral", buffer=buffer, **_LINES,
    )


@pytest.mark.unit
def test_inside_window_without_breakout_is_still_forming():
    result = _classify([100.0] * 62)  # last bar 61 < window-last bar 65
    assert result.status == "forming"
    assert result.breakout_index is None
    assert "post-apex" in result.timing_evidence


@pytest.mark.unit
def test_window_exhausted_without_breakout_expires_the_triangle():
    result = _classify([100.0] * 66)  # last bar 65 == final window bar
    assert result.status == "failed"
    assert result.risk_flags == ["triangle_expired_at_apex"]


@pytest.mark.unit
def test_breakout_beyond_the_window_never_confirms():
    closes = [100.0] * 72
    closes[66:] = [103.0] * 6
    result = _classify(closes)
    assert result.status == "failed"
    assert result.breakout_index is None
    assert "triangle_expired_at_apex" in result.risk_flags


@pytest.mark.unit
def test_post_apex_breakout_reverses_on_half_buffer_close():
    closes = [100.0] * 70
    closes[60:63] = [103.0] * 3
    closes[63:] = [98.8] * (70 - 63)  # trips 99.0 (half buffer), not 98.5 (full)
    result = _classify(closes)
    assert result.status == "failed"
    assert result.signal_end_index == 63
    assert "post_apex_breakout" in result.risk_flags
    assert "breakout_reversed_back_through_triangle" in result.risk_flags


@pytest.mark.unit
def test_post_apex_breakout_holds_when_reversal_comes_late_and_shallow():
    closes = [100.0] * 75
    closes[60:70] = [103.0] * 10
    closes[70:] = [98.8] * 5  # beyond breakout + 8 bars: full buffer applies again
    result = _classify(closes)
    assert result.status == "confirmed"
    assert "post_apex_breakout" in result.risk_flags
    assert result.upper_level == pytest.approx(99.5)
    assert result.lower_level == pytest.approx(99.5)


@pytest.mark.unit
def test_late_apex_breakout_also_gets_the_asymmetric_reversal():
    closes = [100.0] * 70
    closes[52:55] = [103.0] * 3
    closes[55:] = [99.2] * (70 - 55)  # upper(55)=100.0: trips 99.5, not 99.0
    result = _classify(closes)
    assert result.status == "failed"
    assert "late_apex_breakout" in result.risk_flags
    assert "breakout_reversed_back_through_triangle" in result.risk_flags


@pytest.mark.unit
def test_normal_breakout_keeps_the_full_reversal_buffer():
    closes = [100.0] * 70
    closes[40:43] = [106.0] * 3
    closes[43:] = [101.5] * (70 - 43)  # upper(43)=102.4: half buffer would trip at 101.9
    result = _classify(closes)
    assert result.status == "confirmed"
    assert result.risk_flags == []
```

- [ ] **Step 3: Run new/updated tests to verify they fail**

Run: `pytest tests/test_triangle_breakout_window.py tests/test_triangle_breakout.py -q`
Expected: 5 FAIL, 9 pass across the two files. Failing (these assert the new behavior):
`test_inside_window_without_breakout_is_still_forming`,
`test_post_apex_breakout_reverses_on_half_buffer_close`,
`test_post_apex_breakout_holds_when_reversal_comes_late_and_shallow`,
`test_late_apex_breakout_also_gets_the_asymmetric_reversal`, and
`test_post_apex_breakout_inside_window_is_confirmed_with_flag`. The renamed expiry
test and the window-exhausted / beyond-window / full-buffer tests already pass because
current code expires everything at the apex and always uses the full buffer.

- [ ] **Step 4: Rewrite `triangle_breakout.py`**

Replace the entire file with:

```python
"""Triangle trendline-breakout timing classification.

Extracted out of ``chart_patterns._triangle_pattern`` (see
CHART_PATTERN_ANALYSIS_PLAN.md, "三角形整理") so the apex / post-apex timing
rules can evolve independently. Past the theoretical apex the two trendlines
have crossed and swapped position, so searching for breakouts against their
extrapolation indefinitely would produce meaningless levels. The post-apex
regime (finite window, apex-frozen levels, asymmetric reversal) lives in
``triangle_post_apex``; this module orchestrates it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from tradingagents.dataflows.triangle_post_apex import (
    find_post_apex_breakout,
    find_reversal_index,
    line_before_apex,
    line_value,
    post_apex_watch_evidence,
    post_apex_window_bars,
    timing_assessment,
)

PatternStatus = Literal["forming", "confirmed", "failed"]
PatternDirection = Literal["bullish", "bearish", "neutral"]


@dataclass
class TriangleBreakout:
    status: PatternStatus
    direction: PatternDirection
    breakout_index: int | None
    signal_end_index: int
    breakout_progress: float | None
    upper_level: float
    lower_level: float
    risk_flags: list[str] = field(default_factory=list)
    timing_evidence: str = "No confirmed trendline breakout yet."
    timing_adjustment: float = 0.0


def classify_triangle_breakout(
    df: pd.DataFrame,
    *,
    high_slope: float,
    high_intercept: float,
    low_slope: float,
    low_intercept: float,
    start_index: int,
    formation_end: int,
    apex_index: float,
    bias: PatternDirection,
    buffer: float,
) -> TriangleBreakout:
    """Search for and classify a triangle trendline breakout near or after its apex."""
    real_end_index = len(df) - 1
    # Pre-apex search: only bars strictly before the trendline intersection.
    search_bound = min(len(df), max(formation_end + 1, math.ceil(apex_index)))

    breakout_index: int | None = None
    breakout_direction: PatternDirection | None = None
    for index in range(formation_end + 1, search_bound):
        upper = line_value(high_slope, high_intercept, index)
        lower = line_value(low_slope, low_intercept, index)
        close = float(df.at[index, "Close"])
        if close > upper + buffer:
            breakout_index, breakout_direction = index, "bullish"
            break
        if close < lower - buffer:
            breakout_index, breakout_direction = index, "bearish"
            break

    apex_price = line_value(high_slope, high_intercept, apex_index)
    window_bars = post_apex_window_bars(start_index, apex_index)
    window_last_index = math.ceil(apex_index) + window_bars - 1
    post_apex = False
    if breakout_index is None:
        hit = find_post_apex_breakout(
            df,
            formation_end=formation_end,
            apex_index=apex_index,
            apex_price=apex_price,
            buffer=buffer,
            window_bars=window_bars,
        )
        if hit is not None:
            breakout_index, breakout_direction = hit  # type: ignore[assignment]
            post_apex = True

    risk_flags: list[str] = []
    timing_evidence = "No confirmed trendline breakout yet."
    timing_adjustment = 0.0
    breakout_progress: float | None = None
    if breakout_index is not None:
        breakout_progress = (breakout_index - start_index) / (apex_index - start_index)
        timing_evidence, timing_adjustment, risk_flags = timing_assessment(
            breakout_progress, post_apex=post_apex
        )

    failure_index: int | None = None
    if breakout_index is not None and breakout_direction is not None:
        failure_index = find_reversal_index(
            df,
            high_slope=high_slope,
            high_intercept=high_intercept,
            low_slope=low_slope,
            low_intercept=low_intercept,
            apex_index=apex_index,
            breakout_index=breakout_index,
            breakout_direction=breakout_direction,
            risk_flags=risk_flags,
            buffer=buffer,
            window_bars=window_bars,
        )

    if failure_index is not None:
        status: PatternStatus = "failed"
        direction: PatternDirection = breakout_direction or bias
        signal_end_index = failure_index
        risk_flags.append("breakout_reversed_back_through_triangle")
    elif breakout_index is not None:
        status = "confirmed"
        direction = breakout_direction or bias
        signal_end_index = breakout_index
    elif real_end_index >= window_last_index:
        status = "failed"
        direction = bias
        signal_end_index = real_end_index
        risk_flags.append("triangle_expired_at_apex")
    elif real_end_index >= apex_index:
        status = "forming"
        direction = bias
        signal_end_index = real_end_index
        timing_evidence = post_apex_watch_evidence(window_bars)
    else:
        status = "forming"
        direction = bias
        signal_end_index = real_end_index

    level_index = breakout_index if breakout_index is not None else min(real_end_index, apex_index)

    return TriangleBreakout(
        status=status,
        direction=direction,
        breakout_index=breakout_index,
        signal_end_index=signal_end_index,
        breakout_progress=breakout_progress,
        upper_level=line_before_apex(high_slope, high_intercept, level_index, apex_index),
        lower_level=line_before_apex(low_slope, low_intercept, level_index, apex_index),
        risk_flags=risk_flags,
        timing_evidence=timing_evidence,
        timing_adjustment=timing_adjustment,
    )
```

Note the two deliberate level changes vs. the old file: levels always go through
`line_before_apex` (so a post-apex `breakout_index` yields the apex price on both
boundaries), and expiry waits for `window_last_index` instead of firing at
`apex_index`.

- [ ] **Step 5: Run the triangle test files**

Run: `pytest tests/test_triangle_breakout.py tests/test_triangle_breakout_window.py tests/test_triangle_post_apex.py -q`
Expected: 23 passed (7 + 7 + 9).

- [ ] **Step 6: Lint and line-count check**

Run: `ruff check tradingagents/dataflows/triangle_breakout.py tests/test_triangle_breakout.py tests/test_triangle_breakout_window.py && wc -l tradingagents/dataflows/triangle_breakout.py tests/test_triangle_breakout_window.py`
Expected: no ruff errors; `triangle_breakout.py` ≤150 lines (compress its docstring if
marginally over), new test file ≤150.

---

### Task 3: Apex-anchored target in `chart_patterns.py` + pipeline tests

**Files:**
- Modify: `tradingagents/dataflows/chart_patterns.py` (the confirmed-target branch inside
  `_triangle_pattern`, currently near lines 558-564)
- Modify: `tests/test_chart_patterns.py` (replace one test, add one)

**Interfaces:**
- Consumes: `TriangleBreakout.risk_flags` containing `"post_apex_breakout"`, and
  `upper_level`/`lower_level` both equal to the apex price for post-apex breakouts
  (Task 2 guarantees this).
- Produces: no new names — `analyze_chart_patterns_from_data` output schema unchanged.

- [ ] **Step 1: Update the pipeline tests**

In `tests/test_chart_patterns.py`, replace
`test_post_apex_move_expires_triangle_through_full_pipeline` (entire function — its
fixture's bar-65 jump now lands inside the 8-bar post-apex window) with:

```python
@pytest.mark.unit
def test_post_apex_breakout_confirms_with_apex_anchored_prices():
    # Flat at the apex value until bar 64 (no pivots form on a flat run), then a
    # jump at bar 65 — inside the 8-bar post-apex window after the bar-60.5 apex.
    anchors = [(0, 100), (5, 110), (10, 90), (15, 108), (20, 92), (25, 106), (30, 94)]
    closes = _interpolate_anchors(anchors)
    closes += [99.5] * (65 - len(closes))
    closes += [112.0] * 6
    data = _ohlcv(closes, breakout_volume_index=65)

    result = patterns.analyze_chart_patterns_from_data(
        data, data["Date"].iloc[-1].strftime("%Y-%m-%d"), pivot_span=3
    )
    signal = _find(result, "symmetrical_triangle")

    assert signal["status"] == "confirmed"
    assert "post_apex_breakout" in signal["risk_flags"]
    assert signal["levels"]["breakout_progress"] == pytest.approx(1.0811, abs=1e-3)
    assert signal["levels"]["upper_trendline"] == signal["levels"]["lower_trendline"]
    assert signal["invalidation_price"] == pytest.approx(99.5, abs=0.05)
    # The measured move anchors at the apex price, not at the 112.0 breakout close.
    assert signal["target_price"] == pytest.approx(99.5 + 22.2, abs=0.1)
    assert signal["confidence"] < 0.5


@pytest.mark.unit
def test_flat_drift_past_the_window_expires_triangle_through_full_pipeline():
    anchors = [(0, 100), (5, 110), (10, 90), (15, 108), (20, 92), (25, 106), (30, 94)]
    closes = _interpolate_anchors(anchors)
    closes += [99.5] * (75 - len(closes))
    data = _ohlcv(closes)

    result = patterns.analyze_chart_patterns_from_data(
        data, data["Date"].iloc[-1].strftime("%Y-%m-%d"), pivot_span=3
    )
    signal = _find(result, "symmetrical_triangle")

    assert signal["status"] == "failed"
    assert signal["levels"]["breakout_progress"] is None
    assert "triangle_expired_at_apex" in signal["risk_flags"]
    assert signal["levels"]["upper_trendline"] == signal["levels"]["lower_trendline"]
```

Contingency: if the flat-75 fixture yields no `symmetrical_triangle` signal (`_find`
raises), shorten the flat run to 70 total bars — the prototype validated expiry at both
lengths under the new window-last bar of 68.

- [ ] **Step 2: Run the two tests to verify current state**

Run: `pytest tests/test_chart_patterns.py -q`
Expected: the confirm test FAILS on `target_price` (it currently computes
`112.0 + 22.2 = 134.2` from the breakout close); the expiry test already passes.
(Everything else in the file must still pass — Task 2 did not change pre-apex behavior.)

- [ ] **Step 3: Implement the apex-anchored target branch**

In `tradingagents/dataflows/chart_patterns.py`, inside `_triangle_pattern`, replace:

```python
    if direction == "bullish" and status == "confirmed" and breakout_price is not None:
        target, invalidation = breakout_price + start_gap, lower_level
    elif direction == "bearish" and status == "confirmed" and breakout_price is not None:
        target, invalidation = breakout_price - start_gap, upper_level
```

with:

```python
    # Post-apex breakouts anchor the measured move at the apex price (both frozen
    # levels equal it); extending from the breakout close would inflate the target.
    if direction == "bullish" and status == "confirmed" and breakout_price is not None:
        anchor = upper_level if "post_apex_breakout" in risk_flags else breakout_price
        target, invalidation = anchor + start_gap, lower_level
    elif direction == "bearish" and status == "confirmed" and breakout_price is not None:
        anchor = lower_level if "post_apex_breakout" in risk_flags else breakout_price
        target, invalidation = anchor - start_gap, upper_level
```

- [ ] **Step 4: Run the full chart-pattern + triangle test set**

Run: `pytest tests/test_chart_patterns.py tests/test_triangle_breakout.py tests/test_triangle_breakout_window.py tests/test_triangle_post_apex.py -q`
Expected: all pass.

- [ ] **Step 5: Lint**

Run: `ruff check tradingagents/dataflows/chart_patterns.py tests/test_chart_patterns.py`
Expected: no errors.
