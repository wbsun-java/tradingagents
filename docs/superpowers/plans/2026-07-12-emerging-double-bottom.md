# Emerging Double-Bottom Stage (SP3b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Note for this repo specifically:** execute each task through the `codex-delegate` skill. Codex prompts must open with the "YOU are the implementer" paragraph (feedback_codex_nested_delegation memory).

**Goal:** Recognize a W-bottom's second low before it confirms as a pivot — a new
`emerging` PatternStatus double_bottom, guarded by a conservative turn-up — and route it to
`predictive_bottom` so aggressive traders get the earliest entry.

**Architecture:** A new module `double_bottom_emerging.py` owns detection; `chart_patterns.py`
gains only the `emerging` status value, its sort order, and a gated call (append the
emerging pattern only when no `double_bottom` already exists). `entry_assessment.py` maps
`emerging → predictive_bottom`; `market_analyst.py` gets one approved sentence.

**Tech Stack:** Python 3.14, pandas, pytest (`@pytest.mark.unit`), ruff.

**Design source of truth:** `docs/superpowers/specs/2026-07-12-emerging-double-bottom-design.md`.

## Global Constraints

- **New files ≤150 lines**: `double_bottom_emerging.py` ~85, `test_double_bottom_emerging.py`
  ~95, `test_emerging_pipeline.py` ~75. Additions to `test_entry_assessment.py` (~114→~130)
  and `test_market_analyst_prefetch.py` stay under 150.
- **Constants, exact names** (interim, in `double_bottom_emerging.py`):
  `EMERGING_WINDOW_BARS_MARGIN = 2` (candidate window = `span + 2`),
  `EMERGING_TURN_UP_ATR = 0.5`, `EMERGING_CONFIDENCE = 0.4`.
- **No import cycle:** `double_bottom_emerging.py` imports `PricePattern` **lazily** inside
  the function (chart_patterns imports the detector at module top). It duck-types the
  `pivots` items (`.kind`, `.index`, `.price`).
- **Emerging is gated, never a duplicate:** appended only when no `double_bottom` is already
  in `patterns`. `_double_patterns` and `find_pivots` are NOT modified.
- **Long-only, double_bottom only.** No double-top emerging; no other structures.
- **Upstream edit pre-approved for SP3b only** (project_sp3_market_analyst_approval): one
  sentence in market_analyst.py's existing chart-pattern paragraph, nothing else.
- All tests `@pytest.mark.unit`, synthetic frames only, no network/LLM. Do NOT
  `git add`/`git commit`.

**Validated fixture geometry (for the detector unit test):** closes interpolated through
anchors `[(0,100),(8,95.8),(18,108.8),(35,96.2),(39,98)]` (40 bars), High/Low = close±0.8.
First bottom = a `low` pivot at index 8, price 95.0 (= close 95.8 − 0.8). With `span=3`
(window 5 = bars 35–39) the candidate low is bar 35 (Low 95.4); last close 98 ≥ 95.4 +
0.5·1.5 turn-up; no lower low after 35; `gap = 27`; neckline = max High in [8,35] = 109.6;
`average = 95.2`, `depth = 14.4`, `target = 124.0`.

---

### Task 1: The emerging detector

**Files:**
- Create: `tradingagents/dataflows/double_bottom_emerging.py`
- Test: `tests/test_double_bottom_emerging.py`

**Interfaces:**
- Produces: `find_emerging_double_bottom(df, pivots, atr, span) -> PricePattern | None`;
  constants `EMERGING_WINDOW_BARS_MARGIN`, `EMERGING_TURN_UP_ATR`, `EMERGING_CONFIDENCE`.
- Consumes: `PricePattern` (lazy import from `chart_patterns`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_double_bottom_emerging.py
"""Emerging double-bottom detection (SP3b)."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from tradingagents.dataflows.double_bottom_emerging import find_emerging_double_bottom


def _interp(anchors):
    values = []
    for (s, sv), (e, ev) in zip(anchors, anchors[1:]):
        values += [sv + (ev - sv) * o / (e - s) for o in range(e - s)]
    values.append(anchors[-1][1])
    return values


def _df(anchors):
    closes = _interp(anchors)
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2026-01-02", periods=len(closes)),
            "Open": closes, "High": [c + 0.8 for c in closes], "Low": [c - 0.8 for c in closes],
            "Close": closes, "Volume": [1_000_000.0] * len(closes),
        }
    )


def _first_bottom():
    return [SimpleNamespace(kind="low", index=8, price=95.0, date="2026-01-13")]


_ANCHORS = [(0, 100), (8, 95.8), (18, 108.8), (35, 96.2), (39, 98)]


@pytest.mark.unit
def test_emerging_double_bottom_is_detected():
    pattern = find_emerging_double_bottom(_df(_ANCHORS), _first_bottom(), 1.5, 3)
    assert pattern is not None
    assert pattern.pattern == "double_bottom"
    assert pattern.status == "emerging"
    assert pattern.direction == "bullish"
    assert pattern.confidence == 0.4
    assert pattern.levels["first_extreme"] == pytest.approx(95.0)
    assert pattern.levels["second_extreme"] == pytest.approx(95.4)
    assert pattern.levels["breakout_price"] is None
    assert pattern.target_price > pattern.levels["neckline"]


@pytest.mark.unit
def test_no_turn_up_yields_none():
    # last close sits right at the candidate low -> no nascent turn-up
    pattern = find_emerging_double_bottom(
        _df([(0, 100), (8, 95.8), (18, 108.8), (35, 96.2), (39, 95.6)]), _first_bottom(), 1.5, 3
    )
    assert pattern is None


@pytest.mark.unit
def test_deep_undercut_yields_none():
    # candidate low crashes well below the first bottom -> a breakdown, not a double
    pattern = find_emerging_double_bottom(
        _df([(0, 100), (8, 95.8), (18, 108.8), (35, 89.0), (39, 92.0)]), _first_bottom(), 1.5, 3
    )
    assert pattern is None


@pytest.mark.unit
def test_no_matching_first_bottom_yields_none():
    # first pivot far too high to be a double with the candidate low
    pivots = [SimpleNamespace(kind="low", index=8, price=80.0, date="2026-01-13")]
    assert find_emerging_double_bottom(_df(_ANCHORS), pivots, 1.5, 3) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest -q tests/test_double_bottom_emerging.py`
Expected: FAIL with `ModuleNotFoundError: ... double_bottom_emerging`.

- [ ] **Step 3: Write the module**

```python
# tradingagents/dataflows/double_bottom_emerging.py
"""Emerging double-bottom detection (SP3b): the W's second bottom before it confirms.

find_pivots only confirms a swing low `span` bars later, so a fresh second bottom is
invisible to _double_patterns. This module recognizes it early -- guarded by a conservative
turn-up so a still-falling low never qualifies -- and emits a status="emerging" double
bottom that feeds predictive_bottom. Constants are interim, pending a future backtest read
(docs/superpowers/specs/2026-07-12-emerging-double-bottom-design.md).
"""

from __future__ import annotations

import math

import pandas as pd

EMERGING_WINDOW_BARS_MARGIN = 2
EMERGING_TURN_UP_ATR = 0.5
EMERGING_CONFIDENCE = 0.4


def _round(value: float | None) -> float | None:
    return None if value is None or not math.isfinite(value) else round(float(value), 4)


def _match_first_bottom(df, pivots, atr, span, candidate_index, candidate_low):
    """Most-recent confirmed low pivot that forms a valid double with the candidate."""
    lows = sorted(
        (p for p in pivots if p.kind == "low" and p.index < candidate_index),
        key=lambda p: p.index, reverse=True,
    )
    for first in lows:
        gap = candidate_index - first.index
        if gap < max(5, span * 2) or gap > 80:
            continue
        average = (first.price + candidate_low) / 2
        tolerance = max(atr, average * 0.03)
        if abs(first.price - candidate_low) > tolerance or candidate_low < first.price - tolerance:
            continue
        neckline = float(df["High"].iloc[first.index : candidate_index + 1].max())
        depth = neckline - average
        if depth < max(atr * 1.25, average * 0.02):
            continue
        return first, average, neckline, depth
    return None


def find_emerging_double_bottom(df: pd.DataFrame, pivots, atr: float, span: int):
    """Return an emerging double_bottom PricePattern, or None if any gate fails."""
    if atr <= 0 or len(df) < span + 5:
        return None
    window = span + EMERGING_WINDOW_BARS_MARGIN
    candidate_index = int(df["Low"].iloc[len(df) - window :].idxmin())
    candidate_low = float(df.at[candidate_index, "Low"])
    last_index = len(df) - 1
    if candidate_index >= last_index:
        return None
    if float(df["Close"].iloc[-1]) < candidate_low + EMERGING_TURN_UP_ATR * atr:
        return None
    if float(df["Low"].iloc[candidate_index + 1 :].min()) < candidate_low:
        return None
    match = _match_first_bottom(df, pivots, atr, span, candidate_index, candidate_low)
    if match is None:
        return None
    first, average, neckline, depth = match

    from tradingagents.dataflows.chart_patterns import PricePattern

    return PricePattern(
        pattern="double_bottom",
        status="emerging",
        direction="bullish",
        confidence=EMERGING_CONFIDENCE,
        start_date=df.at[first.index, "Date"].strftime("%Y-%m-%d"),
        end_date=df.at[last_index, "Date"].strftime("%Y-%m-%d"),
        levels={
            "first_extreme": _round(first.price),
            "second_extreme": _round(candidate_low),
            "neckline": _round(neckline),
            "breakout_price": None,
        },
        target_price=_round(neckline + depth),
        invalidation_price=_round(candidate_low - atr * 0.2),
        volume_confirmed=None,
        evidence=[
            f"First bottom near {_round(first.price)} on {df.at[first.index, 'Date']:%Y-%m-%d}.",
            f"An emerging second bottom printed at {_round(candidate_low)} on "
            f"{df.at[candidate_index, 'Date']:%Y-%m-%d}, not yet a confirmed pivot.",
            f"Price turned up at least {EMERGING_TURN_UP_ATR} ATR off that low with no new low.",
            f"Neckline resistance {_round(neckline)}; measured target {_round(neckline + depth)}.",
        ],
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest -q tests/test_double_bottom_emerging.py`
Expected: PASS (4 passed).

- [ ] **Step 5: Budget + ruff, then STOP for review** (do not commit)

Run: `wc -l tradingagents/dataflows/double_bottom_emerging.py` (expect ~85, ≤150)
Run: `ruff check tradingagents/dataflows/double_bottom_emerging.py tests/test_double_bottom_emerging.py`
Expected: `All checks passed!`

---

### Task 2: Route emerging → predictive_bottom

**Files:**
- Modify: `tradingagents/dataflows/entry_assessment.py`
- Test: `tests/test_entry_assessment.py` (append one test)

**Interfaces:**
- Consumes: existing `extract_levels`, `_make`, `PREDICTIVE_BOTTOM`,
  `PREDICTIVE_UNDERSHOOT_ATR`, `ENTRY_PROXIMITY_ATR`.
- Produces: `assess_entry` returns `predictive_bottom` for any `status == "emerging"`
  long-eligible pattern.

- [ ] **Step 1: Write the failing test** — append to `tests/test_entry_assessment.py`:

```python
@pytest.mark.unit
def test_emerging_double_bottom_is_predictive_bottom():
    p = _pat("double_bottom", "emerging", "bullish",
             {"first_extreme": 95.0, "second_extreme": 95.4, "neckline": 109.6}, invalidation=95.1)
    a = assess_entry(_df([98.0] * 21), p, ATR, 98.0)
    assert (a.state, a.direction) == ("predictive_bottom", "long")
    assert a.trigger_price == pytest.approx(95.0)  # min(first, second)
    assert a.volume_role == "supporting_not_required"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest -q tests/test_entry_assessment.py::test_emerging_double_bottom_is_predictive_bottom`
Expected: FAIL — the emerging pattern currently falls through to `observe`/no branch.

- [ ] **Step 3: Add the branch.** In `entry_assessment.py`'s `assess_entry`, immediately
  AFTER the `prox = ENTRY_PROXIMITY_ATR * atr` line and BEFORE `if pattern.status ==
  "failed":`, insert:

```python
    if pattern.status == "emerging":
        bottom = levels["bottom_boundary"]
        return _make(PREDICTIVE_BOTTOM, "long", bottom - PREDICTIVE_UNDERSHOOT_ATR * atr,
                     bottom + prox, bottom, levels["failure_level"],
                     "Emerging second bottom with a nascent turn-up.", "supporting_not_required")
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest -q tests/test_entry_assessment.py`
Expected: PASS (11 passed).

- [ ] **Step 5: Ruff, then STOP for review** (do not commit)

Run: `ruff check tradingagents/dataflows/entry_assessment.py tests/test_entry_assessment.py`
Expected: `All checks passed!`

---

### Task 3: Wire the status + gated call into `chart_patterns.py`

**Files:**
- Modify: `tradingagents/dataflows/chart_patterns.py`
- Test: `tests/test_emerging_pipeline.py`

**Interfaces:**
- Consumes: `find_emerging_double_bottom` from `double_bottom_emerging`.
- Produces: `analyze_chart_patterns_from_data` output may contain an `emerging`
  double_bottom (with `entry_assessment.state == "predictive_bottom"`), gated so it never
  co-exists with another `double_bottom`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_emerging_pipeline.py
"""End-to-end wiring of the emerging double_bottom into the pipeline (SP3b)."""

from __future__ import annotations

import pandas as pd
import pytest

import tradingagents.dataflows.chart_patterns as patterns


def _rising_df():
    closes = [100 + i * 0.3 for i in range(60)]
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2026-01-02", periods=len(closes)),
            "Open": closes, "High": [c + 0.5 for c in closes], "Low": [c - 0.5 for c in closes],
            "Close": closes, "Volume": [1_000_000.0] * len(closes),
        }
    )


def _fake_emerging():
    return patterns.PricePattern(
        pattern="double_bottom", status="emerging", direction="bullish", confidence=0.4,
        start_date="2026-01-02", end_date="2026-02-01",
        levels={"first_extreme": 95.0, "second_extreme": 95.4, "neckline": 109.6,
                "breakout_price": None},
        target_price=124.0, invalidation_price=95.1, volume_confirmed=None, evidence=["x"],
    )


@pytest.mark.unit
def test_emerging_is_appended_and_gets_predictive_bottom(monkeypatch):
    monkeypatch.setattr(patterns, "find_emerging_double_bottom", lambda *a: _fake_emerging())
    data = _rising_df()
    result = patterns.analyze_chart_patterns_from_data(
        data, data["Date"].iloc[-1].strftime("%Y-%m-%d"), pivot_span=3
    )
    emerging = [p for p in result["patterns"]
                if p["pattern"] == "double_bottom" and p["status"] == "emerging"]
    assert len(emerging) == 1
    assert emerging[0]["entry_assessment"]["state"] == "predictive_bottom"


@pytest.mark.unit
def test_emerging_is_suppressed_when_a_double_bottom_already_exists(monkeypatch):
    monkeypatch.setattr(patterns, "find_emerging_double_bottom", lambda *a: _fake_emerging())

    def _interp(anchors):
        v = []
        for (s, sv), (e, ev) in zip(anchors, anchors[1:]):
            v += [sv + (ev - sv) * o / (e - s) for o in range(e - s)]
        v.append(anchors[-1][1])
        return v

    closes = _interp([(0, 108), (12, 95), (24, 108), (38, 96), (50, 111), (65, 114)])
    data = pd.DataFrame(
        {
            "Date": pd.bdate_range("2026-01-02", periods=len(closes)),
            "Open": closes, "High": [c + 0.6 for c in closes], "Low": [c - 0.6 for c in closes],
            "Close": closes, "Volume": [1_000_000.0] * len(closes),
        }
    )
    result = patterns.analyze_chart_patterns_from_data(
        data, data["Date"].iloc[-1].strftime("%Y-%m-%d"), pivot_span=2
    )
    doubles = [p for p in result["patterns"] if p["pattern"] == "double_bottom"]
    assert len(doubles) == 1
    assert doubles[0]["status"] != "emerging"  # the real confirmed double wins; emerging gated out
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest -q tests/test_emerging_pipeline.py`
Expected: FAIL — `find_emerging_double_bottom` not defined on the module / not called.

- [ ] **Step 3a: Add the import** after the existing
  `from tradingagents.dataflows.entry_types import EntryAssessment` line:

```python
from tradingagents.dataflows.double_bottom_emerging import find_emerging_double_bottom
```

- [ ] **Step 3b: Add `"emerging"` to the status Literal.** Change:

```python
PatternStatus = Literal["forming", "confirmed", "failed"]
```
to:
```python
PatternStatus = Literal["forming", "confirmed", "emerging", "failed"]
```

- [ ] **Step 3c: Update `status_order`.** Change:

```python
    status_order = {"confirmed": 0, "forming": 1, "failed": 2}
```
to:
```python
    status_order = {"confirmed": 0, "forming": 1, "emerging": 2, "failed": 3}
```

- [ ] **Step 3d: Add the gated call.** Immediately AFTER
  `patterns.extend(_triangle_pattern(df, pivots, atr_value))` and BEFORE the
  `for pattern in patterns:` entry-assessment post-pass, insert:

```python
    if not any(pattern.pattern == "double_bottom" for pattern in patterns):
        emerging = find_emerging_double_bottom(df, pivots, atr_value, pivot_span)
        if emerging is not None:
            patterns.append(emerging)
```

- [ ] **Step 4: Run the pipeline test**

Run: `pytest -q tests/test_emerging_pipeline.py`
Expected: PASS (2 passed).

- [ ] **Step 5: Regression — chart + entry suites**

Run: `pytest -q tests/test_chart_patterns.py tests/test_entry_pipeline.py tests/test_false_break_pipeline.py`
Expected: all PASS. The `status_order` change only affects output ordering; `entry_assessment`
is additive; no existing assertion depends on the failed sort key being `2`. If one does,
update it to the new order — do not revert the wiring.

- [ ] **Step 6: Ruff, then STOP for review** (do not commit)

Run: `ruff check tradingagents/dataflows/chart_patterns.py tests/test_emerging_pipeline.py`
Expected: `All checks passed!`

---

### Task 4: Market Analyst prompt note (upstream, approved)

**Files:**
- Modify: `tradingagents/agents/analysts/market_analyst.py` (one sentence in the existing
  chart-pattern paragraph)
- Test: `tests/test_market_analyst_prefetch.py` (append one test)

**Interfaces:**
- Produces: the analyst prompt explains the `emerging` status.

- [ ] **Step 1: Write the failing test** — append to `tests/test_market_analyst_prefetch.py`:

```python
@pytest.mark.unit
def test_emerging_status_guidance_reaches_the_prompt(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.agents.analysts.market_analyst.analyze_wyckoff_structure",
        lambda *_args: '{"phase_bias":"neutral"}',
    )
    monkeypatch.setattr(
        "tradingagents.agents.analysts.market_analyst.analyze_oneil_setup",
        lambda *_args: '{"primary_pattern":null,"setup_bias":"neutral","other_detections":[]}',
    )

    create_market_analyst(_fake_llm())(_make_state())

    assert "An `emerging` pattern" in _system_content()
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest -q tests/test_market_analyst_prefetch.py::test_emerging_status_guidance_reaches_the_prompt`
Expected: FAIL.

- [ ] **Step 3: Append the sentence.** In `market_analyst.py`, find the chart-pattern
  paragraph whose LAST sentence (added by SP3) ends `...are contrarian reversal signals,
  not continuation entries.`. Append this to the SAME paragraph, immediately after that
  sentence:

```
 An `emerging` pattern is a still-forming candidate, even more tentative than `forming`; act only on its `entry_assessment.state` and never treat it as confirmed.
```

- [ ] **Step 4: Run the prompt test**

Run: `pytest -q tests/test_market_analyst_prefetch.py::test_emerging_status_guidance_reaches_the_prompt`
Expected: PASS.

- [ ] **Step 5: Full local suite + ruff, then STOP for review** (do not commit)

Run: `pytest -q -m 'not integration'` and `ruff check .`
Expected: all PASS (the one live-yfinance `@pytest.mark.integration` test is excluded),
`All checks passed!`. Report `wc -l` for the new files.

---

## Self-Review

**Spec coverage:** ✔ detector with candidate-low + turn-up + no-new-low + tolerance/gap/
depth/shallow-undercut match (Task 1); ✔ conservative turn-up `EMERGING_TURN_UP_ATR`
(Task 1, `test_no_turn_up`/`test_new_low`); ✔ new `emerging` status + `status_order` +
gated non-duplicate call (Task 3, both tests); ✔ `emerging → predictive_bottom` bypassing
the proximity check (Task 2); ✔ approved one-sentence prompt note (Task 4); ✔ constants
named/interim, `extract_levels` reused unchanged; ✔ non-goals honored (no double-top, no
find_pivots/_double_patterns change, no calibration).

**Placeholder scan:** no TBD/"handle edge cases"/"similar to Task N"; every code step is
complete. (Task 4 Step 3 spells out exactly where the sentence attaches.)

**Type consistency:** `find_emerging_double_bottom(df, pivots, atr, span)` signature matches
between Task 1 (definition), Task 3 (call site + monkeypatch), and the detector test. The
emitted PricePattern's `levels` keys (`first_extreme`/`second_extreme`/`neckline`/
`breakout_price`) match what `entry_rules.extract_levels` reads for `double_bottom`, so
Task 2's `predictive_bottom` resolves `bottom_boundary = min(first, second)`. `emerging`
is added to the Literal (Task 3b) before any code emits it (Task 1 emits the string, Task 3
wires it — both consistent).
