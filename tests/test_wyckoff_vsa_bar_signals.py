"""Unit tests for the bar-only VSA detectors (no rng/boundary needed)."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.wyckoff_vsa_signals import (
    climax_bar,
    effort_no_result_down,
    effort_no_result_up,
    no_demand,
    no_supply,
    stopping_volume,
)

ATR = 2.0


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
def test_no_demand_fires_on_up_bar_narrow_spread_low_volume():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.5, 99.5, 1_000_000.0),
            ("2023-01-03", 100.5, 100.8, 100.3, 500_000.0),
        ]
    )
    hit = no_demand(df, 1, ATR)
    assert hit is not None
    assert hit.native_direction == "bearish"
    assert hit.volume_ratio == pytest.approx(0.5)


@pytest.mark.unit
def test_no_demand_silent_when_volume_is_not_low():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.5, 99.5, 1_000_000.0),
            ("2023-01-03", 100.5, 100.8, 100.3, 1_500_000.0),
        ]
    )
    assert no_demand(df, 1, ATR) is None


@pytest.mark.unit
def test_no_supply_fires_on_down_bar_narrow_spread_low_volume():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.5, 99.5, 1_000_000.0),
            ("2023-01-03", 99.5, 99.8, 99.2, 500_000.0),
        ]
    )
    hit = no_supply(df, 1, ATR)
    assert hit is not None
    assert hit.native_direction == "bullish"


@pytest.mark.unit
def test_stopping_volume_fires_on_wide_down_bar_absorbed_high_volume():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.5, 99.5, 1_000_000.0),
            ("2023-01-03", 98.0, 99.0, 95.0, 2_500_000.0),
        ]
    )
    hit = stopping_volume(df, 1, ATR)
    assert hit is not None
    assert hit.native_direction == "bullish"
    assert hit.volume_ratio == pytest.approx(2.5)


@pytest.mark.unit
def test_stopping_volume_silent_when_spread_is_not_wide():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.5, 99.5, 1_000_000.0),
            ("2023-01-03", 98.0, 98.5, 97.5, 2_500_000.0),
        ]
    )
    assert stopping_volume(df, 1, ATR) is None


@pytest.mark.unit
def test_climax_bar_fires_on_new_low_wide_range_extreme_volume():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.5, 99.5, 1_000_000.0),
            ("2023-01-03", 99.0, 99.5, 98.5, 1_000_000.0),
            ("2023-01-04", 90.0, 91.0, 80.0, 4_000_000.0),
        ]
    )
    hit = climax_bar(df, 2, ATR)
    assert hit is not None
    assert hit.native_direction == "bullish"


@pytest.mark.unit
def test_climax_bar_silent_when_spread_is_not_wide():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.5, 99.5, 1_000_000.0),
            ("2023-01-03", 99.0, 99.5, 98.5, 1_000_000.0),
            ("2023-01-04", 95.0, 95.5, 94.5, 4_000_000.0),
        ]
    )
    assert climax_bar(df, 2, ATR) is None


@pytest.mark.unit
def test_effort_no_result_up_fires_when_high_volume_fails_to_hold_close():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.4, 99.6, 1_000_000.0),
            ("2023-01-03", 99.7, 100.4, 99.6, 2_000_000.0),
        ]
    )
    hit = effort_no_result_up(df, 1, ATR)
    assert hit is not None
    assert hit.native_direction == "bearish"


@pytest.mark.unit
def test_effort_no_result_down_fires_when_high_volume_fails_to_break_close():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.4, 99.6, 1_000_000.0),
            ("2023-01-03", 100.3, 100.4, 99.6, 2_000_000.0),
        ]
    )
    hit = effort_no_result_down(df, 1, ATR)
    assert hit is not None
    assert hit.native_direction == "bullish"
