"""Triangle trendline-breakout timing classification.

Extracted out of ``chart_patterns._triangle_pattern`` (see
CHART_PATTERN_ANALYSIS_PLAN.md, "三角形整理") so the apex / post-apex timing
rules can evolve independently. Past the theoretical apex the two trendlines
have crossed and swapped position, so searching for breakouts against their
extrapolation indefinitely would produce meaningless levels; this module
bounds that search and classifies breakouts by proximity to the apex.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

PatternStatus = Literal["forming", "confirmed", "failed"]
PatternDirection = Literal["bullish", "bearish", "neutral"]

@dataclass
class TriangleBreakout:
    status: PatternStatus
    direction: PatternDirection
    breakout_index: int | None
    signal_end_index: int
    breakout_progress: float | None
    upper_level: float
    lower_level: float
    risk_flags: list[str] = field(default_factory=list)
    timing_evidence: str = "No confirmed trendline breakout yet."
    timing_adjustment: float = 0.0


def _line(slope: float, intercept: float, index: float) -> float:
    return slope * index + intercept


def _line_before_apex(slope: float, intercept: float, index: int, apex_index: float) -> float:
    """Evaluate a boundary without extrapolating beyond crossed trendlines."""
    return _line(slope, intercept, min(index, apex_index))


def classify_triangle_breakout(
    df: pd.DataFrame,
    *,
    high_slope: float,
    high_intercept: float,
    low_slope: float,
    low_intercept: float,
    start_index: int,
    formation_end: int,
    apex_index: float,
    bias: PatternDirection,
    buffer: float,
) -> TriangleBreakout:
    """Search for and classify a triangle trendline breakout near its apex."""
    real_end_index = len(df) - 1
    # A triangle ceases to exist at its theoretical apex. Search only bars
    # strictly before that intersection; later movement belongs to a new
    # structure and must never be labelled a confirmed triangle breakout.
    search_bound = min(len(df), max(formation_end + 1, math.ceil(apex_index)))

    breakout_index: int | None = None
    breakout_direction: PatternDirection | None = None
    for index in range(formation_end + 1, search_bound):
        upper = _line(high_slope, high_intercept, index)
        lower = _line(low_slope, low_intercept, index)
        close = float(df.at[index, "Close"])
        if close > upper + buffer:
            breakout_index, breakout_direction = index, "bullish"
            break
        if close < lower - buffer:
            breakout_index, breakout_direction = index, "bearish"
            break

    failure_index: int | None = None
    if breakout_index is not None and breakout_direction is not None:
        for index in range(breakout_index + 1, len(df)):
            # A valid pre-apex break can reverse after the apex. Freeze both
            # boundaries at their intersection instead of extrapolating lines
            # that have crossed and swapped meaning.
            upper = _line_before_apex(high_slope, high_intercept, index, apex_index)
            lower = _line_before_apex(low_slope, low_intercept, index, apex_index)
            close = float(df.at[index, "Close"])
            if breakout_direction == "bullish" and close < upper - buffer:
                failure_index = index
                break
            if breakout_direction == "bearish" and close > lower + buffer:
                failure_index = index
                break

    risk_flags: list[str] = []
    timing_evidence = "No confirmed trendline breakout yet."
    timing_adjustment = 0.0
    breakout_progress: float | None = None
    if breakout_index is not None:
        breakout_progress = (breakout_index - start_index) / (apex_index - start_index)
        timing_evidence = f"Breakout occurred at {breakout_progress:.1%} of the base-to-apex distance."
        if 0.55 <= breakout_progress <= 0.75:
            timing_evidence += " This is in the preferred zone around two-thirds."
            timing_adjustment = 0.1
        elif breakout_progress < 0.55:
            timing_evidence += " This is before the preferred zone; do not penalize it, but re-evaluate whether price is evolving into a different structure."
        elif breakout_progress > 0.85:
            timing_evidence += " This is a late apex breakout with elevated false-break risk."
            risk_flags.append("late_apex_breakout")
            timing_adjustment = -0.2 if breakout_progress <= 0.97 else -0.3
        else:
            timing_evidence += " Timing is acceptable but outside the preferred two-thirds zone."
            timing_adjustment = 0.02

    if failure_index is not None:
        status: PatternStatus = "failed"
        direction: PatternDirection = breakout_direction or bias
        signal_end_index = failure_index
        risk_flags.append("breakout_reversed_back_through_triangle")
    elif breakout_index is not None:
        status = "confirmed"
        direction = breakout_direction or bias
        signal_end_index = breakout_index
    elif real_end_index >= apex_index:
        status = "failed"
        direction = bias
        signal_end_index = real_end_index
        risk_flags.append("triangle_expired_at_apex")
    else:
        status = "forming"
        direction = bias
        signal_end_index = real_end_index

    level_index = breakout_index if breakout_index is not None else min(real_end_index, apex_index)

    return TriangleBreakout(
        status=status,
        direction=direction,
        breakout_index=breakout_index,
        signal_end_index=signal_end_index,
        breakout_progress=breakout_progress,
        upper_level=_line(high_slope, high_intercept, level_index),
        lower_level=_line(low_slope, low_intercept, level_index),
        risk_flags=risk_flags,
        timing_evidence=timing_evidence,
        timing_adjustment=timing_adjustment,
    )
