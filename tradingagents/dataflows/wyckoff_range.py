"""Shared trading-range geometry for Wyckoff accumulation/distribution.

Finds the consolidation band once (via the same centered swing-pivot logic
used in chart_patterns.py) so both event detectors start from the same
objective range geometry instead of each re-deriving support/resistance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

from tradingagents.dataflows.chart_patterns import Pivot, find_pivots

TrendDirection = Literal["up", "down", "flat"]


@dataclass
class TradingRange:
    range_high: float
    range_low: float
    start_index: int
    start_date: str
    high_touches: list[Pivot]
    low_touches: list[Pivot]
    prior_trend: TrendDirection


def prepare_ohlcv(data: pd.DataFrame, curr_date: str, look_back_days: int) -> pd.DataFrame:
    required = {"Date", "Open", "High", "Low", "Close", "Volume"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"OHLCV data is missing required columns: {sorted(missing)}")
    df = data.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    for column in required - {"Date"}:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = (
        df.dropna(subset=["Date", "High", "Low", "Close"])
        .loc[lambda frame: frame["Date"] <= pd.Timestamp(curr_date)]
        .sort_values("Date")
        .drop_duplicates("Date", keep="last")
        .tail(max(60, int(look_back_days)))
        .reset_index(drop=True)
    )
    if len(df) < 40:
        raise ValueError("At least 40 OHLCV rows are required for Wyckoff analysis.")
    return df


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    previous_close = df["Close"].shift(1)
    true_range = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - previous_close).abs(),
            (df["Low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(period, min_periods=1).mean()


def volume_ratio(df: pd.DataFrame, index: int, window: int = 20) -> float | None:
    if index < 1 or pd.isna(df.at[index, "Volume"]):
        return None
    baseline = pd.to_numeric(df["Volume"].iloc[max(0, index - window) : index], errors="coerce").mean()
    return float(df.at[index, "Volume"]) / float(baseline) if baseline else None


def _cluster(pivots: list[Pivot], tolerance: float) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []
    for pivot in sorted(pivots, key=lambda item: item.price):
        matching = next((c for c in clusters if abs(pivot.price - c["price"]) <= tolerance), None)
        if matching is None:
            clusters.append({"price": pivot.price, "pivots": [pivot]})
            continue
        matching["pivots"].append(pivot)
        matching["price"] = sum(p.price for p in matching["pivots"]) / len(matching["pivots"])
    return clusters


def _prior_trend(df: pd.DataFrame, start_index: int, atr_value: float) -> TrendDirection:
    lookback = max(0, start_index - 20)
    if start_index <= lookback:
        return "flat"
    change = float(df.at[start_index, "Close"]) - float(df.at[lookback, "Close"])
    if change <= -atr_value * 1.5:
        return "down"
    if change >= atr_value * 1.5:
        return "up"
    return "flat"


def _candidate_range(
    df: pd.DataFrame, hc: dict[str, Any], lc: dict[str, Any], atr_value: float
) -> TradingRange | None:
    upper, lower = float(hc["price"]), float(lc["price"])
    if upper <= lower:
        return None
    width, mid = upper - lower, (upper + lower) / 2
    if width < atr_value * 3 or width / mid > 0.4:
        return None
    hc_idx = [p.index for p in hc["pivots"]]
    lc_idx = [p.index for p in lc["pivots"]]
    if max(hc_idx) < min(lc_idx) or max(lc_idx) < min(hc_idx):
        return None  # boundaries never coexist in time, so this isn't one range
    current_price = float(df["Close"].iloc[-1])
    if current_price < lower - width or current_price > upper + width:
        return None  # price has drifted far enough away that this range no longer applies
    touches = hc["pivots"] + lc["pivots"]
    start_index = min(p.index for p in touches)
    return TradingRange(
        range_high=upper,
        range_low=lower,
        start_index=start_index,
        start_date=df.at[start_index, "Date"].strftime("%Y-%m-%d"),
        high_touches=hc["pivots"],
        low_touches=lc["pivots"],
        prior_trend=_prior_trend(df, start_index, atr_value),
    )


def detect_trading_range(
    df: pd.DataFrame, atr_value: float, pivot_span: int = 3
) -> TradingRange | None:
    """Find the most active recent band bounded by repeatedly touched pivots."""
    pivots = find_pivots(df, pivot_span)
    price = float(df["Close"].iloc[-1])
    tolerance = max(atr_value * 0.75, price * 0.02)
    high_clusters = [c for c in _cluster([p for p in pivots if p.kind == "high"], tolerance) if len(c["pivots"]) >= 2]
    low_clusters = [c for c in _cluster([p for p in pivots if p.kind == "low"], tolerance) if len(c["pivots"]) >= 2]
    candidates = [
        candidate
        for hc in high_clusters
        for lc in low_clusters
        if (candidate := _candidate_range(df, hc, lc, atr_value)) is not None
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda c: max(p.index for p in c.high_touches + c.low_touches))
