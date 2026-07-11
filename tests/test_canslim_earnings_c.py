"""Unit tests for the CANSLIM C earnings-growth scorer."""

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
        for off, e in zip(offsets, eps, strict=True)
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
def test_empty_history_is_unavailable_on_both_letters():
    result = score_canslim_ca(_history())
    assert result["c"]["verdict"] == "unavailable"
    assert result["a"]["verdict"] == "unavailable"
