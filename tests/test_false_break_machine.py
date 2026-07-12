"""End-to-end machine behavior for the false-breakout state machine (SP2)."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from tradingagents.dataflows.false_break_machine import detect_false_break
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


def _ctx(direction, level=100.0, flags=()):
    return FalseBreakContext(
        breakout_index=5, direction=direction, high_slope=0.0, high_intercept=level,
        low_slope=0.0, low_intercept=level, apex_index=math.inf, buffer=0.3, window_bars=0,
        parent_pattern="rectangle", parent_risk_flags=flags,
        target_price=(level - 5 if direction == "bullish" else level + 5),
    )


SHORT = _frame([97, 98, 99, 99.5, 99.8, 101.2, 101.0, 100.4, 99.4, 98.7, 98.2])
LONG = _frame(
    [103, 102, 101, 100.6, 100.3, 98.8, 98.0, 99.0, 100.1, 101.1, 101.4],
    lows=[102, 101, 101, 100.5, 100.2, 98.5, 97.8, 98.4, 99.6, 100.9, 101.2],
)


@pytest.mark.unit
def test_upward_false_break_confirms_short_at_standard_tier():
    signal = detect_false_break(SHORT, _ctx("bullish"))
    assert signal is not None
    assert (signal.signal_type, signal.direction, signal.status) == (
        "false_breakout_short", "bearish", "confirmed",
    )
    assert signal.aggressive is False
    assert (signal.reentry_index, signal.trigger_index) == (8, 9)
    assert signal.confidence == 0.6
    assert signal.invalidation_price == pytest.approx(102.0)
    assert signal.target_price == pytest.approx(95.0)


@pytest.mark.unit
def test_short_stays_forming_when_window_has_no_confirmation():
    signal = detect_false_break(_frame([97, 98, 99, 99.5, 99.8, 101.2, 101.0, 100.4, 99.4]),
                                _ctx("bullish"))
    assert signal is not None
    assert signal.status == "forming"
    assert signal.trigger_index is None
    assert signal.confidence == 0.45


@pytest.mark.unit
def test_late_apex_parent_confirms_short_aggressively_at_reentry():
    signal = detect_false_break(SHORT, _ctx("bullish", flags=("late_apex_breakout",)))
    assert signal.status == "confirmed"
    assert signal.aggressive is True
    assert signal.trigger_index == signal.reentry_index == 8
    assert signal.confidence == 0.55


@pytest.mark.unit
def test_downward_false_break_confirms_long_and_upgrades_to_standard():
    signal = detect_false_break(LONG, _ctx("bearish"))
    assert signal is not None
    assert (signal.signal_type, signal.direction, signal.status) == (
        "false_breakdown_long", "bullish", "confirmed",
    )
    assert signal.aggressive is False  # upgraded at bar 10
    assert (signal.reentry_index, signal.trigger_index) == (9, 10)
    assert signal.confidence == 0.6


@pytest.mark.unit
def test_long_returns_none_when_new_low_guard_fails():
    guard_fail = _frame(
        [103, 102, 101, 100.5, 100.2, 99.0, 98.5, 98.2, 97.5, 100.6],
        lows=[102, 101, 101, 100.5, 100.2, 98.5, 98.0, 97.9, 97.2, 100.3],
    )
    assert detect_false_break(guard_fail, _ctx("bearish")) is None


@pytest.mark.unit
def test_reentry_beyond_window_emits_nothing():
    late = _frame([97, 98, 99, 99.5, 99.8] + [101.5] * 12 + [99.0, 98.0])
    assert detect_false_break(late, _ctx("bullish")) is None
