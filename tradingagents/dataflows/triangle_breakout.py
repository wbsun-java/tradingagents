"""Triangle trendline-breakout timing classification.

Delegates finite post-apex, apex-frozen-level, asymmetric-reversal rules to
``triangle_post_apex``; its calibration constants are interim SP4 placeholders.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from tradingagents.dataflows.triangle_post_apex import (
    find_post_apex_breakout,
    find_reversal_index,
    line_before_apex,
    line_value,
    post_apex_watch_evidence,
    post_apex_window_bars,
    timing_assessment,
)

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
    """Search for and classify a triangle trendline breakout near or after its apex."""
    real_end_index = len(df) - 1
    # Pre-apex search: only bars strictly before the trendline intersection.
    search_bound = min(len(df), max(formation_end + 1, math.ceil(apex_index)))

    breakout_index: int | None = None
    breakout_direction: PatternDirection | None = None
    for index in range(formation_end + 1, search_bound):
        upper = line_value(high_slope, high_intercept, index)
        lower = line_value(low_slope, low_intercept, index)
        close = float(df.at[index, "Close"])
        if close > upper + buffer:
            breakout_index, breakout_direction = index, "bullish"
            break
        if close < lower - buffer:
            breakout_index, breakout_direction = index, "bearish"
            break
    apex_price = line_value(high_slope, high_intercept, apex_index)
    window_bars = post_apex_window_bars(start_index, apex_index)
    window_last_index = math.ceil(apex_index) + window_bars - 1
    post_apex = False
    if breakout_index is None:
        hit = find_post_apex_breakout(
            df,
            formation_end=formation_end,
            apex_index=apex_index,
            apex_price=apex_price,
            buffer=buffer,
            window_bars=window_bars,
        )
        if hit is not None:
            breakout_index, breakout_direction = hit  # type: ignore[assignment]
            post_apex = True
    risk_flags: list[str] = []
    timing_evidence = "No confirmed trendline breakout yet."
    timing_adjustment = 0.0
    breakout_progress: float | None = None
    if breakout_index is not None:
        breakout_progress = (breakout_index - start_index) / (apex_index - start_index)
        timing_evidence, timing_adjustment, risk_flags = timing_assessment(
            breakout_progress, post_apex=post_apex
        )
    failure_index: int | None = None
    if breakout_index is not None and breakout_direction is not None:
        failure_index = find_reversal_index(
            df,
            high_slope=high_slope,
            high_intercept=high_intercept,
            low_slope=low_slope,
            low_intercept=low_intercept,
            apex_index=apex_index,
            breakout_index=breakout_index,
            breakout_direction=breakout_direction,
            risk_flags=risk_flags,
            buffer=buffer,
            window_bars=window_bars,
        )

    if failure_index is not None:
        status: PatternStatus = "failed"
        direction: PatternDirection = breakout_direction or bias
        signal_end_index = failure_index
        risk_flags.append("breakout_reversed_back_through_triangle")
    elif breakout_index is not None:
        status = "confirmed"
        direction = breakout_direction or bias
        signal_end_index = breakout_index
    elif real_end_index >= window_last_index:
        status = "failed"
        direction = bias
        signal_end_index = real_end_index
        risk_flags.append("triangle_expired_at_apex")
    elif real_end_index >= apex_index:
        status = "forming"
        direction = bias
        signal_end_index = real_end_index
        timing_evidence = post_apex_watch_evidence(window_bars)
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
        upper_level=line_before_apex(high_slope, high_intercept, level_index, apex_index),
        lower_level=line_before_apex(low_slope, low_intercept, level_index, apex_index),
        risk_flags=risk_flags,
        timing_evidence=timing_evidence,
        timing_adjustment=timing_adjustment,
    )
