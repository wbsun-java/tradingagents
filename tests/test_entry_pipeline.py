"""End-to-end entry_assessment wiring through analyze_chart_patterns_from_data (SP3)."""

from __future__ import annotations

import pandas as pd
import pytest

import tradingagents.dataflows.chart_patterns as patterns


def _interp(anchors):
    values = []
    for (s, sv), (e, ev) in zip(anchors, anchors[1:], strict=False):
        values += [sv + (ev - sv) * o / (e - s) for o in range(e - s)]
    values.append(anchors[-1][1])
    return values


def _ohlcv(closes, bvi=None):
    volume = [1_000_000.0] * len(closes)
    if bvi is not None:
        volume[bvi] = 1_600_000.0
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2026-01-02", periods=len(closes)),
            "Open": closes,
            "High": [c + 0.6 for c in closes],
            "Low": [c - 0.6 for c in closes],
            "Close": closes,
            "Volume": volume,
        }
    )


def _result():
    closes = _interp([(0, 108), (12, 95), (24, 108), (38, 96), (50, 111), (65, 114)])
    data = _ohlcv(closes, bvi=48)
    return patterns.analyze_chart_patterns_from_data(
        data, data["Date"].iloc[-1].strftime("%Y-%m-%d"), pivot_span=2
    )


@pytest.mark.unit
def test_extended_confirmed_double_bottom_is_observe():
    db = next(p for p in _result()["patterns"] if p["pattern"] == "double_bottom")
    assert db["entry_assessment"]["state"] == "observe"
    assert db["entry_assessment"]["direction"] == "none"


@pytest.mark.unit
def test_every_pattern_carries_an_entry_assessment():
    result = _result()
    assert result["patterns"]
    for p in result["patterns"]:
        assert p["entry_assessment"] is not None
        assert p["entry_assessment"]["state"]
