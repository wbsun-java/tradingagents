"""Minervini's Trend Template: an 8-point technical stage-2 filter.

Reference: Mark Minervini, "Trade Like a Stock Market Wizard". Every
criterion is a threshold comparison on moving averages and 52-week price
extremes computed straight from OHLCV — no LLM judgment, consistent with
"code decides, LLM explains." Relative strength is approximated as a stock's
price ratio against a benchmark index sitting at a new high, since a true
percentile rank needs a whole-market universe this project doesn't hold.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pandas as pd

from tradingagents.dataflows.stockstats_utils import load_ohlcv

_MONTH_BARS = 21  # ~1 trading month, for the "200-day MA rising" check
_QUARTER_BARS = 63  # ~1 trading quarter
_QUARTER_WEIGHTS = (0.4, 0.2, 0.2, 0.2)  # most recent quarter weighted heaviest (O'Neil/IBD style)


def relative_strength_score(df: pd.DataFrame, benchmark_df: pd.DataFrame) -> float | None:
    """Quarter-weighted excess return vs. benchmark; most recent quarter weighted heaviest.

    Additive alongside `_relative_strength_at_new_high`'s boolean criterion --
    does not change that criterion's, `passed_count`'s, or `stage_2_uptrend`'s
    behavior. Returns None when there isn't a full year of aligned history.
    """
    merged = pd.merge(df[["Date", "Close"]], benchmark_df[["Date", "Close"]], on="Date", suffixes=("", "_bm"))
    needed = _QUARTER_BARS * len(_QUARTER_WEIGHTS) + 1
    if len(merged) < needed:
        return None
    closes = merged["Close"].to_numpy()
    bm_closes = merged["Close_bm"].to_numpy()
    score = 0.0
    for i, weight in enumerate(_QUARTER_WEIGHTS):
        end = len(closes) - 1 - i * _QUARTER_BARS
        start = end - _QUARTER_BARS
        stock_ret = closes[end] / closes[start] - 1.0
        bm_ret = bm_closes[end] / bm_closes[start] - 1.0
        score += weight * (stock_ret - bm_ret)
    return round(float(score), 4)


@dataclass
class TrendTemplateResult:
    criteria: dict[str, bool]
    passed_count: int
    total_criteria: int
    stage_2_uptrend: bool
    values: dict[str, float | None] = field(default_factory=dict)


def _sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()


def _relative_strength_at_new_high(df: pd.DataFrame, benchmark_df: pd.DataFrame) -> bool | None:
    merged = pd.merge(
        df[["Date", "Close"]], benchmark_df[["Date", "Close"]], on="Date", suffixes=("", "_bm")
    )
    if len(merged) < 2:
        return None
    rs_line = merged["Close"] / merged["Close_bm"]
    return bool(rs_line.iloc[-1] >= rs_line.max() - 1e-9)


def evaluate_trend_template(
    df: pd.DataFrame, benchmark_df: pd.DataFrame | None = None
) -> TrendTemplateResult:
    """Score a stock against Minervini's 8-point trend template."""
    close = df["Close"]
    sma50, sma150, sma200 = _sma(close, 50), _sma(close, 150), _sma(close, 200)
    price = float(close.iloc[-1])
    high_52w, low_52w = float(df["High"].tail(252).max()), float(df["Low"].tail(252).min())

    have_history = not pd.isna(sma200.iloc[-1]) and len(sma200) > _MONTH_BARS
    sma50_now = float(sma50.iloc[-1]) if not pd.isna(sma50.iloc[-1]) else None
    sma150_now = float(sma150.iloc[-1]) if not pd.isna(sma150.iloc[-1]) else None
    sma200_now = float(sma200.iloc[-1]) if have_history else None
    sma200_month_ago = float(sma200.iloc[-1 - _MONTH_BARS]) if have_history else None

    criteria = {
        "price_above_150_and_200_sma": bool(
            have_history and sma150_now and price > sma150_now and price > sma200_now
        ),
        "sma150_above_sma200": bool(have_history and sma150_now > sma200_now),
        "sma200_trending_up_1_month": bool(have_history and sma200_now > sma200_month_ago),
        "sma50_above_sma150_and_sma200": bool(
            have_history and sma50_now and sma50_now > sma150_now > sma200_now
        ),
        "price_above_sma50": bool(sma50_now and price > sma50_now),
        "price_30pct_above_52w_low": price >= low_52w * 1.30,
        "price_within_25pct_of_52w_high": price >= high_52w * 0.75,
    }

    rs_new_high = _relative_strength_at_new_high(df, benchmark_df) if benchmark_df is not None else None
    if rs_new_high is not None:
        criteria["relative_strength_at_new_high"] = rs_new_high

    values = {
        "price": price,
        "sma_50": sma50_now,
        "sma_150": sma150_now,
        "sma_200": sma200_now,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "pct_above_52w_low": round((price / low_52w - 1) * 100, 2),
        "pct_below_52w_high": round((1 - price / high_52w) * 100, 2),
        "rs_score": relative_strength_score(df, benchmark_df) if benchmark_df is not None else None,
    }

    passed = sum(criteria.values())
    return TrendTemplateResult(
        criteria=criteria,
        passed_count=passed,
        total_criteria=len(criteria),
        stage_2_uptrend=passed == len(criteria),
        values=values,
    )


def analyze_trend_template(symbol: str, curr_date: str, benchmark: str = "SPY") -> str:
    """Load cutoff-safe OHLCV for `symbol` (and `benchmark`) and score the template."""
    df = load_ohlcv(symbol, curr_date)
    try:
        benchmark_df = load_ohlcv(benchmark, curr_date) if benchmark else None
    except ValueError:
        benchmark_df = None

    result = evaluate_trend_template(df, benchmark_df)
    return json.dumps(
        {
            "symbol": symbol.upper(),
            "benchmark": benchmark.upper() if benchmark_df is not None else None,
            "analysis_date": curr_date,
            "stage_2_uptrend": result.stage_2_uptrend,
            "passed_count": result.passed_count,
            "total_criteria": result.total_criteria,
            "criteria": result.criteria,
            "values": result.values,
        },
        indent=2,
    )
