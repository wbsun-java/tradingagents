"""O'Neil double-bottom (W) base detection."""

from __future__ import annotations

import pandas as pd

from tradingagents.dataflows.chart_patterns import Pivot, find_pivots
from tradingagents.dataflows.oneil_base_types import (
    BaseCandidate,
    contained_below,
    prior_uptrend,
    volume_dry_up,
)
from tradingagents.dataflows.oneil_double_bottom_rules import (
    DB_EQUAL_LOW_ATR,
    DB_MAX_UNDERCUT_ATR,
    DB_MAX_UNDERCUT_RATIO,
    DB_UNDERCUT_MAX_BARS,
    classify_second_low,
    halves_are_valid,
    leg_volume_declines,
    right_side_volume_evidence,
    undercut_is_valid,
)

__all__ = ["DB_EQUAL_LOW_ATR", "DB_MAX_UNDERCUT_ATR", "DB_MAX_UNDERCUT_RATIO", "DB_UNDERCUT_MAX_BARS", "detect_double_bottom"]

DB_MIN_BASE_DURATION = 35
DB_MAX_BASE_DURATION = 325
DB_LOW_TOLERANCE_ATR = DB_EQUAL_LOW_ATR
DB_MIN_DEPTH = 0.15
DB_MAX_DEPTH = 0.50
DB_MIN_DEPTH_ATR = 3.0
DB_VOLUME_MAX_RATIO = 1.0

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
        volume_ok, volume_evidence = leg_volume_declines(df, peak.index, first.index)
        if not volume_ok:
            continue
        for middle in sorted(
            (p for p in highs if p.index > first.index),
            key=lambda pivot: (pivot.index, -pivot.price),
        ):
            later_lows = [p for p in lows if p.index > middle.index]
            if not later_lows:
                continue
            second = min(later_lows, key=lambda pivot: (pivot.price, pivot.index))
            if not _is_window_low(df, first, peak.index + 1, middle.index, tolerance):
                continue
            if not _is_window_low(df, second, middle.index + 1, len(df) - 1, tolerance):
                continue
            if second.price < first.price and not undercut_is_valid(
                df, first, second, atr_value
            ):
                continue
            if not halves_are_valid(peak, first, middle, second):
                continue
            base_low = min(first.price, second.price)
            depth = peak.price - base_low
            depth_pct = depth / peak.price if peak.price else 0.0
            if depth < DB_MIN_DEPTH_ATR * atr_value:
                continue
            if not DB_MIN_DEPTH <= depth_pct <= DB_MAX_DEPTH:
                continue
            if not contained_below(df, peak.index, peak.price, second.index, atr_value):
                continue
            volume_ratio, _ = volume_dry_up(df, first.index, second.index)
            if volume_ratio is None or volume_ratio >= DB_VOLUME_MAX_RATIO:
                continue
            return first, middle, second, volume_evidence
    return None


def detect_double_bottom(df: pd.DataFrame, atr_value: float) -> BaseCandidate | None:
    """Return the highest qualifying complete W base."""
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
        behavior, low_evidence = classify_second_low(first, second, atr_value)
        if second.price < first.price and not undercut_is_valid(
            df, first, second, atr_value
        ):
            continue
        if not halves_are_valid(peak, first, middle, second):
            continue
        base_low_price = min(first.price, second.price)
        depth = peak.price - base_low_price
        depth_pct = depth / peak.price if peak.price else 0.0
        if depth < DB_MIN_DEPTH_ATR * atr_value or not DB_MIN_DEPTH <= depth_pct <= DB_MAX_DEPTH:
            continue
        volume_ratio, volume_evidence = volume_dry_up(df, first.index, second.index)
        if volume_ratio is None or volume_ratio >= DB_VOLUME_MAX_RATIO:
            continue
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
                "second_low_behavior": behavior,
            },
            evidence=[
                uptrend_evidence,
                f"Leg one declined from {peak.date} at {peak.price:.2f} to {first.date} at {first.price:.2f}; {leg_volume_evidence}",
                low_evidence,
                f"From {first.date} at {first.price:.2f} through {second.date} at {second.price:.2f}, {volume_evidence}",
                right_side_volume_evidence(df, second),
                f"The base declined {depth_pct:.1%} from {peak.date} at {peak.price:.2f} to its {base_low_price:.2f} low.",
            ],
            undercut=behavior == "undercut",
            start_index=peak.index,
            base_low_price=base_low_price,
        )
    return None
