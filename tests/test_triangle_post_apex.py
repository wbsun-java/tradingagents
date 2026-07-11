"""Unit tests for the post-apex triangle breakout rules (SP1)."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.triangle_post_apex import (
    POST_APEX_TIMING_ADJUSTMENT,
    POST_APEX_WINDOW_MAX_BARS,
    POST_APEX_WINDOW_MIN_BARS,
    find_post_apex_breakout,
    find_reversal_index,
    post_apex_watch_evidence,
    post_apex_window_bars,
    timing_assessment,
)

# Same geometry as test_triangle_breakout.py: upper(x) = 111 - 0.2x,
# lower(x) = 88 + 0.2x; they cross at index 57.5 where both equal 99.5.
_LINES = {
    "high_slope": -0.2, "high_intercept": 111.0, "low_slope": 0.2, "low_intercept": 88.0,
}
_APEX_INDEX = 57.5
_APEX_PRICE = 99.5


def _df(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"Close": closes})


@pytest.mark.unit
def test_window_scales_with_triangle_length_and_clamps():
    assert post_apex_window_bars(5, 57.5) == 8  # round(0.15 * 52.5)
    assert post_apex_window_bars(50, 55.0) == POST_APEX_WINDOW_MIN_BARS
    assert post_apex_window_bars(0, 300.0) == POST_APEX_WINDOW_MAX_BARS


@pytest.mark.unit
def test_post_apex_timing_flags_and_penalizes_beyond_late_apex():
    evidence, adjustment, flags = timing_assessment(1.05, post_apex=True)
    assert flags == ["post_apex_breakout"]
    assert adjustment == POST_APEX_TIMING_ADJUSTMENT
    assert adjustment < -0.3  # strictly worse than the worst late-apex penalty
    assert "past its theoretical apex" in evidence
    assert "false break" in evidence


@pytest.mark.unit
def test_pre_apex_timing_bands_are_preserved():
    assert timing_assessment(0.65, post_apex=False)[1:] == (0.1, [])
    assert timing_assessment(0.40, post_apex=False)[1:] == (0.0, [])
    assert timing_assessment(0.80, post_apex=False)[1:] == (0.02, [])
    assert timing_assessment(0.90, post_apex=False)[1:] == (-0.2, ["late_apex_breakout"])
    assert timing_assessment(0.99, post_apex=False)[1:] == (-0.3, ["late_apex_breakout"])


@pytest.mark.unit
def test_breakout_found_only_inside_the_post_apex_window():
    closes = [100.0] * 70
    closes[60] = 103.0
    hit = find_post_apex_breakout(
        _df(closes), formation_end=30, apex_index=_APEX_INDEX,
        apex_price=_APEX_PRICE, buffer=1.0, window_bars=8,
    )
    assert hit == (60, "bullish")

    late = [100.0] * 72
    late[66] = 103.0  # window covers bars 58-65 only
    assert find_post_apex_breakout(
        _df(late), formation_end=30, apex_index=_APEX_INDEX,
        apex_price=_APEX_PRICE, buffer=1.0, window_bars=8,
    ) is None


@pytest.mark.unit
def test_post_apex_breakdown_is_bearish():
    closes = [100.0] * 70
    closes[59] = 96.0
    hit = find_post_apex_breakout(
        _df(closes), formation_end=30, apex_index=_APEX_INDEX,
        apex_price=_APEX_PRICE, buffer=1.0, window_bars=8,
    )
    assert hit == (59, "bearish")


@pytest.mark.unit
def test_flagged_breakout_reverses_at_half_buffer_inside_reversal_window():
    closes = [100.0] * 70
    closes[60:63] = [103.0] * 3
    closes[63:] = [98.8] * (70 - 63)  # trips 99.0 (half buffer), not 98.5 (full)
    kwargs = dict(_LINES, apex_index=_APEX_INDEX, breakout_index=60,
                  breakout_direction="bullish", buffer=1.0, window_bars=8)
    assert find_reversal_index(_df(closes), risk_flags=["post_apex_breakout"], **kwargs) == 63
    assert find_reversal_index(_df(closes), risk_flags=[], **kwargs) is None


@pytest.mark.unit
def test_half_buffer_stops_applying_after_the_reversal_window():
    closes = [100.0] * 75
    closes[60:70] = [103.0] * 10
    closes[70:] = [98.8] * 5  # bar 70 is past breakout 60 + window 8
    assert find_reversal_index(
        _df(closes), risk_flags=["post_apex_breakout"],
        **dict(_LINES, apex_index=_APEX_INDEX, breakout_index=60,
               breakout_direction="bullish", buffer=1.0, window_bars=8),
    ) is None


@pytest.mark.unit
def test_late_apex_flag_uses_half_buffer_on_the_pre_apex_frozen_boundary():
    closes = [100.0] * 70
    closes[52:55] = [103.0] * 3
    closes[55:] = [99.2] * (70 - 55)  # upper(55)=100.0: trips 99.5, not 99.0
    kwargs = dict(_LINES, apex_index=_APEX_INDEX, breakout_index=52,
                  breakout_direction="bullish", buffer=1.0, window_bars=8)
    assert find_reversal_index(_df(closes), risk_flags=["late_apex_breakout"], **kwargs) == 55
    assert find_reversal_index(_df(closes), risk_flags=[], **kwargs) is None


@pytest.mark.unit
def test_watch_evidence_names_the_window_length():
    text = post_apex_watch_evidence(8)
    assert "8-bar" in text
    assert "apex" in text
