"""Unit tests for range-aware VSA detectors and the full detector set's
negative path on a plain, unremarkable bar."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.wyckoff_range import TradingRange
from tradingagents.dataflows.wyckoff_vsa_range_signals import (
    test_bar as detect_test_bar,
    upthrust_shakeout_on_volume,
)
from tradingagents.dataflows.wyckoff_vsa_signals import (
    climax_bar,
    effort_no_result_down,
    effort_no_result_up,
    no_demand,
    no_supply,
    stopping_volume,
)

ATR = 2.0
RNG = TradingRange(
    range_high=105.0, range_low=95.0, start_index=0, start_date="2023-01-02",
    high_touches=[], low_touches=[], prior_trend="down",
)


def _df(rows: list[tuple[str, float, float, float, float]]) -> pd.DataFrame:
    dates, closes, highs, lows, volumes = zip(*rows, strict=True)
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(dates),
            "Open": closes,
            "High": highs,
            "Low": lows,
            "Close": closes,
            "Volume": volumes,
        }
    )


@pytest.mark.unit
def test_test_bar_fires_bullish_near_range_low():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.4, 99.6, 1_000_000.0),
            ("2023-01-03", 94.7, 95.3, 94.5, 700_000.0),
        ]
    )
    hit = detect_test_bar(df, 1, ATR, RNG)
    assert hit is not None
    assert hit.native_direction == "bullish"


@pytest.mark.unit
def test_test_bar_fires_bearish_near_range_high():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.4, 99.6, 1_000_000.0),
            ("2023-01-03", 105.3, 105.5, 104.7, 700_000.0),
        ]
    )
    hit = detect_test_bar(df, 1, ATR, RNG)
    assert hit is not None
    assert hit.native_direction == "bearish"


@pytest.mark.unit
def test_upthrust_shakeout_fires_bullish_on_pierce_and_close_back_inside_low():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.4, 99.6, 1_000_000.0),
            ("2023-01-03", 96.0, 97.0, 93.0, 1_500_000.0),
        ]
    )
    hit = upthrust_shakeout_on_volume(df, 1, ATR, RNG)
    assert hit is not None
    assert hit.native_direction == "bullish"


@pytest.mark.unit
def test_upthrust_shakeout_fires_bearish_on_pierce_and_close_back_inside_high():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.4, 99.6, 1_000_000.0),
            ("2023-01-03", 104.5, 108.0, 104.0, 1_500_000.0),
        ]
    )
    hit = upthrust_shakeout_on_volume(df, 1, ATR, RNG)
    assert hit is not None
    assert hit.native_direction == "bearish"


@pytest.mark.unit
def test_all_detectors_stay_silent_on_an_unremarkable_bar():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.6, 99.4, 1_000_000.0),
            ("2023-01-03", 100.5, 101.1, 99.9, 1_050_000.0),
        ]
    )
    assert no_demand(df, 1, ATR) is None
    assert no_supply(df, 1, ATR) is None
    assert stopping_volume(df, 1, ATR) is None
    assert climax_bar(df, 1, ATR) is None
    assert effort_no_result_up(df, 1, ATR) is None
    assert effort_no_result_down(df, 1, ATR) is None
    assert detect_test_bar(df, 1, ATR, RNG) is None
    assert upthrust_shakeout_on_volume(df, 1, ATR, RNG) is None
