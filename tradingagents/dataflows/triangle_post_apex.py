"""Post-apex triangle breakout rules (SP1).

Once a triangle's trendlines cross at the theoretical apex the pattern no
longer exists geometrically, but a breakout can still print shortly after the
crossing. This module owns that regime: the finite post-apex search window,
the apex-frozen boundary helpers, the breakout-timing assessment, and the
asymmetric (lower-threshold) reversal detection for late/post-apex breakouts.
Every constant here is an interim placeholder pending SP4 backtest calibration
(docs/superpowers/specs/2026-07-11-post-apex-breakout-design.md).
"""

from __future__ import annotations

import math

import pandas as pd

POST_APEX_WINDOW_FRACTION = 0.15
POST_APEX_WINDOW_MIN_BARS = 3
POST_APEX_WINDOW_MAX_BARS = 10
POST_APEX_TIMING_ADJUSTMENT = -0.4
REVERSAL_BUFFER_FRACTION = 0.5
ASYMMETRIC_REVERSAL_FLAGS = frozenset({"late_apex_breakout", "post_apex_breakout"})


def line_value(slope: float, intercept: float, index: float) -> float:
    return slope * index + intercept


def line_before_apex(slope: float, intercept: float, index: float, apex_index: float) -> float:
    """Evaluate a boundary without extrapolating beyond crossed trendlines."""
    return line_value(slope, intercept, min(index, apex_index))


def post_apex_window_bars(start_index: int, apex_index: float) -> int:
    """Finite bars after the apex in which a breakout may still be recognized."""
    scaled = round(POST_APEX_WINDOW_FRACTION * (apex_index - start_index))
    return int(min(POST_APEX_WINDOW_MAX_BARS, max(POST_APEX_WINDOW_MIN_BARS, scaled)))


def find_post_apex_breakout(
    df: pd.DataFrame,
    *,
    formation_end: int,
    apex_index: float,
    apex_price: float,
    buffer: float,
    window_bars: int,
) -> tuple[int, str] | None:
    """Search the finite post-apex window for a buffered close beyond the apex price."""
    begin = max(formation_end + 1, math.ceil(apex_index))
    end = min(len(df), math.ceil(apex_index) + window_bars)
    for index in range(begin, end):
        close = float(df.at[index, "Close"])
        if close > apex_price + buffer:
            return index, "bullish"
        if close < apex_price - buffer:
            return index, "bearish"
    return None


def find_reversal_index(
    df: pd.DataFrame,
    *,
    high_slope: float,
    high_intercept: float,
    low_slope: float,
    low_intercept: float,
    apex_index: float,
    breakout_index: int,
    breakout_direction: str,
    risk_flags: list[str],
    buffer: float,
    window_bars: int,
) -> int | None:
    """Find the bar where a confirmed breakout reverses back through the boundary.

    Late/post-apex breakouts reverse at half buffer inside the reversal window
    (reversal is their default expectation); the standard full-buffer check
    continues unbounded afterwards.
    """
    asymmetric = bool(ASYMMETRIC_REVERSAL_FLAGS & set(risk_flags))
    for index in range(breakout_index + 1, len(df)):
        upper = line_before_apex(high_slope, high_intercept, index, apex_index)
        lower = line_before_apex(low_slope, low_intercept, index, apex_index)
        close = float(df.at[index, "Close"])
        effective = buffer
        if asymmetric and index <= breakout_index + window_bars:
            effective = buffer * REVERSAL_BUFFER_FRACTION
        if breakout_direction == "bullish" and close < upper - effective:
            return index
        if breakout_direction == "bearish" and close > lower + effective:
            return index
    return None


def timing_assessment(breakout_progress: float, *, post_apex: bool) -> tuple[str, float, list[str]]:
    """Evidence text, confidence adjustment, and risk flags for a breakout's timing."""
    evidence = f"Breakout occurred at {breakout_progress:.1%} of the base-to-apex distance."
    if post_apex:
        evidence += (
            " The triangle is already past its theoretical apex, so this breakout is"
            " more likely a false break, with elevated odds of being pushed back inside"
            " the former triangle within a few sessions."
        )
        return evidence, POST_APEX_TIMING_ADJUSTMENT, ["post_apex_breakout"]
    if 0.55 <= breakout_progress <= 0.75:
        return evidence + " This is in the preferred zone around two-thirds.", 0.1, []
    if breakout_progress < 0.55:
        return (
            evidence + " This is before the preferred zone; do not penalize it, but"
            " re-evaluate whether price is evolving into a different structure.",
            0.0,
            [],
        )
    if breakout_progress > 0.85:
        return (
            evidence + " This is a late apex breakout with elevated false-break risk.",
            -0.2 if breakout_progress <= 0.97 else -0.3,
            ["late_apex_breakout"],
        )
    return (
        evidence + " Timing is acceptable but outside the preferred two-thirds zone.",
        0.02,
        [],
    )


def post_apex_watch_evidence(window_bars: int) -> str:
    return (
        "No confirmed trendline breakout yet; the triangle has passed its theoretical"
        f" apex and only a finite {window_bars}-bar post-apex window is being watched"
        " before the pattern expires."
    )
