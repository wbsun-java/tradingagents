"""Unit tests for the Wyckoff breakout-failure (invalidation) check."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.wyckoff_events import WyckoffEvent
from tradingagents.dataflows.wyckoff_invalidation import check_invalidation
from tradingagents.dataflows.wyckoff_range import TradingRange


def _df(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({
        "Date": pd.bdate_range("2023-01-02", periods=len(closes)),
        "Open": closes, "High": [c + 0.5 for c in closes], "Low": [c - 0.5 for c in closes],
        "Close": closes, "Volume": [1_000_000.0] * len(closes),
    })


def _range(high: float, low: float) -> TradingRange:
    return TradingRange(
        range_high=high, range_low=low, start_index=0, start_date="2023-01-02",
        high_touches=[], low_touches=[], prior_trend="down",
    )


def _events(last_date: str) -> list[WyckoffEvent]:
    return [WyckoffEvent(event="back_up", date=last_date, price=95.0, volume_ratio=1.1, evidence=["..."])]


@pytest.mark.unit
def test_accumulation_reversal_past_range_low_is_flagged():
    df = _df([95.0, 95.0, 95.0, 74.0])  # last bar reverses well below range_low
    events = _events(df["Date"].iloc[2].strftime("%Y-%m-%d"))
    rng = _range(high=93.0, low=77.0)

    failure = check_invalidation(df, atr_value=2.0, rng=rng, direction="accumulation", events=events, phase="E")

    assert failure is not None
    assert failure.event == "range_failure"
    assert failure.price == 74.0


@pytest.mark.unit
def test_accumulation_no_reversal_is_not_flagged():
    df = _df([95.0, 95.0, 95.0, 90.0])  # stays well above range_low, no failure
    events = _events(df["Date"].iloc[2].strftime("%Y-%m-%d"))
    rng = _range(high=93.0, low=77.0)

    failure = check_invalidation(df, atr_value=2.0, rng=rng, direction="accumulation", events=events, phase="E")

    assert failure is None


@pytest.mark.unit
def test_distribution_reversal_past_range_high_is_flagged():
    df = _df([70.0, 70.0, 70.0, 96.0])  # last bar reverses well above range_high
    events = _events(df["Date"].iloc[2].strftime("%Y-%m-%d"))
    rng = _range(high=93.0, low=77.0)

    failure = check_invalidation(df, atr_value=2.0, rng=rng, direction="distribution", events=events, phase="D")

    assert failure is not None
    assert failure.event == "range_failure"
    assert failure.price == 96.0


@pytest.mark.unit
def test_phase_c_is_never_checked_for_invalidation():
    df = _df([95.0, 95.0, 95.0, 50.0])  # would qualify as a reversal, but C has no breakout to fail
    events = _events(df["Date"].iloc[2].strftime("%Y-%m-%d"))
    rng = _range(high=93.0, low=77.0)

    failure = check_invalidation(df, atr_value=2.0, rng=rng, direction="accumulation", events=events, phase="C")

    assert failure is None


@pytest.mark.unit
def test_empty_events_returns_none_without_crashing():
    df = _df([95.0, 95.0, 95.0, 74.0])
    rng = _range(high=93.0, low=77.0)

    failure = check_invalidation(df, atr_value=2.0, rng=rng, direction="accumulation", events=[], phase="E")

    assert failure is None
