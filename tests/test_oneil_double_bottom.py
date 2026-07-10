"""Unit tests for O'Neil double-bottom base detection."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.oneil_cup import prepare_ohlcv
from tradingagents.dataflows.oneil_double_bottom import detect_double_bottom


def _double_bottom(
    second_low_offset: float = -1.0,
    rally_days: int = 18,
    decline_days: int = 18,
    base_volume: float = 500_000.0,
    up_gain: float = 40.0,
) -> pd.DataFrame:
    closes, volumes = [], []
    for index in range(40):
        closes.append(90.0 if up_gain == 0 else 50.0 + up_gain * index / 39)
        volumes.append(1_000_000.0)
    first_low = 70.0
    for price in np.linspace(closes[-1] - 2, first_low, 8):
        closes.append(float(price))
        volumes.append(base_volume)
    for price in np.linspace(first_low + 1, 86.0, rally_days):
        closes.append(float(price))
        volumes.append(base_volume)
    second_low = first_low + second_low_offset
    for price in np.linspace(86.0 - 1, second_low, decline_days):
        closes.append(float(price))
        volumes.append(base_volume)
    for price in np.linspace(second_low + 1, 79.0, 8):
        closes.append(float(price))
        volumes.append(base_volume)
    closes_arr = np.array(closes)
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2024-01-02", periods=len(closes)),
            "Open": closes_arr,
            "High": closes_arr + 0.5,
            "Low": closes_arr - 0.5,
            "Close": closes_arr,
            "Volume": volumes,
        }
    )


def _candidate(**kwargs: float | int) -> object | None:
    return detect_double_bottom(_double_bottom(**kwargs), atr_value=1.0)


@pytest.mark.unit
def test_textbook_w_with_undercut_detected():
    candidate = _candidate()

    assert candidate is not None
    assert candidate.geometry["second_low_behavior"] == "undercut"
    assert candidate.undercut is True
    assert candidate.pivot_price == candidate.geometry["middle_peak"]["price"]


@pytest.mark.unit
def test_equal_lows_valid_without_undercut_flag():
    candidate = _candidate(second_low_offset=0.0)

    assert candidate is not None
    assert candidate.geometry["second_low_behavior"] == "equal"
    assert candidate.undercut is False


@pytest.mark.unit
def test_higher_second_low_valid():
    candidate = _candidate(second_low_offset=0.5)

    assert candidate is not None
    assert candidate.geometry["second_low_behavior"] == "higher"


@pytest.mark.unit
def test_second_low_far_above_band_rejected():
    assert _candidate(second_low_offset=5.0) is None


@pytest.mark.unit
def test_too_short_w_rejected():
    assert _candidate(rally_days=8, decline_days=8) is None


@pytest.mark.unit
def test_no_volume_dry_up_rejected():
    assert _candidate(base_volume=1_500_000.0) is None


@pytest.mark.unit
def test_no_prior_uptrend_rejected():
    assert _candidate(up_gain=0.0) is None


@pytest.mark.unit
def test_evidence_narrates_shakeout_and_volume():
    candidate = _candidate()

    assert candidate is not None
    behavior = next(item for item in candidate.evidence if "shakeout" in item.lower())
    assert candidate.geometry["first_low"]["date"] in behavior
    assert f"{candidate.geometry['first_low']['price']:.2f}" in behavior
    assert candidate.geometry["second_low"]["date"] in behavior
    assert f"{candidate.geometry['second_low']['price']:.2f}" in behavior
    assert "contracted" in " ".join(candidate.evidence).lower()


@pytest.mark.unit
def test_prepare_ohlcv_drops_future_rows_past_curr_date():
    frame = _double_bottom()
    cutoff = frame["Date"].iloc[85].strftime("%Y-%m-%d")

    prepared = prepare_ohlcv(frame, cutoff, look_back_days=420)

    assert prepared["Date"].max() <= pd.Timestamp(cutoff)
