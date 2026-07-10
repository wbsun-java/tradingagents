"""Cup detection for O'Neil's cup-with-handle pattern.

Finds a rounded consolidation base that follows a meaningful prior uptrend,
using the same centered swing-pivot logic as chart_patterns.py and
wyckoff_range.py. See ONEIL_CANSLIM_ANALYSIS_PLAN.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from tradingagents.dataflows.chart_patterns import find_pivots
from tradingagents.dataflows.oneil_base_types import contained_below, prior_uptrend
from tradingagents.dataflows.oneil_cup_quality import bottom_volume_dry_up

MIN_CUP_DAYS = 35
MAX_CUP_DAYS = 325
MIN_DEPTH_ATR = 3.0
MIN_DEPTH_PCT = 0.08
MAX_DEPTH_PCT = 0.60
RECOVERY_BUFFER_ATR = 1.0
ROUNDING_WINDOW = 5
ROUNDING_TOLERANCE_ATR = 1.5
ROUNDING_MIN_BARS = 3
VOLUME_RATIO_WINDOW = 50


@dataclass
class CupCandidate:
    left_high_index: int
    left_high_date: str
    left_high_price: float
    low_date: str
    low_price: float
    right_high_index: int
    right_high_date: str
    depth_pct: float
    duration_days: int
    evidence: list[str] = field(default_factory=list)


def prepare_ohlcv(data: pd.DataFrame, curr_date: str, look_back_days: int) -> pd.DataFrame:
    required = {"Date", "Open", "High", "Low", "Close", "Volume"}
    df = data.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    for column in required - {"Date"}:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = (
        df.dropna(subset=["Date", "High", "Low", "Close"])
        .loc[lambda frame: frame["Date"] <= pd.Timestamp(curr_date)]
        .sort_values("Date")
        .drop_duplicates("Date", keep="last")
        .tail(max(80, int(look_back_days)))
        .reset_index(drop=True)
    )
    if len(df) < 80:
        raise ValueError("At least 80 OHLCV rows are required for O'Neil cup-with-handle analysis.")
    return df


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    previous_close = df["Close"].shift(1)
    true_range = pd.concat(
        [df["High"] - df["Low"], (df["High"] - previous_close).abs(), (df["Low"] - previous_close).abs()],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(period, min_periods=1).mean()


def volume_ratio(df: pd.DataFrame, index: int, window: int = VOLUME_RATIO_WINDOW) -> float | None:
    if index < 1 or pd.isna(df.at[index, "Volume"]):
        return None
    baseline = pd.to_numeric(df["Volume"].iloc[max(0, index - window) : index], errors="coerce").mean()
    return float(df.at[index, "Volume"]) / float(baseline) if baseline else None


def _has_rounding_base(df: pd.DataFrame, low_index: int, low_price: float, atr_value: float, lo_bound: int, hi_bound: int) -> bool:
    lo = max(lo_bound + 1, low_index - ROUNDING_WINDOW)
    hi = min(hi_bound - 1, low_index + ROUNDING_WINDOW)
    if hi < lo:
        return False
    window = df.iloc[lo : hi + 1]
    near_low = (window["Close"] - low_price).abs() <= atr_value * ROUNDING_TOLERANCE_ATR
    return int(near_low.sum()) >= ROUNDING_MIN_BARS


def detect_cup(df: pd.DataFrame, atr_value: float, pivot_span: int = 3) -> CupCandidate | None:
    """Find the most recent complete cup: prior uptrend, rounded decline to a
    low, and recovery back near the left-side high, within adaptive bounds."""
    highs = [p for p in find_pivots(df, pivot_span) if p.kind == "high"]
    candidates: list[CupCandidate] = []
    for lh in highs:
        has_uptrend, uptrend_evidence = prior_uptrend(df, lh.index, atr_value)
        if not has_uptrend:
            continue
        window_end = min(len(df) - 1, lh.index + MAX_CUP_DAYS)
        if window_end - lh.index < MIN_CUP_DAYS:
            continue
        low_search = df.iloc[lh.index + 1 : window_end + 1]
        if low_search.empty:
            continue
        low_index = int(low_search["Low"].idxmin())
        low_price = float(df.at[low_index, "Low"])
        depth_abs = lh.price - low_price
        depth_pct = depth_abs / lh.price if lh.price else 0.0
        if depth_abs < atr_value * MIN_DEPTH_ATR or not (MIN_DEPTH_PCT <= depth_pct <= MAX_DEPTH_PCT):
            continue
        buffer = atr_value * RECOVERY_BUFFER_ATR
        right_high_index = next(
            (i for i in range(low_index + 1, window_end + 1) if float(df.at[i, "Close"]) >= lh.price - buffer),
            None,
        )
        if right_high_index is None:
            continue
        if not contained_below(df, lh.index, lh.price, right_high_index - 1, atr_value):
            continue
        duration_days = right_high_index - lh.index
        if not (MIN_CUP_DAYS <= duration_days <= MAX_CUP_DAYS):
            continue
        if not _has_rounding_base(df, low_index, low_price, atr_value, lh.index, right_high_index):
            continue
        bottom_dry, bottom_evidence = bottom_volume_dry_up(
            df, lh.index, low_index, right_high_index, ROUNDING_WINDOW
        )
        if not bottom_dry:
            continue
        low_date = df.at[low_index, "Date"].strftime("%Y-%m-%d")
        right_high_date = df.at[right_high_index, "Date"].strftime("%Y-%m-%d")
        candidates.append(CupCandidate(
            left_high_index=lh.index, left_high_date=lh.date, left_high_price=lh.price,
            low_date=low_date, low_price=low_price,
            right_high_index=right_high_index, right_high_date=right_high_date,
            depth_pct=depth_pct, duration_days=duration_days,
            evidence=[
                uptrend_evidence,
                bottom_evidence,
                f"Cup declined {depth_pct:.1%} to {low_price:.2f} on {low_date}, basing near the low "
                f"before recovering to {lh.price:.2f} by {right_high_date} over {duration_days} trading days.",
            ],
        ))
    if not candidates:
        return None
    return max(candidates, key=lambda c: c.right_high_index)
