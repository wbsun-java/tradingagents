"""Handle detection for O'Neil's cup-with-handle pattern.

Finds the handle's earliest confirmed trough after a completed cup, requiring
it to stay in the cup's upper half and show lower volume than the cup itself
("volume dry-up"). See ONEIL_CANSLIM_ANALYSIS_PLAN.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from tradingagents.dataflows.chart_patterns import find_pivots
from tradingagents.dataflows.oneil_cup import CupCandidate

MIN_HANDLE_DAYS = 5
MAX_HANDLE_DAYS = 25


@dataclass
class HandleCandidate:
    start_date: str
    end_index: int
    end_date: str
    low_price: float
    high_index: int
    high_price: float
    volume_ratio_vs_cup: float | None
    duration_days: int
    valid: bool
    evidence: list[str] = field(default_factory=list)


def detect_handle(
    df: pd.DataFrame,
    cup: CupCandidate,
    atr_value: float,
    pivot_span: int = 3,
) -> HandleCandidate | None:
    """Find the handle's earliest confirmed trough after the cup completes.

    Uses the earliest confirmed swing-low pivot after the cup, not the lowest
    close in the whole search window -- a later, deeper dip (e.g. a failed
    breakout reversing hard after the handle already completed) must not be
    mistaken for the handle's own low.
    """
    start = cup.right_high_index + 1
    last = len(df) - 1
    if last < start:
        return None
    window_end = min(last, cup.right_high_index + MAX_HANDLE_DAYS)
    low_pivots = [
        p
        for p in find_pivots(df, pivot_span)
        if p.kind == "low" and start <= p.index <= window_end
    ]
    if not low_pivots:
        return None
    trough = min(low_pivots, key=lambda p: p.index)
    duration_days = trough.index - start + 1
    if duration_days < MIN_HANDLE_DAYS:
        return None

    window = df.iloc[start : trough.index + 1]
    cup_window = df.iloc[cup.left_high_index : cup.right_high_index + 1]
    cup_avg_vol = float(pd.to_numeric(cup_window["Volume"], errors="coerce").mean())
    handle_avg_vol = float(pd.to_numeric(window["Volume"], errors="coerce").mean())
    volume_ratio_vs_cup = handle_avg_vol / cup_avg_vol if cup_avg_vol else None
    midpoint = (cup.left_high_price + cup.low_price) / 2.0
    high_index = int(window["High"].idxmax())
    high_price = float(df.at[high_index, "High"])

    evidence: list[str] = []
    valid = True
    if trough.price < midpoint:
        valid = False
        evidence.append(
            f"Handle low of {trough.price:.2f} dropped into the cup's lower half "
            f"(below midpoint {midpoint:.2f}), invalidating the base."
        )
    if volume_ratio_vs_cup is not None and volume_ratio_vs_cup >= 1.0:
        valid = False
        evidence.append(
            f"Handle volume ({volume_ratio_vs_cup:.2f}x the cup's average) did not "
            "dry up relative to the cup."
        )
    if duration_days >= cup.duration_days:
        valid = False
        evidence.append(
            f"Handle duration of {duration_days} days is not shorter than the "
            f"{cup.duration_days}-day cup."
        )
    split = (len(window) + 1) // 2
    first_half_close = float(window["Close"].iloc[:split].mean())
    second_half_close = float(window["Close"].iloc[split:].mean())
    if second_half_close > first_half_close:
        valid = False
        evidence.append(
            f"Handle drifted upward: second-half mean close {second_half_close:.2f} "
            f"exceeded first-half mean close {first_half_close:.2f}."
        )
    if valid:
        evidence.append(
            f"Handle formed in the cup's upper half (low {trough.price:.2f} above "
            f"midpoint {midpoint:.2f}) on {volume_ratio_vs_cup:.2f}x the cup's "
            f"volume over {duration_days} days."
        )
    return HandleCandidate(
        start_date=df.at[start, "Date"].strftime("%Y-%m-%d"),
        end_index=trough.index,
        end_date=trough.date,
        low_price=trough.price,
        high_index=high_index,
        high_price=high_price,
        volume_ratio_vs_cup=volume_ratio_vs_cup,
        duration_days=duration_days,
        valid=valid,
        evidence=evidence,
    )
