"""Classification-level tests for the post-apex window and asymmetric reversal (SP1)."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.triangle_breakout import classify_triangle_breakout

# upper(x) = 111 - 0.2x, lower(x) = 88 + 0.2x, apex 57.5 at price 99.5.
# Window = round(0.15 * 52.5) = 8 bars: the post-apex search covers bars 58-65
# and flagged breakouts get the half-buffer reversal through breakout_index + 8.
_LINES = {
    "high_slope": -0.2, "high_intercept": 111.0, "low_slope": 0.2, "low_intercept": 88.0,
}


def _classify(closes: list[float], buffer: float = 1.0):
    return classify_triangle_breakout(
        pd.DataFrame({"Close": closes}),
        start_index=5, formation_end=30, apex_index=57.5,
        bias="neutral", buffer=buffer, **_LINES,
    )


@pytest.mark.unit
def test_inside_window_without_breakout_is_still_forming():
    result = _classify([100.0] * 62)  # last bar 61 < window-last bar 65
    assert result.status == "forming"
    assert result.breakout_index is None
    assert "post-apex" in result.timing_evidence


@pytest.mark.unit
def test_window_exhausted_without_breakout_expires_the_triangle():
    result = _classify([100.0] * 66)  # last bar 65 == final window bar
    assert result.status == "failed"
    assert result.risk_flags == ["triangle_expired_at_apex"]


@pytest.mark.unit
def test_breakout_beyond_the_window_never_confirms():
    closes = [100.0] * 72
    closes[66:] = [103.0] * 6
    result = _classify(closes)
    assert result.status == "failed"
    assert result.breakout_index is None
    assert "triangle_expired_at_apex" in result.risk_flags


@pytest.mark.unit
def test_post_apex_breakout_reverses_on_half_buffer_close():
    closes = [100.0] * 70
    closes[60:63] = [103.0] * 3
    closes[63:] = [98.8] * (70 - 63)  # trips 99.0 (half buffer), not 98.5 (full)
    result = _classify(closes)
    assert result.status == "failed"
    assert result.signal_end_index == 63
    assert "post_apex_breakout" in result.risk_flags
    assert "breakout_reversed_back_through_triangle" in result.risk_flags


@pytest.mark.unit
def test_post_apex_breakout_holds_when_reversal_comes_late_and_shallow():
    closes = [100.0] * 75
    closes[60:70] = [103.0] * 10
    closes[70:] = [98.8] * 5  # beyond breakout + 8 bars: full buffer applies again
    result = _classify(closes)
    assert result.status == "confirmed"
    assert "post_apex_breakout" in result.risk_flags
    assert result.upper_level == pytest.approx(99.5)
    assert result.lower_level == pytest.approx(99.5)


@pytest.mark.unit
def test_late_apex_breakout_also_gets_the_asymmetric_reversal():
    closes = [100.0] * 70
    closes[52:55] = [103.0] * 3
    closes[55:] = [99.2] * (70 - 55)  # upper(55)=100.0: trips 99.5, not 99.0
    result = _classify(closes)
    assert result.status == "failed"
    assert "late_apex_breakout" in result.risk_flags
    assert "breakout_reversed_back_through_triangle" in result.risk_flags


@pytest.mark.unit
def test_normal_breakout_keeps_the_full_reversal_buffer():
    closes = [100.0] * 70
    closes[40:43] = [106.0] * 3
    closes[43:] = [101.5] * (70 - 43)  # upper(43)=102.4: half buffer would trip at 101.9
    result = _classify(closes)
    assert result.status == "confirmed"
    assert result.risk_flags == []
