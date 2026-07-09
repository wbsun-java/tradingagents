"""Unit tests for Pocket Pivot context flags: downtrend, MA position,
V-shape risk, and extension from the 10dma."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.pocket_pivot_context import (
    extended_from_ma,
    ma_position,
    multi_month_downtrend,
    v_shape_risk,
)

ATR = 2.0


def _flat(n: int, price: float = 100.0, volume: float = 1_000_000.0) -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    closes = [price] * n
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": closes,
            "High": [c + 0.5 for c in closes],
            "Low": [c - 0.5 for c in closes],
            "Close": closes,
            "Volume": [volume] * n,
        }
    )


@pytest.mark.unit
def test_multi_month_downtrend_true_when_price_fell_over_105_bars():
    df = _flat(200)
    df.loc[df.index[-1], "Close"] = 80.0
    assert multi_month_downtrend(df, len(df) - 1) is True


@pytest.mark.unit
def test_multi_month_downtrend_false_when_price_rose_over_105_bars():
    df = _flat(200)
    df.loc[df.index[-1], "Close"] = 120.0
    assert multi_month_downtrend(df, len(df) - 1) is False


@pytest.mark.unit
def test_multi_month_downtrend_none_with_insufficient_history():
    df = _flat(50)
    assert multi_month_downtrend(df, len(df) - 1) is None


@pytest.mark.unit
def test_ma_position_flags_above_both_smas():
    df = _flat(250)
    df.loc[df.index[-1], "Close"] = 150.0
    ctx = ma_position(df, len(df) - 1)
    assert ctx["above_sma50"] is True
    assert ctx["above_sma200"] is True


@pytest.mark.unit
def test_ma_position_sma200_none_with_insufficient_history():
    df = _flat(100)
    ctx = ma_position(df, len(df) - 1)
    assert ctx["sma200"] is None
    assert ctx["above_sma200"] is None


@pytest.mark.unit
def test_v_shape_risk_true_on_deep_undercut_and_fast_reversal():
    df = _flat(60)
    i = len(df) - 1
    df.loc[df.index[i - 2], "Close"] = 80.0
    df.loc[df.index[i - 1], "Close"] = 90.0
    df.loc[df.index[i], "Close"] = 101.0
    assert v_shape_risk(df, i, 10, ATR) is True


@pytest.mark.unit
def test_v_shape_risk_false_on_shallow_undercut():
    df = _flat(60)
    i = len(df) - 1
    df.loc[df.index[i - 2], "Close"] = 99.5
    df.loc[df.index[i - 1], "Close"] = 99.8
    df.loc[df.index[i], "Close"] = 101.0
    assert v_shape_risk(df, i, 10, ATR) is False


@pytest.mark.unit
def test_extended_from_ma_true_when_far_above_10dma():
    df = _flat(60)
    i = len(df) - 1
    df.loc[df.index[i], "Close"] = 110.0
    assert extended_from_ma(df, i, 10, ATR) is True


@pytest.mark.unit
def test_extended_from_ma_none_for_50dma():
    df = _flat(60)
    i = len(df) - 1
    assert extended_from_ma(df, i, 50, ATR) is None
