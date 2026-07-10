"""Strict O'Neil double-bottom (W) base detection."""

from __future__ import annotations

import pandas as pd

from tradingagents.dataflows.chart_patterns import Pivot, find_pivots
from tradingagents.dataflows.oneil_base_types import (
    BaseCandidate,
    contained_below,
    prior_uptrend,
    volume_dry_up,
)

DB_MIN_BASE_DURATION = 35
DB_MAX_BASE_DURATION = 325
DB_LEG_VOLUME_DECLINE_RATIO = 1.0
DB_LOW_TOLERANCE_ATR = 0.25
DB_MIN_DEPTH = 0.20
DB_MAX_DEPTH = 0.50
DB_MIN_DEPTH_ATR = 3.0
DB_VOLUME_MAX_RATIO = 1.0


def _leg_volume_declines(df: pd.DataFrame, start: int, end: int) -> tuple[bool, str]:
    leg = pd.to_numeric(df["Volume"].iloc[start : end + 1], errors="coerce")
    third = len(leg) // 3
    if not third:
        return False, "Leg-one volume trend is unavailable because the leg is too short."
    first_mean = leg.iloc[:third].mean()
    final_mean = leg.iloc[-third:].mean()
    ratio = final_mean / first_mean if first_mean and pd.notna(first_mean) else float("nan")
    qualifies = pd.notna(ratio) and ratio < DB_LEG_VOLUME_DECLINE_RATIO
    return bool(qualifies), f"Leg-one volume declined to {ratio:.2f}x its opening-third average."


def _is_window_low(df: pd.DataFrame, pivot: Pivot, start: int, end: int, tolerance: float) -> bool:
    low = pd.to_numeric(df["Low"].iloc[start : end + 1], errors="coerce").min()
    return bool(pd.notna(low) and abs(pivot.price - float(low)) <= tolerance)


def _structure(
    df: pd.DataFrame, peak: Pivot, pivots: list[Pivot], atr_value: float
) -> tuple[Pivot, Pivot, Pivot, str] | None:
    lows = [pivot for pivot in pivots if pivot.kind == "low" and pivot.index > peak.index]
    highs = [pivot for pivot in pivots if pivot.kind == "high"]
    tolerance = DB_LOW_TOLERANCE_ATR * atr_value
    for first in lows:
        volume_ok, volume_evidence = _leg_volume_declines(df, peak.index, first.index)
        if not volume_ok:
            continue
        for second in lows:
            if second.index <= first.index:
                continue
            middle_highs = [p for p in highs if first.index < p.index < second.index]
            if not middle_highs:
                continue
            middle = max(middle_highs, key=lambda pivot: (pivot.price, -pivot.index))
            later_lows = [p for p in lows if p.index > middle.index]
            if not later_lows or second != min(later_lows, key=lambda pivot: (pivot.price, pivot.index)):
                continue
            if middle.price >= peak.price or second.price >= first.price:
                continue
            if not _is_window_low(df, first, peak.index + 1, middle.index, tolerance):
                continue
            if not _is_window_low(df, second, peak.index + 1, len(df) - 1, tolerance):
                continue
            return first, middle, second, volume_evidence
    return None


def detect_double_bottom(df: pd.DataFrame, atr_value: float) -> BaseCandidate | None:
    """Return the highest qualifying complete strict-under-cut W base."""
    pivots = find_pivots(df)
    last_index = len(df) - 1
    peaks = [pivot for pivot in pivots if pivot.kind == "high"]
    for peak in sorted(peaks, key=lambda pivot: (-pivot.price, pivot.index)):
        uptrend, uptrend_evidence = prior_uptrend(df, peak.index, atr_value)
        duration = last_index - peak.index
        if not uptrend or not DB_MIN_BASE_DURATION <= duration <= DB_MAX_BASE_DURATION:
            continue
        structure = _structure(df, peak, pivots, atr_value)
        if structure is None:
            continue
        first, middle, second, leg_volume_evidence = structure
        if not contained_below(df, peak.index, peak.price, second.index, atr_value):
            continue
        depth = peak.price - second.price
        depth_pct = depth / peak.price if peak.price else 0.0
        if depth < DB_MIN_DEPTH_ATR * atr_value or not DB_MIN_DEPTH <= depth_pct <= DB_MAX_DEPTH:
            continue
        volume_ratio, volume_evidence = volume_dry_up(df, first.index, second.index)
        if volume_ratio is None or volume_ratio >= DB_VOLUME_MAX_RATIO:
            continue
        shakeout = (
            f"The second low ({second.date} at {second.price:.2f}) undercut the first low "
            f"({first.date} at {first.price:.2f}) in a shakeout."
        )
        return BaseCandidate(
            pattern_type="double_bottom_base",
            complete=True,
            pivot_price=middle.price,
            pivot_date=middle.date,
            complete_index=second.index,
            geometry={
                "base_start": {"date": peak.date, "price": peak.price},
                "first_low": {"date": first.date, "price": first.price},
                "middle_peak": {"date": middle.date, "price": middle.price},
                "second_low": {"date": second.date, "price": second.price},
                "depth_pct": depth_pct * 100,
                "duration_days": duration,
                "second_low_behavior": "undercut",
            },
            evidence=[
                uptrend_evidence,
                f"Leg one declined from {peak.date} at {peak.price:.2f} to {first.date} at {first.price:.2f}; {leg_volume_evidence}",
                shakeout,
                f"From {first.date} at {first.price:.2f} through {second.date} at {second.price:.2f}, {volume_evidence}",
                f"The base declined {depth_pct:.1%} from {peak.date} at {peak.price:.2f} to {second.date} at {second.price:.2f}.",
            ],
            undercut=True,
        )
    return None
