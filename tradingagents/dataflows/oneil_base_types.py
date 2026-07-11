"""Shared candidate types and validation helpers for O'Neil base patterns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import pandas as pd

from tradingagents.dataflows.chart_patterns import Pivot, find_pivots

if TYPE_CHECKING:
    from tradingagents.dataflows.oneil_handle import HandleCandidate

PatternType = Literal[
    "cup_with_handle",
    "cup_without_handle",
    "flat_base",
    "double_bottom_base",
    "ascending_base",
    "high_tight_flag",
]

PRIOR_UPTREND_MIN_GAIN_RATIO = 0.3
PRIOR_UPTREND_MIN_GAIN_ATR = 6.0
PRIOR_UPTREND_MIN_BARS = 30
VOLUME_BASELINE_BARS = 20
START_CONTAINMENT_TOLERANCE_ATR = 0.25
BASE_MAX_AGE_DAYS = 325


@dataclass
class BaseCandidate:
    """A detected base before shared breakout evaluation."""

    pattern_type: PatternType
    complete: bool
    pivot_price: float
    pivot_date: str
    complete_index: int
    geometry: dict[str, Any]
    evidence: list[str]
    handle: HandleCandidate | None = None
    undercut: bool = False
    continuation_state: str | None = None
    start_index: int | None = None
    base_low_price: float | None = None


def starting_peak(df: pd.DataFrame, before_index: int) -> Pivot | None:
    """Return the last settled pivot high strictly before ``before_index``."""
    highs = (pivot for pivot in find_pivots(df) if pivot.kind == "high" and pivot.index < before_index)
    return max(highs, key=lambda pivot: pivot.index, default=None)


def contained_below(
    df: pd.DataFrame,
    peak_index: int,
    peak_price: float,
    end_index: int,
    atr_value: float,
) -> bool:
    """Return whether the interior remains below the starting peak tolerance."""
    interior_high = df["High"].iloc[peak_index + 1 : end_index + 1].max()
    ceiling = peak_price + START_CONTAINMENT_TOLERANCE_ATR * atr_value
    return bool(pd.isna(interior_high) or float(interior_high) <= ceiling)


def prior_uptrend(df: pd.DataFrame, start_index: int, atr_value: float) -> tuple[bool, str]:
    """Assess whether a base began after a meaningful advance."""
    if start_index < PRIOR_UPTREND_MIN_BARS:
        return False, (
            f"Prior uptrend unavailable: only {start_index} bars precede the base, "
            f"below the required {PRIOR_UPTREND_MIN_BARS}."
        )

    window = df.iloc[max(0, start_index - 120) : start_index]
    low_index = int(window["Close"].idxmin())
    low_close = float(df.at[low_index, "Close"])
    start_close = float(df.at[start_index, "Close"])
    gain = start_close - low_close
    gain_pct = gain / low_close * 100 if low_close else 0.0
    required_gain = max(
        PRIOR_UPTREND_MIN_GAIN_RATIO * low_close,
        PRIOR_UPTREND_MIN_GAIN_ATR * atr_value,
    )
    low_date = pd.Timestamp(df.at[low_index, "Date"]).strftime("%Y-%m-%d")
    qualifies = gain >= required_gain
    outcome = "qualifies" if qualifies else "does not qualify"
    return qualifies, (
        f"Prior advance from the {low_date} low of {low_close:.2f} to "
        f"{start_close:.2f} gained {gain_pct:.1f}% and {outcome} as an uptrend."
    )


def volume_dry_up(df: pd.DataFrame, base_start: int, base_end: int) -> tuple[float | None, str]:
    """Compare inclusive base volume with the preceding 20-bar baseline."""
    if base_start < VOLUME_BASELINE_BARS:
        return None, (
            f"Volume comparison unavailable: only {base_start} bars precede the base, "
            f"below the required {VOLUME_BASELINE_BARS}."
        )

    prior_mean = pd.to_numeric(
        df["Volume"].iloc[base_start - VOLUME_BASELINE_BARS : base_start], errors="coerce"
    ).mean()
    base_mean = pd.to_numeric(df["Volume"].iloc[base_start : base_end + 1], errors="coerce").mean()
    if not prior_mean or pd.isna(prior_mean) or pd.isna(base_mean):
        return None, "Volume comparison unavailable because the prior baseline has no usable mean."
    ratio = float(base_mean / prior_mean)
    if ratio < 1:
        behavior = "contracted"
    elif ratio > 1:
        behavior = "expanded"
    else:
        behavior = "was unchanged (neither contracted nor expanded)"
    return ratio, f"Base volume {behavior} to {ratio:.2f}x the preceding 20-bar average."
