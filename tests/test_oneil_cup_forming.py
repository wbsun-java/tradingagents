"""Unit tests for O'Neil cups with an unfinished right side."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.oneil_cup import atr, detect_cup
from tradingagents.dataflows.oneil_cup_forming import FORMING_MIN_RETRACE, detect_forming_cup


def _forming_cup(depth: float = 0.55, retrace: float = 0.60, extension: float = 0.0) -> pd.DataFrame:
    closes = list(np.linspace(50.0, 110.0, 50))
    if extension:
        closes.extend(np.linspace(110.5, 110.0 + extension, 10))
    rim = closes[-1]
    low = rim * (1 - depth)
    for index in range(50):
        progress = (index + 1) / 50
        closes.append(rim - (rim - low) * (1 - np.cos(progress * np.pi)) / 2)
    rng = np.random.default_rng(42)
    closes.extend(low + rng.uniform(-0.3, 0.3, 20))
    target = low + (rim - low) * retrace
    for index in range(45):
        progress = (index + 1) / 45
        closes.append(low + (target - low) * (1 - np.cos(progress * np.pi)) / 2)
    values = np.array(closes)
    volumes = np.full(len(values), 1_000_000.0)
    low_index = int(np.argmin(values))
    volumes[low_index - 5 : low_index + 6] = 600_000.0
    return pd.DataFrame({
        "Date": pd.bdate_range("2024-01-02", periods=len(values)),
        "Open": values,
        "High": values + 0.5,
        "Low": values - 0.5,
        "Close": values,
        "Volume": volumes,
    })


def _detected(data: pd.DataFrame):
    return detect_forming_cup(data, float(atr(data).iloc[-1]))


@pytest.mark.unit
def test_hood_shaped_forming_cup_detected():
    data = _forming_cup()
    candidate = _detected(data)

    assert candidate is not None
    assert candidate.complete is False
    assert candidate.pattern_type == "cup_without_handle"
    assert candidate.pivot_price == pytest.approx(110.5)
    assert candidate.start_index is not None
    assert candidate.base_low_price == pytest.approx(candidate.geometry["low_price"])
    assert 50 < candidate.geometry["depth_pct"] < 60
    assert 50 < candidate.geometry["retrace_pct"] < 70


@pytest.mark.unit
def test_local_high_exceeded_later_is_not_a_start():
    candidate = _detected(_forming_cup(extension=20.0))

    assert candidate is None or candidate.pivot_price > 110.5


@pytest.mark.unit
def test_highest_contained_rim_wins(monkeypatch: pytest.MonkeyPatch):
    data = _forming_cup()
    true_rim = float(data.at[49, "High"])
    data.at[75, "High"] = 100.0
    candidate = _detected(data)

    assert candidate is not None
    assert candidate.pivot_price == pytest.approx(true_rim)


@pytest.mark.unit
def test_no_recovery_yet_rejected():
    assert _detected(_forming_cup(retrace=FORMING_MIN_RETRACE - 0.01)) is None


@pytest.mark.unit
def test_completed_recovery_belongs_to_detect_cup():
    data = _forming_cup(retrace=1.0)
    atr_value = float(atr(data).iloc[-1])

    assert detect_forming_cup(data, atr_value) is None
    assert detect_cup(data, atr_value) is not None


@pytest.mark.unit
def test_too_shallow_decline_rejected():
    assert _detected(_forming_cup(depth=0.05)) is None


@pytest.mark.unit
def test_depth_above_cap_rejected():
    assert _detected(_forming_cup(depth=0.65)) is None


@pytest.mark.unit
def test_future_rows_do_not_contaminate_truncated_detection():
    data = _forming_cup()
    expected = _detected(data)
    future = pd.concat((data, _forming_cup().assign(Date=lambda frame: frame["Date"] + pd.Timedelta(days=500))), ignore_index=True)

    assert expected == _detected(future.iloc[: len(data)].copy())
