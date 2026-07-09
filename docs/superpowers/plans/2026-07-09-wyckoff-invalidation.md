# Wyckoff Breakout-Failure (Invalidation) Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect when a Wyckoff Phase D/E breakout later reverses back through the original range boundary, and stop presenting that read as a live confirmed directional call.

**Architecture:** A new pure function `check_invalidation` (new file `wyckoff_invalidation.py`) scans bars after the last detected Phase D/E event for a close back through the original boundary. `wyckoff_accumulation.py`/`wyckoff_distribution.py` call it and add an `invalidated: bool` field to their result dataclasses, appending a `range_failure` event when triggered. `wyckoff_bias.py` reads that field and overrides `phase_bias`→`"neutral"`, `confidence`→`0.0`, `trading_range.status`→`"invalidated"`, adds a top-level `"invalidated"` key, and skips the VSA call entirely when invalidated.

**Tech Stack:** Python, pandas, pytest (`@pytest.mark.unit`), ruff.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-09-wyckoff-invalidation-design.md`.
- `wyckoff_invalidation.py` is a new file — CLAUDE.md's 150-line cap applies.
- `wyckoff_events.py` must NOT be edited — it is already at exactly 150 lines (the existing-file cap is grandfathered, but this design deliberately avoids growing it; see spec's "Approaches considered").
- All touched/added files (`wyckoff_invalidation.py`, `wyckoff_accumulation.py`, `wyckoff_distribution.py`, `wyckoff_bias.py`) are project-custom, not upstream — no upstream-approval gate applies.
- No changes to `market_analyst.py`, `trading_graph.py`, or `wyckoff_range.py` — tool signature, prompt wiring, and range-detection geometry are all unchanged.
- Default verification per CLAUDE.md for an isolated additive change: run each task's own test file(s) plus `ruff check` on touched files — no full-suite run needed until the final task.

---

### Task 1: `wyckoff_invalidation.py` — the invalidation check

**Files:**
- Create: `tradingagents/dataflows/wyckoff_invalidation.py`
- Test: `tests/test_wyckoff_invalidation.py`

**Interfaces:**
- Consumes: `WyckoffEvent`, `Phase` from `tradingagents/dataflows/wyckoff_events.py` (unchanged); `TradingRange` from `tradingagents/dataflows/wyckoff_range.py` (unchanged); `volume_ratio` from `tradingagents/dataflows/wyckoff_range.py` (unchanged).
- Produces: `check_invalidation(df: pd.DataFrame, atr_value: float, rng: TradingRange, direction: Literal["accumulation", "distribution"], events: list[WyckoffEvent], phase: Phase) -> WyckoffEvent | None`. Task 2 calls this directly.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_wyckoff_invalidation.py`:

```python
"""Unit tests for the Wyckoff breakout-failure (invalidation) check."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.wyckoff_events import WyckoffEvent
from tradingagents.dataflows.wyckoff_invalidation import check_invalidation
from tradingagents.dataflows.wyckoff_range import TradingRange


def _df(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({
        "Date": pd.bdate_range("2023-01-02", periods=len(closes)),
        "Open": closes, "High": [c + 0.5 for c in closes], "Low": [c - 0.5 for c in closes],
        "Close": closes, "Volume": [1_000_000.0] * len(closes),
    })


def _range(high: float, low: float) -> TradingRange:
    return TradingRange(
        range_high=high, range_low=low, start_index=0, start_date="2023-01-02",
        high_touches=[], low_touches=[], prior_trend="down",
    )


def _events(last_date: str) -> list[WyckoffEvent]:
    return [WyckoffEvent(event="back_up", date=last_date, price=95.0, volume_ratio=1.1, evidence=["..."])]


@pytest.mark.unit
def test_accumulation_reversal_past_range_low_is_flagged():
    df = _df([95.0, 95.0, 95.0, 74.0])  # last bar reverses well below range_low
    events = _events(df["Date"].iloc[2].strftime("%Y-%m-%d"))
    rng = _range(high=93.0, low=77.0)

    failure = check_invalidation(df, atr_value=2.0, rng=rng, direction="accumulation", events=events, phase="E")

    assert failure is not None
    assert failure.event == "range_failure"
    assert failure.price == 74.0


@pytest.mark.unit
def test_accumulation_no_reversal_is_not_flagged():
    df = _df([95.0, 95.0, 95.0, 90.0])  # stays well above range_low, no failure
    events = _events(df["Date"].iloc[2].strftime("%Y-%m-%d"))
    rng = _range(high=93.0, low=77.0)

    failure = check_invalidation(df, atr_value=2.0, rng=rng, direction="accumulation", events=events, phase="E")

    assert failure is None


@pytest.mark.unit
def test_distribution_reversal_past_range_high_is_flagged():
    df = _df([70.0, 70.0, 70.0, 96.0])  # last bar reverses well above range_high
    events = _events(df["Date"].iloc[2].strftime("%Y-%m-%d"))
    rng = _range(high=93.0, low=77.0)

    failure = check_invalidation(df, atr_value=2.0, rng=rng, direction="distribution", events=events, phase="D")

    assert failure is not None
    assert failure.event == "range_failure"
    assert failure.price == 96.0


@pytest.mark.unit
def test_phase_c_is_never_checked_for_invalidation():
    df = _df([95.0, 95.0, 95.0, 50.0])  # would qualify as a reversal, but C has no breakout to fail
    events = _events(df["Date"].iloc[2].strftime("%Y-%m-%d"))
    rng = _range(high=93.0, low=77.0)

    failure = check_invalidation(df, atr_value=2.0, rng=rng, direction="accumulation", events=events, phase="C")

    assert failure is None


@pytest.mark.unit
def test_empty_events_returns_none_without_crashing():
    df = _df([95.0, 95.0, 95.0, 74.0])
    rng = _range(high=93.0, low=77.0)

    failure = check_invalidation(df, atr_value=2.0, rng=rng, direction="accumulation", events=[], phase="E")

    assert failure is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_wyckoff_invalidation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tradingagents.dataflows.wyckoff_invalidation'`.

- [ ] **Step 3: Implement `wyckoff_invalidation.py`**

Create `tradingagents/dataflows/wyckoff_invalidation.py`:

```python
"""Detects a Phase D/E Wyckoff breakout that later reversed.

`detect_events` (wyckoff_events.py) only checks whether Sign-of-Strength /
Last-Point / Back-Up occurred in sequence — it never checks whether that
breakout held. This module adds that check as a separate pass so
wyckoff_events.py (already at the 150-line cap) doesn't have to grow.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd

from tradingagents.dataflows.wyckoff_events import Phase, WyckoffEvent
from tradingagents.dataflows.wyckoff_range import TradingRange, volume_ratio

Direction = Literal["accumulation", "distribution"]


def check_invalidation(
    df: pd.DataFrame,
    atr_value: float,
    rng: TradingRange,
    direction: Direction,
    events: list[WyckoffEvent],
    phase: Phase,
) -> WyckoffEvent | None:
    """Return a ``range_failure`` event if the Phase D/E breakout reversed, else None."""
    if phase not in ("D", "E") or not events:
        return None
    accum = direction == "accumulation"
    buffer = atr_value * 0.2
    last_index = df.index[df["Date"] == pd.Timestamp(events[-1].date)]
    if not len(last_index):
        return None
    start = int(last_index[0]) + 1
    for i in range(start, len(df)):
        close = float(df.at[i, "Close"])
        failed = close < rng.range_low - buffer if accum else close > rng.range_high + buffer
        if not failed:
            continue
        date = df.at[i, "Date"].strftime("%Y-%m-%d")
        boundary = rng.range_low if accum else rng.range_high
        noun = "accumulation" if accum else "distribution"
        side = "below the original range low" if accum else "above the original range high"
        evidence = (
            f"Price closed back {side} of {boundary:.2f} on {date}, giving back the "
            f"prior breakout — this {noun} read no longer holds."
        )
        return WyckoffEvent(
            event="range_failure", date=date, price=close,
            volume_ratio=volume_ratio(df, i), evidence=[evidence],
        )
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_wyckoff_invalidation.py -v`
Expected: PASS, 5 passed.

- [ ] **Step 5: Line count and ruff**

Run: `wc -l tradingagents/dataflows/wyckoff_invalidation.py`
Expected: `<= 150`.

Run: `ruff check tradingagents/dataflows/wyckoff_invalidation.py tests/test_wyckoff_invalidation.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/dataflows/wyckoff_invalidation.py tests/test_wyckoff_invalidation.py
git commit -m "feat(wyckoff): add breakout-failure (invalidation) check"
```

---

### Task 2: Wire invalidation into the accumulation/distribution wrappers

**Files:**
- Modify: `tradingagents/dataflows/wyckoff_accumulation.py`
- Modify: `tradingagents/dataflows/wyckoff_distribution.py`
- Test: `tests/test_wyckoff_accumulation.py`
- Test: `tests/test_wyckoff_distribution.py`

**Interfaces:**
- Consumes: `check_invalidation(df, atr_value, rng, direction, events, phase) -> WyckoffEvent | None` from Task 1's `tradingagents/dataflows/wyckoff_invalidation.py`.
- Produces: `AccumulationResult`/`DistributionResult` each gain `invalidated: bool = False`. When `True`, the dataclass's `events` list has a trailing `range_failure` `WyckoffEvent`. Task 3 (`wyckoff_bias.py`) reads `result.invalidated` on the object returned by `analyze_accumulation`/`analyze_distribution`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_wyckoff_accumulation.py`, add this line to the existing `test_textbook_sequence_reaches_phase_e_with_all_core_events` function, right after `assert result.confidence > 0.8`:

```python
    assert result.invalidated is False
```

Then append this new test after it:

```python
_REVERSAL = [(74.0, 73.0, 74.5, 1_500_000.0)]  # closes back below the original range low


@pytest.mark.unit
def test_reversal_after_back_up_marks_the_read_invalidated():
    closes, highs, lows, volumes = _base_bars()
    _extend(closes, highs, lows, volumes, _TEXTBOOK_EVENTS)
    _extend(closes, highs, lows, volumes, _AFTER_SPRING)
    _extend(closes, highs, lows, volumes, [], pad_bars=30, pad_bar=(85.0, 84.0, 86.0))
    _extend(closes, highs, lows, volumes, [(82.0, 81.0, 83.0, 1_000_000.0), (86.0, 85.0, 87.0, 1_000_000.0), (90.0, 89.0, 91.0, 1_000_000.0)])
    _extend(closes, highs, lows, volumes, _BREAKOUT)
    _extend(closes, highs, lows, volumes, [], pad_bars=5, pad_bar=(95.0, 94.0, 96.0))
    _extend(closes, highs, lows, volumes, _REVERSAL)

    result = analyze_accumulation(*_prepared_inputs(_to_df(closes, highs, lows, volumes)))

    assert result is not None
    assert result.phase == "E"
    assert result.invalidated is True
    assert result.events[-1].event == "range_failure"
```

In `tests/test_wyckoff_distribution.py`, add this line to the existing `test_textbook_sequence_reaches_phase_e_with_all_core_events` function, right after `assert result.confidence > 0.8`:

```python
    assert result.invalidated is False
```

Then append this new test after it:

```python
_REVERSAL = [(96.0, 95.5, 97.0, 1_500_000.0)]  # closes back above the original range high


@pytest.mark.unit
def test_reversal_after_upthrust_marks_the_read_invalidated():
    closes, highs, lows, volumes = _base_bars()
    _extend(closes, highs, lows, volumes, _TEXTBOOK_EVENTS)
    _extend(closes, highs, lows, volumes, _AFTER_UTAD)
    _extend(closes, highs, lows, volumes, [], pad_bars=30, pad_bar=(85.0, 84.0, 86.0))
    _extend(closes, highs, lows, volumes, [(88.0, 87.0, 89.0, 1_000_000.0), (84.0, 83.0, 85.0, 1_000_000.0), (80.0, 79.0, 81.0, 1_000_000.0)])
    _extend(closes, highs, lows, volumes, _BREAKDOWN)
    _extend(closes, highs, lows, volumes, [], pad_bars=5, pad_bar=(73.0, 72.0, 74.0))
    _extend(closes, highs, lows, volumes, _REVERSAL)

    result = analyze_distribution(*_prepared_inputs(_to_df(closes, highs, lows, volumes)))

    assert result is not None
    assert result.phase == "E"
    assert result.invalidated is True
    assert result.events[-1].event == "range_failure"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_wyckoff_accumulation.py tests/test_wyckoff_distribution.py -v`
Expected: FAIL — `AttributeError: 'AccumulationResult' object has no attribute 'invalidated'` (and same for `DistributionResult`).

- [ ] **Step 3: Wire `wyckoff_accumulation.py`**

Replace the full contents of `tradingagents/dataflows/wyckoff_accumulation.py` with:

```python
"""Accumulation-side Wyckoff event/phase detection.

Thin wrapper around wyckoff_events.detect_events: only runs when the shared
trading range formed after a downtrend (a precondition for accumulation),
and turns the generic event/phase result into a scored, direction-labeled
result the bias synthesizer can compare against the distribution side.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from tradingagents.dataflows.wyckoff_events import WyckoffEvent, confidence_for, detect_events
from tradingagents.dataflows.wyckoff_invalidation import check_invalidation
from tradingagents.dataflows.wyckoff_range import TradingRange


@dataclass
class AccumulationResult:
    events: list[WyckoffEvent]
    phase: str
    confidence: float
    invalidated: bool = False


def analyze_accumulation(
    df: pd.DataFrame, atr_value: float, rng: TradingRange | None
) -> AccumulationResult | None:
    """Try to read ``rng`` as an accumulation range; None if it doesn't qualify."""
    if rng is None or rng.prior_trend != "down":
        return None
    events, phase = detect_events(df, atr_value, rng, "accumulation")
    if phase == "undetermined":
        return None
    failure = check_invalidation(df, atr_value, rng, "accumulation", events, phase)
    if failure is not None:
        events = [*events, failure]
    return AccumulationResult(
        events=events, phase=phase, confidence=confidence_for(events, phase), invalidated=failure is not None
    )
```

- [ ] **Step 4: Wire `wyckoff_distribution.py`**

Replace the full contents of `tradingagents/dataflows/wyckoff_distribution.py` with:

```python
"""Distribution-side Wyckoff event/phase detection.

Mirror of wyckoff_accumulation.py: only runs when the shared trading range
formed after an uptrend (a precondition for distribution), and turns the
generic event/phase result into a scored, direction-labeled result the bias
synthesizer can compare against the accumulation side.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from tradingagents.dataflows.wyckoff_events import WyckoffEvent, confidence_for, detect_events
from tradingagents.dataflows.wyckoff_invalidation import check_invalidation
from tradingagents.dataflows.wyckoff_range import TradingRange


@dataclass
class DistributionResult:
    events: list[WyckoffEvent]
    phase: str
    confidence: float
    invalidated: bool = False


def analyze_distribution(
    df: pd.DataFrame, atr_value: float, rng: TradingRange | None
) -> DistributionResult | None:
    """Try to read ``rng`` as a distribution range; None if it doesn't qualify."""
    if rng is None or rng.prior_trend != "up":
        return None
    events, phase = detect_events(df, atr_value, rng, "distribution")
    if phase == "undetermined":
        return None
    failure = check_invalidation(df, atr_value, rng, "distribution", events, phase)
    if failure is not None:
        events = [*events, failure]
    return DistributionResult(
        events=events, phase=phase, confidence=confidence_for(events, phase), invalidated=failure is not None
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_wyckoff_accumulation.py tests/test_wyckoff_distribution.py -v`
Expected: PASS, all tests in both files (including the two new ones and the two modified ones).

- [ ] **Step 6: Ruff check**

Run: `ruff check tradingagents/dataflows/wyckoff_accumulation.py tradingagents/dataflows/wyckoff_distribution.py tests/test_wyckoff_accumulation.py tests/test_wyckoff_distribution.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add tradingagents/dataflows/wyckoff_accumulation.py tradingagents/dataflows/wyckoff_distribution.py tests/test_wyckoff_accumulation.py tests/test_wyckoff_distribution.py
git commit -m "feat(wyckoff): flag accumulation/distribution reads whose breakout reversed"
```

---

### Task 3: Wire invalidation into `wyckoff_bias.py`'s payload

**Files:**
- Modify: `tradingagents/dataflows/wyckoff_bias.py`
- Test: `tests/test_wyckoff_bias.py`

**Interfaces:**
- Consumes: `AccumulationResult.invalidated` / `DistributionResult.invalidated` from Task 2.
- Produces: `analyze_wyckoff_structure_from_data(...)`'s result dict gains a top-level `"invalidated": bool` key (always present on non-neutral reads). When `True`: `trading_range.status == "invalidated"`, `phase_bias == "neutral"`, `confidence == 0.0`, and neither `vsa_signals` nor `vsa_confidence_delta` are present (VSA is skipped).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_wyckoff_bias.py` (append at the end of the file):

```python
def _accumulation_invalidated_df() -> pd.DataFrame:
    down_len = 60
    closes = [150.0 - 70.0 * i / (down_len - 1) for i in range(down_len)]
    volumes = [1_000_000.0] * down_len
    for i in range(29):
        phase = i % 14
        val = 78.0 + phase * 2.0 if phase <= 7 else 92.0 - (phase - 7) * 2.0
        closes.append(val)
        volumes.append(1_000_000.0)
    volumes[down_len + 28] = 2_500_000.0
    highs = [c + 1.0 for c in closes]
    lows = [c - 1.0 for c in closes]
    bars = (
        [
            (85.0, 84.0, 86.0, 1e6), (88.0, 87.0, 89.0, 1e6), (90.0, 89.0, 91.0, 1e6),
            (84.0, 83.0, 85.0, 1e6), (78.0, 77.0, 79.0, 1e6), (81.0, 80.0, 82.0, 1e6),
            (77.3, 62.0, 78.0, 1e6),
        ]
        + [(80.0, 79.0, 81.0, 1e6)] * 40
        + [
            (95.0, 94.5, 95.5, 2.0e6),   # sign_of_strength
            (93.0, 92.5, 93.5, 1.0e6),   # last_point_of_support
            (97.0, 96.5, 97.5, 1.2e6),   # back_up
            (75.0, 74.5, 75.5, 1.5e6),   # reversal: closes back below range_low
        ]
    )
    for c, low, high, vol in bars:
        closes.append(c)
        highs.append(high)
        lows.append(low)
        volumes.append(vol)
    return _to_df(closes, highs, lows, volumes)


@pytest.mark.unit
def test_invalidated_accumulation_forces_neutral_and_skips_vsa():
    df = _accumulation_invalidated_df()
    result = analyze_wyckoff_structure_from_data(df, df["Date"].iloc[-1].strftime("%Y-%m-%d"))

    assert result["current_phase"] == "E"
    assert result["invalidated"] is True
    assert result["phase_bias"] == "neutral"
    assert result["confidence"] == 0.0
    assert result["trading_range"]["status"] == "invalidated"
    assert result["events"][-1]["event"] == "range_failure"
    assert "vsa_signals" not in result
    assert "vsa_confidence_delta" not in result


@pytest.mark.unit
def test_non_invalidated_accumulation_has_invalidated_false():
    df = _accumulation_df()
    result = analyze_wyckoff_structure_from_data(df, df["Date"].iloc[-1].strftime("%Y-%m-%d"))

    assert result["invalidated"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_wyckoff_bias.py -k invalidat -v`
Expected: FAIL — `KeyError: 'invalidated'`.

- [ ] **Step 3: Wire `wyckoff_bias.py`**

In `tradingagents/dataflows/wyckoff_bias.py`, replace the `_payload` function:

```python
def _payload(kind: Literal["accumulation", "distribution"], rng, result: AccumulationResult | DistributionResult) -> dict[str, Any]:
    return {
        "symbol": "",
        "trading_range": {
            "kind": kind,
            "range_high": round(rng.range_high, 4),
            "range_low": round(rng.range_low, 4),
            "start_date": rng.start_date,
            "status": _STATUS_BY_PHASE.get(result.phase, "forming"),
        },
        "events": [asdict(e) for e in result.events],
        "current_phase": result.phase,
        "phase_bias": "bullish" if kind == "accumulation" else "bearish",
        "confidence": result.confidence,
        "dominant_weight": DOMINANT_WEIGHT,
        "weight_note": WEIGHT_NOTE,
    }
```

with:

```python
def _payload(kind: Literal["accumulation", "distribution"], rng, result: AccumulationResult | DistributionResult) -> dict[str, Any]:
    payload = {
        "symbol": "",
        "trading_range": {
            "kind": kind,
            "range_high": round(rng.range_high, 4),
            "range_low": round(rng.range_low, 4),
            "start_date": rng.start_date,
            "status": _STATUS_BY_PHASE.get(result.phase, "forming"),
        },
        "events": [asdict(e) for e in result.events],
        "current_phase": result.phase,
        "phase_bias": "bullish" if kind == "accumulation" else "bearish",
        "confidence": result.confidence,
        "dominant_weight": DOMINANT_WEIGHT,
        "weight_note": WEIGHT_NOTE,
        "invalidated": result.invalidated,
    }
    if result.invalidated:
        payload["trading_range"]["status"] = "invalidated"
        payload["phase_bias"] = "neutral"
        payload["confidence"] = 0.0
    return payload
```

Then in `analyze_wyckoff_structure_from_data`, replace:

```python
    result = {"analysis_date": curr_date}
    if accumulation is not None:
        result.update(_payload("accumulation", rng, accumulation))
    elif distribution is not None:
        result.update(_payload("distribution", rng, distribution))
    else:
        result.update(_neutral())
        return result

    vsa_signals, delta = analyze_vsa(df, atr_value, rng, result["phase_bias"], curr_date)
```

with:

```python
    result = {"analysis_date": curr_date}
    if accumulation is not None:
        result.update(_payload("accumulation", rng, accumulation))
    elif distribution is not None:
        result.update(_payload("distribution", rng, distribution))
    else:
        result.update(_neutral())
        return result

    if result["invalidated"]:
        return result

    vsa_signals, delta = analyze_vsa(df, atr_value, rng, result["phase_bias"], curr_date)
```

(the two lines after that, `result["vsa_signals"] = ...` and the rest, are unchanged).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_wyckoff_bias.py -v`
Expected: PASS, all tests in the file (12 total: the 10 pre-existing plus the 2 new ones).

- [ ] **Step 5: Ruff check**

Run: `ruff check tradingagents/dataflows/wyckoff_bias.py tests/test_wyckoff_bias.py`
Expected: no errors.

- [ ] **Step 6: Full-module regression check**

Run: `pytest -q tests/test_wyckoff_range.py tests/test_wyckoff_events.py tests/test_wyckoff_accumulation.py tests/test_wyckoff_distribution.py tests/test_wyckoff_vsa_bar_signals.py tests/test_wyckoff_vsa_range_signals.py tests/test_wyckoff_vsa.py tests/test_wyckoff_bias.py tests/test_wyckoff_invalidation.py`
Expected: PASS, no failures anywhere in the Wyckoff module (confirms Tasks 1-3 didn't regress Stage 1/Stage 2).

Run: `ruff check tradingagents/dataflows/wyckoff_invalidation.py tradingagents/dataflows/wyckoff_accumulation.py tradingagents/dataflows/wyckoff_distribution.py tradingagents/dataflows/wyckoff_bias.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add tradingagents/dataflows/wyckoff_bias.py tests/test_wyckoff_bias.py
git commit -m "feat(wyckoff): neutralize confidence and skip VSA on an invalidated read"
```

---

## Acceptance Criteria (from spec)

- No detection logic in `wyckoff_range.py`/`wyckoff_events.py` changes.
- `wyckoff_events.py` stays at 150 lines (untouched).
- New `wyckoff_invalidation.py` stays at or under 150 lines.
- A Phase D/E read that reverses through the original boundary is reported with `phase_bias: "neutral"`, `confidence: 0.0`, `status: "invalidated"`, and `invalidated: true` — never presented as a live confirmed directional call.
- All existing Wyckoff/VSA/market-analyst tests still pass unmodified.
- No future-data leakage: the invalidation scan only ever looks at bars already inside the `df` passed in.

> This module is for research and analysis support only; it does not constitute investment advice and does not place trades.
