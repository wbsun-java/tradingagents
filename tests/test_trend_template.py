"""Unit tests for Minervini's trend template scorer, using synthetic OHLCV."""

from __future__ import annotations

import pandas as pd
import pytest

import tradingagents.dataflows.trend_template as trend_template
from tradingagents.dataflows.trend_template import analyze_trend_template, evaluate_trend_template


def _ramp_ohlcv(start: float, end: float, length: int) -> pd.DataFrame:
    closes = [start + (end - start) * i / (length - 1) for i in range(length)]
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2024-01-02", periods=length),
            "Open": closes,
            "High": [c + 0.5 for c in closes],
            "Low": [c - 0.5 for c in closes],
            "Close": closes,
            "Volume": [1_000_000.0] * length,
        }
    )


@pytest.mark.unit
def test_steady_uptrend_passes_every_price_based_criterion():
    df = _ramp_ohlcv(50.0, 150.0, 260)

    result = evaluate_trend_template(df)

    assert result.criteria["price_above_150_and_200_sma"]
    assert result.criteria["sma150_above_sma200"]
    assert result.criteria["sma200_trending_up_1_month"]
    assert result.criteria["sma50_above_sma150_and_sma200"]
    assert result.criteria["price_above_sma50"]
    assert result.criteria["price_30pct_above_52w_low"]
    assert result.criteria["price_within_25pct_of_52w_high"]
    assert result.passed_count == 7
    assert result.stage_2_uptrend  # no benchmark supplied -> judged on the 7 available


@pytest.mark.unit
def test_steady_downtrend_fails_the_stage_criteria():
    df = _ramp_ohlcv(150.0, 50.0, 260)

    result = evaluate_trend_template(df)

    assert not result.criteria["price_above_150_and_200_sma"]
    assert not result.criteria["sma150_above_sma200"]
    assert not result.criteria["sma200_trending_up_1_month"]
    assert not result.stage_2_uptrend


@pytest.mark.unit
def test_insufficient_history_does_not_crash_and_fails_sma200_criteria():
    df = _ramp_ohlcv(90.0, 100.0, 120)  # under 200 bars

    result = evaluate_trend_template(df)

    assert result.values["sma_200"] is None
    assert not result.criteria["price_above_150_and_200_sma"]
    assert not result.stage_2_uptrend


@pytest.mark.unit
def test_relative_strength_flags_new_high_against_a_lagging_benchmark():
    stock = _ramp_ohlcv(50.0, 150.0, 260)
    benchmark = _ramp_ohlcv(50.0, 80.0, 260)  # stock outperforms -> RS line at a new high

    result = evaluate_trend_template(stock, benchmark)

    assert result.criteria["relative_strength_at_new_high"] is True
    assert result.total_criteria == 8


@pytest.mark.unit
def test_relative_strength_is_false_when_benchmark_outperforms():
    stock = _ramp_ohlcv(50.0, 80.0, 260)
    benchmark = _ramp_ohlcv(50.0, 150.0, 260)

    result = evaluate_trend_template(stock, benchmark)

    assert result.criteria["relative_strength_at_new_high"] is False


@pytest.mark.unit
def test_analyze_trend_template_falls_back_when_benchmark_unavailable(monkeypatch):
    stock = _ramp_ohlcv(50.0, 150.0, 260)

    def fake_load(symbol, date):
        if symbol == "SPY":
            raise ValueError("no data")
        return stock

    monkeypatch.setattr(trend_template, "load_ohlcv", fake_load)

    payload = analyze_trend_template("nvda", "2024-12-01")

    assert '"symbol": "NVDA"' in payload
    assert '"benchmark": null' in payload
