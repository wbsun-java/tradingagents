"""Unit tests for the VSA orchestrator: range-window scoping, curr_date
cutoff, and the bounded confidence delta."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.wyckoff_range import TradingRange
from tradingagents.dataflows.wyckoff_vsa import analyze_vsa

ATR = 2.0
RNG = TradingRange(
    range_high=105.0, range_low=95.0, start_index=2, start_date="2023-01-04",
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
def test_single_confirming_signal_adds_bounded_delta():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.5, 99.5, 1_000_000.0),
            ("2023-01-03", 99.0, 99.4, 98.6, 500_000.0),
            ("2023-01-04", 97.0, 97.4, 96.6, 500_000.0),
        ]
    )
    signals, delta = analyze_vsa(df, ATR, RNG, "bullish", "2023-01-04")
    assert len(signals) == 1
    assert signals[0]["signal"] == "no_supply"
    assert signals[0]["direction"] == "confirming"
    assert delta == pytest.approx(0.05)


@pytest.mark.unit
def test_single_contradicting_signal_subtracts_bounded_delta():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.5, 99.5, 1_000_000.0),
            ("2023-01-03", 99.0, 99.4, 98.6, 500_000.0),
            ("2023-01-04", 97.0, 97.4, 96.6, 500_000.0),
        ]
    )
    signals, delta = analyze_vsa(df, ATR, RNG, "bearish", "2023-01-04")
    assert len(signals) == 1
    assert signals[0]["direction"] == "contradicting"
    assert delta == pytest.approx(-0.05)


@pytest.mark.unit
def test_confidence_delta_is_clamped_at_the_positive_cap():
    # 6 cycles of [no_supply signal bar, 2 flat filler bars]: each signal bar
    # drops price 1.0 from the prior filler's close on low relative volume,
    # narrow spread, far from both range boundaries -- only no_supply fires.
    rows = [("2023-01-02", 100.0, 100.4, 99.6, 1_000_000.0)]
    price, day = 100.0, 3
    for _ in range(6):
        price -= 1.0
        rows.append((f"2023-01-{day:02d}", price, price + 0.3, price - 0.3, 400_000.0))
        day += 1
        for _ in range(2):
            rows.append((f"2023-01-{day:02d}", price, price + 0.4, price - 0.4, 1_000_000.0))
            day += 1
    df = _df(rows)
    rng = TradingRange(
        range_high=105.0, range_low=80.0, start_index=1, start_date=rows[1][0],
        high_touches=[], low_touches=[], prior_trend="down",
    )
    signals, delta = analyze_vsa(df, ATR, rng, "bullish", rows[-1][0])
    assert len(signals) == 6
    assert all(s["signal"] == "no_supply" and s["direction"] == "confirming" for s in signals)
    assert delta == pytest.approx(0.15)


@pytest.mark.unit
def test_bars_before_range_start_are_excluded():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.5, 99.5, 1_000_000.0),
            ("2023-01-03", 99.0, 99.4, 98.6, 500_000.0),
            ("2023-01-04", 97.0, 97.4, 96.6, 500_000.0),
        ]
    )
    signals, delta = analyze_vsa(df, ATR, RNG, "bullish", "2023-01-04")
    assert len(signals) == 1
    assert signals[0]["date"] == "2023-01-04"


@pytest.mark.unit
def test_bars_after_curr_date_are_excluded():
    df = _df(
        [
            ("2023-01-02", 100.0, 100.4, 99.6, 1_000_000.0),
            ("2023-01-10", 99.0, 99.4, 98.6, 500_000.0),
        ]
    )
    rng = TradingRange(
        range_high=105.0, range_low=95.0, start_index=0, start_date="2023-01-02",
        high_touches=[], low_touches=[], prior_trend="down",
    )
    signals, delta = analyze_vsa(df, ATR, rng, "bullish", "2023-01-05")
    assert signals == []
    assert delta == 0.0
