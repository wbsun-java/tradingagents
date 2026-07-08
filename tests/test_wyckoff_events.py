"""Unit tests for volume-aware evidence text in the shared Wyckoff event engine."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.wyckoff_events import detect_events
from tradingagents.dataflows.wyckoff_range import atr, detect_trading_range, prepare_ohlcv

_BASE_EVENTS = [
    (85.0, 84.0, 86.0, 1e6), (88.0, 87.0, 89.0, 1e6), (90.0, 89.0, 91.0, 1e6),
    (84.0, 83.0, 85.0, 1e6), (78.0, 77.0, 79.0, 1e6), (81.0, 80.0, 82.0, 1e6),
]


def _fixture(spring_volume: float) -> pd.DataFrame:
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
    bars = list(_BASE_EVENTS) + [(77.3, 62.0, 78.0, spring_volume)] + [(80.0, 79.0, 81.0, 1e6)] * 10
    for c, low, high, vol in bars:
        closes.append(c)
        highs.append(high)
        lows.append(low)
        volumes.append(vol)
    return pd.DataFrame({
        "Date": pd.bdate_range("2023-01-02", periods=len(closes)),
        "Open": closes, "High": highs, "Low": lows, "Close": closes, "Volume": volumes,
    })


def _spring_event(spring_volume: float):
    raw = _fixture(spring_volume)
    df = prepare_ohlcv(raw, raw["Date"].iloc[-1].strftime("%Y-%m-%d"), look_back_days=504)
    atr_value = float(atr(df).iloc[-1])
    rng = detect_trading_range(df, atr_value)
    events, phase = detect_events(df, atr_value, rng, "accumulation")
    return next(e for e in events if e.event == "spring")


@pytest.mark.unit
def test_high_volume_spring_evidence_calls_out_a_terminal_shakeout():
    spring = _spring_event(spring_volume=6_000_000.0)  # ~6x average: violent, high-volume undercut
    assert spring.volume_ratio >= 1.5
    assert "shakeout" in spring.evidence[0].lower()


@pytest.mark.unit
def test_low_volume_spring_evidence_calls_out_a_quiet_spring():
    spring = _spring_event(spring_volume=500_000.0)  # ~0.5x average: quiet, light-volume undercut
    assert spring.volume_ratio < 1.5
    assert "quiet" in spring.evidence[0].lower()
