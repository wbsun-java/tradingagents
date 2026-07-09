"""Unit tests for Minervini's trend template scorer, using synthetic OHLCV."""

from __future__ import annotations

import pandas as pd
import pytest

import tradingagents.dataflows.trend_template as trend_template
from tradingagents.dataflows.trend_template import analyze_trend_template, evaluate_trend_template


def _ramp_with_recent_surge(length: int = 260, base_end: float = 130.0, surge_to: float = 169.0) -> pd.Series:
    """A steady ramp to base_end, then a strong surge in the final quarter."""
    closes = pd.Series(_ramp_ohlcv(100.0, base_end, length - 63)["Close"].tolist() + [None] * 63)
    closes.iloc[-63:] = pd.Series(
        [closes.iloc[-64] * (1.0 + (surge_to / base_end - 1.0) * i / 62) for i in range(63)]
    ).to_numpy()
    return closes


def _series_to_df(closes: pd.Series, length: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2024-01-02", periods=length),
            "Open": closes,
            "High": closes + 0.5,
            "Low": closes - 0.5,
            "Close": closes,
            "Volume": [1_000_000.0] * length,
        }
    )


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
def test_rs_score_weights_the_most_recent_quarter_more_heavily():
    length = 260
    benchmark = _ramp_ohlcv(100.0, 130.0, length)  # steady benchmark uptrend, no surge

    recent_surge_closes = _ramp_with_recent_surge(length, base_end=130.0, surge_to=169.0)
    recent_df = _series_to_df(recent_surge_closes, length)

    # Same total outperformance, but the surge happened a year-plus-a-quarter
    # ago instead of in the most recent quarter -- construct by taking the
    # recent-surge series and reversing which segment holds the big move.
    base = 100.0
    first_quarter_target = base * (169.0 / 130.0)
    old_segment = [base + (first_quarter_target - base) * i / 62 for i in range(63)]
    remainder = [old_segment[-1] * (1.0 + 0.30 * i / (length - 63 - 1)) for i in range(length - 63)]
    old_df = _series_to_df(pd.Series(old_segment + remainder), length)

    recent_result = evaluate_trend_template(recent_df, benchmark)
    old_result = evaluate_trend_template(old_df, benchmark)

    assert recent_result.values["rs_score"] is not None
    assert old_result.values["rs_score"] is not None
    assert recent_result.values["rs_score"] > old_result.values["rs_score"]


@pytest.mark.unit
def test_rs_score_is_none_with_less_than_a_year_of_history():
    stock = _ramp_ohlcv(50.0, 150.0, 200)  # under the 253-bar requirement
    benchmark = _ramp_ohlcv(50.0, 80.0, 200)

    result = evaluate_trend_template(stock, benchmark)

    assert result.values["rs_score"] is None


@pytest.mark.unit
def test_existing_relative_strength_criterion_unaffected_by_rs_score():
    stock = _ramp_ohlcv(50.0, 150.0, 260)
    benchmark = _ramp_ohlcv(50.0, 80.0, 260)

    result = evaluate_trend_template(stock, benchmark)

    # Unchanged from before rs_score existed.
    assert result.criteria["relative_strength_at_new_high"] is True
    assert result.passed_count == 8
    assert result.stage_2_uptrend


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
