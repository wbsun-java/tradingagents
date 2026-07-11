"""Unit tests for the O'Neil base-pattern JSON payload."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.canslim_earnings_data import AnnualEps, EarningsHistory, QuarterEps
from tradingagents.dataflows.oneil_base_patterns import PatternDetection
from tradingagents.dataflows.oneil_base_types import BaseCandidate
from tradingagents.dataflows.oneil_bias import (
    SECONDARY_WEIGHT,
    analyze_oneil_setup,
    analyze_oneil_setup_from_data,
)


def _full_sequence(breakout_vol_mult: float = 1.8) -> pd.DataFrame:
    lengths = (50, 45, 20, 45, 13, 15)
    closes: list[float] = []
    volumes: list[float] = []
    for index in range(lengths[0]):
        closes.append(50.0 + 60.0 * index / (lengths[0] - 1))
        volumes.append(1_000_000.0)
    high, low = closes[-1], closes[-1] * 0.8
    for index in range(lengths[1]):
        ease = (1 - np.cos((index + 1) * np.pi / lengths[1])) / 2
        closes.append(high - (high - low) * ease)
        volumes.append(1_000_000.0)
    rng = np.random.default_rng(42)
    for _ in range(lengths[2]):
        closes.append(low + rng.uniform(-0.3, 0.3))
        volumes.append(900_000.0)
    for index in range(lengths[3]):
        ease = (1 - np.cos(index * np.pi / (lengths[3] - 1))) / 2
        closes.append(low + (high - low) * ease)
        volumes.append(1_000_000.0)
    handle_low = closes[-1] * 0.94
    for index in range(lengths[4]):
        closes.append(high - (high - handle_low) * np.sin(index * np.pi / (lengths[4] - 1)))
        volumes.append(600_000.0)
    for index in range(lengths[5]):
        closes.append(high * (1.02 + 0.01 * index))
        volumes.append(1_000_000.0 * (breakout_vol_mult if index == 0 else 1))
    prices = np.array(closes)
    return pd.DataFrame({"Date": pd.bdate_range("2024-01-02", periods=len(prices)), "Open": prices,
                         "High": prices + 0.5, "Low": prices - 0.5, "Close": prices, "Volume": volumes})


def _flat_frame() -> pd.DataFrame:
    return pd.DataFrame({"Date": pd.bdate_range("2024-01-02", periods=200), "Open": 100.0,
                         "High": 100.5, "Low": 99.5, "Close": 100.0, "Volume": 1_000_000.0})


@pytest.mark.unit
def test_nothing_detected_yields_null_primary():
    data = _flat_frame()
    result = analyze_oneil_setup_from_data(data, data["Date"].iloc[-1].strftime("%Y-%m-%d"))
    assert result["primary_pattern"] is None
    assert result["setup_bias"] == "neutral"
    assert result["other_detections"] == []
    assert result["confidence"] == 0.0


@pytest.mark.unit
def test_all_failed_reports_most_recent_failure_neutral(monkeypatch: pytest.MonkeyPatch):
    candidate = BaseCandidate("flat_base", True, 100.0, "2024-06-01", 10, {}, [])
    failed = PatternDetection(candidate, "failed", None, 0.0)
    monkeypatch.setattr("tradingagents.dataflows.oneil_bias.detect_all", lambda *_: [candidate])
    monkeypatch.setattr("tradingagents.dataflows.oneil_bias.evaluate_candidates", lambda *_: [failed])
    data = _flat_frame()
    result = analyze_oneil_setup_from_data(data, data["Date"].iloc[-1].strftime("%Y-%m-%d"))
    assert result["primary_pattern"]["status"] == "failed"
    assert result["setup_bias"] == "neutral"


@pytest.mark.unit
def test_payload_contract_keys_always_present():
    data = _full_sequence()
    result = analyze_oneil_setup_from_data(data, data["Date"].iloc[-1].strftime("%Y-%m-%d"), rs_score=0.05)
    assert {"pattern_type", "status", "pivot_price", "pivot_date", "geometry", "handle", "breakout"} <= result["primary_pattern"].keys()
    assert {"setup_bias", "confidence", "secondary_weight", "weight_note", "evidence", "analysis_date", "other_detections"} <= result.keys()
    assert result["secondary_weight"] == SECONDARY_WEIGHT


@pytest.mark.unit
def test_weight_note_says_base_pattern_not_cup():
    assert "base-pattern" in analyze_oneil_setup_from_data(_flat_frame(), "2024-10-07")["weight_note"]
    assert "CANSLIM" not in analyze_oneil_setup_from_data(_flat_frame(), "2024-10-07")["weight_note"]


@pytest.mark.unit
def test_cup_with_handle_fixture_preserves_confirmed_status():
    data = _full_sequence()
    result = analyze_oneil_setup_from_data(data, data["Date"].iloc[-1].strftime("%Y-%m-%d"), rs_score=0.05)
    assert result["primary_pattern"]["pattern_type"] == "cup_with_handle"
    assert result["primary_pattern"]["status"] == "confirmed"
    assert result["setup_bias"] == "bullish"


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
