"""Detection of O'Neil cups whose right side is still forming."""

from __future__ import annotations

import pandas as pd

from tradingagents.dataflows.chart_patterns import find_pivots
from tradingagents.dataflows.oneil_base_types import BaseCandidate, contained_below, prior_uptrend
from tradingagents.dataflows.oneil_cup import (
    MAX_CUP_DAYS,
    MAX_DEPTH_PCT,
    MIN_CUP_DAYS,
    MIN_DEPTH_ATR,
    MIN_DEPTH_PCT,
    RECOVERY_BUFFER_ATR,
    ROUNDING_WINDOW,
    _has_rounding_base,
)
from tradingagents.dataflows.oneil_cup_quality import bottom_volume_dry_up

FORMING_MIN_RETRACE = 0.25


def detect_forming_cup(df: pd.DataFrame, atr_value: float) -> BaseCandidate | None:
    """Return the highest qualifying cup that has not yet regained its rim."""
    last_index = len(df) - 1
    rims = [
        pivot for pivot in find_pivots(df)
        if pivot.kind == "high"
        and contained_below(df, pivot.index, pivot.price, last_index, atr_value)
    ]
    for lh in sorted(rims, key=lambda pivot: (-pivot.price, pivot.index)):
        has_uptrend, uptrend_evidence = prior_uptrend(df, lh.index, atr_value)
        if not has_uptrend:
            continue
        duration_days = last_index - lh.index
        if not MIN_CUP_DAYS <= duration_days <= MAX_CUP_DAYS:
            continue
        lows = df.iloc[lh.index + 1 :]
        if lows.empty:
            continue
        low_index = int(lows["Low"].idxmin())
        low_price = float(df.at[low_index, "Low"])
        depth_abs = lh.price - low_price
        depth_pct = depth_abs / lh.price if lh.price else 0.0
        if depth_abs < MIN_DEPTH_ATR * atr_value or not MIN_DEPTH_PCT <= depth_pct <= MAX_DEPTH_PCT:
            continue
        if not _has_rounding_base(df, low_index, low_price, atr_value, lh.index, last_index):
            continue
        bottom_dry, bottom_evidence = bottom_volume_dry_up(
            df, lh.index, low_index, last_index, ROUNDING_WINDOW
        )
        if not bottom_dry:
            continue
        last_close = float(df.at[last_index, "Close"])
        retrace_pct = (last_close - low_price) / depth_abs if depth_abs else 0.0
        if retrace_pct < FORMING_MIN_RETRACE or last_close >= lh.price - RECOVERY_BUFFER_ATR * atr_value:
            continue
        low_date = pd.Timestamp(df.at[low_index, "Date"]).strftime("%Y-%m-%d")
        last_date = pd.Timestamp(df.at[last_index, "Date"]).strftime("%Y-%m-%d")
        return BaseCandidate(
            pattern_type="cup_without_handle",
            complete=False,
            pivot_price=lh.price,
            pivot_date=lh.date,
            complete_index=last_index,
            geometry={
                "start_date": lh.date,
                "left_high": lh.price,
                "low_date": low_date,
                "low_price": low_price,
                "depth_pct": depth_pct * 100,
                "retrace_pct": retrace_pct * 100,
                "duration_days": duration_days,
            },
            evidence=[
                uptrend_evidence,
                bottom_evidence,
                f"Cup declined {depth_pct:.1%} to {low_price:.2f} on {low_date}.",
                f"Recovery is in progress at {retrace_pct:.1%} retraced by {last_date} close of {last_close:.2f}.",
            ],
            start_index=lh.index,
            base_low_price=low_price,
        )
    return None
