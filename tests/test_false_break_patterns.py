"""PricePattern rendering and parent mutation for the false-breakout machine (SP2)."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from tradingagents.dataflows.chart_patterns import PricePattern
from tradingagents.dataflows.false_break_patterns import (
    apply_parent_side_effects,
    build_false_break_signal,
)
from tradingagents.dataflows.false_break_types import FalseBreakContext


def _frame(closes, lows=None, highs=None):
    lows = lows if lows is not None else [c - 0.5 for c in closes]
    highs = highs if highs is not None else [c + 0.5 for c in closes]
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2026-01-02", periods=len(closes)),
            "Open": closes, "High": highs, "Low": lows, "Close": closes,
            "Volume": [1_000_000.0] * len(closes),
        }
    )


def _failed_parent():
    return PricePattern(
        pattern="rectangle", status="failed", direction="neutral", confidence=0.5,
        start_date="2026-01-02", end_date="2026-01-20", levels={}, target_price=123.0,
        invalidation_price=None, volume_confirmed=None, evidence=[],
        risk_flags=["some_existing_flag"],
    )


@pytest.mark.unit
def test_apply_parent_side_effects_voids_target_and_flags_expansion():
    parent = _failed_parent()
    apply_parent_side_effects(parent)
    assert parent.target_price is None
    assert "structure_may_be_expanding" in parent.risk_flags
    apply_parent_side_effects(parent)  # idempotent
    assert parent.risk_flags.count("structure_may_be_expanding") == 1


@pytest.mark.unit
def test_short_signal_renders_as_bearish_pricepattern():
    df = _frame([97, 98, 99, 99.5, 99.8, 101.2, 101.0, 100.4, 99.4, 98.7, 98.2])
    ctx = FalseBreakContext(
        breakout_index=5, direction="bullish", high_slope=0.0, high_intercept=100.0,
        low_slope=0.0, low_intercept=100.0, apex_index=math.inf, buffer=0.3, window_bars=0,
        parent_pattern="rectangle", target_price=95.0,
    )
    pattern = build_false_break_signal(df, ctx)
    assert isinstance(pattern, PricePattern)
    assert pattern.pattern == "false_breakout_short"
    assert pattern.direction == "bearish"
    assert pattern.status == "confirmed"
    assert pattern.target_price == pytest.approx(95.0)
    assert pattern.invalidation_price == pytest.approx(102.0)
    assert set(pattern.levels) == {
        "boundary_price", "false_break_extreme", "reentry_close", "trigger_price",
    }
    assert len(pattern.evidence) == 6
    assert pattern.risk_flags == []


@pytest.mark.unit
def test_aggressive_short_carries_the_aggressive_confirmation_flag():
    df = _frame([97, 98, 99, 99.5, 99.8, 101.2, 101.0, 100.4, 99.4, 98.7, 98.2])
    ctx = FalseBreakContext(
        breakout_index=5, direction="bullish", high_slope=0.0, high_intercept=100.0,
        low_slope=0.0, low_intercept=100.0, apex_index=math.inf, buffer=0.3, window_bars=0,
        parent_pattern="symmetrical_triangle", parent_risk_flags=("late_apex_breakout",),
    )
    pattern = build_false_break_signal(df, ctx)
    assert pattern.risk_flags == ["aggressive_confirmation"]


@pytest.mark.unit
def test_build_returns_none_when_machine_finds_no_signal():
    df = _frame([97, 98, 99, 99.5, 99.8] + [101.5] * 12 + [99.0, 98.0])
    ctx = FalseBreakContext(
        breakout_index=5, direction="bullish", high_slope=0.0, high_intercept=100.0,
        low_slope=0.0, low_intercept=100.0, apex_index=math.inf, buffer=0.3, window_bars=0,
        parent_pattern="rectangle",
    )
    assert build_false_break_signal(df, ctx) is None
