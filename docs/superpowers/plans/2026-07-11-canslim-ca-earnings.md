# CANSLIM C+A Earnings-Growth Scorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Note for this repo specifically:** this project's established workflow runs each task through the `codex-delegate` skill (Codex CLI, non-interactive, self-verifying) rather than a generic Claude subagent. When executing, use `codex-delegate` per task; the review-gate structure below still applies.

**Goal:** Score O'Neil's C (current quarterly EPS growth, YoY-matched, report-date-gated)
and A (annual EPS growth) letters deterministically and surface them as an additive
`canslim_earnings` key in the O'Neil JSON payload the Market Analyst narrates.

**Architecture:** A pure scorer (`canslim_earnings.py` + `canslim_earnings_rules.py`)
operates on a vendor-normalized, point-in-time-filtered `EarningsHistory`
(`canslim_earnings_data.py`, dispatching on `data_vendors["fundamental_data"]`:
yfinance `get_earnings_dates` / new Alpha Vantage `EARNINGS` wrapper).
`oneil_bias.py::analyze_oneil_setup` merges the score best-effort; `market_analyst.py`
gains narration sentences. Narration-only — no confidence coupling.

**Tech Stack:** Python 3.14, pandas, yfinance, pytest (`@pytest.mark.unit`), ruff.

**Design source of truth:** `docs/superpowers/specs/2026-07-11-canslim-ca-earnings-design.md`.

**One deliberate delta from the spec's file list:** the scorer is split into
`canslim_earnings.py` (verdict functions) + `canslim_earnings_rules.py` (constants and
matching/growth/acceleration helpers) because a single scorer file was estimated at ~152
lines, over the repo's 150-line cap for new files. This follows the existing
`oneil_double_bottom.py` / `oneil_double_bottom_rules.py` precedent. The typed containers
stay in `canslim_earnings_data.py` per the spec.

## Global Constraints

- No upstream-file edits. `market_analyst.py` prompt edits are precedented (commit 266bfaf);
  everything else touched is project-custom.
- Point-in-time rule: a quarter reported after `curr_date` never influences any verdict,
  even when its fiscal period ended before `curr_date`. Quarterly gating is by
  reported/announcement date, never `fiscalDateEnding`. Do NOT reuse
  `_filter_reports_by_date` (it is the leaky fiscal-end gate).
- Vendor routing: dispatch on `config["data_vendors"]["fundamental_data"]`; unsupported
  vendor → `ValueError` naming it. Never silently switch vendors.
- Canonical constants (exact values): `C_MIN_GROWTH_PCT = 25.0`, `A_MIN_CAGR_PCT = 25.0`,
  `C_MIN_QUARTERS = 5`, `A_MIN_YEARS = 4`, `YOY_MATCH_TOLERANCE_DAYS = 45`,
  `EPS_ZERO_EPSILON = 0.01`.
- Verdicts are exactly `"pass" | "fail" | "unavailable"`. Payload shape is exactly
  `{"c": {"verdict", "growth_pct", "acceleration", "evidence"}, "a": {"verdict",
  "growth_pct", "evidence"}}`.
- Acceleration is reported alongside C but never changes the C verdict.
- Every new file ≤150 lines. All new tests `@pytest.mark.unit` with no network; the single
  live-network test is `@pytest.mark.integration`.
- After each task: run that task's listed pytest command and
  `ruff check <changed files>`. Do NOT run `git add`/`git commit` — commits require
  separate explicit user approval.

**Empirically verified vendor facts (2026-07-11, baked into the code below — do not
"improve" them from memory):**
- `yf.Ticker("AAPL").get_earnings_dates(limit=28)` returned 50 rows; columns exactly
  `['EPS Estimate', 'Reported EPS', 'Surprise(%)']`; index named `Earnings Date`, dtype
  `datetime64[us, America/New_York]` (tz-aware). Future rows exist with NaN `Reported EPS`.
  There is NO fiscal-end column — hence `QuarterEps.fiscal_end` is optional and YoY
  matching falls back to `reported_date`.
- `yf.Ticker("AAPL").income_stmt` has a `Diluted EPS` row; columns are fiscal-year-end
  `Timestamp`s (5 columns, oldest was NaN → NaN years must be dropped).
- The Alpha Vantage `EARNINGS` endpoint shape (`quarterlyEarnings` entries with
  `fiscalDateEnding`, `reportedDate`, `reportedEPS`; `annualEarnings` entries with
  `fiscalDateEnding`, `reportedEPS`) is from AV's published docs, not live-verified (no AV
  key in this environment) — the monkeypatched tests define the contract.

---

### Task 1: Typed containers, rules, and the pure scorer

**Files:**
- Create: `tradingagents/dataflows/canslim_earnings_data.py` (types only in this task)
- Create: `tradingagents/dataflows/canslim_earnings_rules.py`
- Create: `tradingagents/dataflows/canslim_earnings.py`
- Test: `tests/test_canslim_earnings.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces:
  - `QuarterEps(fiscal_end: str | None, reported_date: str, eps: float)` (frozen dataclass)
  - `AnnualEps(fiscal_year: str, eps: float)` (frozen dataclass)
  - `EarningsHistory(quarters: list[QuarterEps], annual: list[AnnualEps])` (frozen
    dataclass; both lists newest-first) — all three in `canslim_earnings_data.py`.
  - `score_canslim_ca(history: EarningsHistory) -> dict[str, Any]` in
    `canslim_earnings.py`, returning the payload shape from Global Constraints.
  - Constants listed in Global Constraints, exported from `canslim_earnings_rules.py`.

- [ ] **Step 1: Create the typed containers**

```python
# tradingagents/dataflows/canslim_earnings_data.py
"""Typed, point-in-time-filtered earnings history for the CANSLIM C+A scorer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QuarterEps:
    """One reported quarter. ``fiscal_end`` is None when the vendor lacks it (yfinance)."""

    fiscal_end: str | None
    reported_date: str
    eps: float


@dataclass(frozen=True)
class AnnualEps:
    fiscal_year: str
    eps: float


@dataclass(frozen=True)
class EarningsHistory:
    """Quarterly and annual EPS series, both newest-first, already curr_date-filtered."""

    quarters: list[QuarterEps]
    annual: list[AnnualEps]
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_canslim_earnings.py
"""Unit tests for the pure CANSLIM C+A earnings-growth scorer."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from tradingagents.dataflows.canslim_earnings import score_canslim_ca
from tradingagents.dataflows.canslim_earnings_data import (
    AnnualEps,
    EarningsHistory,
    QuarterEps,
)


def _quarters(eps_newest_first: list[float], spacing_days: int = 91) -> list[QuarterEps]:
    newest = date(2026, 4, 25)
    return [
        QuarterEps(None, (newest - timedelta(days=spacing_days * i)).isoformat(), eps)
        for i, eps in enumerate(eps_newest_first)
    ]


def _annual(eps_newest_first: list[float]) -> list[AnnualEps]:
    return [AnnualEps(f"{2025 - i}-09-30", eps) for i, eps in enumerate(eps_newest_first)]


def _history(quarters=None, annual=None) -> EarningsHistory:
    return EarningsHistory(quarters=quarters or [], annual=annual or [])


@pytest.mark.unit
def test_c_pass_with_acceleration():
    # newest-first: 2.00 vs 1.20 a year ago = +66.7%; growth sequence accelerates
    quarters = _quarters([2.00, 1.60, 1.30, 1.10, 1.20, 1.10, 1.00, 1.00])
    result = score_canslim_ca(_history(quarters=quarters))
    assert result["c"]["verdict"] == "pass"
    assert result["c"]["growth_pct"] == pytest.approx(66.7, abs=0.1)
    assert result["c"]["acceleration"] == "accelerating"
    assert "+66.7%" in result["c"]["evidence"]


@pytest.mark.unit
def test_c_exactly_25_percent_is_pass():
    quarters = _quarters([1.25, 1.10, 1.05, 1.02, 1.00, 0.95, 0.90, 0.88])
    result = score_canslim_ca(_history(quarters=quarters))
    assert result["c"]["growth_pct"] == pytest.approx(25.0, abs=0.01)
    assert result["c"]["verdict"] == "pass"


@pytest.mark.unit
def test_c_below_threshold_is_fail():
    quarters = _quarters([1.10, 1.05, 1.02, 1.01, 1.00, 0.98, 0.97, 0.96])
    result = score_canslim_ca(_history(quarters=quarters))
    assert result["c"]["verdict"] == "fail"


@pytest.mark.unit
def test_c_negative_current_eps_is_automatic_fail():
    # -0.10 vs -0.50 a year ago is +80% by the abs-denominator formula, but still fails
    quarters = _quarters([-0.10, 0.20, 0.10, 0.05, -0.50, -0.60, -0.70, -0.80])
    result = score_canslim_ca(_history(quarters=quarters))
    assert result["c"]["verdict"] == "fail"
    assert "negative" in result["c"]["evidence"].lower()


@pytest.mark.unit
def test_c_near_zero_year_ago_base_is_unavailable():
    quarters = _quarters([1.00, 0.80, 0.60, 0.40, 0.005, 0.10, 0.20, 0.30])
    result = score_canslim_ca(_history(quarters=quarters))
    assert result["c"]["verdict"] == "unavailable"


@pytest.mark.unit
def test_c_insufficient_quarters_is_unavailable():
    result = score_canslim_ca(_history(quarters=_quarters([2.0, 1.8, 1.6, 1.4])))
    assert result["c"]["verdict"] == "unavailable"
    assert "4" in result["c"]["evidence"]


@pytest.mark.unit
def test_c_no_counterpart_within_tolerance_is_unavailable():
    # 5 quarters spaced 60 days apart: a year back lands nowhere near any report
    result = score_canslim_ca(
        _history(quarters=_quarters([2.0, 1.8, 1.6, 1.4, 1.2], spacing_days=60))
    )
    assert result["c"]["verdict"] == "unavailable"


@pytest.mark.unit
def test_c_53_week_drift_still_matches():
    # counterpart reported 371 days before the latest (4 quarters back at ~92.75d spacing)
    newest = date(2026, 4, 25)
    offsets = [0, 93, 186, 279, 371, 464, 557, 650]
    eps = [2.00, 1.60, 1.30, 1.10, 1.20, 1.10, 1.00, 1.00]
    quarters = [
        QuarterEps(None, (newest - timedelta(days=off)).isoformat(), e)
        for off, e in zip(offsets, eps)
    ]
    result = score_canslim_ca(_history(quarters=quarters))
    assert result["c"]["verdict"] == "pass"


@pytest.mark.unit
def test_c_matches_on_fiscal_end_when_present():
    newest = date(2026, 3, 31)
    quarters = [
        QuarterEps(
            (newest - timedelta(days=91 * i)).isoformat(),
            (newest - timedelta(days=91 * i) + timedelta(days=25)).isoformat(),
            e,
        )
        for i, e in enumerate([2.00, 1.60, 1.30, 1.10, 1.20, 1.10, 1.00, 1.00])
    ]
    result = score_canslim_ca(_history(quarters=quarters))
    assert result["c"]["verdict"] == "pass"


@pytest.mark.unit
def test_c_acceleration_null_when_too_few_computable():
    quarters = _quarters([2.00, 1.60, 1.30, 1.10, 1.20])
    result = score_canslim_ca(_history(quarters=quarters))
    assert result["c"]["acceleration"] is None


@pytest.mark.unit
def test_c_deceleration_and_mixed():
    decel = _quarters([1.30, 1.60, 1.80, 1.90, 1.00, 1.10, 1.20, 1.25])
    assert score_canslim_ca(_history(quarters=decel))["c"]["acceleration"] == "decelerating"
    mixed = _quarters([2.00, 1.30, 1.80, 1.10, 1.20, 1.10, 1.20, 1.00])
    assert score_canslim_ca(_history(quarters=mixed))["c"]["acceleration"] == "mixed"


@pytest.mark.unit
def test_a_pass_on_strong_cagr():
    # chronological 1.00 -> 2.20 over 3 intervals = ~30.1% CAGR, zero down years
    result = score_canslim_ca(_history(annual=_annual([2.20, 1.70, 1.30, 1.00])))
    assert result["a"]["verdict"] == "pass"
    assert result["a"]["growth_pct"] == pytest.approx(30.1, abs=0.1)


@pytest.mark.unit
def test_a_one_down_year_tolerated_two_fail():
    one_down = _annual([2.20, 1.20, 1.30, 1.00])  # one decline; CAGR ~30% -> pass
    assert score_canslim_ca(_history(annual=one_down))["a"]["verdict"] == "pass"
    # chronological 1.00 -> 0.90 -> 0.80 -> 2.20: CAGR ~30% but two down years -> fail
    two_down = _annual([2.20, 0.80, 0.90, 1.00])
    assert score_canslim_ca(_history(annual=two_down))["a"]["verdict"] == "fail"


@pytest.mark.unit
def test_a_low_cagr_is_fail():
    result = score_canslim_ca(_history(annual=_annual([1.30, 1.20, 1.10, 1.00])))
    assert result["a"]["verdict"] == "fail"


@pytest.mark.unit
def test_a_negative_oldest_fallback():
    turnaround = _annual([2.10, 1.20, 0.50, -1.00])
    result = score_canslim_ca(_history(annual=turnaround))
    assert result["a"]["verdict"] == "pass"
    assert result["a"]["growth_pct"] is None
    weak = _annual([1.50, 1.20, 0.50, -1.00])  # newest < 2x abs(oldest)
    assert score_canslim_ca(_history(annual=weak))["a"]["verdict"] == "unavailable"


@pytest.mark.unit
def test_a_insufficient_years_is_unavailable():
    result = score_canslim_ca(_history(annual=_annual([2.0, 1.5, 1.2])))
    assert result["a"]["verdict"] == "unavailable"


@pytest.mark.unit
def test_empty_history_is_unavailable_on_both_letters():
    result = score_canslim_ca(_history())
    assert result["c"]["verdict"] == "unavailable"
    assert result["a"]["verdict"] == "unavailable"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_canslim_earnings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tradingagents.dataflows.canslim_earnings'`

- [ ] **Step 4: Implement the rules helpers**

```python
# tradingagents/dataflows/canslim_earnings_rules.py
"""Matching, growth, and acceleration rules for the CANSLIM C+A scorer."""

from __future__ import annotations

from datetime import date, timedelta

from tradingagents.dataflows.canslim_earnings_data import QuarterEps

C_MIN_GROWTH_PCT = 25.0
A_MIN_CAGR_PCT = 25.0
C_MIN_QUARTERS = 5
A_MIN_YEARS = 4
YOY_MATCH_TOLERANCE_DAYS = 45
EPS_ZERO_EPSILON = 0.01


def match_key(quarter: QuarterEps) -> date:
    """Date used for YoY pairing: fiscal end when the vendor provides it, else report date."""
    return date.fromisoformat(quarter.fiscal_end or quarter.reported_date)


def find_yoy_counterpart(
    older: list[QuarterEps], target: QuarterEps
) -> QuarterEps | None:
    """Return the quarter closest to one year before ``target`` within tolerance."""
    wanted = match_key(target) - timedelta(days=365)
    best: tuple[int, QuarterEps] | None = None
    for quarter in older:
        delta = abs((match_key(quarter) - wanted).days)
        if delta <= YOY_MATCH_TOLERANCE_DAYS and (best is None or delta < best[0]):
            best = (delta, quarter)
    return best[1] if best else None


def growth_pct(now: float, year_ago: float) -> float:
    """YoY growth with an absolute-value base so a negative year-ago EPS scores sanely."""
    return (now - year_ago) / abs(year_ago) * 100.0


def classify_acceleration(quarters: list[QuarterEps]) -> tuple[str | None, str]:
    """YoY growth trend across the latest three quarters; informational, never a gate."""
    growths: list[float] = []
    for index in range(min(3, len(quarters))):
        target = quarters[index]
        counterpart = find_yoy_counterpart(quarters[index + 1 :], target)
        if counterpart is None or abs(counterpart.eps) < EPS_ZERO_EPSILON:
            break
        growths.append(growth_pct(target.eps, counterpart.eps))
    if len(growths) < 3:
        return None, "Year-over-year growth is computable for fewer than three recent quarters."
    chronological = list(reversed(growths))
    if chronological[0] < chronological[1] < chronological[2]:
        label = "accelerating"
    elif chronological[0] > chronological[1] > chronological[2]:
        label = "decelerating"
    else:
        label = "mixed"
    sequence = " -> ".join(f"{value:+.1f}%" for value in chronological)
    return label, f"Quarterly EPS growth ran {sequence} across the last three reports ({label})."
```

- [ ] **Step 5: Implement the scorer**

```python
# tradingagents/dataflows/canslim_earnings.py
"""Pure CANSLIM C+A verdicts over a point-in-time-filtered EarningsHistory."""

from __future__ import annotations

from typing import Any

from tradingagents.dataflows.canslim_earnings_data import AnnualEps, EarningsHistory
from tradingagents.dataflows.canslim_earnings_rules import (
    A_MIN_CAGR_PCT,
    A_MIN_YEARS,
    C_MIN_GROWTH_PCT,
    C_MIN_QUARTERS,
    EPS_ZERO_EPSILON,
    classify_acceleration,
    find_yoy_counterpart,
    growth_pct,
)


def _c_result(verdict: str, growth: float | None, acceleration: str | None, evidence: str) -> dict[str, Any]:
    return {"verdict": verdict, "growth_pct": growth, "acceleration": acceleration, "evidence": evidence}


def _score_c(history: EarningsHistory) -> dict[str, Any]:
    quarters = history.quarters
    if len(quarters) < C_MIN_QUARTERS:
        return _c_result(
            "unavailable", None, None,
            f"Only {len(quarters)} reported quarters are available, below the required {C_MIN_QUARTERS}.",
        )
    latest = quarters[0]
    counterpart = find_yoy_counterpart(quarters[1:], latest)
    if counterpart is None:
        return _c_result(
            "unavailable", None, None,
            f"No same-quarter counterpart was reported near one year before {latest.reported_date}.",
        )
    if abs(counterpart.eps) < EPS_ZERO_EPSILON:
        return _c_result(
            "unavailable", None, None,
            f"The year-ago quarterly EPS of {counterpart.eps:.2f} is too small a base for a meaningful growth rate.",
        )
    growth = round(growth_pct(latest.eps, counterpart.eps), 1)
    acceleration, acceleration_text = classify_acceleration(quarters)
    if latest.eps < 0:
        evidence = (
            f"Current quarterly EPS is negative ({latest.eps:.2f}, reported {latest.reported_date}); "
            "O'Neil requires positive current earnings."
        )
        return _c_result("fail", growth, acceleration, f"{evidence} {acceleration_text}")
    verdict = "pass" if growth >= C_MIN_GROWTH_PCT else "fail"
    relation = "meeting" if verdict == "pass" else "below"
    evidence = (
        f"Quarterly EPS of {latest.eps:.2f} (reported {latest.reported_date}) versus "
        f"{counterpart.eps:.2f} a year earlier ({counterpart.reported_date}) is {growth:+.1f}% "
        f"year-over-year, {relation} the {C_MIN_GROWTH_PCT:.0f}% CANSLIM threshold."
    )
    return _c_result(verdict, growth, acceleration, f"{evidence} {acceleration_text}")


def _a_result(verdict: str, growth: float | None, evidence: str) -> dict[str, Any]:
    return {"verdict": verdict, "growth_pct": growth, "evidence": evidence}


def _score_a(annual: list[AnnualEps]) -> dict[str, Any]:
    if len(annual) < A_MIN_YEARS:
        return _a_result(
            "unavailable", None,
            f"Only {len(annual)} annual EPS values are available, below the required {A_MIN_YEARS}.",
        )
    span = annual[:A_MIN_YEARS]
    newest, oldest = span[0], span[-1]
    values = ", ".join(f"{item.fiscal_year[:4]}: {item.eps:.2f}" for item in reversed(span))
    if oldest.eps < EPS_ZERO_EPSILON:
        newer_positive = all(item.eps > 0 for item in span[:-1])
        if newer_positive and newest.eps >= 2 * abs(oldest.eps):
            return _a_result(
                "pass", None,
                f"Annual EPS recovered from {oldest.eps:.2f} to {newest.eps:.2f} ({values}); the "
                "growth rate from a non-positive base is undefined but the turnaround qualifies.",
            )
        return _a_result(
            "unavailable", None,
            f"Annual EPS growth is not meaningfully computable from a base year of {oldest.eps:.2f} ({values}).",
        )
    down_years = sum(1 for i in range(len(span) - 1) if span[i].eps < span[i + 1].eps)
    cagr = round(((newest.eps / oldest.eps) ** (1 / (A_MIN_YEARS - 1)) - 1) * 100, 1)
    verdict = "pass" if cagr >= A_MIN_CAGR_PCT and down_years <= 1 else "fail"
    evidence = (
        f"Annual EPS ran {values} over the last {A_MIN_YEARS} fiscal years: {cagr:+.1f}% CAGR "
        f"with {down_years} down year(s)."
    )
    return _a_result(verdict, cagr, evidence)


def score_canslim_ca(history: EarningsHistory) -> dict[str, Any]:
    """Score O'Neil's C and A letters; verdicts are pass/fail/unavailable, never guessed."""
    return {"c": _score_c(history), "a": _score_a(history.annual)}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_canslim_earnings.py -v`
Expected: 17 passed

- [ ] **Step 7: Ruff check**

```bash
ruff check tradingagents/dataflows/canslim_earnings_data.py tradingagents/dataflows/canslim_earnings_rules.py tradingagents/dataflows/canslim_earnings.py tests/test_canslim_earnings.py
```

Expected: clean. Do NOT commit (user approval happens outside the task).

---

### Task 2: Vendor fetch and normalization

**Files:**
- Modify: `tradingagents/dataflows/canslim_earnings_data.py` (add loaders below the types)
- Modify: `tradingagents/dataflows/alpha_vantage_fundamentals.py` (+1 function)
- Test: `tests/test_canslim_earnings_data.py`

**Interfaces:**
- Consumes: `QuarterEps`, `AnnualEps`, `EarningsHistory` from Task 1 (same file).
- Produces: `load_earnings_history(symbol: str, curr_date: str, config: dict | None = None)
  -> EarningsHistory` in `canslim_earnings_data.py`; `get_earnings(ticker: str,
  curr_date: str = None) -> dict | str` in `alpha_vantage_fundamentals.py`.

- [ ] **Step 1: Add the Alpha Vantage EARNINGS wrapper**

Append to `tradingagents/dataflows/alpha_vantage_fundamentals.py`:

```python
def get_earnings(ticker: str, curr_date: str = None):
    """Retrieve reported quarterly/annual EPS history using Alpha Vantage EARNINGS.

    Deliberately not passed through _filter_reports_by_date: that gate uses
    fiscalDateEnding and would leak quarters that ended but were not yet
    reported. Point-in-time filtering by reportedDate happens in
    canslim_earnings_data.load_earnings_history.
    """
    return _make_api_request("EARNINGS", {"symbol": ticker})
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_canslim_earnings_data.py
"""Unit tests for CANSLIM earnings-history loading and point-in-time filtering."""

from __future__ import annotations

import pandas as pd
import pytest

import tradingagents.dataflows.canslim_earnings_data as ced
from tradingagents.dataflows.canslim_earnings_data import load_earnings_history


def _yf_config():
    return {"data_vendors": {"fundamental_data": "yfinance"}}


def _av_config():
    return {"data_vendors": {"fundamental_data": "alpha_vantage"}}


class _StubTicker:
    """Mimics the empirically verified yfinance shapes (tz-aware earnings index)."""

    def __init__(self, symbol):
        index = pd.DatetimeIndex(
            ["2026-07-30 16:00", "2026-04-30 16:00", "2026-01-29 16:00", "2025-10-30 16:00"],
            tz="America/New_York", name="Earnings Date",
        )
        self._earnings = pd.DataFrame(
            {"EPS Estimate": [1.89, 1.94, 2.67, 1.77],
             "Reported EPS": [float("nan"), 2.01, 2.84, 1.85],
             "Surprise(%)": [float("nan"), 3.46, 6.25, 4.52]},
            index=index,
        )
        self.income_stmt = pd.DataFrame(
            {pd.Timestamp("2025-09-30"): [7.46], pd.Timestamp("2024-09-30"): [6.08],
             pd.Timestamp("2023-09-30"): [6.13], pd.Timestamp("2022-09-30"): [float("nan")]},
            index=["Diluted EPS"],
        )

    def get_earnings_dates(self, limit=28):
        return self._earnings


@pytest.mark.unit
def test_yfinance_drops_future_and_nan_quarters(monkeypatch):
    monkeypatch.setattr(ced.yf, "Ticker", _StubTicker)
    history = load_earnings_history("AAPL", "2026-05-15", config=_yf_config())
    assert [q.eps for q in history.quarters] == [2.01, 2.84, 1.85]
    assert history.quarters[0].reported_date == "2026-04-30"
    assert history.quarters[0].fiscal_end is None


@pytest.mark.unit
def test_yfinance_report_date_gate_excludes_recent_quarter(monkeypatch):
    # 2026-04-30 report excluded at curr_date 2026-04-10 even though Q ended in March
    monkeypatch.setattr(ced.yf, "Ticker", _StubTicker)
    history = load_earnings_history("AAPL", "2026-04-10", config=_yf_config())
    assert [q.eps for q in history.quarters] == [2.84, 1.85]


@pytest.mark.unit
def test_yfinance_annual_gated_by_90_day_window_and_nan_dropped(monkeypatch):
    monkeypatch.setattr(ced.yf, "Ticker", _StubTicker)
    # 2025-09-30 fiscal end + 90d = 2025-12-29 <= curr_date, so 3 usable years (2022 NaN)
    history = load_earnings_history("AAPL", "2026-05-15", config=_yf_config())
    assert [a.eps for a in history.annual] == [7.46, 6.08, 6.13]
    # at 2025-11-01 the FY2025 10-K window has not elapsed
    history = load_earnings_history("AAPL", "2025-11-01", config=_yf_config())
    assert [a.eps for a in history.annual] == [6.08, 6.13]


@pytest.mark.unit
def test_alpha_vantage_reported_date_gate(monkeypatch):
    payload = {
        "symbol": "TEST",
        "quarterlyEarnings": [
            {"fiscalDateEnding": "2026-03-31", "reportedDate": "2026-04-25", "reportedEPS": "2.10"},
            {"fiscalDateEnding": "2025-12-31", "reportedDate": "2026-01-28", "reportedEPS": "2.80"},
            {"fiscalDateEnding": "2025-09-30", "reportedDate": "2025-10-30", "reportedEPS": "1.90"},
            {"fiscalDateEnding": "2025-06-30", "reportedDate": "2025-07-31", "reportedEPS": "1.60"},
        ],
        "annualEarnings": [
            {"fiscalDateEnding": "2025-09-30", "reportedEPS": "7.40"},
            {"fiscalDateEnding": "2024-09-30", "reportedEPS": "6.10"},
        ],
    }
    monkeypatch.setattr(ced, "get_av_earnings", lambda symbol: payload)
    # THE leakage case: fiscal period ended 2026-03-31, before curr_date 2026-04-10,
    # but the report landed 2026-04-25 — it must be excluded.
    history = load_earnings_history("TEST", "2026-04-10", config=_av_config())
    assert [q.eps for q in history.quarters] == [2.80, 1.90, 1.60]
    assert history.quarters[0].fiscal_end == "2025-12-31"
    # annual FY2025 usable: a quarterly report with fiscal_end >= 2025-09-30 has landed
    assert [a.eps for a in history.annual] == [7.40, 6.10]


@pytest.mark.unit
def test_alpha_vantage_annual_needs_covering_quarterly_report(monkeypatch):
    payload = {
        "symbol": "TEST",
        "quarterlyEarnings": [
            {"fiscalDateEnding": "2025-06-30", "reportedDate": "2025-07-31", "reportedEPS": "1.60"},
        ],
        "annualEarnings": [
            {"fiscalDateEnding": "2025-09-30", "reportedEPS": "7.40"},
            {"fiscalDateEnding": "2024-09-30", "reportedEPS": "6.10"},
        ],
    }
    monkeypatch.setattr(ced, "get_av_earnings", lambda symbol: payload)
    history = load_earnings_history("TEST", "2025-08-15", config=_av_config())
    # FY2025 not yet covered by any quarterly report at/after its fiscal end
    assert [a.eps for a in history.annual] == [6.10]


@pytest.mark.unit
def test_unsupported_vendor_raises_value_error():
    with pytest.raises(ValueError, match="local_csv"):
        load_earnings_history(
            "TEST", "2026-05-15", config={"data_vendors": {"fundamental_data": "local_csv"}}
        )


@pytest.mark.integration
def test_yfinance_live_history_shape():
    history = load_earnings_history("AAPL", "2026-07-01", config=_yf_config())
    assert len(history.quarters) >= 5
    assert len(history.annual) >= 3
    assert all(q.reported_date <= "2026-07-01" for q in history.quarters)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_canslim_earnings_data.py -m unit -v`
Expected: FAIL with `ImportError: cannot import name 'load_earnings_history'`

- [ ] **Step 4: Implement the loaders**

Append to `tradingagents/dataflows/canslim_earnings_data.py` (extend the imports at the
top of the file accordingly):

```python
import pandas as pd
import yfinance as yf

from tradingagents.dataflows.alpha_vantage_fundamentals import get_earnings as get_av_earnings
from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.stockstats_utils import yf_retry
from tradingagents.dataflows.symbol_utils import NoMarketDataError, normalize_symbol

ANNUAL_REPORT_LAG_DAYS = 90


def load_earnings_history(symbol: str, curr_date: str, config: dict | None = None) -> EarningsHistory:
    """Load point-in-time quarterly/annual EPS via the configured fundamental_data vendor."""
    vendor = (config or get_config()).get("data_vendors", {}).get("fundamental_data")
    canonical = normalize_symbol(symbol)
    if vendor == "yfinance":
        return _load_yfinance(symbol, canonical, curr_date)
    if vendor == "alpha_vantage":
        return _load_alpha_vantage(symbol, canonical, curr_date)
    raise ValueError(
        f"CANSLIM earnings history has no adapter for fundamental_data vendor {vendor!r}"
    )


def _load_yfinance(symbol: str, canonical: str, curr_date: str) -> EarningsHistory:
    ticker = yf.Ticker(canonical)
    frame = yf_retry(lambda: ticker.get_earnings_dates(limit=28))
    if frame is None or frame.empty:
        raise NoMarketDataError(symbol, canonical, "no earnings dates returned")
    cutoff = pd.Timestamp(curr_date)
    quarters = []
    for stamp, row in frame.iterrows():
        reported = pd.Timestamp(stamp).tz_localize(None).normalize()
        eps = row.get("Reported EPS")
        if pd.isna(eps) or reported > cutoff:
            continue
        quarters.append(QuarterEps(None, reported.strftime("%Y-%m-%d"), float(eps)))
    quarters.sort(key=lambda q: q.reported_date, reverse=True)
    annual = []
    income = yf_retry(lambda: ticker.income_stmt)
    if income is not None and not income.empty and "Diluted EPS" in income.index:
        for column, value in income.loc["Diluted EPS"].items():
            fiscal_end = pd.Timestamp(column)
            # yfinance annual statements carry no report date; approximate the
            # 10-K filing window so a just-ended fiscal year is not leaked.
            if pd.isna(value) or fiscal_end + pd.Timedelta(days=ANNUAL_REPORT_LAG_DAYS) > cutoff:
                continue
            annual.append(AnnualEps(fiscal_end.strftime("%Y-%m-%d"), float(value)))
    annual.sort(key=lambda item: item.fiscal_year, reverse=True)
    return EarningsHistory(quarters=quarters, annual=annual)


def _load_alpha_vantage(symbol: str, canonical: str, curr_date: str) -> EarningsHistory:
    data = get_av_earnings(canonical)
    if not isinstance(data, dict) or "quarterlyEarnings" not in data:
        raise NoMarketDataError(symbol, canonical, "no EARNINGS payload returned")
    quarters = []
    for entry in data.get("quarterlyEarnings", []):
        reported = entry.get("reportedDate") or ""
        if not reported or reported > curr_date:
            continue
        try:
            eps = float(entry.get("reportedEPS"))
        except (TypeError, ValueError):
            continue
        quarters.append(QuarterEps(entry.get("fiscalDateEnding"), reported, eps))
    quarters.sort(key=lambda q: q.reported_date, reverse=True)
    covered = {q.fiscal_end for q in quarters if q.fiscal_end}
    annual = []
    for entry in data.get("annualEarnings", []):
        fiscal_year = entry.get("fiscalDateEnding") or ""
        try:
            eps = float(entry.get("reportedEPS"))
        except (TypeError, ValueError):
            continue
        # An annual figure is public only once its Q4/FY report has landed:
        # require a reported quarter whose fiscal end is at/after this year end.
        if fiscal_year and any(end >= fiscal_year for end in covered):
            annual.append(AnnualEps(fiscal_year, eps))
    annual.sort(key=lambda item: item.fiscal_year, reverse=True)
    return EarningsHistory(quarters=quarters, annual=annual)
```

Note: if this pushes `canslim_earnings_data.py` past 150 lines, move the three dataclasses
to the TOP of the file and trim comments — the verified budget is ~135 lines total. Do not
split the file.

- [ ] **Step 5: Run unit tests to verify they pass**

Run: `pytest tests/test_canslim_earnings_data.py -m unit -v`
Expected: 6 passed (the integration test is deselected)

- [ ] **Step 6: Ruff check**

```bash
ruff check tradingagents/dataflows/canslim_earnings_data.py tradingagents/dataflows/alpha_vantage_fundamentals.py tests/test_canslim_earnings_data.py
```

Expected: clean. Do NOT commit.

---

### Task 3: O'Neil payload integration and Market Analyst narration

**Files:**
- Modify: `tradingagents/dataflows/oneil_bias.py`
- Modify: `tradingagents/agents/analysts/market_analyst.py` (prompt text only)
- Test: `tests/test_oneil_bias.py` (extend, do not rewrite)

**Interfaces:**
- Consumes: `load_earnings_history` (Task 2), `score_canslim_ca` (Task 1).
- Produces: additive top-level `canslim_earnings` key in `analyze_oneil_setup`'s JSON.
  `analyze_oneil_setup_from_data` (the frame-based entry used by most tests) is unchanged
  and does NOT carry the key — only the symbol-aware entry point does.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_oneil_bias.py` (add `import json` and
`from tradingagents.dataflows.canslim_earnings_data import AnnualEps, EarningsHistory, QuarterEps`
and `from tradingagents.dataflows.oneil_bias import analyze_oneil_setup` to the imports;
`analyze_oneil_setup_from_data` is already imported):

```python
@pytest.mark.unit
def test_canslim_key_degrades_when_fetch_fails(monkeypatch):
    data = _flat_frame()
    curr = data["Date"].iloc[-1].strftime("%Y-%m-%d")
    monkeypatch.setattr(
        "tradingagents.dataflows.oneil_bias.load_ohlcv", lambda symbol, curr_date: data
    )
    def _boom(symbol, curr_date, config=None):
        raise RuntimeError("no earnings vendor")
    monkeypatch.setattr("tradingagents.dataflows.oneil_bias.load_earnings_history", _boom)
    result = json.loads(analyze_oneil_setup("TEST", curr))
    assert result["canslim_earnings"]["c"]["verdict"] == "unavailable"
    assert "no earnings vendor" in result["canslim_earnings"]["c"]["evidence"]
    assert result["canslim_earnings"]["a"]["verdict"] == "unavailable"
    assert result["setup_bias"] == "neutral"  # technical payload intact


@pytest.mark.unit
def test_canslim_key_scores_when_history_available(monkeypatch):
    data = _flat_frame()
    curr = data["Date"].iloc[-1].strftime("%Y-%m-%d")
    monkeypatch.setattr(
        "tradingagents.dataflows.oneil_bias.load_ohlcv", lambda symbol, curr_date: data
    )
    from datetime import date, timedelta
    newest = date(2024, 9, 25)
    quarters = [
        QuarterEps(None, (newest - timedelta(days=91 * i)).isoformat(), eps)
        for i, eps in enumerate([2.00, 1.60, 1.30, 1.10, 1.20, 1.10, 1.00, 1.00])
    ]
    annual = [AnnualEps(f"{2023 - i}-09-30", eps) for i, eps in enumerate([2.20, 1.70, 1.30, 1.00])]
    monkeypatch.setattr(
        "tradingagents.dataflows.oneil_bias.load_earnings_history",
        lambda symbol, curr_date, config=None: EarningsHistory(quarters, annual),
    )
    result = json.loads(analyze_oneil_setup("TEST", curr))
    assert result["canslim_earnings"]["c"]["verdict"] == "pass"
    assert result["canslim_earnings"]["a"]["verdict"] == "pass"


@pytest.mark.unit
def test_frame_based_entry_point_has_no_canslim_key():
    data = _flat_frame()
    result = analyze_oneil_setup_from_data(data, data["Date"].iloc[-1].strftime("%Y-%m-%d"))
    assert "canslim_earnings" not in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_oneil_bias.py -k canslim -v`
Expected: FAIL with `ImportError: cannot import name 'load_earnings_history' from 'tradingagents.dataflows.oneil_bias'` (or AttributeError from monkeypatch — either failure mode is the expected "not wired yet" signal)

- [ ] **Step 3: Wire the payload into `oneil_bias.py`**

Add imports:

```python
from tradingagents.dataflows.canslim_earnings import score_canslim_ca
from tradingagents.dataflows.canslim_earnings_data import load_earnings_history
```

Add this helper above `analyze_oneil_setup`:

```python
def _canslim_earnings_payload(symbol: str, curr_date: str) -> dict[str, Any]:
    """Best-effort C+A read; a fundamentals outage must never break the technical read."""
    try:
        return score_canslim_ca(load_earnings_history(symbol, curr_date))
    except Exception as exc:
        reason = f"unavailable: {exc}"
        return {
            "c": {"verdict": "unavailable", "growth_pct": None, "acceleration": None, "evidence": reason},
            "a": {"verdict": "unavailable", "growth_pct": None, "evidence": reason},
        }
```

In `analyze_oneil_setup`, after `result["symbol"] = symbol.upper()` add:

```python
    result["canslim_earnings"] = _canslim_earnings_payload(symbol, curr_date)
```

- [ ] **Step 4: Add the narration sentences to `market_analyst.py`**

In the O'Neil prompt paragraph (the f-string ending with "...do not eyeball structures
from the raw CSV."), extend via exact-match Edit — old text:

```
Do not invent patterns beyond what this JSON reports, and do not eyeball structures from the raw CSV.
```

new text:

```
Do not invent patterns beyond what this JSON reports, and do not eyeball structures from the raw CSV. The JSON's `canslim_earnings` block carries a deterministic read of O'Neil's C (current quarterly EPS growth, year-over-year) and A (annual EPS growth) letters: state each letter's verdict with its numbers and dates from the `evidence` strings, mention `acceleration` when it is not null, and treat these as fundamental context for the base-pattern read -- they never change the technical `setup_bias` or the precedence rules above. When a verdict is `unavailable`, say so and why; never infer earnings growth from any other data.
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_oneil_bias.py -v`
Expected: all pass (existing tests plus the 3 new ones)

- [ ] **Step 6: Run the scoped verification slice and ruff**

```bash
pytest -q tests/test_canslim_earnings.py tests/test_canslim_earnings_data.py -m unit
pytest -q tests/test_oneil_bias.py tests/test_market_analyst_prefetch.py
ruff check tradingagents/dataflows/oneil_bias.py tradingagents/agents/analysts/market_analyst.py tests/test_oneil_bias.py
```

Expected: all pass, ruff clean. (`test_market_analyst_prefetch.py` guards the prompt
wiring; if it asserts on paragraph text it must still pass unchanged since the edit is
purely additive at the end of the paragraph.)

Do NOT commit.

---

## Codex model tier per task

Per the design spec: Task 1 (pure scorer) **terra**; Task 2 (vendor fetch/normalization —
the date-gating subtleties across two vendors are the hardest part) **sol**; Task 3
(integration + prompt) **terra**. Always pass `-m gpt-5.6-<tier>` explicitly.

## Acceptance criteria (from spec)

- A quarter reported after `curr_date` never influences any verdict, even when its fiscal
  period ended before `curr_date` (the leakage tests in Task 2 are the contract).
- With `fundamental_data: yfinance` and no network, the technical payload is byte-identical
  to today's except for the added `canslim_earnings` key with `unavailable` verdicts.
- Verdicts narrated with numbers and dates; `unavailable` stated as such, never guessed.
- No confidence coupling; no `interface.py` or Fundamentals Analyst changes.

> Research/analysis support only; not investment advice; no trade execution.
