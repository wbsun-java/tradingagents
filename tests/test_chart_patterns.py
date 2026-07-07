"""Deterministic chart-pattern recognition tests using synthetic OHLCV."""

from __future__ import annotations

import pandas as pd
import pytest

import tradingagents.dataflows.chart_patterns as patterns


def _interpolate_anchors(anchors: list[tuple[int, float]]) -> list[float]:
    values: list[float] = []
    for pair_index, ((start, start_value), (end, end_value)) in enumerate(
        zip(anchors, anchors[1:], strict=False)
    ):
        count = end - start
        segment = [
            start_value + (end_value - start_value) * offset / count for offset in range(count)
        ]
        if pair_index == 0:
            values.extend(segment)
        else:
            values.extend(segment)
    values.append(anchors[-1][1])
    return values


def _ohlcv(closes: list[float], *, breakout_volume_index: int | None = None) -> pd.DataFrame:
    volume = [1_000_000.0] * len(closes)
    if breakout_volume_index is not None:
        volume[breakout_volume_index] = 1_600_000.0
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2026-01-02", periods=len(closes)),
            "Open": closes,
            "High": [close + 0.6 for close in closes],
            "Low": [close - 0.6 for close in closes],
            "Close": closes,
            "Volume": volume,
        }
    )


def _find(result: dict, pattern_name: str) -> dict:
    return next(item for item in result["patterns"] if item["pattern"] == pattern_name)


@pytest.mark.unit
def test_confirmed_double_bottom_has_neckline_target_and_invalidation():
    closes = _interpolate_anchors([(0, 108), (12, 95), (24, 108), (38, 96), (50, 111), (65, 114)])
    data = _ohlcv(closes, breakout_volume_index=48)

    result = patterns.analyze_chart_patterns_from_data(
        data, data["Date"].iloc[-1].strftime("%Y-%m-%d"), pivot_span=2
    )
    signal = _find(result, "double_bottom")

    assert signal["status"] == "confirmed"
    assert signal["direction"] == "bullish"
    assert signal["levels"]["neckline"] > signal["levels"]["second_extreme"]
    assert signal["target_price"] > signal["levels"]["neckline"]
    assert signal["invalidation_price"] < signal["levels"]["second_extreme"]


@pytest.mark.unit
def test_double_bottom_without_neckline_break_is_forming():
    closes = _interpolate_anchors([(0, 108), (12, 95), (24, 108), (38, 96), (55, 105)])
    data = _ohlcv(closes)
    result = patterns.analyze_chart_patterns_from_data(
        data, data["Date"].iloc[-1].strftime("%Y-%m-%d"), pivot_span=2
    )
    assert _find(result, "double_bottom")["status"] == "forming"


@pytest.mark.unit
def test_confirmed_double_top_is_bearish():
    closes = _interpolate_anchors([(0, 98), (12, 112), (24, 100), (38, 111), (50, 96), (65, 93)])
    data = _ohlcv(closes, breakout_volume_index=48)
    result = patterns.analyze_chart_patterns_from_data(
        data, data["Date"].iloc[-1].strftime("%Y-%m-%d"), pivot_span=2
    )
    signal = _find(result, "double_top")
    assert signal["status"] == "confirmed"
    assert signal["direction"] == "bearish"
    assert signal["target_price"] < signal["levels"]["neckline"]


@pytest.mark.unit
def test_rectangle_requires_repeated_touches_and_confirms_breakout():
    closes = _interpolate_anchors(
        [
            (0, 100),
            (6, 105),
            (12, 95),
            (18, 105),
            (24, 95),
            (30, 105),
            (36, 95),
            (42, 105),
            (48, 95),
            (54, 105),
            (62, 109),
        ]
    )
    data = _ohlcv(closes, breakout_volume_index=58)
    result = patterns.analyze_chart_patterns_from_data(
        data, data["Date"].iloc[-1].strftime("%Y-%m-%d"), pivot_span=2
    )
    signal = _find(result, "rectangle")
    assert signal["status"] == "confirmed"
    assert signal["direction"] == "bullish"
    assert signal["levels"]["resistance"] > signal["levels"]["support"]


@pytest.mark.unit
def test_symmetrical_triangle_reports_converging_trendlines():
    closes = _interpolate_anchors(
        [
            (0, 100),
            (5, 110),
            (10, 92),
            (15, 108),
            (20, 94),
            (25, 106),
            (30, 96),
            (35, 104),
            (40, 98),
            (45, 102.5),
            (50, 99.5),
            (53, 101),
        ]
    )
    data = _ohlcv(closes)
    result = patterns.analyze_chart_patterns_from_data(
        data, data["Date"].iloc[-1].strftime("%Y-%m-%d"), pivot_span=2
    )
    signal = _find(result, "symmetrical_triangle")
    assert signal["status"] == "forming"
    assert signal["levels"]["upper_trendline"] > signal["levels"]["lower_trendline"]


def _triangle_breakout_data(breakout_index: int, *, reverse_after: bool = False) -> pd.DataFrame:
    anchors = [
        (0, 100),
        (5, 110),
        (10, 90),
        (15, 108),
        (20, 92),
        (25, 106),
        (30, 94),
        (breakout_index - 2, 99.5),
        (breakout_index, 105 if breakout_index < 50 else 103),
    ]
    if reverse_after:
        anchors.append((breakout_index + 2, 99.5))
    else:
        anchors.append((breakout_index + 3, 106 if breakout_index < 50 else 104))
    closes = _interpolate_anchors(anchors)
    return _ohlcv(closes, breakout_volume_index=breakout_index)


@pytest.mark.unit
def test_early_triangle_breakout_is_not_penalized_as_risky():
    data = _triangle_breakout_data(34)
    result = patterns.analyze_chart_patterns_from_data(
        data, data["Date"].iloc[-1].strftime("%Y-%m-%d"), pivot_span=3
    )
    signal = _find(result, "symmetrical_triangle")

    assert signal["status"] == "confirmed"
    assert signal["levels"]["breakout_progress"] < 0.55
    assert "early_triangle_breakout" not in signal["risk_flags"]
    assert any("do not penalize it" in item for item in signal["evidence"])


@pytest.mark.unit
def test_triangle_breakout_near_two_thirds_gets_preferred_timing():
    data = _triangle_breakout_data(42)
    result = patterns.analyze_chart_patterns_from_data(
        data, data["Date"].iloc[-1].strftime("%Y-%m-%d"), pivot_span=3
    )
    signal = _find(result, "symmetrical_triangle")

    assert signal["status"] == "confirmed"
    assert 0.55 <= signal["levels"]["breakout_progress"] <= 0.75
    assert "late_apex_breakout" not in signal["risk_flags"]
    assert any("preferred zone around two-thirds" in item for item in signal["evidence"])


@pytest.mark.unit
def test_triangle_breakout_near_apex_is_flagged_and_penalized():
    ideal_data = _triangle_breakout_data(42)
    late_data = _triangle_breakout_data(53)
    ideal = _find(
        patterns.analyze_chart_patterns_from_data(
            ideal_data,
            ideal_data["Date"].iloc[-1].strftime("%Y-%m-%d"),
            pivot_span=3,
        ),
        "symmetrical_triangle",
    )
    late = _find(
        patterns.analyze_chart_patterns_from_data(
            late_data,
            late_data["Date"].iloc[-1].strftime("%Y-%m-%d"),
            pivot_span=3,
        ),
        "symmetrical_triangle",
    )

    assert late["status"] == "confirmed"
    assert late["levels"]["breakout_progress"] > 0.85
    assert "late_apex_breakout" in late["risk_flags"]
    assert late["confidence"] < ideal["confidence"]


@pytest.mark.unit
def test_late_triangle_breakout_that_reenters_is_failed():
    data = _triangle_breakout_data(53, reverse_after=True)
    result = patterns.analyze_chart_patterns_from_data(
        data, data["Date"].iloc[-1].strftime("%Y-%m-%d"), pivot_span=3
    )
    signal = _find(result, "symmetrical_triangle")

    assert signal["status"] == "failed"
    assert "late_apex_breakout" in signal["risk_flags"]
    assert "breakout_reversed_back_through_triangle" in signal["risk_flags"]


@pytest.mark.unit
def test_post_apex_move_expires_triangle_through_full_pipeline():
    # Price sits flat at the theoretical apex value for a while (no new
    # pivots form on a flat run) before a late move well past the original
    # trendlines — this exercises the extracted triangle_breakout module via
    # the full _triangle_pattern -> analyze_chart_patterns_from_data path.
    anchors = [(0, 100), (5, 110), (10, 90), (15, 108), (20, 92), (25, 106), (30, 94)]
    closes = _interpolate_anchors(anchors)
    closes += [99.5] * (65 - len(closes))
    closes += [112.0] * 6
    data = _ohlcv(closes, breakout_volume_index=len(closes) - 3)

    result = patterns.analyze_chart_patterns_from_data(
        data, data["Date"].iloc[-1].strftime("%Y-%m-%d"), pivot_span=3
    )
    signal = _find(result, "symmetrical_triangle")

    assert signal["status"] == "failed"
    assert signal["levels"]["breakout_progress"] is None
    assert "triangle_expired_at_apex" in signal["risk_flags"]
    assert signal["levels"]["upper_trendline"] == signal["levels"]["lower_trendline"]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("anchors", "pattern_name", "direction"),
    [
        (
            [
                (0, 100),
                (5, 110),
                (10, 92),
                (15, 110),
                (20, 95),
                (25, 110),
                (30, 98),
                (35, 110),
                (40, 101),
                (48, 106),
            ],
            "ascending_triangle",
            "bullish",
        ),
        (
            [
                (0, 100),
                (5, 110),
                (10, 92),
                (15, 107),
                (20, 92),
                (25, 104),
                (30, 92),
                (35, 101),
                (40, 92),
                (48, 97),
            ],
            "descending_triangle",
            "bearish",
        ),
    ],
)
def test_directional_triangles(anchors, pattern_name, direction):
    closes = _interpolate_anchors(anchors)
    data = _ohlcv(closes)
    result = patterns.analyze_chart_patterns_from_data(
        data, data["Date"].iloc[-1].strftime("%Y-%m-%d"), pivot_span=2
    )
    signal = _find(result, pattern_name)
    assert signal["status"] == "forming"
    assert signal["direction"] == direction


@pytest.mark.unit
def test_repeated_resistance_level_produces_standalone_breakout_signal():
    closes = _interpolate_anchors(
        [(0, 100), (6, 105), (12, 98), (18, 105), (24, 99), (30, 105), (38, 108)]
    )
    data = _ohlcv(closes, breakout_volume_index=34)
    result = patterns.analyze_chart_patterns_from_data(
        data, data["Date"].iloc[-1].strftime("%Y-%m-%d"), pivot_span=2
    )
    signal = _find(result, "resistance_breakout")
    assert signal["status"] == "confirmed"
    assert signal["direction"] == "bullish"
    assert signal["levels"]["breakout_price"] > signal["levels"]["broken_level"]


@pytest.mark.unit
def test_repeated_support_level_produces_standalone_breakdown_signal():
    closes = _interpolate_anchors(
        [(0, 100), (6, 95), (12, 102), (18, 95), (24, 101), (30, 95), (38, 92)]
    )
    data = _ohlcv(closes, breakout_volume_index=34)
    result = patterns.analyze_chart_patterns_from_data(
        data, data["Date"].iloc[-1].strftime("%Y-%m-%d"), pivot_span=2
    )
    signal = _find(result, "support_breakdown")
    assert signal["status"] == "confirmed"
    assert signal["direction"] == "bearish"
    assert signal["levels"]["breakout_price"] < signal["levels"]["broken_level"]


@pytest.mark.unit
def test_analysis_date_excludes_future_breakout():
    closes = _interpolate_anchors([(0, 108), (12, 95), (24, 108), (38, 96), (50, 111), (65, 114)])
    data = _ohlcv(closes)
    cutoff = data["Date"].iloc[44].strftime("%Y-%m-%d")
    result = patterns.analyze_chart_patterns_from_data(data, cutoff, pivot_span=2)
    signal = _find(result, "double_bottom")

    assert result["latest_row"] == cutoff
    assert signal["status"] == "forming"


@pytest.mark.unit
def test_tool_delegates_to_cutoff_safe_loader(monkeypatch):
    closes = _interpolate_anchors([(0, 100), (10, 95), (20, 105), (30, 96), (45, 108)])
    data = _ohlcv(closes)
    monkeypatch.setattr(patterns, "load_ohlcv", lambda symbol, date: data)

    payload = patterns.analyze_chart_patterns("cof", data["Date"].iloc[-1].strftime("%Y-%m-%d"))

    assert '"symbol": "COF"' in payload
    assert '"patterns"' in payload
