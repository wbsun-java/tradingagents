"""Double-bottom base detection for O'Neil-style bases."""

from __future__ import annotations

import pandas as pd

from tradingagents.dataflows.chart_patterns import Pivot, find_pivots
from tradingagents.dataflows.oneil_base_types import BaseCandidate, prior_uptrend, volume_dry_up

DB_MIN_DAYS = 35
DB_MAX_DAYS = 120
DB_PEAK_MIN_ATR = 1.25
DB_PEAK_MIN_RATIO = 0.02
DB_UNDERCUT_ATR = 1.5
DB_UNDERCUT_RATIO = 0.03
DB_HIGHER_LOW_ATR = 1.0
DB_HIGHER_LOW_RATIO = 0.02
DB_EQUAL_LOW_ATR = 0.25
DB_VOLUME_MAX_RATIO = 1.0


def _middle_peak(df: pd.DataFrame, first: Pivot, second: Pivot) -> tuple[int, float]:
    """Return the highest high strictly between the two confirmed lows."""
    middle = df.iloc[first.index + 1 : second.index]
    index = int(middle["High"].idxmax())
    return index, float(df.at[index, "High"])


def _second_low_behavior(first: Pivot, second: Pivot, atr_value: float) -> tuple[str, bool, str]:
    difference = second.price - first.price
    if difference < -DB_EQUAL_LOW_ATR * atr_value:
        return (
            "undercut",
            True,
            f"The second low ({second.date} at {second.price:.2f}) undercut the first low "
            f"({first.date} at {first.price:.2f}) in a shakeout.",
        )
    if difference > DB_EQUAL_LOW_ATR * atr_value:
        return (
            "higher",
            False,
            f"The second low ({second.date} at {second.price:.2f}) held above the first low "
            f"({first.date} at {first.price:.2f}).",
        )
    return (
        "equal",
        False,
        f"The second low ({second.date} at {second.price:.2f}) matched the first low "
        f"({first.date} at {first.price:.2f}).",
    )


def detect_double_bottom(df: pd.DataFrame, atr_value: float) -> BaseCandidate | None:
    """Return the latest complete W base that meets O'Neil-style constraints."""
    lows = [pivot for pivot in find_pivots(df) if pivot.kind == "low"]
    pairs = [
        (first, second)
        for first_index, first in enumerate(lows)
        for second in lows[first_index + 1 :]
        if DB_MIN_DAYS <= second.index - first.index <= DB_MAX_DAYS
    ]
    if not pairs:
        return None
    first, second = max(pairs, key=lambda pair: (pair[1].index, pair[0].index))
    uptrend, uptrend_evidence = prior_uptrend(df, first.index, atr_value)
    if not uptrend:
        return None
    peak_index, peak_price = _middle_peak(df, first, second)
    average_low = (first.price + second.price) / 2
    required_rise = max(DB_PEAK_MIN_ATR * atr_value, DB_PEAK_MIN_RATIO * average_low)
    if peak_price - max(first.price, second.price) < required_rise:
        return None
    lower_bound = first.price - max(DB_UNDERCUT_ATR * atr_value, DB_UNDERCUT_RATIO * first.price)
    upper_bound = first.price + max(DB_HIGHER_LOW_ATR * atr_value, DB_HIGHER_LOW_RATIO * first.price)
    if not lower_bound <= second.price <= upper_bound:
        return None
    volume_ratio, volume_evidence = volume_dry_up(df, first.index, second.index)
    if volume_ratio is None or volume_ratio >= DB_VOLUME_MAX_RATIO:
        return None
    behavior, undercut, behavior_evidence = _second_low_behavior(first, second, atr_value)
    peak_date = pd.Timestamp(df.at[peak_index, "Date"]).strftime("%Y-%m-%d")
    duration = second.index - first.index
    return BaseCandidate(
        pattern_type="double_bottom_base",
        complete=True,
        pivot_price=peak_price,
        pivot_date=peak_date,
        complete_index=second.index,
        geometry={
            "first_low": {"date": first.date, "price": first.price},
            "second_low": {"date": second.date, "price": second.price},
            "middle_peak": {"date": peak_date, "price": peak_price},
            "second_low_behavior": behavior,
            "duration_days": duration,
        },
        evidence=[uptrend_evidence, volume_evidence, behavior_evidence],
        undercut=undercut,
    )
