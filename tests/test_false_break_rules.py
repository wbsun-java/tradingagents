"""Pure false-break detectors (SP2)."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows import false_break_rules as r


def _frame(closes, lows=None, highs=None, volume=None):
    lows = lows if lows is not None else [c - 0.5 for c in closes]
    highs = highs if highs is not None else [c + 0.5 for c in closes]
    volume = volume if volume is not None else [1_000_000.0] * len(closes)
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2026-01-02", periods=len(closes)),
            "Open": closes, "High": highs, "Low": lows, "Close": closes, "Volume": volume,
        }
    )


SHORT = _frame([97, 98, 99, 99.5, 99.8, 101.2, 101.0, 100.4, 99.4, 98.7, 98.2])
LONG = _frame(
    [103, 102, 101, 100.6, 100.3, 98.8, 98.0, 99.0, 100.1, 101.1, 101.4],
    lows=[102, 101, 101, 100.5, 100.2, 98.5, 97.8, 98.4, 99.6, 100.9, 101.2],
)


@pytest.mark.unit
def test_pullback_low_and_extreme_high_over_breakout_to_reentry():
    assert r.pullback_low(SHORT, 5, 8) == pytest.approx(98.9)
    assert r.false_break_extreme(SHORT, 5, 8, "bullish") == pytest.approx(101.7)


@pytest.mark.unit
def test_rebound_high_extreme_low_and_trough_over_breakdown_to_reentry():
    assert r.rebound_high(LONG, 5, 9) == pytest.approx(101.6)
    assert r.false_break_extreme(LONG, 5, 9, "bearish") == pytest.approx(97.8)
    assert r.trough_index(LONG, 5, 9) == 6


@pytest.mark.unit
def test_no_new_low_guard_passes_when_trough_is_early_fails_when_late():
    assert r.no_new_low_guard(LONG, breakdown_index=5, reentry_index=9, grace_bars=2) is True
    late = _frame(
        [103, 102, 101, 100.5, 100.2, 99.0, 98.5, 98.2, 97.5, 100.6],
        lows=[102, 101, 101, 100.5, 100.2, 98.5, 98.0, 97.9, 97.2, 100.3],
    )
    assert r.no_new_low_guard(late, breakdown_index=5, reentry_index=9, grace_bars=2) is False


@pytest.mark.unit
def test_short_trigger_fires_on_pullback_low_break():
    assert (
        r.short_trigger_index(
            SHORT, reentry_index=8, boundary_price=100.0, pullback_low_price=98.9,
            buffer=0.3, confirm_window=8,
        )
        == 9
    )


@pytest.mark.unit
def test_short_trigger_fires_on_failed_retest_before_pullback_break():
    # High tags 100-0.3 from below at bar 9 but Close stays below 100; pullback low far away.
    frame = _frame([97, 98, 99, 99.5, 99.8, 101.2, 100.9, 100.2, 99.4, 99.8, 99.5],
                   highs=[97.5, 98.5, 99.5, 100, 100.3, 101.7, 101.4, 100.7, 99.9, 100.5, 100])
    assert (
        r.short_trigger_index(
            frame, reentry_index=8, boundary_price=100.0, pullback_low_price=90.0,
            buffer=0.3, confirm_window=8,
        )
        == 9
    )


@pytest.mark.unit
def test_short_trigger_returns_none_when_no_confirmation_in_window():
    flat = _frame([97, 98, 99, 99.5, 99.8, 101.2, 100.9, 100.4, 99.4])  # ends at re-entry
    assert (
        r.short_trigger_index(
            flat, reentry_index=8, boundary_price=100.0, pullback_low_price=98.9,
            buffer=0.3, confirm_window=8,
        )
        is None
    )


@pytest.mark.unit
def test_long_upgrade_fires_when_retest_holds():
    assert (
        r.long_upgrade_index(
            LONG, reentry_index=9, boundary_price=100.0, rebound_high_price=101.6, buffer=0.3
        )
        == 10
    )


@pytest.mark.unit
def test_long_upgrade_returns_none_without_break_or_held_retest():
    stalled = _frame([103, 102, 101, 100.6, 100.3, 98.8, 98.0, 99.0, 100.1, 100.05],
                     lows=[102, 101, 101, 100.5, 100.2, 98.5, 97.8, 98.4, 99.6, 99.0])
    assert (
        r.long_upgrade_index(
            stalled, reentry_index=8, boundary_price=100.0, rebound_high_price=101.6, buffer=0.3
        )
        is None
    )


@pytest.mark.unit
def test_volume_expanded_true_on_spike_false_on_flat():
    spike = _frame([100] * 22, volume=[1_000_000.0] * 21 + [1_600_000.0])
    assert r.volume_expanded(spike, 21) is True
    assert r.volume_expanded(_frame([100] * 22), 21) is False
