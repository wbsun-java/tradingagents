# Wyckoff Stage 2 VSA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Volume Spread Analysis (VSA) as a bounded confidence adjustment on top of the existing, completed Wyckoff Stage 1 structural read, per `docs/superpowers/specs/2026-07-09-wyckoff-vsa-design.md`.

**Architecture:** Three new files — `wyckoff_vsa_signals.py` (6 bar-only detector functions), `wyckoff_vsa_range_signals.py` (2 range-aware detector functions, split out to respect the 150-line-per-file cap), and `wyckoff_vsa.py` (thin orchestrator: range-window filtering, confirming/contradicting tagging, bounded confidence delta) — plus a small wiring edit to the existing `wyckoff_bias.py`.

**Tech Stack:** Python, pandas (existing project stack — no new dependencies).

## Global Constraints

- Every newly created file is at most 150 lines (CLAUDE.md). If a test file would exceed this, split it by responsibility rather than growing past the cap.
- No upstream file may be modified without explicit user approval for that exact file (CLAUDE.md). All files this plan touches (`wyckoff_bias.py` and its tests) or creates are project-custom, created 2026-07-01–07 for the Wyckoff feature — not upstream. This plan does not touch `market_analyst.py`, `trading_graph.py`, or `wyckoff_tools.py`.
- No signal may be computed from data after `curr_date` (plan principle 2 / spec).
- Every emitted VSA signal must carry an auditable date, volume-ratio, and evidence string explaining the effort-vs-result reasoning (spec principle 4).
- VSA may only move `confidence`, and only within `[-0.15, +0.15]` net, clamped to `[0.0, 1.0]` after combining with Stage 1's confidence. It must never change `phase_bias`, `current_phase`, or `dominant_weight`.
- Per CLAUDE.md's default verification policy: this is an isolated additive change to custom files, so run `pytest -q tests/test_wyckoff_vsa_bar_signals.py tests/test_wyckoff_vsa_range_signals.py tests/test_wyckoff_vsa.py tests/test_wyckoff_bias.py` and `ruff check tradingagents/dataflows/wyckoff_vsa_signals.py tradingagents/dataflows/wyckoff_vsa_range_signals.py tradingagents/dataflows/wyckoff_vsa.py tradingagents/dataflows/wyckoff_bias.py tests/test_wyckoff_vsa_bar_signals.py tests/test_wyckoff_vsa_range_signals.py tests/test_wyckoff_vsa.py tests/test_wyckoff_bias.py` — not the full suite.
- Existing helpers to reuse, do not reimplement: `volume_ratio(df, index, window=20)` and `TradingRange` from `tradingagents/dataflows/wyckoff_range.py`.

---

### Task 1: VSA signal dataclass + no_demand / no_supply / stopping_volume

**Files:**
- Create: `tradingagents/dataflows/wyckoff_vsa_signals.py`
- Test: `tests/test_wyckoff_vsa_bar_signals.py`

**Interfaces:**
- Produces: `VsaSignal` dataclass (`signal: str`, `native_direction: Literal["bullish", "bearish"]`, `volume_ratio: float | None`, `evidence: str`); `no_demand(df, i, atr_value) -> VsaSignal | None`; `no_supply(df, i, atr_value) -> VsaSignal | None`; `stopping_volume(df, i, atr_value) -> VsaSignal | None`; module constants `NARROW_SPREAD_ATR = 0.5`, `STOPPING_VOLUME_SPREAD_ATR = 1.5`, `STOPPING_VOLUME_RATIO = 2.0`, `LOW_VOLUME_RATIO = 1.0`.
- Consumes: `volume_ratio` from `tradingagents.dataflows.wyckoff_range`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_wyckoff_vsa_bar_signals.py`:

```python
"""Unit tests for the bar-only VSA detectors (no rng/boundary needed)."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.wyckoff_vsa_signals import no_demand, no_supply, stopping_volume

ATR = 2.0


def _df(rows: list[tuple[str, float, float, float, float]]) -> pd.DataFrame:
    dates, closes, highs, lows, volumes = zip(*rows)
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(dates),
            "Open": closes,
            "High": highs,
            "Low": lows,
            "Close": closes,
            "Volume": volumes,
        }
    )


@pytest.mark.unit
def test_no_demand_fires_on_up_bar_narrow_spread_low_volume():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.5, 99.5, 1_000_000.0),
            ("2023-01-03", 100.5, 100.8, 100.3, 500_000.0),
        ]
    )
    hit = no_demand(df, 1, ATR)
    assert hit is not None
    assert hit.native_direction == "bearish"
    assert hit.volume_ratio == pytest.approx(0.5)


@pytest.mark.unit
def test_no_demand_silent_when_volume_is_not_low():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.5, 99.5, 1_000_000.0),
            ("2023-01-03", 100.5, 100.8, 100.3, 1_500_000.0),
        ]
    )
    assert no_demand(df, 1, ATR) is None


@pytest.mark.unit
def test_no_supply_fires_on_down_bar_narrow_spread_low_volume():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.5, 99.5, 1_000_000.0),
            ("2023-01-03", 99.5, 99.8, 99.2, 500_000.0),
        ]
    )
    hit = no_supply(df, 1, ATR)
    assert hit is not None
    assert hit.native_direction == "bullish"


@pytest.mark.unit
def test_stopping_volume_fires_on_wide_down_bar_absorbed_high_volume():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.5, 99.5, 1_000_000.0),
            ("2023-01-03", 98.0, 99.0, 95.0, 2_500_000.0),
        ]
    )
    hit = stopping_volume(df, 1, ATR)
    assert hit is not None
    assert hit.native_direction == "bullish"
    assert hit.volume_ratio == pytest.approx(2.5)


@pytest.mark.unit
def test_stopping_volume_silent_when_spread_is_not_wide():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.5, 99.5, 1_000_000.0),
            ("2023-01-03", 98.0, 98.5, 97.5, 2_500_000.0),
        ]
    )
    assert stopping_volume(df, 1, ATR) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_wyckoff_vsa_bar_signals.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'tradingagents.dataflows.wyckoff_vsa_signals'`

- [ ] **Step 3: Implement the module**

Create `tradingagents/dataflows/wyckoff_vsa_signals.py`:

```python
"""Per-bar Volume Spread Analysis (VSA) detectors: classic effort-vs-result
signals scored against ATR (spread) and 20-day average volume, each tagged
with the market direction it natively supports. wyckoff_vsa.py decides which
bars to scan and whether a hit confirms or contradicts the active Wyckoff
phase_bias; this module only answers "does this bar match this pattern."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from tradingagents.dataflows.wyckoff_range import volume_ratio

NativeDirection = Literal["bullish", "bearish"]

NARROW_SPREAD_ATR = 0.5
STOPPING_VOLUME_SPREAD_ATR = 1.5
STOPPING_VOLUME_RATIO = 2.0
LOW_VOLUME_RATIO = 1.0


@dataclass
class VsaSignal:
    signal: str
    native_direction: NativeDirection
    volume_ratio: float | None
    evidence: str


def _spread(df: pd.DataFrame, i: int) -> float:
    return float(df.at[i, "High"] - df.at[i, "Low"])


def _prev_close(df: pd.DataFrame, i: int) -> float | None:
    return float(df.at[i - 1, "Close"]) if i >= 1 else None


def no_demand(df: pd.DataFrame, i: int, atr_value: float) -> VsaSignal | None:
    prev = _prev_close(df, i)
    vr = volume_ratio(df, i)
    if prev is None or vr is None:
        return None
    close, spread = float(df.at[i, "Close"]), _spread(df, i)
    if close > prev and spread < NARROW_SPREAD_ATR * atr_value and vr < LOW_VOLUME_RATIO:
        return VsaSignal(
            "no_demand", "bearish", vr,
            f"up bar on {vr:.1f}x avg volume with a spread of only {spread:.2f} — weak buying interest",
        )
    return None


def no_supply(df: pd.DataFrame, i: int, atr_value: float) -> VsaSignal | None:
    prev = _prev_close(df, i)
    vr = volume_ratio(df, i)
    if prev is None or vr is None:
        return None
    close, spread = float(df.at[i, "Close"]), _spread(df, i)
    if close < prev and spread < NARROW_SPREAD_ATR * atr_value and vr < LOW_VOLUME_RATIO:
        return VsaSignal(
            "no_supply", "bullish", vr,
            f"down bar on {vr:.1f}x avg volume with a spread of only {spread:.2f} — weak selling pressure",
        )
    return None


def stopping_volume(df: pd.DataFrame, i: int, atr_value: float) -> VsaSignal | None:
    prev = _prev_close(df, i)
    vr = volume_ratio(df, i)
    if prev is None or vr is None:
        return None
    close = float(df.at[i, "Close"])
    high, low = float(df.at[i, "High"]), float(df.at[i, "Low"])
    spread = high - low
    if (
        close < prev
        and spread > STOPPING_VOLUME_SPREAD_ATR * atr_value
        and vr > STOPPING_VOLUME_RATIO
        and close >= (high + low) / 2
    ):
        return VsaSignal(
            "stopping_volume", "bullish", vr,
            f"wide-range down bar on {vr:.1f}x avg volume, closed in the upper half of its range — absorption of selling",
        )
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_wyckoff_vsa_bar_signals.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/dataflows/wyckoff_vsa_signals.py tests/test_wyckoff_vsa_bar_signals.py
git commit -m "feat(wyckoff): add VSA no_demand/no_supply/stopping_volume detectors"
```

---

### Task 2: climax_bar / effort_no_result_up / effort_no_result_down

**Files:**
- Modify: `tradingagents/dataflows/wyckoff_vsa_signals.py` (append)
- Modify: `tests/test_wyckoff_vsa_bar_signals.py` (append)

**Interfaces:**
- Produces: `climax_bar(df, i, atr_value, window=10) -> VsaSignal | None`; `effort_no_result_up(df, i, atr_value) -> VsaSignal | None`; `effort_no_result_down(df, i, atr_value) -> VsaSignal | None`; module constants `WIDE_SPREAD_ATR = 1.2`, `CLIMAX_VOLUME_RATIO = 3.0`, `ELEVATED_VOLUME_RATIO = 1.5`.
- Consumes: nothing new beyond Task 1.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_wyckoff_vsa_bar_signals.py` (add to the existing import line so it reads `from tradingagents.dataflows.wyckoff_vsa_signals import climax_bar, effort_no_result_down, effort_no_result_up, no_demand, no_supply, stopping_volume`):

```python
@pytest.mark.unit
def test_climax_bar_fires_on_new_low_wide_range_extreme_volume():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.5, 99.5, 1_000_000.0),
            ("2023-01-03", 99.0, 99.5, 98.5, 1_000_000.0),
            ("2023-01-04", 90.0, 91.0, 80.0, 4_000_000.0),
        ]
    )
    hit = climax_bar(df, 2, ATR)
    assert hit is not None
    assert hit.native_direction == "bullish"


@pytest.mark.unit
def test_climax_bar_silent_when_spread_is_not_wide():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.5, 99.5, 1_000_000.0),
            ("2023-01-03", 99.0, 99.5, 98.5, 1_000_000.0),
            ("2023-01-04", 95.0, 95.5, 94.5, 4_000_000.0),
        ]
    )
    assert climax_bar(df, 2, ATR) is None


@pytest.mark.unit
def test_effort_no_result_up_fires_when_high_volume_fails_to_hold_close():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.4, 99.6, 1_000_000.0),
            ("2023-01-03", 99.7, 100.4, 99.6, 2_000_000.0),
        ]
    )
    hit = effort_no_result_up(df, 1, ATR)
    assert hit is not None
    assert hit.native_direction == "bearish"


@pytest.mark.unit
def test_effort_no_result_down_fires_when_high_volume_fails_to_break_close():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.4, 99.6, 1_000_000.0),
            ("2023-01-03", 100.3, 100.4, 99.6, 2_000_000.0),
        ]
    )
    hit = effort_no_result_down(df, 1, ATR)
    assert hit is not None
    assert hit.native_direction == "bullish"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_wyckoff_vsa_bar_signals.py -v`
Expected: FAIL — `ImportError: cannot import name 'climax_bar'`

- [ ] **Step 3: Implement the detectors**

Append to `tradingagents/dataflows/wyckoff_vsa_signals.py`, and add `WIDE_SPREAD_ATR = 1.2`, `CLIMAX_VOLUME_RATIO = 3.0`, `ELEVATED_VOLUME_RATIO = 1.5` next to the existing module constants:

```python
def climax_bar(df: pd.DataFrame, i: int, atr_value: float, window: int = 10) -> VsaSignal | None:
    vr = volume_ratio(df, i)
    if vr is None or vr < CLIMAX_VOLUME_RATIO or _spread(df, i) <= WIDE_SPREAD_ATR * atr_value:
        return None
    lo = max(0, i - window)
    low_i, high_i = float(df.at[i, "Low"]), float(df.at[i, "High"])
    if low_i <= df["Low"].iloc[lo : i + 1].min():
        return VsaSignal(
            "climax_bar", "bullish", vr,
            f"{vr:.1f}x avg volume on a wide-range bar making a new {window}-bar low — capitulation",
        )
    if high_i >= df["High"].iloc[lo : i + 1].max():
        return VsaSignal(
            "climax_bar", "bearish", vr,
            f"{vr:.1f}x avg volume on a wide-range bar making a new {window}-bar high — blow-off",
        )
    return None


def effort_no_result_up(df: pd.DataFrame, i: int, atr_value: float) -> VsaSignal | None:
    vr = volume_ratio(df, i)
    spread = _spread(df, i)
    if vr is None or vr < ELEVATED_VOLUME_RATIO or not 0 < spread < NARROW_SPREAD_ATR * atr_value:
        return None
    close, low = float(df.at[i, "Close"]), float(df.at[i, "Low"])
    if (close - low) <= 0.3 * spread:
        return VsaSignal(
            "effort_no_result_up", "bearish", vr,
            f"{vr:.1f}x avg volume but closed near the bar's low — buying effort failed to produce a result",
        )
    return None


def effort_no_result_down(df: pd.DataFrame, i: int, atr_value: float) -> VsaSignal | None:
    vr = volume_ratio(df, i)
    spread = _spread(df, i)
    if vr is None or vr < ELEVATED_VOLUME_RATIO or not 0 < spread < NARROW_SPREAD_ATR * atr_value:
        return None
    close, high = float(df.at[i, "Close"]), float(df.at[i, "High"])
    if (high - close) <= 0.3 * spread:
        return VsaSignal(
            "effort_no_result_down", "bullish", vr,
            f"{vr:.1f}x avg volume but closed near the bar's high — selling effort failed to produce a result",
        )
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_wyckoff_vsa_bar_signals.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/dataflows/wyckoff_vsa_signals.py tests/test_wyckoff_vsa_bar_signals.py
git commit -m "feat(wyckoff): add VSA climax_bar and effort-no-result detectors"
```

---

### Task 3: test_bar / upthrust_shakeout_on_volume (range-aware detectors)

**Amendment (post-Task-2):** `wyckoff_vsa_signals.py` is already 151 lines
after Task 2 (over the 150-line-per-file cap), so Task 3's two detectors go
in a new sibling file, `wyckoff_vsa_range_signals.py`, instead of appending
to `wyckoff_vsa_signals.py`. This mirrors the test-file split the plan
already uses (`test_wyckoff_vsa_bar_signals.py` vs
`test_wyckoff_vsa_range_signals.py`) and CLAUDE.md's guidance to split by
signal type when a file grows past the cap. Task 4's orchestrator import
list is updated accordingly (see Task 4 below).

**Files:**
- Create: `tradingagents/dataflows/wyckoff_vsa_range_signals.py`
- Create: `tests/test_wyckoff_vsa_range_signals.py`

**Interfaces:**
- Produces: `test_bar(df, i, atr_value, rng: TradingRange) -> VsaSignal | None`; `upthrust_shakeout_on_volume(df, i, atr_value, rng: TradingRange) -> VsaSignal | None`; module constant `ABOVE_AVERAGE_VOLUME_RATIO = 1.3`.
- Consumes: `VsaSignal`, `_spread`, `NARROW_SPREAD_ATR`, `WIDE_SPREAD_ATR`, `LOW_VOLUME_RATIO` from `tradingagents.dataflows.wyckoff_vsa_signals`; `volume_ratio`, `TradingRange` from `tradingagents.dataflows.wyckoff_range`; all detectors from Tasks 1–2 (for the "all detectors silent" test).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_wyckoff_vsa_range_signals.py`:

```python
"""Unit tests for range-aware VSA detectors and the full detector set's
negative path on a plain, unremarkable bar."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.wyckoff_range import TradingRange
from tradingagents.dataflows.wyckoff_vsa_range_signals import test_bar, upthrust_shakeout_on_volume
from tradingagents.dataflows.wyckoff_vsa_signals import (
    climax_bar,
    effort_no_result_down,
    effort_no_result_up,
    no_demand,
    no_supply,
    stopping_volume,
)

ATR = 2.0
RNG = TradingRange(
    range_high=105.0, range_low=95.0, start_index=0, start_date="2023-01-02",
    high_touches=[], low_touches=[], prior_trend="down",
)


def _df(rows: list[tuple[str, float, float, float, float]]) -> pd.DataFrame:
    dates, closes, highs, lows, volumes = zip(*rows)
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(dates),
            "Open": closes,
            "High": highs,
            "Low": lows,
            "Close": closes,
            "Volume": volumes,
        }
    )


@pytest.mark.unit
def test_test_bar_fires_bullish_near_range_low():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.4, 99.6, 1_000_000.0),
            ("2023-01-03", 94.7, 95.3, 94.5, 700_000.0),
        ]
    )
    hit = test_bar(df, 1, ATR, RNG)
    assert hit is not None
    assert hit.native_direction == "bullish"


@pytest.mark.unit
def test_test_bar_fires_bearish_near_range_high():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.4, 99.6, 1_000_000.0),
            ("2023-01-03", 105.3, 105.5, 104.7, 700_000.0),
        ]
    )
    hit = test_bar(df, 1, ATR, RNG)
    assert hit is not None
    assert hit.native_direction == "bearish"


@pytest.mark.unit
def test_upthrust_shakeout_fires_bullish_on_pierce_and_close_back_inside_low():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.4, 99.6, 1_000_000.0),
            ("2023-01-03", 96.0, 97.0, 93.0, 1_500_000.0),
        ]
    )
    hit = upthrust_shakeout_on_volume(df, 1, ATR, RNG)
    assert hit is not None
    assert hit.native_direction == "bullish"


@pytest.mark.unit
def test_upthrust_shakeout_fires_bearish_on_pierce_and_close_back_inside_high():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.4, 99.6, 1_000_000.0),
            ("2023-01-03", 104.5, 108.0, 104.0, 1_500_000.0),
        ]
    )
    hit = upthrust_shakeout_on_volume(df, 1, ATR, RNG)
    assert hit is not None
    assert hit.native_direction == "bearish"


@pytest.mark.unit
def test_all_detectors_stay_silent_on_an_unremarkable_bar():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.6, 99.4, 1_000_000.0),
            ("2023-01-03", 100.5, 101.1, 99.9, 1_050_000.0),
        ]
    )
    assert no_demand(df, 1, ATR) is None
    assert no_supply(df, 1, ATR) is None
    assert stopping_volume(df, 1, ATR) is None
    assert climax_bar(df, 1, ATR) is None
    assert effort_no_result_up(df, 1, ATR) is None
    assert effort_no_result_down(df, 1, ATR) is None
    assert test_bar(df, 1, ATR, RNG) is None
    assert upthrust_shakeout_on_volume(df, 1, ATR, RNG) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_wyckoff_vsa_range_signals.py -v`
Expected: FAIL — `ImportError: cannot import name 'test_bar'`

- [ ] **Step 3: Implement the detectors**

Create `tradingagents/dataflows/wyckoff_vsa_range_signals.py`:

```python
"""Range-aware VSA detectors: test_bar and upthrust/shakeout-on-volume need
the active Wyckoff trading range's boundaries, unlike the bar-only detectors
in wyckoff_vsa_signals.py. Split out to keep both files under the
150-line-per-file cap.
"""

from __future__ import annotations

import pandas as pd

from tradingagents.dataflows.wyckoff_range import TradingRange, volume_ratio
from tradingagents.dataflows.wyckoff_vsa_signals import (
    LOW_VOLUME_RATIO,
    NARROW_SPREAD_ATR,
    WIDE_SPREAD_ATR,
    VsaSignal,
    _spread,
)

ABOVE_AVERAGE_VOLUME_RATIO = 1.3


def test_bar(df: pd.DataFrame, i: int, atr_value: float, rng: TradingRange) -> VsaSignal | None:
    vr = volume_ratio(df, i)
    spread = _spread(df, i)
    if vr is None or vr >= LOW_VOLUME_RATIO or spread >= NARROW_SPREAD_ATR * atr_value:
        return None
    tolerance = max(atr_value * 0.6, rng.range_low * 0.02)
    low, high, close = float(df.at[i, "Low"]), float(df.at[i, "High"]), float(df.at[i, "Close"])
    if abs(low - rng.range_low) <= tolerance and (close - low) <= 0.3 * spread:
        return VsaSignal(
            "test_bar", "bullish", vr,
            f"quiet retest near {rng.range_low:.2f} on {vr:.1f}x avg volume, closed off the low",
        )
    if abs(high - rng.range_high) <= tolerance and (high - close) <= 0.3 * spread:
        return VsaSignal(
            "test_bar", "bearish", vr,
            f"quiet retest near {rng.range_high:.2f} on {vr:.1f}x avg volume, closed off the high",
        )
    return None


def upthrust_shakeout_on_volume(df: pd.DataFrame, i: int, atr_value: float, rng: TradingRange) -> VsaSignal | None:
    vr = volume_ratio(df, i)
    if vr is None or vr < ABOVE_AVERAGE_VOLUME_RATIO or _spread(df, i) <= WIDE_SPREAD_ATR * atr_value:
        return None
    buffer = atr_value * 0.2
    low, high, close = float(df.at[i, "Low"]), float(df.at[i, "High"]), float(df.at[i, "Close"])
    if low < rng.range_low - buffer and close >= rng.range_low:
        return VsaSignal(
            "upthrust_shakeout_on_volume", "bullish", vr,
            f"pierced {rng.range_low:.2f} intrabar on {vr:.1f}x avg volume and closed back inside the range — shakeout, not a breakdown",
        )
    if high > rng.range_high + buffer and close <= rng.range_high:
        return VsaSignal(
            "upthrust_shakeout_on_volume", "bearish", vr,
            f"pierced {rng.range_high:.2f} intrabar on {vr:.1f}x avg volume and closed back inside the range — upthrust, not a breakout",
        )
    return None
```

Note: `_spread` is a private (underscore-prefixed) helper in `wyckoff_vsa_signals.py` being imported cross-module here — this is an accepted, deliberate exception for this closely-related sibling file (both are the two halves of one detector set split only to satisfy the line cap), not a general pattern to repeat elsewhere.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_wyckoff_vsa_bar_signals.py tests/test_wyckoff_vsa_range_signals.py -v`
Expected: PASS (14 passed)

- [ ] **Step 5: Run ruff and commit**

```bash
ruff check tradingagents/dataflows/wyckoff_vsa_range_signals.py tests/test_wyckoff_vsa_range_signals.py
wc -l tradingagents/dataflows/wyckoff_vsa_signals.py tradingagents/dataflows/wyckoff_vsa_range_signals.py
git add tradingagents/dataflows/wyckoff_vsa_range_signals.py tests/test_wyckoff_vsa_range_signals.py
git commit -m "feat(wyckoff): add VSA test_bar and upthrust/shakeout-on-volume detectors"
```

Confirm both files are at or under 150 lines before committing.

---

### Task 4: VSA orchestrator (`analyze_vsa`)

**Files:**
- Create: `tradingagents/dataflows/wyckoff_vsa.py`
- Test: `tests/test_wyckoff_vsa.py`

**Interfaces:**
- Consumes: 6 bar-only detectors from `wyckoff_vsa_signals.py` (Tasks 1–2) plus `test_bar`/`upthrust_shakeout_on_volume` from `wyckoff_vsa_range_signals.py` (Task 3); `TradingRange` from `wyckoff_range.py`.
- Produces: `analyze_vsa(df, atr_value, rng, phase_bias, curr_date) -> tuple[list[dict], float]` where each dict has keys `signal`, `date`, `direction` (`"confirming"`/`"contradicting"`), `volume_ratio`, `evidence` (list[str]); module constants `PER_SIGNAL_DELTA = 0.05`, `MAX_TOTAL_DELTA = 0.15`. This is what Task 5 (`wyckoff_bias.py`) calls.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_wyckoff_vsa.py`:

```python
"""Unit tests for the VSA orchestrator: range-window scoping, curr_date
cutoff, and the bounded confidence delta."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.wyckoff_range import TradingRange
from tradingagents.dataflows.wyckoff_vsa import analyze_vsa

ATR = 2.0
RNG = TradingRange(
    range_high=105.0, range_low=95.0, start_index=2, start_date="2023-01-04",
    high_touches=[], low_touches=[], prior_trend="down",
)


def _df(rows: list[tuple[str, float, float, float, float]]) -> pd.DataFrame:
    dates, closes, highs, lows, volumes = zip(*rows)
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(dates),
            "Open": closes,
            "High": highs,
            "Low": lows,
            "Close": closes,
            "Volume": volumes,
        }
    )


@pytest.mark.unit
def test_single_confirming_signal_adds_bounded_delta():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.5, 99.5, 1_000_000.0),
            ("2023-01-03", 99.0, 99.4, 98.6, 500_000.0),
            ("2023-01-04", 97.0, 97.4, 96.6, 500_000.0),
        ]
    )
    signals, delta = analyze_vsa(df, ATR, RNG, "bullish", "2023-01-04")
    assert len(signals) == 1
    assert signals[0]["signal"] == "no_supply"
    assert signals[0]["direction"] == "confirming"
    assert delta == pytest.approx(0.05)


@pytest.mark.unit
def test_single_contradicting_signal_subtracts_bounded_delta():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.5, 99.5, 1_000_000.0),
            ("2023-01-03", 99.0, 99.4, 98.6, 500_000.0),
            ("2023-01-04", 97.0, 97.4, 96.6, 500_000.0),
        ]
    )
    signals, delta = analyze_vsa(df, ATR, RNG, "bearish", "2023-01-04")
    assert len(signals) == 1
    assert signals[0]["direction"] == "contradicting"
    assert delta == pytest.approx(-0.05)


@pytest.mark.unit
def test_confidence_delta_is_clamped_at_the_positive_cap():
    # 6 cycles of [no_supply signal bar, 2 flat filler bars]: each signal bar
    # drops price 1.0 from the prior filler's close on low relative volume,
    # narrow spread, far from both range boundaries — only no_supply fires.
    rows = [("2023-01-02", 100.0, 100.4, 99.6, 1_000_000.0)]
    price, day = 100.0, 3
    for _ in range(6):
        price -= 1.0
        rows.append((f"2023-01-{day:02d}", price, price + 0.3, price - 0.3, 400_000.0))
        day += 1
        for _ in range(2):
            rows.append((f"2023-01-{day:02d}", price, price + 0.4, price - 0.4, 1_000_000.0))
            day += 1
    df = _df(rows)
    rng = TradingRange(
        range_high=105.0, range_low=80.0, start_index=1, start_date=rows[1][0],
        high_touches=[], low_touches=[], prior_trend="down",
    )
    signals, delta = analyze_vsa(df, ATR, rng, "bullish", rows[-1][0])
    assert len(signals) == 6
    assert all(s["signal"] == "no_supply" and s["direction"] == "confirming" for s in signals)
    assert delta == pytest.approx(0.15)


@pytest.mark.unit
def test_bars_before_range_start_are_excluded():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.5, 99.5, 1_000_000.0),
            ("2023-01-03", 99.0, 99.4, 98.6, 500_000.0),  # would fire no_supply, but before start_index
            ("2023-01-04", 97.0, 97.4, 96.6, 500_000.0),  # start_index — the only bar in scope
        ]
    )
    signals, delta = analyze_vsa(df, ATR, RNG, "bullish", "2023-01-04")
    assert len(signals) == 1
    assert signals[0]["date"] == "2023-01-04"


@pytest.mark.unit
def test_bars_after_curr_date_are_excluded():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.4, 99.6, 1_000_000.0),
            ("2023-01-10", 99.0, 99.4, 98.6, 500_000.0),  # dated after curr_date, would otherwise fire
        ]
    )
    rng = TradingRange(
        range_high=105.0, range_low=95.0, start_index=0, start_date="2023-01-02",
        high_touches=[], low_touches=[], prior_trend="down",
    )
    signals, delta = analyze_vsa(df, ATR, rng, "bullish", "2023-01-05")
    assert signals == []
    assert delta == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_wyckoff_vsa.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tradingagents.dataflows.wyckoff_vsa'`

- [ ] **Step 3: Implement the orchestrator**

Create `tradingagents/dataflows/wyckoff_vsa.py`:

```python
"""Stage 2 VSA orchestration: scores per-bar effort-vs-result signals across
the Stage 1 trading range and folds them into a bounded confidence
adjustment, without altering phase_bias or current_phase (plan principles
1 and 6 — VSA aids an existing structural read, it never stands alone).
"""

from __future__ import annotations

from typing import Literal

import pandas as pd

from tradingagents.dataflows.wyckoff_range import TradingRange
from tradingagents.dataflows.wyckoff_vsa_range_signals import test_bar, upthrust_shakeout_on_volume
from tradingagents.dataflows.wyckoff_vsa_signals import (
    climax_bar,
    effort_no_result_down,
    effort_no_result_up,
    no_demand,
    no_supply,
    stopping_volume,
)

PhaseBias = Literal["bullish", "bearish"]

PER_SIGNAL_DELTA = 0.05
MAX_TOTAL_DELTA = 0.15

_BAR_ONLY_DETECTORS = (
    no_demand, no_supply, stopping_volume, climax_bar, effort_no_result_up, effort_no_result_down,
)
_RANGE_AWARE_DETECTORS = (test_bar, upthrust_shakeout_on_volume)


def analyze_vsa(
    df: pd.DataFrame, atr_value: float, rng: TradingRange, phase_bias: PhaseBias, curr_date: str
) -> tuple[list[dict], float]:
    """Score VSA signals from rng.start_index through curr_date.

    Returns (vsa_signals, confidence_delta); delta is bounded to
    [-MAX_TOTAL_DELTA, +MAX_TOTAL_DELTA].
    """
    end_ts = pd.Timestamp(curr_date)
    signals: list[dict] = []
    delta = 0.0
    for i in range(rng.start_index, len(df)):
        if df.at[i, "Date"] > end_ts:
            break
        hits = [d(df, i, atr_value) for d in _BAR_ONLY_DETECTORS]
        hits += [d(df, i, atr_value, rng) for d in _RANGE_AWARE_DETECTORS]
        for hit in hits:
            if hit is None:
                continue
            direction = "confirming" if hit.native_direction == phase_bias else "contradicting"
            delta += PER_SIGNAL_DELTA if direction == "confirming" else -PER_SIGNAL_DELTA
            signals.append(
                {
                    "signal": hit.signal,
                    "date": df.at[i, "Date"].strftime("%Y-%m-%d"),
                    "direction": direction,
                    "volume_ratio": round(hit.volume_ratio, 2) if hit.volume_ratio is not None else None,
                    "evidence": [hit.evidence],
                }
            )
    bounded_delta = max(-MAX_TOTAL_DELTA, min(MAX_TOTAL_DELTA, delta))
    return signals, bounded_delta
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_wyckoff_vsa.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Run ruff and commit**

```bash
ruff check tradingagents/dataflows/wyckoff_vsa.py tests/test_wyckoff_vsa.py
git add tradingagents/dataflows/wyckoff_vsa.py tests/test_wyckoff_vsa.py
git commit -m "feat(wyckoff): add VSA orchestrator with bounded confidence adjustment"
```

---

### Task 5: Wire VSA into `wyckoff_bias.py`

**Files:**
- Modify: `tradingagents/dataflows/wyckoff_bias.py:71-88` (the `analyze_wyckoff_structure_from_data` function)
- Modify: `tests/test_wyckoff_bias.py` (append)

**Interfaces:**
- Consumes: `analyze_vsa(df, atr_value, rng, phase_bias, curr_date) -> tuple[list[dict], float]` from Task 4.
- Produces: `get_wyckoff_structure`'s JSON gains a `vsa_signals` key (only for non-neutral reads) and `confidence` reflects the VSA-adjusted value. No change to the public function signatures in `wyckoff_bias.py`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_wyckoff_bias.py`:

```python
@pytest.mark.unit
def test_accumulation_result_includes_vsa_signals_key():
    df = _accumulation_df()
    result = analyze_wyckoff_structure_from_data(df, df["Date"].iloc[-1].strftime("%Y-%m-%d"))

    assert "vsa_signals" in result
    assert isinstance(result["vsa_signals"], list)


@pytest.mark.unit
def test_neutral_result_has_no_vsa_signals_key():
    length = 120
    closes = [50.0 + 100.0 * i / (length - 1) for i in range(length)]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    volumes = [1_000_000.0] * length
    df = _to_df(closes, highs, lows, volumes)

    result = analyze_wyckoff_structure_from_data(df, df["Date"].iloc[-1].strftime("%Y-%m-%d"))

    assert "vsa_signals" not in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_wyckoff_bias.py -v -k vsa`
Expected: FAIL — `assert "vsa_signals" in result` (KeyError-style assertion failure, key absent)

- [ ] **Step 3: Wire `analyze_vsa` into `wyckoff_bias.py`**

In `tradingagents/dataflows/wyckoff_bias.py`, add the import alongside the existing `wyckoff_range` import:

```python
from tradingagents.dataflows.wyckoff_range import atr, detect_trading_range, prepare_ohlcv
from tradingagents.dataflows.wyckoff_vsa import analyze_vsa
```

Replace the body of `analyze_wyckoff_structure_from_data` (currently `tradingagents/dataflows/wyckoff_bias.py:71-88`):

```python
def analyze_wyckoff_structure_from_data(
    data: pd.DataFrame, curr_date: str, look_back_days: int = 504
) -> dict[str, Any]:
    """Analyze an OHLCV frame and return a JSON-serializable Wyckoff structure read."""
    df = prepare_ohlcv(data, curr_date, look_back_days)
    atr_value = float(atr(df).iloc[-1])
    rng = detect_trading_range(df, atr_value)
    accumulation = analyze_accumulation(df, atr_value, rng)
    distribution = analyze_distribution(df, atr_value, rng)

    result = {"analysis_date": curr_date}
    if accumulation is not None:
        result.update(_payload("accumulation", rng, accumulation))
    elif distribution is not None:
        result.update(_payload("distribution", rng, distribution))
    else:
        result.update(_neutral())
        return result

    vsa_signals, delta = analyze_vsa(df, atr_value, rng, result["phase_bias"], curr_date)
    result["vsa_signals"] = vsa_signals
    result["confidence"] = round(max(0.0, min(1.0, result["confidence"] + delta)), 2)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_wyckoff_bias.py -v`
Expected: PASS (6 passed — the 4 pre-existing plus the 2 new ones)

- [ ] **Step 5: Run ruff and commit**

```bash
ruff check tradingagents/dataflows/wyckoff_bias.py tests/test_wyckoff_bias.py
git add tradingagents/dataflows/wyckoff_bias.py tests/test_wyckoff_bias.py
git commit -m "feat(wyckoff): wire VSA confidence adjustment into wyckoff_bias"
```

---

### Task 6: Isolated verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full set of directly-affected tests**

Run:
```bash
pytest -q tests/test_wyckoff_vsa_bar_signals.py tests/test_wyckoff_vsa_range_signals.py tests/test_wyckoff_vsa.py tests/test_wyckoff_bias.py tests/test_market_toolnode.py
```
Expected: all pass, no regressions in `test_market_toolnode.py` (confirms `get_wyckoff_structure`'s tool wiring is unaffected).

- [ ] **Step 2: Run ruff on every touched/created file**

Run:
```bash
ruff check tradingagents/dataflows/wyckoff_vsa_signals.py tradingagents/dataflows/wyckoff_vsa_range_signals.py tradingagents/dataflows/wyckoff_vsa.py tradingagents/dataflows/wyckoff_bias.py tests/test_wyckoff_vsa_bar_signals.py tests/test_wyckoff_vsa_range_signals.py tests/test_wyckoff_vsa.py tests/test_wyckoff_bias.py
```
Expected: `All checks passed!`

- [ ] **Step 3: Update `WYCKOFF_ANALYSIS_PLAN.md`'s status section**

Add a `## Stage 2 实施状态` section mirroring the existing `## 当前实施状态` section's checklist style, marking VSA detectors, orchestrator, and `wyckoff_bias.py` wiring as done, with the actual test-count/ruff output substituted for the placeholders above once Step 1/2 results are known.

- [ ] **Step 4: Commit**

```bash
git add WYCKOFF_ANALYSIS_PLAN.md
git commit -m "docs(wyckoff): mark Stage 2 VSA implementation complete"
```
