"""Edge-case tests for Pocket Pivot core detection."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.pocket_pivot_signals import find_pocket_pivots

ATR = 2.0


def _flat_then_bounce() -> pd.DataFrame:
    closes = [100.0] * 11 + [101.0]
    dates = pd.date_range("2020-01-01", periods=len(closes), freq="D")
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": closes,
            "High": [c + 0.5 for c in closes],
            "Low": [c - 0.5 for c in closes],
            "Close": closes,
            "Volume": [1_000_000.0] * len(closes),
        }
    )


def _decline_then_bounce() -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=16, freq="D")
    step = (110.0 - 90.0) / 14
    closes = [110.0 - step * k for k in range(15)]
    opens = list(closes)
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    # Bounce bar: Open stays at/below the prior close (90.0) so it does not
    # gap up, while Close jumps to 101.0 (clears the 10dma on strong volume).
    closes.append(101.0)
    opens.append(90.0)
    highs.append(101.5)
    lows.append(89.5)
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": opens,
            "High": highs,
            "Low": lows,
            "Close": closes,
            "Volume": [1_000_000.0] * 15 + [5_000_000.0],
        }
    )


@pytest.mark.unit
def test_no_down_day_window_auto_passes_volume_rule():
    events = find_pocket_pivots(_flat_then_bounce(), ATR, ma_periods=(10,))
    assert len(events) == 1
    assert events[0].highest_down_volume_10d == 0.0


@pytest.mark.unit
def test_gap_up_false_when_open_does_not_exceed_prior_close():
    df = _decline_then_bounce()
    assert df.loc[df.index[-1], "Open"] <= df.loc[df.index[-2], "Close"]
    events = find_pocket_pivots(df, ATR, ma_periods=(10,))
    assert len(events) == 1
    assert events[0].gap_up is False
