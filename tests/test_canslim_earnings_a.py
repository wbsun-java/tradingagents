"""Unit tests for the CANSLIM A earnings-growth scorer."""

from __future__ import annotations

import pytest

from tests.test_canslim_earnings_c import _annual, _history
from tradingagents.dataflows.canslim_earnings import score_canslim_ca


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
