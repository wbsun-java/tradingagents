"""Pure detectors for the false-breakout state machine (SP2).

Pullback-low / rebound-high extremes, the post-breakdown no-new-low guard, the short
confirmation trigger, the long standard-tier upgrade, and volume expansion. No dependency
on chart_patterns (kept import-cycle free).
"""

from __future__ import annotations

import pandas as pd

from tradingagents.dataflows.false_break_types import VOLUME_MULTIPLE


def pullback_low(df: pd.DataFrame, breakout_index: int, reentry_index: int) -> float:
    """Lowest Low from the breakout bar through the re-entry bar (inclusive)."""
    return float(df["Low"].iloc[breakout_index : reentry_index + 1].min())


def rebound_high(df: pd.DataFrame, breakdown_index: int, reentry_index: int) -> float:
    """Highest High from the breakdown bar through the re-entry bar (inclusive)."""
    return float(df["High"].iloc[breakdown_index : reentry_index + 1].max())


def false_break_extreme(
    df: pd.DataFrame, breakout_index: int, reentry_index: int, direction: str
) -> float:
    """Furthest excursion outside the boundary during the false break."""
    window = df.iloc[breakout_index : reentry_index + 1]
    if direction == "bullish":
        return float(window["High"].max())
    return float(window["Low"].min())


def trough_index(df: pd.DataFrame, breakdown_index: int, reentry_index: int) -> int:
    """Absolute index of the lowest Low between breakdown and re-entry (inclusive)."""
    return int(df["Low"].iloc[breakdown_index : reentry_index + 1].idxmin())


def no_new_low_guard(
    df: pd.DataFrame, *, breakdown_index: int, reentry_index: int, grace_bars: int
) -> bool:
    """True when the post-breakdown trough is at least grace_bars before re-entry."""
    return trough_index(df, breakdown_index, reentry_index) <= reentry_index - grace_bars


def short_trigger_index(
    df: pd.DataFrame,
    *,
    reentry_index: int,
    boundary_price: float,
    pullback_low_price: float,
    buffer: float,
    confirm_window: int,
) -> int | None:
    """First bar in the window confirming the short: pullback-low break or failed retest."""
    end = min(len(df), reentry_index + 1 + confirm_window)
    for index in range(reentry_index + 1, end):
        close = float(df.at[index, "Close"])
        high = float(df.at[index, "High"])
        if close < pullback_low_price:
            return index
        if high >= boundary_price - buffer and close < boundary_price:
            return index
    return None


def long_upgrade_index(
    df: pd.DataFrame,
    *,
    reentry_index: int,
    boundary_price: float,
    rebound_high_price: float,
    buffer: float,
) -> int | None:
    """First bar upgrading the long to standard tier: rebound-high break or a held retest."""
    for index in range(reentry_index + 1, len(df)):
        close = float(df.at[index, "Close"])
        low = float(df.at[index, "Low"])
        if close > rebound_high_price:
            return index
        if low >= boundary_price - buffer and close >= boundary_price:
            return index
    return None


def volume_expanded(df: pd.DataFrame, index: int, multiple: float = VOLUME_MULTIPLE) -> bool:
    """Bar volume vs. the trailing 20-bar average (same mechanism as _volume_confirmation)."""
    if index < 1 or pd.isna(df.at[index, "Volume"]):
        return False
    start = max(0, index - 20)
    baseline = pd.to_numeric(df["Volume"].iloc[start:index], errors="coerce").mean()
    return bool(baseline and float(df.at[index, "Volume"]) >= float(baseline) * multiple)
