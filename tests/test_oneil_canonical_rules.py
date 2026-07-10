"""Regression tests for O'Neil's canonical cup-and-handle anatomy."""

from __future__ import annotations

import pandas as pd
import pytest

from tests.test_oneil_cup import _cup, _prepared
from tradingagents.dataflows.oneil_base_patterns import PatternDetection, _cup_candidates
from tradingagents.dataflows.oneil_bias import analyze_oneil_setup_from_data
from tradingagents.dataflows.oneil_cup import CupCandidate, detect_cup
from tradingagents.dataflows.oneil_handle import HandleCandidate, detect_handle


@pytest.mark.unit
def test_cup_bottom_without_volume_dryup_rejected():
    flat, flat_atr = _prepared(_cup().assign(Volume=1_000_000.0))
    assert detect_cup(flat, flat_atr) is None

    contracted, contracted_atr = _prepared(_cup())
    candidate = detect_cup(contracted, contracted_atr)
    assert candidate is not None
    assert any("Volume at" in item and "dried up" in item for item in candidate.evidence)


@pytest.mark.unit
def test_prior_advance_below_30_pct_rejected():
    prepared, atr_value = _prepared(_cup(up_gain=12.5))
    assert detect_cup(prepared, atr_value) is None


@pytest.mark.unit
def test_cup_shorter_than_seven_weeks_rejected():
    prepared, atr_value = _prepared(
        _cup(decline_len=12, base_len=6, recover_len=12, extra_flat=80)
    )
    assert detect_cup(prepared, atr_value) is None


@pytest.mark.unit
def test_upward_wedging_handle_invalid(monkeypatch: pytest.MonkeyPatch):
    values = [100.0, 90.0, 91.0, 92.0, 93.0, 96.0, 97.0, 98.0, 89.0, 95.0, 96.0, 97.0]
    df = pd.DataFrame({
        "Date": pd.bdate_range("2024-01-02", periods=len(values)),
        "Open": values, "High": [value + 0.5 for value in values],
        "Low": [value - 0.5 for value in values], "Close": values, "Volume": 500_000.0,
    })
    cup = CupCandidate(0, "2024-01-02", 100.5, "2024-01-02", 79.0, 0,
                       "2024-01-02", 0.21, 40)
    trough = type("PivotStub", (), {"kind": "low", "index": 8, "price": 88.5,
                                     "date": "2024-01-12"})()
    monkeypatch.setattr("tradingagents.dataflows.oneil_handle.find_pivots", lambda *_: [trough])
    handle = detect_handle(df, cup, 1.0)
    assert handle is not None and handle.valid is False
    assert any("drifted upward" in item for item in handle.evidence)


@pytest.mark.unit
def test_cup_with_handle_pivot_is_the_handle_high(monkeypatch: pytest.MonkeyPatch):
    import tradingagents.dataflows.oneil_base_patterns as patterns
    import tradingagents.dataflows.oneil_bias as bias

    df = pd.DataFrame({"Date": pd.bdate_range("2024-01-02", periods=80), "Open": 90.0,
                       "High": 91.0, "Low": 89.0, "Close": 90.0, "Volume": 1_000_000.0})
    cup = CupCandidate(10, "2024-01-16", 100.0, "2024-02-01", 75.0, 50,
                       "2024-03-12", 0.25, 40)
    handle = HandleCandidate("2024-03-13", 60, "2024-03-26", 90.0, 54, 97.0,
                             0.6, 10, True)
    monkeypatch.setattr(patterns, "detect_cup", lambda *_: cup)
    monkeypatch.setattr(patterns, "detect_handle", lambda *_: handle)
    monkeypatch.setattr(patterns, "detect_forming_cup", lambda *_: None)
    candidate = _cup_candidates(df, 1.0)[0]
    assert candidate.pivot_price == 97.0 != cup.left_high_price
    assert candidate.pivot_date == df.at[54, "Date"].strftime("%Y-%m-%d")
    assert candidate.start_index == cup.left_high_index
    assert candidate.base_low_price == handle.low_price

    detection = PatternDetection(candidate, "developing", None, 0.5)
    monkeypatch.setattr(bias, "detect_all", lambda *_: [candidate])
    monkeypatch.setattr(bias, "evaluate_candidates", lambda *_: [detection])
    payload = analyze_oneil_setup_from_data(df, "2024-04-22")
    assert payload["primary_pattern"]["pivot_price"] == 97.0
