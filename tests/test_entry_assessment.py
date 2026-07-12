"""State classification for the entry layer (SP3)."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from tradingagents.dataflows.entry_assessment import assess_entry

ATR = 1.0  # PROX = 0.5


def _df(closes, lows=None, vols=None):
    lows = lows if lows is not None else [c - 0.5 for c in closes]
    vols = vols if vols is not None else [1_000_000.0] * len(closes)
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2026-01-02", periods=len(closes)),
            "Open": closes, "High": [c + 0.5 for c in closes], "Low": lows,
            "Close": closes, "Volume": vols,
        }
    )


def _pat(pattern, status, direction, levels, invalidation=None):
    return SimpleNamespace(
        pattern=pattern, status=status, direction=direction, levels=levels,
        invalidation_price=invalidation, volume_confirmed=None,
    )


def _rect(status, direction="bullish"):
    return _pat("rectangle", status, direction, {"support": 96.0, "resistance": 100.0})


@pytest.mark.unit
def test_confirmed_fresh_break_is_breakout_entry():
    a = assess_entry(_df([100.0] * 21), _rect("confirmed"), ATR, 100.4)
    assert (a.state, a.direction, a.trigger_price) == ("breakout_entry", "long", 100.0)
    assert a.volume_role == "expansion_preferred"


@pytest.mark.unit
def test_confirmed_extended_is_observe():
    a = assess_entry(_df([100.0] * 21), _rect("confirmed"), ATR, 103.0)
    assert a.state == "observe" and a.direction == "none"


@pytest.mark.unit
def test_confirmed_low_volume_retest_is_retest_entry():
    closes = [100.0] * 18 + [102.0, 100.2, 101.0]
    lows = [99.5] * 18 + [101.5, 99.8, 100.5]
    vols = [1_000_000.0] * 18 + [1_000_000.0, 300_000.0, 1_000_000.0]
    a = assess_entry(_df(closes, lows, vols), _rect("confirmed"), ATR, 101.0)
    assert a.state == "breakout_retest_entry"
    assert a.volume_role == "low_volume_preferred"


@pytest.mark.unit
def test_forming_near_bottom_is_predictive_bottom():
    a = assess_entry(_df([96.4] * 21), _rect("forming", "neutral"), ATR, 96.4)
    assert (a.state, a.trigger_price) == ("predictive_bottom", 96.0)
    assert a.invalidation_price == pytest.approx(95.8)
    assert a.entry_zone_low == pytest.approx(95.75)


@pytest.mark.unit
def test_forming_mid_structure_is_observe():
    a = assess_entry(_df([100.0] * 21), _rect("forming", "neutral"), ATR, 100.0)
    assert a.state == "observe"


@pytest.mark.unit
def test_failed_long_pattern_is_avoid():
    p = _pat("ascending_triangle", "failed", "bullish",
             {"lower_trendline": 95.0, "upper_trendline": 100.0}, invalidation=94.8)
    assert assess_entry(_df([98.0] * 21), p, ATR, 98.0).state == "avoid"


@pytest.mark.unit
def test_bearish_pattern_is_avoid():
    p = _pat("double_top", "confirmed", "bearish",
             {"first_extreme": 110.0, "second_extreme": 111.0, "neckline": 100.0})
    a = assess_entry(_df([95.0] * 21), p, ATR, 95.0)
    assert (a.state, a.direction) == ("avoid", "none")


@pytest.mark.unit
def test_unknown_bullish_pattern_falls_back_to_observe():
    p = _pat("head_shoulders", "confirmed", "bullish", {})
    assert assess_entry(_df([100.0] * 21), p, ATR, 100.0).state == "observe"


@pytest.mark.unit
def test_sp2_short_signal_passthrough():
    p = _pat("false_breakout_short", "confirmed", "bearish",
             {"boundary_price": 100.6, "false_break_extreme": 103.6, "reentry_close": 99.5,
              "trigger_price": 98.9}, invalidation=103.9)
    a = assess_entry(_df([99.0] * 21), p, ATR, 99.0)
    assert (a.state, a.direction, a.trigger_price, a.invalidation_price) == (
        "false_breakout_short", "short", 98.9, 103.9,
    )
    assert (a.entry_zone_low, a.entry_zone_high) == (99.5, 100.6)


@pytest.mark.unit
def test_sp2_long_signal_passthrough():
    p = _pat("false_breakdown_long", "confirmed", "bullish",
             {"boundary_price": 100.0, "false_break_extreme": 97.8, "reentry_close": 100.1,
              "trigger_price": 101.6}, invalidation=97.5)
    a = assess_entry(_df([101.0] * 21), p, ATR, 101.0)
    assert (a.state, a.direction) == ("false_breakdown_long", "long")


@pytest.mark.unit
def test_emerging_double_bottom_is_predictive_bottom():
    p = _pat("double_bottom", "emerging", "bullish",
             {"first_extreme": 95.0, "second_extreme": 95.4, "neckline": 109.6}, invalidation=95.1)
    a = assess_entry(_df([98.0] * 21), p, ATR, 98.0)
    assert (a.state, a.direction) == ("predictive_bottom", "long")
    assert a.trigger_price == pytest.approx(95.0)  # min(first, second)
    assert a.volume_role == "supporting_not_required"
