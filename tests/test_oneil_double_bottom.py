"""Unit tests for O'Neil double-bottom detection."""

from __future__ import annotations

import pandas as pd
import pytest

from tests.oneil_double_bottom_fixtures import delay_reclaim, detect, w_frame
from tradingagents.dataflows.oneil_cup import prepare_ohlcv
from tradingagents.dataflows.oneil_double_bottom import detect_double_bottom


@pytest.mark.unit
def test_textbook_w_detected():
    candidate = detect()
    assert candidate is not None and candidate.complete and candidate.undercut
    assert candidate.pivot_price == candidate.geometry["middle_peak"]["price"]
    assert candidate.geometry["base_start"]["price"] == pytest.approx(100.5)
    assert candidate.start_index is not None
    assert candidate.base_low_price == candidate.geometry["second_low"]["price"]
    evidence = " ".join(candidate.evidence).lower()
    assert "shakeout" in evidence and "leg-one volume declined" in evidence
    assert "base volume contracted" in evidence


@pytest.mark.unit
def test_shallow_swift_undercut_valid():
    candidate = detect(first=70, second=68.95)
    assert candidate.geometry["second_low_behavior"] == "undercut"
    assert candidate.undercut is True
    assert "shakeout" in " ".join(candidate.evidence)


@pytest.mark.unit
def test_googl_shaped_breakdown_rejected():
    frame = w_frame(first=296.36, middle=318.60, second=272.45, prior_gain=298.05)
    assert frame["High"].iloc[44] == pytest.approx(348.55)
    assert detect(frame) is None


@pytest.mark.unit
def test_undercut_reclaimed_too_slowly_rejected():
    assert detect(delay_reclaim(w_frame())) is None


@pytest.mark.unit
def test_equal_lows_valid():
    candidate = detect(second=70)
    assert candidate.geometry["second_low_behavior"] == "equal"
    assert candidate.undercut is False
    assert "floor was retested" in " ".join(candidate.evidence)


@pytest.mark.unit
def test_higher_second_low_valid():
    candidate = detect(second=75)
    assert candidate.geometry["second_low_behavior"] == "higher"
    assert candidate.undercut is False
    assert candidate.base_low_price == candidate.geometry["first_low"]["price"]


@pytest.mark.unit
def test_middle_peak_at_or_above_start_rejected():
    assert detect(middle=101) is None


@pytest.mark.unit
def test_second_low_in_upper_half_rejected():
    assert detect(second=87, recovery=90) is None


@pytest.mark.unit
def test_middle_peak_below_upper_half_rejected():
    assert detect(middle=83.9) is None


@pytest.mark.unit
def test_depth_15_pct_boundary():
    assert detect(first=83, second=82, middle=94) is not None


@pytest.mark.unit
def test_depth_above_50_pct_rejected():
    assert detect(first=49, second=48) is None


@pytest.mark.unit
def test_base_shorter_than_35_days_rejected():
    assert detect(leg=10, cross=8, down=8, tail=5) is None


@pytest.mark.unit
def test_base_older_than_325_days_rejected():
    assert detect(tail=250) is None


@pytest.mark.unit
def test_rising_volume_into_first_low_rejected():
    assert detect(rising_leg_volume=True) is None


@pytest.mark.unit
def test_no_base_wide_dryup_rejected():
    assert detect(base_volume=1_200_000) is None


@pytest.mark.unit
def test_prior_advance_below_30_pct_rejected():
    assert detect(prior_gain=10) is None


@pytest.mark.unit
def test_interior_high_above_start_rejected():
    frame = w_frame()
    frame.loc[100, ["High", "Close"]] = [102, 101]
    assert detect(frame) is None


@pytest.mark.unit
def test_first_minor_dip_is_not_forced_as_l1():
    candidate = detect(minor_dip=True)
    assert candidate is not None
    assert candidate.geometry["first_low"]["price"] == pytest.approx(69.5)


@pytest.mark.unit
def test_right_side_volume_is_narrated():
    frame = w_frame()
    second = int(frame["Low"].iloc[45:].idxmin())
    for offset, close in enumerate([71, 70, 73, 72, 75, 74], start=1):
        index = second + offset
        frame.loc[index, ["Open", "Close", "High", "Low"]] = [close, close, close + 0.5, close - 0.5]
        frame.loc[index, "Volume"] = 700_000 if offset % 2 else 300_000
    evidence = " ".join(detect(frame).evidence)
    assert "Right-side up/down-day volume" in evidence
    assert "up-days dominate (accumulation)" in evidence


@pytest.mark.unit
def test_prepare_ohlcv_does_not_leak_future_rows():
    frame = w_frame()
    cutoff = frame["Date"].iloc[100].strftime("%Y-%m-%d")
    prepared = prepare_ohlcv(frame, cutoff, look_back_days=420)
    assert prepared["Date"].max() <= pd.Timestamp(cutoff)
    assert detect_double_bottom(prepared, 1.0) is None
