"""End-to-end wiring of the emerging double_bottom into the pipeline (SP3b)."""

from __future__ import annotations

import pandas as pd
import pytest

import tradingagents.dataflows.chart_patterns as patterns


def _rising_df():
    closes = [100 + i * 0.3 for i in range(60)]
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2026-01-02", periods=len(closes)),
            "Open": closes,
            "High": [c + 0.5 for c in closes],
            "Low": [c - 0.5 for c in closes],
            "Close": closes,
            "Volume": [1_000_000.0] * len(closes),
        }
    )


def _fake_emerging():
    return patterns.PricePattern(
        pattern="double_bottom",
        status="emerging",
        direction="bullish",
        confidence=0.4,
        start_date="2026-01-02",
        end_date="2026-02-01",
        levels={
            "first_extreme": 95.0,
            "second_extreme": 95.4,
            "neckline": 109.6,
            "breakout_price": None,
        },
        target_price=124.0,
        invalidation_price=95.1,
        volume_confirmed=None,
        evidence=["x"],
    )


@pytest.mark.unit
def test_emerging_is_appended_and_gets_predictive_bottom(monkeypatch):
    monkeypatch.setattr(patterns, "find_emerging_double_bottom", lambda *a: _fake_emerging())
    data = _rising_df()
    result = patterns.analyze_chart_patterns_from_data(
        data, data["Date"].iloc[-1].strftime("%Y-%m-%d"), pivot_span=3
    )
    emerging = [
        p
        for p in result["patterns"]
        if p["pattern"] == "double_bottom" and p["status"] == "emerging"
    ]
    assert len(emerging) == 1
    assert emerging[0]["entry_assessment"]["state"] == "predictive_bottom"


@pytest.mark.unit
def test_emerging_is_suppressed_when_a_double_bottom_already_exists(monkeypatch):
    monkeypatch.setattr(patterns, "find_emerging_double_bottom", lambda *a: _fake_emerging())

    def _interp(anchors):
        values = []
        for (start, start_value), (end, end_value) in zip(anchors, anchors[1:], strict=False):
            values += [
                start_value + (end_value - start_value) * offset / (end - start)
                for offset in range(end - start)
            ]
        values.append(anchors[-1][1])
        return values

    closes = _interp([(0, 108), (12, 95), (24, 108), (38, 96), (50, 111), (65, 114)])
    data = pd.DataFrame(
        {
            "Date": pd.bdate_range("2026-01-02", periods=len(closes)),
            "Open": closes,
            "High": [c + 0.6 for c in closes],
            "Low": [c - 0.6 for c in closes],
            "Close": closes,
            "Volume": [1_000_000.0] * len(closes),
        }
    )
    result = patterns.analyze_chart_patterns_from_data(
        data, data["Date"].iloc[-1].strftime("%Y-%m-%d"), pivot_span=2
    )
    doubles = [p for p in result["patterns"] if p["pattern"] == "double_bottom"]
    assert len(doubles) == 1
    assert doubles[0]["status"] != "emerging"
