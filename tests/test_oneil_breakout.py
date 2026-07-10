"""Unit tests for O'Neil breakout confirmation and status, using synthetic OHLCV."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.oneil_breakout import (
    BREAKOUT_VOLUME_RATIO,
    UNDERCUT_BONUS,
    breakout_reversed,
    compute_confidence,
    determine_status,
    find_breakout,
)
from tradingagents.dataflows.oneil_cup import atr, detect_cup, prepare_ohlcv
from tradingagents.dataflows.oneil_handle import detect_handle


def _full_sequence(breakout_vol_mult: float = 1.8, reverses: bool = False, no_breakout: bool = False) -> pd.DataFrame:
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
    if no_breakout:
        for _ in range(post_len):
            closes.append(closes[-1])
            vols.append(1_000_000.0)
    else:
        for i in range(post_len):
            if i == 0:
                closes.append(pivot * 1.02)
                vols.append(1_000_000.0 * breakout_vol_mult)
            elif reverses:
                closes.append(pivot * 0.94)
                vols.append(1_000_000.0)
            else:
                closes.append(pivot * (1.02 + 0.01 * i))
                vols.append(1_000_000.0)
    dates = pd.bdate_range("2024-01-02", periods=len(closes))
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


def _prepared_cup_handle(df: pd.DataFrame):
    prepared = prepare_ohlcv(df, df["Date"].iloc[-1].strftime("%Y-%m-%d"), look_back_days=420)
    atr_value = float(atr(prepared).iloc[-1])
    cup = detect_cup(prepared, atr_value)
    assert cup is not None
    handle = detect_handle(prepared, cup, atr_value)
    assert handle is not None and handle.valid
    return prepared, atr_value, cup, handle


@pytest.mark.unit
def test_volume_confirmed_breakout_is_confirmed():
    prepared, atr_value, cup, handle = _prepared_cup_handle(_full_sequence())
    breakout = find_breakout(prepared, cup.left_high_price, handle.end_index + 1, atr_value)
    status = determine_status(complete=True, handle=handle, handle_required=True, breakout=breakout, reversed_after=False)
    assert breakout is not None
    assert breakout.volume_confirmed is True
    assert breakout.volume_ratio >= BREAKOUT_VOLUME_RATIO
    assert status == "confirmed"


@pytest.mark.unit
def test_low_volume_breakout_stays_developing_not_failed():
    prepared, atr_value, cup, handle = _prepared_cup_handle(_full_sequence(breakout_vol_mult=0.9))
    breakout = find_breakout(prepared, cup.left_high_price, handle.end_index + 1, atr_value)
    status = determine_status(complete=True, handle=handle, handle_required=True, breakout=breakout, reversed_after=False)
    assert breakout is not None
    assert breakout.volume_confirmed is False
    assert breakout.volume_ratio < BREAKOUT_VOLUME_RATIO
    assert status == "developing"


@pytest.mark.unit
def test_confirmed_breakout_that_reverses_is_failed():
    prepared, atr_value, cup, handle = _prepared_cup_handle(_full_sequence(reverses=True))
    breakout = find_breakout(prepared, cup.left_high_price, handle.end_index + 1, atr_value)
    assert breakout is not None
    status = determine_status(
        complete=True,
        handle=handle,
        handle_required=True,
        breakout=breakout,
        reversed_after=breakout_reversed(prepared, breakout, cup.left_high_price, atr_value),
    )
    assert status == "failed"


@pytest.mark.unit
def test_no_breakout_attempt_yet_is_developing():
    prepared, atr_value, cup, handle = _prepared_cup_handle(_full_sequence(no_breakout=True))
    breakout = find_breakout(prepared, cup.left_high_price, handle.end_index + 1, atr_value)
    status = determine_status(complete=True, handle=handle, handle_required=True, breakout=breakout, reversed_after=False)
    assert breakout is None
    assert status == "developing"


@pytest.mark.unit
def test_confidence_increases_with_stronger_breakout_volume():
    prepared, atr_value, cup, handle = _prepared_cup_handle(_full_sequence(breakout_vol_mult=1.4))
    weak_breakout = find_breakout(prepared, cup.left_high_price, handle.end_index + 1, atr_value)
    prepared2, atr_value2, cup2, handle2 = _prepared_cup_handle(_full_sequence(breakout_vol_mult=3.0))
    strong_breakout = find_breakout(prepared2, cup2.left_high_price, handle2.end_index + 1, atr_value2)
    weak_conf = compute_confidence("cup_with_handle", "confirmed", handle, weak_breakout, None)
    strong_conf = compute_confidence("cup_with_handle", "confirmed", handle2, strong_breakout, None)
    assert strong_conf > weak_conf


@pytest.mark.unit
def test_confidence_increases_with_higher_rs_score():
    prepared, atr_value, cup, handle = _prepared_cup_handle(_full_sequence())
    breakout = find_breakout(prepared, cup.left_high_price, handle.end_index + 1, atr_value)
    low_rs_conf = compute_confidence("cup_with_handle", "confirmed", handle, breakout, 0.01)
    high_rs_conf = compute_confidence("cup_with_handle", "confirmed", handle, breakout, 0.20)
    assert high_rs_conf > low_rs_conf


@pytest.mark.unit
def test_status_is_forming_with_incomplete_pattern():
    assert determine_status(complete=False, handle=None, handle_required=False, breakout=None, reversed_after=False) == "forming"
    assert compute_confidence("cup_with_handle", "none", None, None, None) == 0.0


@pytest.mark.unit
def test_cup_without_handle_reaches_developing():
    status = determine_status(complete=True, handle=None, handle_required=False, breakout=None, reversed_after=False)
    assert status == "developing"


@pytest.mark.unit
def test_cup_without_handle_confirms_below_cup_with_handle():
    cup_confidence = compute_confidence("cup_with_handle", "confirmed", None, None, None)
    no_handle_confidence = compute_confidence("cup_without_handle", "confirmed", None, None, None)
    assert no_handle_confidence < cup_confidence


@pytest.mark.unit
def test_low_volume_breakout_stays_developing_for_non_cup_pattern():
    prepared, atr_value, cup, handle = _prepared_cup_handle(_full_sequence(breakout_vol_mult=0.9))
    breakout = find_breakout(prepared, cup.left_high_price, handle.end_index + 1, atr_value)
    status = determine_status(complete=True, handle=None, handle_required=False, breakout=breakout, reversed_after=False)
    assert breakout is not None and not breakout.volume_confirmed
    assert status == "developing"


@pytest.mark.unit
def test_undercut_bonus_applies_only_when_set():
    base = compute_confidence("double_bottom_base", "developing", None, None, None)
    undercut = compute_confidence("double_bottom_base", "developing", None, None, None, undercut=True)
    assert undercut - base == pytest.approx(UNDERCUT_BONUS)
