"""Unit tests for the O'Neil setup synthesis / top-level JSON shape."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.oneil_bias import SECONDARY_WEIGHT, analyze_oneil_setup_from_data


def _full_sequence(breakout_vol_mult: float = 1.8) -> pd.DataFrame:
    prior_up_len, decline_len, base_len, recover_len, handle_len, post_len = 50, 45, 20, 45, 13, 15
    start_price, up_gain, depth_pct, handle_depth_pct = 50.0, 60.0, 0.20, 0.06
    closes: list[float] = []
    vols: list[float] = []
    for i in range(prior_up_len):
        closes.append(start_price + up_gain * i / (prior_up_len - 1))
        vols.append(1_000_000.0)
    left_high = closes[-1]
    low_price = left_high * (1 - depth_pct)
    for i in range(decline_len):
        t = (i + 1) / decline_len
        ease = (1 - np.cos(t * np.pi)) / 2
        closes.append(left_high - (left_high - low_price) * ease)
        vols.append(1_000_000.0)
    rng = np.random.default_rng(42)
    for _ in range(base_len):
        closes.append(low_price + rng.uniform(-0.3, 0.3))
        vols.append(900_000.0)
    for i in range(recover_len):
        t = i / (recover_len - 1)
        ease = (1 - np.cos(t * np.pi)) / 2
        closes.append(low_price + (left_high - low_price) * ease)
        vols.append(1_000_000.0)
    right_high = closes[-1]
    handle_low = right_high * (1 - handle_depth_pct)
    for i in range(handle_len):
        t = i / (handle_len - 1)
        depth_ease = np.sin(t * np.pi)
        closes.append(right_high - (right_high - handle_low) * depth_ease)
        vols.append(600_000.0)
    pivot = left_high
    for i in range(post_len):
        if i == 0:
            closes.append(pivot * 1.02)
            vols.append(1_000_000.0 * breakout_vol_mult)
        else:
            closes.append(pivot * (1.02 + 0.01 * i))
            vols.append(1_000_000.0)
    n = len(closes)
    dates = pd.bdate_range("2024-01-02", periods=n)
    closes_arr = np.array(closes)
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": closes_arr,
            "High": closes_arr + 0.5,
            "Low": closes_arr - 0.5,
            "Close": closes_arr,
            "Volume": vols,
        }
    )


@pytest.mark.unit
def test_confirmed_setup_has_full_payload_and_bullish_bias():
    df = _full_sequence()
    curr_date = df["Date"].iloc[-1].strftime("%Y-%m-%d")

    result = analyze_oneil_setup_from_data(df, curr_date, rs_score=0.05)

    assert result["status"] == "confirmed"
    assert result["setup_bias"] == "bullish"
    assert result["secondary_weight"] == SECONDARY_WEIGHT
    assert result["cup"] is not None
    assert result["handle"] is not None
    assert result["breakout"] is not None
    assert len(result["evidence"]) >= 3
    assert result["analysis_date"] == curr_date


@pytest.mark.unit
def test_no_cup_returns_neutral_with_secondary_weight_still_present():
    flat = pd.DataFrame(
        {
            "Date": pd.bdate_range("2024-01-02", periods=200),
            "Open": [100.0] * 200, "High": [100.5] * 200, "Low": [99.5] * 200,
            "Close": [100.0] * 200, "Volume": [1_000_000.0] * 200,
        }
    )
    curr_date = flat["Date"].iloc[-1].strftime("%Y-%m-%d")

    result = analyze_oneil_setup_from_data(flat, curr_date)

    assert result["status"] == "none"
    assert result["setup_bias"] == "neutral"
    assert result["cup"] is None
    assert result["secondary_weight"] == SECONDARY_WEIGHT


@pytest.mark.unit
def test_no_future_data_leaks_into_the_result():
    df = _full_sequence()
    cutoff_date = df["Date"].iloc[150].strftime("%Y-%m-%d")

    result = analyze_oneil_setup_from_data(df, cutoff_date)

    # At day 150 the handle/breakout haven't happened yet in this fixture.
    assert result["status"] in ("none", "forming")
