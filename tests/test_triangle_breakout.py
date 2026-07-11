"""Unit tests for the extracted triangle apex / post-apex classification."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.triangle_breakout import classify_triangle_breakout

# Shared trendlines for every test: upper(x) = 111 - 0.2x, lower(x) = 88 + 0.2x.
# They cross at the theoretical apex, index 57.5.
_LINES = {
    "high_slope": -0.2, "high_intercept": 111.0, "low_slope": 0.2, "low_intercept": 88.0,
}
_APEX_INDEX = 57.5
_START_INDEX = 5
_FORMATION_END = 30


def _classify(closes: list[float], buffer: float = 1.0, bias: str = "neutral"):
    df = pd.DataFrame({"Close": closes})
    return classify_triangle_breakout(
        df,
        start_index=_START_INDEX,
        formation_end=_FORMATION_END,
        apex_index=_APEX_INDEX,
        bias=bias,
        buffer=buffer,
        **_LINES,
    )


def _flat(value: float, length: int) -> list[float]:
    return [value] * length


@pytest.mark.unit
def test_preferred_zone_breakout_is_confirmed_with_levels_at_breakout_bar():
    closes = _flat(100.0, 70)
    closes[40:] = [106.0] * (70 - 40)

    result = _classify(closes)

    assert result.status == "confirmed"
    assert result.breakout_index == 40
    assert 0.55 <= result.breakout_progress <= 0.75
    assert result.risk_flags == []
    assert result.upper_level == pytest.approx(111 - 0.2 * 40)
    assert result.lower_level == pytest.approx(88 + 0.2 * 40)


@pytest.mark.unit
def test_late_apex_breakout_is_flagged_but_still_confirmed():
    closes = _flat(100.0, 70)
    closes[52:] = [103.0] * (70 - 52)

    result = _classify(closes)

    assert result.status == "confirmed"
    assert 0.85 < result.breakout_progress <= 0.97
    assert "late_apex_breakout" in result.risk_flags
    assert "post_apex_breakout" not in result.risk_flags
    assert result.timing_adjustment < 0


@pytest.mark.unit
def test_post_apex_breakout_inside_window_is_confirmed_with_flag():
    closes = _flat(100.0, 70)
    closes[60:] = [103.0] * (70 - 60)

    result = _classify(closes)

    assert result.status == "confirmed"
    assert result.breakout_index == 60
    assert result.breakout_progress == pytest.approx((60 - 5) / 52.5)
    assert result.risk_flags == ["post_apex_breakout"]
    assert result.timing_adjustment == -0.4
    assert result.upper_level == pytest.approx(99.5)
    assert result.lower_level == pytest.approx(99.5)


@pytest.mark.unit
def test_no_breakout_through_the_post_apex_window_expires_the_triangle():
    closes = _flat(99.5, 75)

    result = _classify(closes, buffer=3.0)

    assert result.status == "failed"
    assert result.breakout_index is None
    assert result.risk_flags == ["triangle_expired_at_apex"]


@pytest.mark.unit
def test_no_breakout_before_apex_is_still_forming():
    closes = _flat(100.0, 50)

    result = _classify(closes)

    assert result.status == "forming"
    assert result.breakout_index is None
    assert result.risk_flags == []


@pytest.mark.unit
def test_breakout_that_reverses_is_failed_with_reversal_flag():
    closes = _flat(100.0, 70)
    closes[40:45] = [106.0] * 5
    closes[45:] = [95.0] * (70 - 45)

    result = _classify(closes)

    assert result.status == "failed"
    assert result.breakout_index == 40
    assert result.signal_end_index == 45
    assert "breakout_reversed_back_through_triangle" in result.risk_flags
    assert "late_apex_breakout" not in result.risk_flags


@pytest.mark.unit
def test_pre_apex_breakout_reversal_after_apex_uses_frozen_boundary():
    closes = _flat(100.0, 70)
    closes[52:60] = [103.0] * 8
    closes[60:] = [98.0] * 10

    result = _classify(closes)

    assert result.breakout_index == 52
    assert result.status == "failed"
    assert result.signal_end_index == 60
    assert "breakout_reversed_back_through_triangle" in result.risk_flags
