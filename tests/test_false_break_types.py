"""Constants and dataclass defaults for the false-breakout machine (SP2)."""

from __future__ import annotations

import pytest

from tradingagents.dataflows import false_break_types as t


@pytest.mark.unit
def test_calibration_constants_have_exact_values():
    assert t.REENTRY_WINDOW_BARS == 10
    assert t.CONFIRM_WINDOW_BARS == 8
    assert t.NO_NEW_LOW_GRACE_BARS == 2
    assert t.VOLUME_MULTIPLE == 1.3
    assert t.FORMING_CONFIDENCE == 0.45
    assert t.CONFIRMED_STANDARD_CONFIDENCE == 0.60
    assert t.CONFIRMED_AGGRESSIVE_CONFIDENCE == 0.55
    assert (t.CONFIDENCE_FLOOR, t.CONFIDENCE_CEILING) == (0.2, 0.9)


@pytest.mark.unit
def test_context_defaults_are_empty_flags_and_no_target():
    ctx = t.FalseBreakContext(
        breakout_index=5, direction="bullish", high_slope=0.0, high_intercept=100.0,
        low_slope=0.0, low_intercept=100.0, apex_index=float("inf"), buffer=0.3,
        window_bars=0, parent_pattern="rectangle",
    )
    assert ctx.parent_risk_flags == ()
    assert ctx.target_price is None
