"""Unit tests for distribution-side Wyckoff event/phase detection, synthetic OHLCV only."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.wyckoff_distribution import analyze_distribution
from tradingagents.dataflows.wyckoff_range import atr, detect_trading_range, prepare_ohlcv

# (close, low, high, volume) bars laid on top of an uptrend + oscillating range.
_TEXTBOOK_EVENTS = [
    (82.0, 81.0, 83.0, 1_000_000.0),  # automatic reaction building down
    (80.0, 79.0, 81.0, 1_000_000.0),
    (78.0, 77.0, 79.0, 1_000_000.0),  # automatic reaction low
    (84.0, 83.0, 85.0, 1_000_000.0),  # bounce
    (92.0, 91.0, 93.0, 1_000_000.0),  # secondary test of the high, on light volume
    (87.0, 86.0, 88.0, 1_000_000.0),
    (92.7, 92.0, 98.0, 1_000_000.0),  # upthrust after distribution: pierces the high, closes back
]
_AFTER_UTAD = [
    (86.0, 85.0, 87.0, 1_000_000.0),  # recovery, away from the boundary
    (92.5, 91.5, 94.0, 1_000_000.0),  # test of the upthrust high
]
_BREAKDOWN = [
    (74.0, 73.0, 75.0, 2_000_000.0),  # sign of weakness: buffered close below the range
    (75.5, 74.5, 76.3, 1_000_000.0),  # last point of supply, holding former support
    (77.0, 76.0, 78.0, 1_000_000.0),
    (76.5, 75.5, 77.5, 1_000_000.0),
    (73.0, 72.0, 74.0, 1_000_000.0),  # upthrust: extends past the last point of supply
]


def _base_bars(boost_volume: bool = True) -> tuple[list[float], list[float], list[float], list[float]]:
    """Uptrend into an oscillating range, with an optional volume climax at the last high."""
    up_len = 60
    closes = [40.0 + 45.0 * i / (up_len - 1) for i in range(up_len)]
    volumes = [1_000_000.0] * up_len
    for i in range(22):
        phase = i % 14
        val = 78.0 + phase * 2.0 if phase <= 7 else 92.0 - (phase - 7) * 2.0
        closes.append(val)
        volumes.append(1_000_000.0)
    if boost_volume:
        volumes[up_len + 21] = 2_500_000.0  # buying climax at the final oscillation high
    highs = [c + 1.0 for c in closes]
    lows = [c - 1.0 for c in closes]
    return closes, highs, lows, volumes


def _extend(closes, highs, lows, volumes, bars, pad_bars=0, pad_bar=(80.0, 79.0, 81.0)):
    for c, low, high, vol in bars:
        closes.append(c)
        highs.append(high)
        lows.append(low)
        volumes.append(vol)
    for _ in range(pad_bars):
        c, low, high = pad_bar
        closes.append(c)
        highs.append(high)
        lows.append(low)
        volumes.append(1_000_000.0)


def _to_df(closes, highs, lows, volumes) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2023-01-02", periods=len(closes)),
            "Open": closes,
            "High": highs,
            "Low": lows,
            "Close": closes,
            "Volume": volumes,
        }
    )


def _prepared_inputs(df: pd.DataFrame):
    prepared = prepare_ohlcv(df, df["Date"].iloc[-1].strftime("%Y-%m-%d"), look_back_days=504)
    atr_value = float(atr(prepared).iloc[-1])
    rng = detect_trading_range(prepared, atr_value)
    return prepared, atr_value, rng


@pytest.mark.unit
def test_textbook_sequence_reaches_phase_e_with_all_core_events():
    closes, highs, lows, volumes = _base_bars()
    _extend(closes, highs, lows, volumes, _TEXTBOOK_EVENTS)
    _extend(closes, highs, lows, volumes, _AFTER_UTAD)
    _extend(closes, highs, lows, volumes, [], pad_bars=30, pad_bar=(85.0, 84.0, 86.0))
    _extend(closes, highs, lows, volumes, [(88.0, 87.0, 89.0, 1_000_000.0), (84.0, 83.0, 85.0, 1_000_000.0), (80.0, 79.0, 81.0, 1_000_000.0)])
    _extend(closes, highs, lows, volumes, _BREAKDOWN)
    _extend(closes, highs, lows, volumes, [], pad_bars=5, pad_bar=(73.0, 72.0, 74.0))

    result = analyze_distribution(*_prepared_inputs(_to_df(closes, highs, lows, volumes)))

    assert result is not None
    assert result.phase == "E"
    names = {e.event for e in result.events}
    assert names == {
        "buying_climax", "automatic_reaction", "secondary_test", "upthrust_after_distribution",
        "test", "sign_of_weakness", "last_point_of_supply", "upthrust",
    }
    assert result.confidence > 0.8
    assert result.invalidated is False


_REVERSAL = [(96.0, 95.5, 97.0, 1_500_000.0)]  # closes back above the original range high


@pytest.mark.unit
def test_reversal_after_upthrust_marks_the_read_invalidated():
    closes, highs, lows, volumes = _base_bars()
    _extend(closes, highs, lows, volumes, _TEXTBOOK_EVENTS)
    _extend(closes, highs, lows, volumes, _AFTER_UTAD)
    _extend(closes, highs, lows, volumes, [], pad_bars=30, pad_bar=(85.0, 84.0, 86.0))
    _extend(closes, highs, lows, volumes, [(88.0, 87.0, 89.0, 1_000_000.0), (84.0, 83.0, 85.0, 1_000_000.0), (80.0, 79.0, 81.0, 1_000_000.0)])
    _extend(closes, highs, lows, volumes, _BREAKDOWN)
    _extend(closes, highs, lows, volumes, [], pad_bars=5, pad_bar=(73.0, 72.0, 74.0))
    _extend(closes, highs, lows, volumes, _REVERSAL)

    result = analyze_distribution(*_prepared_inputs(_to_df(closes, highs, lows, volumes)))

    assert result is not None
    assert result.phase == "E"
    assert result.invalidated is True
    assert result.events[-1].event == "range_failure"


@pytest.mark.unit
def test_sequence_truncated_right_after_utad_stops_at_phase_c():
    closes, highs, lows, volumes = _base_bars()
    _extend(closes, highs, lows, volumes, _TEXTBOOK_EVENTS)
    _extend(closes, highs, lows, volumes, [], pad_bars=10, pad_bar=(80.0, 79.0, 81.0))

    result = analyze_distribution(*_prepared_inputs(_to_df(closes, highs, lows, volumes)))

    assert result is not None
    assert result.phase == "C"
    names = {e.event for e in result.events}
    assert {"buying_climax", "automatic_reaction", "secondary_test", "upthrust_after_distribution"} <= names
    assert "sign_of_weakness" not in names
    assert "upthrust" not in names


@pytest.mark.unit
def test_no_elevated_volume_bar_is_not_fabricated_into_a_climax():
    closes, highs, lows, volumes = _base_bars(boost_volume=False)

    result = analyze_distribution(*_prepared_inputs(_to_df(closes, highs, lows, volumes)))

    assert result is None


@pytest.mark.unit
def test_pure_downtrend_yields_no_distribution_result():
    length = 120
    closes = [150.0 - 100.0 * i / (length - 1) for i in range(length)]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    volumes = [1_000_000.0] * length

    result = analyze_distribution(*_prepared_inputs(_to_df(closes, highs, lows, volumes)))

    assert result is None
