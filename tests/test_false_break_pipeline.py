"""End-to-end false-break wiring through analyze_chart_patterns_from_data (SP2)."""

from __future__ import annotations

import pandas as pd
import pytest

import tradingagents.dataflows.chart_patterns as patterns


def _interp(anchors):
    values = []
    for start, end in zip(anchors, anchors[1:], strict=False):
        (s, sv), (e, ev) = start, end
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


def _reversed_triangle():
    bi = 53
    anchors = [
        (0, 100),
        (5, 110),
        (10, 90),
        (15, 108),
        (20, 92),
        (25, 106),
        (30, 94),
        (bi - 2, 99.5),
        (bi, 103),
        (bi + 2, 99.5),
    ]
    return _ohlcv(_interp(anchors), bvi=bi)


def _find(result, name):
    return next((p for p in result["patterns"] if p["pattern"] == name), None)


@pytest.mark.unit
def test_reversed_late_apex_triangle_emits_aggressive_short():
    data = _reversed_triangle()
    result = patterns.analyze_chart_patterns_from_data(
        data, data["Date"].iloc[-1].strftime("%Y-%m-%d"), pivot_span=3
    )
    short = _find(result, "false_breakout_short")
    assert short is not None
    assert short["status"] == "confirmed"
    assert short["direction"] == "bearish"
    assert "aggressive_confirmation" in short["risk_flags"]


@pytest.mark.unit
def test_reversed_triangle_parent_marked_expanding_with_void_target():
    data = _reversed_triangle()
    result = patterns.analyze_chart_patterns_from_data(
        data, data["Date"].iloc[-1].strftime("%Y-%m-%d"), pivot_span=3
    )
    parent = _find(result, "symmetrical_triangle")
    assert parent["status"] == "failed"
    assert "structure_may_be_expanding" in parent["risk_flags"]
    assert parent["target_price"] is None
