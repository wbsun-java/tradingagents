"""Level extraction + position predicates for the entry layer (SP3).

Duck-types the pattern object (no chart_patterns import → import-cycle free).
"""

from __future__ import annotations

import pandas as pd


def extract_levels(pattern, atr: float) -> dict[str, float] | None:
    """Return {bottom_boundary, breakout_level, failure_level} for a long-eligible pattern."""
    name = pattern.pattern
    lv = pattern.levels
    buffer = 0.2 * atr
    if name == "double_bottom":
        bottom = min(lv["first_extreme"], lv["second_extreme"])
        return {
            "bottom_boundary": bottom,
            "breakout_level": lv["neckline"],
            "failure_level": pattern.invalidation_price,
        }
    if name in ("ascending_triangle", "symmetrical_triangle"):
        bottom = lv["lower_trendline"]
        return {
            "bottom_boundary": bottom,
            "breakout_level": lv["upper_trendline"],
            "failure_level": bottom - buffer,
        }
    if name == "rectangle":
        bottom = lv["support"]
        return {
            "bottom_boundary": bottom,
            "breakout_level": lv["resistance"],
            "failure_level": bottom - buffer,
        }
    if name == "resistance_breakout":
        level = lv["broken_level"]
        return {
            "bottom_boundary": level,
            "breakout_level": level,
            "failure_level": pattern.invalidation_price,
        }
    return None


def near(value: float, target: float, tolerance: float) -> bool:
    return abs(value - target) <= tolerance


def retest_hold(df: pd.DataFrame, breakout_level: float, prox: float, window: int) -> bool:
    """A trailing bar dipped to the breakout level on below-average volume, price still above."""
    if float(df["Close"].iloc[-1]) < breakout_level:
        return False
    baseline = pd.to_numeric(df["Volume"].tail(20), errors="coerce").mean()
    start = max(1, len(df) - window)
    for index in range(start, len(df)):
        low = float(df.at[index, "Low"])
        volume = float(df.at[index, "Volume"])
        if breakout_level - prox <= low <= breakout_level + prox and (not baseline or volume < baseline):
            return True
    return False
