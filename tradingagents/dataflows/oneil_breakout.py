"""Breakout confirmation for O'Neil's cup-with-handle.

Requires a close above the pivot buy point (the cup's left-side high) with
volume meaningfully above average within a short confirmation window, then
derives the forming/developing/confirmed/failed status and confidence score.
See ONEIL_CANSLIM_ANALYSIS_PLAN.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from tradingagents.dataflows.oneil_cup import CupCandidate, volume_ratio
from tradingagents.dataflows.oneil_handle import HandleCandidate

BREAKOUT_BUFFER_ATR = 0.1
BREAKOUT_VOLUME_RATIO = 1.4
BREAKOUT_CONFIRM_WINDOW = 3
Status = Literal["none", "forming", "developing", "confirmed", "failed"]


@dataclass
class BreakoutEvent:
    index: int
    date: str
    pivot_price: float
    close: float
    volume_ratio: float
    volume_confirmed: bool


def find_breakout(df: pd.DataFrame, cup: CupCandidate, handle: HandleCandidate, atr_value: float) -> BreakoutEvent | None:
    buffer = atr_value * BREAKOUT_BUFFER_ATR
    start = handle.end_index + 1
    if start >= len(df):
        return None
    first_break_idx = next((i for i in range(start, len(df)) if float(df.at[i, "Close"]) > cup.left_high_price + buffer), None)
    if first_break_idx is None:
        return None
    confirm_end = min(len(df), first_break_idx + BREAKOUT_CONFIRM_WINDOW)
    confirming_idx = next(
        (i for i in range(first_break_idx, confirm_end)
         if (volume_ratio(df, i) or 0.0) >= BREAKOUT_VOLUME_RATIO and float(df.at[i, "Close"]) > cup.left_high_price + buffer),
        None,
    )
    idx = confirming_idx if confirming_idx is not None else first_break_idx
    return BreakoutEvent(
        index=idx, date=df.at[idx, "Date"].strftime("%Y-%m-%d"),
        pivot_price=round(cup.left_high_price, 4), close=round(float(df.at[idx, "Close"]), 4),
        volume_ratio=round(volume_ratio(df, idx) or 0.0, 2), volume_confirmed=confirming_idx is not None,
    )


def _reversal_after(df: pd.DataFrame, breakout: BreakoutEvent, cup: CupCandidate, atr_value: float) -> bool:
    buffer = atr_value * BREAKOUT_BUFFER_ATR
    return any(float(df.at[i, "Close"]) < cup.left_high_price - buffer for i in range(breakout.index + 1, len(df)))


def determine_status(cup: CupCandidate | None, handle: HandleCandidate | None, breakout: BreakoutEvent | None, df: pd.DataFrame, atr_value: float) -> Status:
    if cup is None:
        return "none"
    if handle is None:
        return "forming"
    if not handle.valid:
        return "failed"
    if breakout is None or not breakout.volume_confirmed:
        return "developing"
    if _reversal_after(df, breakout, cup, atr_value):
        return "failed"
    return "confirmed"


def compute_confidence(status: Status, handle: HandleCandidate | None, breakout: BreakoutEvent | None, rs_score: float | None) -> float:
    if status in ("none", "failed"):
        return 0.0
    base = {"forming": 0.2, "developing": 0.35, "confirmed": 0.5}[status]
    if handle is not None and handle.valid and handle.volume_ratio_vs_cup is not None:
        base += max(0.0, min(0.15, (1.0 - handle.volume_ratio_vs_cup) * 0.3))
    if breakout is not None:
        base += max(0.0, min(0.2, (breakout.volume_ratio - 1.0) * 0.2))
    if rs_score is not None:
        base += max(0.0, min(0.1, rs_score * 0.1))
    return round(min(0.95, base), 2)
