"""Unit tests for O'Neil handle detection, using synthetic OHLCV."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.oneil_cup import atr, detect_cup, prepare_ohlcv
from tradingagents.dataflows.oneil_handle import detect_handle


def _cup_then_handle(
    handle_depth_pct: float = 0.06,
    handle_vol_mult: float = 0.6,
    break_lower_half: bool = False,
) -> pd.DataFrame:
    prior_up_len, decline_len, base_len, recover_len, handle_len = 50, 45, 20, 45, 13
    start_price, up_gain, depth_pct = 50.0, 60.0, 0.20
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
    if break_lower_half:
        midpoint = (left_high + low_price) / 2
        handle_low = midpoint - 5.0
    for i in range(handle_len):
        t = i / (handle_len - 1)
        depth_ease = np.sin(t * np.pi)
        closes.append(right_high - (right_high - handle_low) * depth_ease)
        vols.append(1_000_000.0 * handle_vol_mult)
    for _ in range(15):
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


def _prepared_cup(df: pd.DataFrame):
    prepared = prepare_ohlcv(df, df["Date"].iloc[-1].strftime("%Y-%m-%d"), look_back_days=420)
    atr_value = float(atr(prepared).iloc[-1])
    cup = detect_cup(prepared, atr_value)
    assert cup is not None, "fixture must produce a valid cup for these handle tests"
    return prepared, atr_value, cup


@pytest.mark.unit
def test_detects_valid_handle_in_upper_half_with_volume_dry_up():
    prepared, atr_value, cup = _prepared_cup(_cup_then_handle())

    handle = detect_handle(prepared, cup, atr_value)

    assert handle is not None
    assert handle.valid is True
    midpoint = (cup.left_high_price + cup.low_price) / 2.0
    assert handle.low_price >= midpoint
    assert handle.volume_ratio_vs_cup is not None
    assert handle.volume_ratio_vs_cup < 1.0
    assert handle.duration_days < cup.duration_days


@pytest.mark.unit
def test_handle_dropping_into_lower_half_is_invalid():
    prepared, atr_value, cup = _prepared_cup(_cup_then_handle(break_lower_half=True))

    handle = detect_handle(prepared, cup, atr_value)

    assert handle is not None
    assert handle.valid is False
    assert "lower half" in handle.evidence[0]


@pytest.mark.unit
def test_handle_without_volume_dry_up_is_invalid():
    prepared, atr_value, cup = _prepared_cup(_cup_then_handle(handle_vol_mult=1.5))

    handle = detect_handle(prepared, cup, atr_value)

    assert handle is not None
    assert handle.valid is False
    assert any("did not dry up" in e for e in handle.evidence)
