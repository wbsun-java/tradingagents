"""Shared breakout confirmation for O'Neil base patterns.

Requires a close above the pivot buy point (the cup's left-side high) with
volume meaningfully above average within a short confirmation window, then
derives the forming/developing/confirmed/failed status and confidence score.
See ONEIL_CANSLIM_ANALYSIS_PLAN.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from tradingagents.dataflows.oneil_base_types import PatternType
from tradingagents.dataflows.oneil_cup import volume_ratio
from tradingagents.dataflows.oneil_handle import HandleCandidate

BREAKOUT_BUFFER_ATR = 0.1
BREAKOUT_VOLUME_RATIO = 1.4
BREAKOUT_CONFIRM_WINDOW = 3
Status = Literal["none", "forming", "developing", "confirmed", "failed"]
PATTERN_CONFIDENCE_BONUS: dict[PatternType, float] = {
    "high_tight_flag": 0.05,
    "cup_with_handle": 0.0,
    "double_bottom_base": -0.02,
    "ascending_base": -0.03,
    "flat_base": -0.04,
    "cup_without_handle": -0.05,
}
UNDERCUT_BONUS = 0.05
PREMATURE_CONTINUATION_PENALTY = 0.05


@dataclass
class BreakoutEvent:
    index: int
    date: str
    pivot_price: float
    close: float
    volume_ratio: float
    volume_confirmed: bool


def find_breakout(
    df: pd.DataFrame,
    pivot_price: float,
    search_start_index: int,
    atr_value: float,
) -> BreakoutEvent | None:
    """Find the first buffered breakout and its near-term volume confirmation."""
    buffer = atr_value * BREAKOUT_BUFFER_ATR
    if search_start_index >= len(df):
        return None
    first_break_idx = next(
        (
            i
            for i in range(search_start_index, len(df))
            if float(df.at[i, "Close"]) > pivot_price + buffer
        ),
        None,
    )
    if first_break_idx is None:
        return None
    confirm_end = min(len(df), first_break_idx + BREAKOUT_CONFIRM_WINDOW)
    confirming_idx = next(
        (i for i in range(first_break_idx, confirm_end)
         if (volume_ratio(df, i) or 0.0) >= BREAKOUT_VOLUME_RATIO
         and float(df.at[i, "Close"]) > pivot_price + buffer),
        None,
    )
    idx = confirming_idx if confirming_idx is not None else first_break_idx
    return BreakoutEvent(
        index=idx, date=df.at[idx, "Date"].strftime("%Y-%m-%d"),
        pivot_price=round(pivot_price, 4), close=round(float(df.at[idx, "Close"]), 4),
        volume_ratio=round(volume_ratio(df, idx) or 0.0, 2), volume_confirmed=confirming_idx is not None,
    )


def breakout_reversed(
    df: pd.DataFrame,
    breakout: BreakoutEvent,
    pivot_price: float,
    atr_value: float,
) -> bool:
    """Return whether a breakout subsequently closed back below its pivot buffer."""
    buffer = atr_value * BREAKOUT_BUFFER_ATR
    return any(
        float(df.at[i, "Close"]) < pivot_price - buffer
        for i in range(breakout.index + 1, len(df))
    )


def determine_status(
    *,
    complete: bool,
    handle: HandleCandidate | None,
    handle_required: bool,
    breakout: BreakoutEvent | None,
    reversed_after: bool,
    structure_broken: bool = False,
) -> Status:
    """Classify a complete base's handle and breakout progression."""
    if not complete:
        return "forming"
    if handle is not None and not handle.valid:
        return "failed"
    if structure_broken:
        return "failed"
    if handle is None and handle_required:
        return "forming"
    if breakout is None or not breakout.volume_confirmed:
        return "developing"
    if reversed_after:
        return "failed"
    return "confirmed"


def compute_confidence(
    pattern_type: PatternType,
    status: Status,
    handle: HandleCandidate | None,
    breakout: BreakoutEvent | None,
    rs_score: float | None,
    undercut: bool = False,
    continuation_state: str | None = None,
) -> float:
    """Score a live base from status, pattern quality, volume, and relative strength."""
    if status in ("none", "failed"):
        return 0.0
    base = {"forming": 0.2, "developing": 0.35, "confirmed": 0.5}[status]
    base += PATTERN_CONFIDENCE_BONUS[pattern_type]
    if undercut:
        base += UNDERCUT_BONUS
    if continuation_state == "premature_continuation":
        base -= PREMATURE_CONTINUATION_PENALTY
    if handle is not None and handle.valid and handle.volume_ratio_vs_cup is not None:
        base += max(0.0, min(0.15, (1.0 - handle.volume_ratio_vs_cup) * 0.3))
    if breakout is not None:
        base += max(0.0, min(0.2, (breakout.volume_ratio - 1.0) * 0.2))
    if rs_score is not None:
        base += max(0.0, min(0.1, rs_score * 0.1))
    return round(max(0.0, min(0.95, base)), 2)
