"""Unit tests for Wyckoff bias synthesis (accumulation vs distribution vs neutral)."""

from __future__ import annotations

import pandas as pd
import pytest

import tradingagents.dataflows.wyckoff_bias as wyckoff_bias
from tradingagents.dataflows.wyckoff_bias import (
    DOMINANT_WEIGHT,
    analyze_wyckoff_structure,
    analyze_wyckoff_structure_from_data,
)


def _to_df(closes, highs, lows, volumes) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2023-01-02", periods=len(closes)),
            "Open": closes, "High": highs, "Low": lows, "Close": closes, "Volume": volumes,
        }
    )


def _accumulation_df() -> pd.DataFrame:
    down_len = 60
    closes = [150.0 - 70.0 * i / (down_len - 1) for i in range(down_len)]
    volumes = [1_000_000.0] * down_len
    for i in range(29):
        phase = i % 14
        val = 78.0 + phase * 2.0 if phase <= 7 else 92.0 - (phase - 7) * 2.0
        closes.append(val)
        volumes.append(1_000_000.0)
    volumes[down_len + 28] = 2_500_000.0
    highs = [c + 1.0 for c in closes]
    lows = [c - 1.0 for c in closes]
    bars = [
        (85.0, 84.0, 86.0, 1e6), (88.0, 87.0, 89.0, 1e6), (90.0, 89.0, 91.0, 1e6),
        (84.0, 83.0, 85.0, 1e6), (78.0, 77.0, 79.0, 1e6), (81.0, 80.0, 82.0, 1e6),
        (77.3, 62.0, 78.0, 1e6),
    ] + [(80.0, 79.0, 81.0, 1e6)] * 10
    for c, low, high, vol in bars:
        closes.append(c)
        highs.append(high)
        lows.append(low)
        volumes.append(vol)
    return _to_df(closes, highs, lows, volumes)


def _distribution_df() -> pd.DataFrame:
    up_len = 60
    closes = [40.0 + 45.0 * i / (up_len - 1) for i in range(up_len)]
    volumes = [1_000_000.0] * up_len
    for i in range(22):
        phase = i % 14
        val = 78.0 + phase * 2.0 if phase <= 7 else 92.0 - (phase - 7) * 2.0
        closes.append(val)
        volumes.append(1_000_000.0)
    volumes[up_len + 21] = 2_500_000.0
    highs = [c + 1.0 for c in closes]
    lows = [c - 1.0 for c in closes]
    bars = [
        (82.0, 81.0, 83.0, 1e6), (80.0, 79.0, 81.0, 1e6), (78.0, 77.0, 79.0, 1e6),
        (84.0, 83.0, 85.0, 1e6), (92.0, 91.0, 93.0, 1e6), (87.0, 86.0, 88.0, 1e6),
        (92.7, 92.0, 98.0, 1e6),
    ] + [(80.0, 79.0, 81.0, 1e6)] * 10
    for c, low, high, vol in bars:
        closes.append(c)
        highs.append(high)
        lows.append(low)
        volumes.append(vol)
    return _to_df(closes, highs, lows, volumes)


@pytest.mark.unit
def test_accumulation_range_yields_bullish_bias_with_dominant_weight():
    df = _accumulation_df()
    result = analyze_wyckoff_structure_from_data(df, df["Date"].iloc[-1].strftime("%Y-%m-%d"))

    assert result["trading_range"]["kind"] == "accumulation"
    assert result["phase_bias"] == "bullish"
    assert result["current_phase"] == "C"
    assert result["dominant_weight"] == DOMINANT_WEIGHT
    assert result["weight_note"]
    assert len(result["events"]) >= 4


@pytest.mark.unit
def test_distribution_range_yields_bearish_bias():
    df = _distribution_df()
    result = analyze_wyckoff_structure_from_data(df, df["Date"].iloc[-1].strftime("%Y-%m-%d"))

    assert result["trading_range"]["kind"] == "distribution"
    assert result["phase_bias"] == "bearish"
    assert result["current_phase"] == "C"


@pytest.mark.unit
def test_pure_uptrend_yields_neutral_with_none_range():
    length = 120
    closes = [50.0 + 100.0 * i / (length - 1) for i in range(length)]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    volumes = [1_000_000.0] * length
    df = _to_df(closes, highs, lows, volumes)

    result = analyze_wyckoff_structure_from_data(df, df["Date"].iloc[-1].strftime("%Y-%m-%d"))

    assert result["trading_range"]["kind"] == "none"
    assert result["phase_bias"] == "neutral"
    assert result["events"] == []
    assert result["dominant_weight"] == DOMINANT_WEIGHT


@pytest.mark.unit
def test_analyze_wyckoff_structure_returns_json_with_uppercased_symbol(monkeypatch):
    df = _accumulation_df()
    monkeypatch.setattr(wyckoff_bias, "load_ohlcv", lambda symbol, date: df)

    payload = analyze_wyckoff_structure("aapl", df["Date"].iloc[-1].strftime("%Y-%m-%d"))

    assert '"symbol": "AAPL"' in payload
    assert '"phase_bias": "bullish"' in payload


@pytest.mark.unit
def test_accumulation_result_includes_vsa_signals_key():
    df = _accumulation_df()
    result = analyze_wyckoff_structure_from_data(df, df["Date"].iloc[-1].strftime("%Y-%m-%d"))

    assert "vsa_signals" in result
    assert isinstance(result["vsa_signals"], list)


@pytest.mark.unit
def test_neutral_result_has_no_vsa_signals_key():
    length = 120
    closes = [50.0 + 100.0 * i / (length - 1) for i in range(length)]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    volumes = [1_000_000.0] * length
    df = _to_df(closes, highs, lows, volumes)

    result = analyze_wyckoff_structure_from_data(df, df["Date"].iloc[-1].strftime("%Y-%m-%d"))

    assert "vsa_signals" not in result
