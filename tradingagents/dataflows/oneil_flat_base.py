"""Detection of peak-anchored O'Neil flat-base consolidations."""

from __future__ import annotations

import pandas as pd

from tradingagents.dataflows.chart_patterns import Pivot, find_pivots
from tradingagents.dataflows.oneil_base_types import BaseCandidate, prior_uptrend, volume_dry_up

FLAT_MIN_DAYS = 25
FLAT_FORMING_MIN_DAYS = 15
FLAT_MAX_DAYS = 120
FLAT_DEPTH_RATIO = 0.15
FLAT_DEPTH_ATR = 4.0
BREAKOUT_BUFFER_ATR = 0.1
FLAT_VOLUME_MAX_RATIO = 1.0


def _base_end(df: pd.DataFrame, peak: Pivot, atr_value: float) -> int:
    """Return the bar before the first buffered close above the fixed peak."""
    end = min(len(df) - 1, peak.index + FLAT_MAX_DAYS)
    breakout = peak.price + BREAKOUT_BUFFER_ATR * atr_value
    for index in range(peak.index + 1, end + 1):
        if float(df.at[index, "Close"]) > breakout:
            return index - 1
    return end


def detect_flat_base(df: pd.DataFrame, atr_value: float) -> BaseCandidate | None:
    """Return the highest qualifying, peak-anchored flat base."""
    peaks = [pivot for pivot in find_pivots(df) if pivot.kind == "high"]
    for peak in sorted(peaks, key=lambda pivot: (-pivot.price, pivot.index)):
        uptrend, uptrend_evidence = prior_uptrend(df, peak.index, atr_value)
        if not uptrend:
            continue
        end = _base_end(df, peak, atr_value)
        duration = end - peak.index + 1
        complete = duration >= FLAT_MIN_DAYS
        if duration < FLAT_FORMING_MIN_DAYS or (not complete and end != len(df) - 1):
            continue
        range_low = float(df["Low"].iloc[peak.index : end + 1].min())
        depth = (peak.price - range_low) / peak.price if peak.price else 0.0
        depth_limit = max(FLAT_DEPTH_RATIO, FLAT_DEPTH_ATR * atr_value / peak.price)
        if depth > depth_limit:
            continue
        volume_ratio, volume_evidence = volume_dry_up(df, peak.index, end)
        if volume_ratio is None or volume_ratio >= FLAT_VOLUME_MAX_RATIO:
            continue
        start_date = peak.date
        end_date = pd.Timestamp(df.at[end, "Date"]).strftime("%Y-%m-%d")
        return BaseCandidate(
            pattern_type="flat_base",
            complete=complete,
            pivot_price=peak.price,
            pivot_date=peak.date,
            complete_index=end,
            geometry={
                "start_date": start_date,
                "end_date": end_date,
                "range_high": peak.price,
                "range_low": range_low,
                "depth_pct": depth * 100,
                "duration_days": duration,
            },
            evidence=[
                f"Advance ended at the {peak.date} peak of {peak.price:.2f}; {uptrend_evidence}",
                f"Tight range from {start_date} at {peak.price:.2f} to {end_date} held "
                f"{depth:.1%} deep over {duration} trading days.",
                volume_evidence,
            ],
        )
    return None
