"""Unit tests for the shared Wyckoff trading-range detector, synthetic OHLCV only."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.wyckoff_range import atr, detect_trading_range, prepare_ohlcv


def _downtrend_then_range(down_len: int = 60, range_len: int = 60) -> pd.DataFrame:
    down_closes = [150.0 - 70.0 * i / (down_len - 1) for i in range(down_len)]
    range_closes = []
    for i in range(range_len):
        phase = i % 12
        offset = phase if phase <= 6 else 12 - phase  # triangle wave, period 12, amplitude 6
        range_closes.append(78.0 + offset * (14.0 / 6.0))  # oscillates ~78..92
    closes = down_closes + range_closes
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2024-01-02", periods=len(closes)),
            "Open": closes,
            "High": [c + 1.0 for c in closes],
            "Low": [c - 1.0 for c in closes],
            "Close": closes,
            "Volume": [1_000_000.0] * len(closes),
        }
    )


def _steady_uptrend(length: int = 120) -> pd.DataFrame:
    closes = [50.0 + 100.0 * i / (length - 1) for i in range(length)]
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2024-01-02", periods=length),
            "Open": closes,
            "High": [c + 0.5 for c in closes],
            "Low": [c - 0.5 for c in closes],
            "Close": closes,
            "Volume": [1_000_000.0] * length,
        }
    )


@pytest.mark.unit
def test_detects_range_after_downtrend_with_correct_bounds():
    df = prepare_ohlcv(_downtrend_then_range(), "2024-12-01", look_back_days=504)
    atr_value = float(atr(df).iloc[-1])

    result = detect_trading_range(df, atr_value)

    assert result is not None
    assert result.prior_trend == "down"
    assert 76.0 <= result.range_low <= 80.0
    assert 90.0 <= result.range_high <= 94.0
    assert len(result.high_touches) >= 2
    assert len(result.low_touches) >= 2


@pytest.mark.unit
def test_pure_uptrend_has_no_repeated_band_to_find():
    df = prepare_ohlcv(_steady_uptrend(), "2024-12-01", look_back_days=504)
    atr_value = float(atr(df).iloc[-1])

    result = detect_trading_range(df, atr_value)

    assert result is None


@pytest.mark.unit
def test_range_stays_valid_through_a_long_quiet_stretch_if_price_is_still_nearby():
    """Accumulation/distribution can sit quietly for months with no new pivot
    touches; the range must not be dropped just because its last touch is old,
    as long as price hasn't left the vicinity of the range.
    """
    df = _downtrend_then_range()
    quiet = pd.DataFrame(
        {
            "Date": pd.bdate_range(df["Date"].iloc[-1] + pd.Timedelta(days=1), periods=80),
            "Open": [85.0] * 80,
            "High": [85.5] * 80,
            "Low": [84.5] * 80,
            "Close": [85.0] * 80,
            "Volume": [1_000_000.0] * 80,
        }
    )
    df = pd.concat([df, quiet], ignore_index=True)
    prepared = prepare_ohlcv(df, df["Date"].iloc[-1].strftime("%Y-%m-%d"), look_back_days=504)
    atr_value = float(atr(prepared).iloc[-1])

    result = detect_trading_range(prepared, atr_value)

    assert result is not None
    assert 76.0 <= result.range_low <= 80.0
    assert 90.0 <= result.range_high <= 94.0


@pytest.mark.unit
def test_range_is_dropped_once_price_has_drifted_far_beyond_it():
    """Once price has moved well past the old range (many range-widths away),
    that range is no longer structurally relevant and must not be reported.
    """
    df = _downtrend_then_range()
    rally_len = 80
    rally = pd.DataFrame(
        {
            "Date": pd.bdate_range(df["Date"].iloc[-1] + pd.Timedelta(days=1), periods=rally_len),
            "Open": [85.0 + 165.0 * i / (rally_len - 1) for i in range(rally_len)],
            "High": [86.0 + 165.0 * i / (rally_len - 1) for i in range(rally_len)],
            "Low": [84.0 + 165.0 * i / (rally_len - 1) for i in range(rally_len)],
            "Close": [85.0 + 165.0 * i / (rally_len - 1) for i in range(rally_len)],
            "Volume": [1_000_000.0] * rally_len,
        }
    )
    df = pd.concat([df, rally], ignore_index=True)
    prepared = prepare_ohlcv(df, df["Date"].iloc[-1].strftime("%Y-%m-%d"), look_back_days=504)
    atr_value = float(atr(prepared).iloc[-1])

    result = detect_trading_range(prepared, atr_value)

    assert result is None


@pytest.mark.unit
def test_prepare_ohlcv_drops_future_rows_past_curr_date():
    df = _downtrend_then_range()
    cutoff_date = df["Date"].iloc[80].strftime("%Y-%m-%d")

    prepared = prepare_ohlcv(df, cutoff_date, look_back_days=504)

    assert prepared["Date"].max() <= pd.Timestamp(cutoff_date)
