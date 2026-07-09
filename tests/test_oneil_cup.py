"""Unit tests for O'Neil cup detection, using synthetic OHLCV."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.oneil_cup import atr, detect_cup, prepare_ohlcv


def _cup(
    prior_up_len: int = 50,
    decline_len: int = 45,
    base_len: int = 20,
    recover_len: int = 45,
    up_gain: float = 60.0,
    depth_pct: float = 0.20,
    start_price: float = 50.0,
    extra_flat: int = 30,
) -> pd.DataFrame:
    closes: list[float] = []
    vols: list[float] = []
    for i in range(prior_up_len):
        closes.append(start_price + up_gain * i / (prior_up_len - 1))
        vols.append(1_000_000.0)
    left_high = closes[-1]
    low_price = left_high * (1 - depth_pct)
    # Decline starts at t>0 so the peak bar stays a strict, unique local max
    # (a flat first step would tie with the peak and defeat find_pivots'
    # uniqueness check).
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
    for _ in range(extra_flat):
        closes.append(closes[-1])
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


def _v_shape() -> pd.DataFrame:
    prior_up_len, drop_len, recover_len, post_len = 50, 3, 3, 100
    start_price, up_gain, depth_pct = 50.0, 60.0, 0.20
    closes, vols = [], []
    for i in range(prior_up_len):
        closes.append(start_price + up_gain * i / (prior_up_len - 1))
        vols.append(1_000_000.0)
    left_high = closes[-1]
    low_price = left_high * (1 - depth_pct)
    for i in range(drop_len):
        t = (i + 1) / drop_len
        closes.append(left_high - (left_high - low_price) * t)
        vols.append(1_000_000.0)
    for i in range(recover_len):
        t = (i + 1) / recover_len
        closes.append(low_price + (left_high - low_price) * t)
        vols.append(1_000_000.0)
    for _ in range(post_len):
        closes.append(left_high)
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


def _prepared(df: pd.DataFrame):
    prepared = prepare_ohlcv(df, df["Date"].iloc[-1].strftime("%Y-%m-%d"), look_back_days=420)
    return prepared, float(atr(prepared).iloc[-1])


@pytest.mark.unit
def test_detects_textbook_cup_with_correct_bounds():
    prepared, atr_value = _prepared(_cup())

    cup = detect_cup(prepared, atr_value)

    assert cup is not None
    assert cup.left_high_date == "2024-03-11"
    assert cup.left_high_price == pytest.approx(110.5, abs=0.01)
    assert cup.low_date == "2024-06-06"
    assert cup.low_price == pytest.approx(87.24, abs=0.5)
    assert cup.right_high_date == "2024-08-06"
    assert 15.0 <= cup.depth_pct * 100 <= 25.0
    assert 90 <= cup.duration_days <= 120


@pytest.mark.unit
def test_v_shape_does_not_qualify_as_cup():
    prepared, atr_value = _prepared(_v_shape())

    assert detect_cup(prepared, atr_value) is None


@pytest.mark.unit
def test_no_prior_uptrend_does_not_qualify_as_cup():
    prepared, atr_value = _prepared(_cup(up_gain=0.0))

    assert detect_cup(prepared, atr_value) is None


@pytest.mark.unit
def test_depth_too_shallow_does_not_qualify_as_cup():
    prepared, atr_value = _prepared(_cup(depth_pct=0.03))

    assert detect_cup(prepared, atr_value) is None


@pytest.mark.unit
def test_depth_too_deep_does_not_qualify_as_cup():
    prepared, atr_value = _prepared(_cup(depth_pct=0.65))

    assert detect_cup(prepared, atr_value) is None


@pytest.mark.unit
def test_prepare_ohlcv_drops_future_rows_past_curr_date():
    df = _cup()
    cutoff_date = df["Date"].iloc[80].strftime("%Y-%m-%d")

    prepared = prepare_ohlcv(df, cutoff_date, look_back_days=420)

    assert prepared["Date"].max() <= pd.Timestamp(cutoff_date)
