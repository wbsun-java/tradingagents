"""Unit tests for strict O'Neil double-bottom detection."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.oneil_cup import prepare_ohlcv
from tradingagents.dataflows.oneil_double_bottom import detect_double_bottom


def _line(values: list[float], end: float, bars: int) -> None:
    values.extend(np.linspace(values[-1], end, bars + 1)[1:].tolist())


def _w(
    *, first: float = 70, second: float = 69, middle: float = 88,
    prior_gain: float = 50, leg: int = 40, cross: int = 20, down: int = 20,
    tail: int = 15, rising_leg_volume: bool = False, base_volume: float = 350_000,
    minor_dip: bool = False,
) -> pd.DataFrame:
    close = np.linspace(50, 50 + prior_gain, 45).tolist()
    if minor_dip:
        _line(close, 78, 10)
        _line(close, 82, 7)
        remaining = leg - 17
    else:
        remaining = leg
    _line(close, first, remaining)
    first_index = len(close) - 1
    _line(close, middle, cross)
    _line(close, second, down)
    second_index = len(close) - 1
    _line(close, min(middle - 4, second + 12), tail)
    volume = np.full(len(close), 1_000_000.0)
    leg_start = 44
    volume[leg_start : first_index + 1] = np.linspace(
        500_000 if rising_leg_volume else 900_000,
        1_100_000 if rising_leg_volume else 450_000,
        first_index - leg_start + 1,
    )
    volume[first_index + 1 : second_index + 1] = base_volume
    volume[second_index + 1 :] = base_volume
    prices = np.asarray(close)
    return pd.DataFrame({
        "Date": pd.bdate_range("2023-01-02", periods=len(prices)),
        "Open": prices, "High": prices + 0.5, "Low": prices - 0.5,
        "Close": prices, "Volume": volume,
    })


def _detect(frame: pd.DataFrame | None = None, **kwargs: object):
    return detect_double_bottom(frame if frame is not None else _w(**kwargs), 1.0)


@pytest.mark.unit
def test_textbook_w_detected():
    candidate = _detect()
    assert candidate is not None and candidate.complete and candidate.undercut
    assert candidate.pivot_price == candidate.geometry["middle_peak"]["price"]
    assert candidate.geometry["base_start"]["price"] == pytest.approx(100.5)
    evidence = " ".join(candidate.evidence).lower()
    assert "shakeout" in evidence and "leg-one volume declined" in evidence
    assert "base volume contracted" in evidence


@pytest.mark.unit
def test_equal_second_low_rejected():
    assert _detect(second=70) is None


@pytest.mark.unit
def test_higher_second_low_rejected():
    assert _detect(second=72) is None


@pytest.mark.unit
def test_middle_peak_at_or_above_start_rejected():
    assert _detect(middle=101) is None


@pytest.mark.unit
def test_depth_below_20_pct_rejected():
    assert _detect(first=82, second=81) is None


@pytest.mark.unit
def test_depth_above_50_pct_rejected():
    assert _detect(first=49, second=48) is None


@pytest.mark.unit
def test_base_shorter_than_35_days_rejected():
    assert _detect(leg=10, cross=8, down=8, tail=5) is None


@pytest.mark.unit
def test_base_older_than_325_days_rejected():
    assert _detect(tail=250) is None


@pytest.mark.unit
def test_rising_volume_into_first_low_rejected():
    assert _detect(rising_leg_volume=True) is None


@pytest.mark.unit
def test_no_base_wide_dryup_rejected():
    assert _detect(base_volume=1_200_000) is None


@pytest.mark.unit
def test_prior_advance_below_30_pct_rejected():
    assert _detect(prior_gain=10) is None


@pytest.mark.unit
def test_interior_high_above_start_rejected():
    frame = _w()
    frame.loc[100, ["High", "Close"]] = [102, 101]
    assert _detect(frame) is None


@pytest.mark.unit
def test_first_minor_dip_is_not_forced_as_l1():
    candidate = _detect(minor_dip=True)
    assert candidate is not None
    assert candidate.geometry["first_low"]["price"] == pytest.approx(69.5)


@pytest.mark.unit
def test_prepare_ohlcv_does_not_leak_future_rows():
    frame = _w()
    cutoff = frame["Date"].iloc[100].strftime("%Y-%m-%d")
    prepared = prepare_ohlcv(frame, cutoff, look_back_days=420)
    assert prepared["Date"].max() <= pd.Timestamp(cutoff)
    assert detect_double_bottom(prepared, 1.0) is None
