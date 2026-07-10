"""Unit tests for O'Neil ascending-base detection."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.oneil_ascending_base import detect_ascending_base
from tradingagents.dataflows.oneil_cup import prepare_ohlcv


def _ascending_base(
    lows: tuple[float, float, float] = (88.0, 94.0, 100.0),
    highs: tuple[float, float, float] = (100.0, 106.0, 112.0),
    leg_days: int = 10,
    complete: bool = True,
    up_gain: float = 40.0,
) -> pd.DataFrame:
    closes = list(np.linspace(50.0 if up_gain else 90.0, 90.0, 40))
    volumes = [1_000_000.0] * len(closes)

    def add_leg(end: float, days: int, volume: float) -> None:
        closes.extend(float(value) for value in np.linspace(closes[-1], end, days + 1)[1:])
        volumes.extend([volume] * days)

    add_leg(highs[0], 5, 900_000.0)
    add_leg(lows[0], leg_days, 800_000.0)
    add_leg(highs[1], leg_days, 850_000.0)
    add_leg(lows[1], max(20, leg_days), 700_000.0)
    if complete:
        add_leg(highs[2], leg_days, 750_000.0)
        add_leg(lows[2], leg_days, 600_000.0)
        add_leg(lows[2] + 5, 5, 650_000.0)
    else:
        add_leg(lows[1] + 5, 5, 650_000.0)
    prices = np.array(closes)
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2024-01-02", periods=len(prices)),
            "Open": prices,
            "High": prices + 0.25,
            "Low": prices - 0.25,
            "Close": prices,
            "Volume": volumes,
        }
    )


def _candidate(**kwargs: object):
    return detect_ascending_base(_ascending_base(**kwargs), atr_value=1.0)


@pytest.mark.unit
def test_textbook_three_pullback_ascending_base():
    candidate = _candidate()
    assert candidate is not None
    assert candidate.complete is True
    assert candidate.pivot_price == candidate.geometry["pullbacks"][2]["high"]["price"]
    assert candidate.start_index is not None
    assert candidate.base_low_price == candidate.geometry["pullbacks"][-1]["low"]["price"]
    assert 55 <= candidate.geometry["duration_days"] <= 65


@pytest.mark.unit
def test_two_pullbacks_is_forming():
    candidate = _candidate(complete=False)
    assert candidate is not None
    assert candidate.complete is False
    assert candidate.geometry["pullbacks_completed"] == 2
    assert candidate.pivot_price == candidate.geometry["pullbacks"][1]["high"]["price"]


@pytest.mark.unit
def test_flat_lows_rejected():
    assert _candidate(lows=(88.0, 88.0, 100.0)) is None


@pytest.mark.unit
def test_pullback_too_deep_rejected():
    assert _candidate(lows=(70.0, 94.0, 100.0)) is None


@pytest.mark.unit
def test_pullback_too_shallow_rejected():
    assert _candidate(lows=(88.0, 94.0, 109.76)) is None


@pytest.mark.unit
def test_span_too_long_rejected():
    assert _candidate(leg_days=22) is None


@pytest.mark.unit
def test_no_prior_uptrend_rejected():
    assert _candidate(up_gain=0.0) is None


@pytest.mark.unit
def test_evidence_narrates_each_pullback_and_volume():
    candidate = _candidate()
    assert candidate is not None
    text = " ".join(candidate.evidence)
    for number, pullback in enumerate(candidate.geometry["pullbacks"], 1):
        assert f"Pullback {number}" in text
        assert pullback["high"]["date"] in text
        assert pullback["low"]["date"] in text
        assert f"{pullback['depth_pct']:.1f}%" in text
    assert "volume" in text.lower()
    assert "contracted" in text.lower()


@pytest.mark.unit
def test_prepare_ohlcv_drops_future_rows_past_curr_date():
    frame = _ascending_base()
    cutoff = frame["Date"].iloc[85].strftime("%Y-%m-%d")
    prepared = prepare_ohlcv(frame, cutoff, look_back_days=420)
    assert prepared["Date"].max() <= pd.Timestamp(cutoff)
