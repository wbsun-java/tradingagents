"""Unit tests for the core Pocket Pivot detector: ATR-adaptive MA cross-up
plus the volume-signature rule."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.pocket_pivot_signals import (
    atr,
    find_pocket_pivots,
    prepare_ohlcv,
)

ATR = 2.0


def _decline_then_bounce(
    decline_days: int,
    start_price: float,
    end_price: float,
    bounce_close: float,
    bounce_volume: float,
    down_volume: float = 1_000_000.0,
) -> pd.DataFrame:
    """`decline_days` bars linearly declining from start_price to end_price
    (each a down day on `down_volume`), followed by one bounce bar closing
    at `bounce_close` on `bounce_volume`."""
    dates = pd.date_range("2020-01-01", periods=decline_days + 1, freq="D")
    step = (start_price - end_price) / (decline_days - 1)
    closes = [start_price - step * k for k in range(decline_days)]
    closes.append(bounce_close)
    volumes = [down_volume] * decline_days + [bounce_volume]
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": closes,
            "High": [c + 0.5 for c in closes],
            "Low": [c - 0.5 for c in closes],
            "Close": closes,
            "Volume": volumes,
        }
    )


@pytest.mark.unit
def test_10dma_pocket_pivot_fires_on_bounce_with_strong_volume():
    df = _decline_then_bounce(
        decline_days=15, start_price=110.0, end_price=90.0,
        bounce_close=101.0, bounce_volume=5_000_000.0,
    )
    events = find_pocket_pivots(df, ATR, ma_periods=(10,))
    assert len(events) == 1
    assert events[0].ma_period == 10
    assert events[0].volume == 5_000_000.0
    assert events[0].highest_down_volume_10d == 1_000_000.0


@pytest.mark.unit
def test_50dma_pocket_pivot_fires_on_deep_bounce_with_strong_volume():
    df = _decline_then_bounce(
        decline_days=70, start_price=150.0, end_price=50.0,
        bounce_close=90.0, bounce_volume=8_000_000.0,
    )
    events = find_pocket_pivots(df, ATR, ma_periods=(50,))
    assert len(events) == 1
    assert events[0].ma_period == 50


@pytest.mark.unit
def test_silent_when_volume_does_not_exceed_highest_down_volume():
    df = _decline_then_bounce(
        decline_days=15, start_price=110.0, end_price=90.0,
        bounce_close=101.0, bounce_volume=500_000.0, down_volume=1_000_000.0,
    )
    assert find_pocket_pivots(df, ATR, ma_periods=(10,)) == []


@pytest.mark.unit
def test_silent_when_bounce_does_not_clear_the_ma():
    df = _decline_then_bounce(
        decline_days=15, start_price=110.0, end_price=90.0,
        bounce_close=90.5, bounce_volume=5_000_000.0,
    )
    assert find_pocket_pivots(df, ATR, ma_periods=(10,)) == []


@pytest.mark.unit
def test_gap_up_flag_reflects_open_vs_prior_close():
    df = _decline_then_bounce(
        decline_days=15, start_price=110.0, end_price=90.0,
        bounce_close=101.0, bounce_volume=5_000_000.0,
    )
    df.loc[df.index[-1], "Open"] = 100.5
    events = find_pocket_pivots(df, ATR, ma_periods=(10,))
    assert len(events) == 1
    assert events[0].gap_up is True


@pytest.mark.unit
def test_prepare_ohlcv_raises_when_fewer_than_min_rows_available():
    dates = pd.date_range("2020-01-01", periods=30, freq="D")
    df = pd.DataFrame(
        {
            "Date": dates,
            "Open": [100.0] * 30,
            "High": [100.5] * 30,
            "Low": [99.5] * 30,
            "Close": [100.0] * 30,
            "Volume": [1_000_000.0] * 30,
        }
    )
    with pytest.raises(ValueError):
        prepare_ohlcv(df, "2020-01-30", look_back_days=30)


@pytest.mark.unit
def test_prepare_ohlcv_raises_for_missing_columns():
    dates = pd.date_range("2020-01-01", periods=60, freq="D")
    df = pd.DataFrame(
        {
            "Date": dates,
            "Open": [100.0] * 60,
            "High": [100.5] * 60,
            "Low": [99.5] * 60,
            "Close": [100.0] * 60,
        }
    )
    with pytest.raises(ValueError):
        prepare_ohlcv(df, "2020-03-01", look_back_days=60)


@pytest.mark.unit
def test_atr_returns_non_nan_value_with_sufficient_rows():
    dates = pd.date_range("2020-01-01", periods=20, freq="D")
    closes = [100.0 + (1 if k % 2 == 0 else -1) for k in range(20)]
    df = pd.DataFrame(
        {
            "Date": dates,
            "Open": closes,
            "High": [c + 0.5 for c in closes],
            "Low": [c - 0.5 for c in closes],
            "Close": closes,
            "Volume": [1_000_000.0] * 20,
        }
    )
    atr_series = atr(df)
    assert not pd.isna(atr_series.iloc[-1])
    assert atr_series.iloc[-1] > 0
