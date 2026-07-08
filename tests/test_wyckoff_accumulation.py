"""Unit tests for accumulation-side Wyckoff event/phase detection, synthetic OHLCV only."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.wyckoff_accumulation import analyze_accumulation
from tradingagents.dataflows.wyckoff_range import atr, detect_trading_range, prepare_ohlcv

# (close, low, high, volume) bars laid on top of a downtrend + oscillating range.
_TEXTBOOK_EVENTS = [
    (85.0, 84.0, 86.0, 1_000_000.0),  # rally toward the range high
    (88.0, 87.0, 89.0, 1_000_000.0),
    (90.0, 89.0, 91.0, 1_000_000.0),  # automatic rally peak
    (84.0, 83.0, 85.0, 1_000_000.0),  # pull back
    (78.0, 77.0, 79.0, 1_000_000.0),  # secondary test of the low, on light volume
    (81.0, 80.0, 82.0, 1_000_000.0),
    (77.3, 62.0, 78.0, 1_000_000.0),  # spring: pierces the low, closes back inside
]
_AFTER_SPRING = [
    (83.0, 82.0, 84.0, 1_000_000.0),  # recovery, away from the boundary
    (77.5, 76.0, 78.5, 1_000_000.0),  # test of the spring low
]
_BREAKOUT = [
    (94.0, 93.0, 95.0, 2_000_000.0),  # sign of strength: buffered close above the range
    (93.5, 92.6, 94.3, 1_000_000.0),  # last point of support, holding former resistance
    (92.0, 91.0, 93.0, 1_000_000.0),
    (91.5, 90.5, 92.5, 1_000_000.0),
    (95.0, 94.0, 96.0, 1_000_000.0),  # back up: extends past the last point of support
]


def _base_bars(boost_volume: bool = True) -> tuple[list[float], list[float], list[float], list[float]]:
    """Downtrend into an oscillating range, with an optional volume climax at the last low."""
    down_len = 60
    closes = [150.0 - 70.0 * i / (down_len - 1) for i in range(down_len)]
    volumes = [1_000_000.0] * down_len
    for i in range(29):
        phase = i % 14
        val = 78.0 + phase * 2.0 if phase <= 7 else 92.0 - (phase - 7) * 2.0
        closes.append(val)
        volumes.append(1_000_000.0)
    if boost_volume:
        volumes[down_len + 28] = 2_500_000.0  # selling climax at the final oscillation low
    highs = [c + 1.0 for c in closes]
    lows = [c - 1.0 for c in closes]
    return closes, highs, lows, volumes


def _extend(closes, highs, lows, volumes, bars, pad_bars=0, pad_bar=(80.0, 79.0, 81.0)):
    for c, low, high, vol in list(bars) + [(*pad_bar, 1_000_000.0)] * pad_bars:
        closes.append(c)
        highs.append(high)
        lows.append(low)
        volumes.append(vol)


def _to_df(closes, highs, lows, volumes) -> pd.DataFrame:
    return pd.DataFrame({
        "Date": pd.bdate_range("2023-01-02", periods=len(closes)),
        "Open": closes, "High": highs, "Low": lows, "Close": closes, "Volume": volumes,
    })


def _prepared_inputs(df: pd.DataFrame):
    prepared = prepare_ohlcv(df, df["Date"].iloc[-1].strftime("%Y-%m-%d"), look_back_days=504)
    atr_value = float(atr(prepared).iloc[-1])
    rng = detect_trading_range(prepared, atr_value)
    return prepared, atr_value, rng


@pytest.mark.unit
def test_textbook_sequence_reaches_phase_e_with_all_core_events():
    closes, highs, lows, volumes = _base_bars()
    _extend(closes, highs, lows, volumes, _TEXTBOOK_EVENTS)
    _extend(closes, highs, lows, volumes, _AFTER_SPRING)
    _extend(closes, highs, lows, volumes, [], pad_bars=30, pad_bar=(85.0, 84.0, 86.0))
    _extend(closes, highs, lows, volumes, [(82.0, 81.0, 83.0, 1_000_000.0), (86.0, 85.0, 87.0, 1_000_000.0), (90.0, 89.0, 91.0, 1_000_000.0)])
    _extend(closes, highs, lows, volumes, _BREAKOUT)
    _extend(closes, highs, lows, volumes, [], pad_bars=5, pad_bar=(95.0, 94.0, 96.0))

    result = analyze_accumulation(*_prepared_inputs(_to_df(closes, highs, lows, volumes)))

    assert result is not None
    assert result.phase == "E"
    names = {e.event for e in result.events}
    assert names == {
        "selling_climax", "automatic_rally", "secondary_test", "spring", "test",
        "sign_of_strength", "last_point_of_support", "back_up",
    }
    assert result.confidence > 0.8


@pytest.mark.unit
def test_sequence_truncated_right_after_spring_stops_at_phase_c():
    closes, highs, lows, volumes = _base_bars()
    _extend(closes, highs, lows, volumes, _TEXTBOOK_EVENTS)
    _extend(closes, highs, lows, volumes, [], pad_bars=10, pad_bar=(80.0, 79.0, 81.0))

    result = analyze_accumulation(*_prepared_inputs(_to_df(closes, highs, lows, volumes)))

    assert result is not None
    assert result.phase == "C"
    names = {e.event for e in result.events}
    assert {"selling_climax", "automatic_rally", "secondary_test", "spring"} <= names
    assert "sign_of_strength" not in names
    assert "back_up" not in names


@pytest.mark.unit
def test_no_elevated_volume_bar_is_not_fabricated_into_a_climax():
    closes, highs, lows, volumes = _base_bars(boost_volume=False)

    result = analyze_accumulation(*_prepared_inputs(_to_df(closes, highs, lows, volumes)))

    assert result is None


@pytest.mark.unit
def test_climax_is_found_even_when_priced_away_from_the_settled_range():
    """Capitulation can print away from where the range settles; climax search must still find it."""
    closes, highs, lows, volumes = _base_bars(boost_volume=False)
    capitulation = [(84.0, 82.0, 86.0, 5e6), (81.0, 80.0, 82.0, 1e6), (79.0, 78.0, 80.0, 1e6)]
    for offset, (c, low, high, vol) in enumerate(capitulation):
        closes.insert(60 + offset, c)
        highs.insert(60 + offset, high)
        lows.insert(60 + offset, low)
        volumes.insert(60 + offset, vol)

    result = analyze_accumulation(*_prepared_inputs(_to_df(closes, highs, lows, volumes)))

    assert result is not None
    assert result.events[0].event == "selling_climax"
    assert result.events[0].volume_ratio >= 1.8


@pytest.mark.unit
def test_pure_uptrend_yields_no_accumulation_result():
    length = 120
    closes = [50.0 + 100.0 * i / (length - 1) for i in range(length)]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    volumes = [1_000_000.0] * length

    result = analyze_accumulation(*_prepared_inputs(_to_df(closes, highs, lows, volumes)))

    assert result is None
