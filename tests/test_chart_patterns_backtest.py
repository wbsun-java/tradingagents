"""Walk-forward calibration report for the chart-pattern constants (SP4)."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows import chart_patterns_backtest as bt


def _interp(anchors):
    values = []
    for (s, sv), (e, ev) in zip(anchors, anchors[1:], strict=False):
        values += [sv + (ev - sv) * o / (e - s) for o in range(e - s)]
    values.append(anchors[-1][1])
    return values


def _osc_df():
    closes = _interp(
        [(0, 100), (10, 112), (22, 94), (34, 110), (46, 92), (58, 111), (70, 95),
         (82, 113), (94, 116)]
    )
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2026-01-02", periods=len(closes)),
            "Open": closes, "High": [c + 0.8 for c in closes], "Low": [c - 0.8 for c in closes],
            "Close": closes, "Volume": [1_000_000.0] * len(closes),
        }
    )


def _record(state, entry_direction, pattern, pattern_direction, status, risk_flags, fwd):
    return {
        "state": state, "entry_direction": entry_direction, "pattern": pattern,
        "pattern_direction": pattern_direction, "status": status,
        "risk_flags": tuple(risk_flags), "forward_return": fwd,
    }


@pytest.mark.unit
def test_edge_signs_by_direction():
    assert bt._edge(0.05, "long") == pytest.approx(0.05)
    assert bt._edge(0.05, "none") == pytest.approx(0.05)
    assert bt._edge(0.05, "short") == pytest.approx(-0.05)


@pytest.mark.unit
def test_pattern_direction_word_mapping():
    assert bt._pattern_direction_word("bullish") == "long"
    assert bt._pattern_direction_word("bearish") == "short"
    assert bt._pattern_direction_word("neutral") == "none"


@pytest.mark.unit
def test_apex_bucket_precedence():
    assert bt._apex_bucket(("post_apex_breakout", "late_apex_breakout")) == "post_apex_breakout"
    assert bt._apex_bucket(("late_apex_breakout",)) == "late_apex_breakout"
    assert bt._apex_bucket(()) == "normal"


@pytest.mark.unit
def test_forward_return_none_past_frame():
    df = _osc_df()
    assert bt._forward_return(df, df["Date"].iloc[-1], 3) is None
    val = bt._forward_return(df, df["Date"].iloc[10], 3)
    assert val == pytest.approx(
        (float(df["Close"].iloc[13]) - float(df["Close"].iloc[10])) / float(df["Close"].iloc[10])
    )


@pytest.mark.unit
def test_aggregate_routes_records_to_the_three_tables():
    records = [
        _record("breakout_entry", "long", "rectangle", "long", "confirmed", [], 0.04),
        _record("observe", "none", "symmetrical_triangle", "long", "confirmed",
                ["post_apex_breakout"], -0.02),
        _record("false_breakout_short", "short", "false_breakout_short", "short", "confirmed",
                ["aggressive_confirmation"], -0.03),
    ]
    stats = bt.new_stats()
    bt.aggregate(records, stats)

    assert stats["entry_state"]["breakout_entry"]["count"] == 1
    assert stats["entry_state"]["breakout_entry"]["hits"] == 1
    assert stats["apex"]["post_apex_breakout"]["count"] == 1
    assert stats["apex"]["post_apex_breakout"]["hits"] == 0
    tier = stats["tier"][("false_breakout_short", True)]
    assert tier["count"] == 1
    assert tier["hits"] == 1
    assert sum(b["count"] for b in stats["apex"].values()) == 1


@pytest.mark.unit
def test_format_report_has_the_three_table_headers():
    stats = bt.new_stats()
    bt.aggregate(
        [_record("avoid", "none", "double_top", "short", "confirmed", [], -0.01)], stats
    )
    text = bt.format_report(stats, ["AAPL"], 10)
    assert "TABLE 1" in text and "entry_state" in text
    assert "TABLE 2" in text and "apex" in text
    assert "TABLE 3" in text
    assert "autocorrelate" in text


@pytest.mark.unit
def test_collect_samples_returns_well_formed_records():
    records = bt.collect_samples(_osc_df(), step=5, holding_days=3)
    assert isinstance(records, list) and len(records) >= 1
    keys = {"state", "entry_direction", "pattern", "pattern_direction", "status",
            "risk_flags", "forward_return"}
    for r in records:
        assert set(r) == keys
        assert isinstance(r["forward_return"], float)
        assert r["state"] in bt.ENTRY_STATES or r["state"] is None
