"""Unit tests for the Pocket Pivot orchestrator: JSON shape and the
active-window computation."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.pocket_pivot_bias import analyze_pocket_pivots_from_data


def _decline_then_bounce(
    decline_days: int,
    start_price: float,
    end_price: float,
    bounce_close: float,
    bounce_volume: float,
    trailing_flat_days: int = 0,
    down_volume: float = 1_000_000.0,
) -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=decline_days + 1 + trailing_flat_days, freq="D")
    step = (start_price - end_price) / (decline_days - 1)
    closes = [start_price - step * k for k in range(decline_days)]
    closes.append(bounce_close)
    closes.extend([bounce_close] * trailing_flat_days)
    volumes = [down_volume] * decline_days + [bounce_volume] + [1_000_000.0] * trailing_flat_days
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": closes,
            "High": [c + 0.5 for c in closes],
            "Low": [c - 0.5 for c in closes],
            "Close": closes,
            "Volume": volumes,
        }
    )


@pytest.mark.unit
def test_analyze_returns_event_and_marks_it_active_near_curr_date():
    # decline_days=50 -> 51 total rows, meeting pocket_pivot_signals.py's
    # MIN_ROWS=51 floor (added during Task 1's review to guard against
    # atr()/sma() silently returning NaN on too-short data). bounce_close=95
    # is calibrated to clear only the 10dma (sma10 ~= 91.97 + ATR buffer)
    # and NOT the 50dma (sma50 ~= 99.7 + buffer), so exactly one event
    # fires -- a bounce large enough to also clear the 50dma would produce
    # two events and break the len(...) == 1 assertions below.
    df = _decline_then_bounce(
        decline_days=50, start_price=110.0, end_price=90.0,
        bounce_close=95.0, bounce_volume=5_000_000.0,
    )
    curr_date = df["Date"].iloc[-1].strftime("%Y-%m-%d")
    result = analyze_pocket_pivots_from_data(df, curr_date)
    assert len(result["events"]) == 1
    assert result["active"] is True
    assert result["most_recent_event_date"] == curr_date
    assert "limitations" in result


@pytest.mark.unit
def test_analyze_marks_event_inactive_once_curr_date_moves_past_window():
    df = _decline_then_bounce(
        decline_days=50, start_price=110.0, end_price=90.0,
        bounce_close=95.0, bounce_volume=5_000_000.0, trailing_flat_days=15,
    )
    curr_date = df["Date"].iloc[-1].strftime("%Y-%m-%d")
    result = analyze_pocket_pivots_from_data(df, curr_date)
    assert len(result["events"]) == 1
    assert result["active"] is False


@pytest.mark.unit
def test_analyze_returns_empty_events_when_no_pivot_present():
    dates = pd.date_range("2020-01-01", periods=60, freq="D")
    closes = [100.0] * 60
    df = pd.DataFrame(
        {
            "Date": dates,
            "Open": closes,
            "High": [c + 0.5 for c in closes],
            "Low": [c - 0.5 for c in closes],
            "Close": closes,
            "Volume": [1_000_000.0] * 60,
        }
    )
    curr_date = df["Date"].iloc[-1].strftime("%Y-%m-%d")
    result = analyze_pocket_pivots_from_data(df, curr_date)
    assert result["events"] == []
    assert result["active"] is False
    assert result["most_recent_event_date"] is None
