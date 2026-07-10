"""Geometry and evidence rules for O'Neil double-bottom bases."""

from __future__ import annotations

import pandas as pd

from tradingagents.dataflows.chart_patterns import Pivot

DB_EQUAL_LOW_ATR = 0.25
DB_MAX_UNDERCUT_RATIO = 0.03
DB_MAX_UNDERCUT_ATR = 1.5
DB_UNDERCUT_MAX_BARS = 10
DB_LEG_VOLUME_DECLINE_RATIO = 1.0


def leg_volume_declines(df: pd.DataFrame, start: int, end: int) -> tuple[bool, str]:
    """Test whether volume declines across the first leg."""
    leg = pd.to_numeric(df["Volume"].iloc[start : end + 1], errors="coerce")
    third = len(leg) // 3
    if not third:
        return False, "Leg-one volume trend is unavailable because the leg is too short."
    first_mean = leg.iloc[:third].mean()
    final_mean = leg.iloc[-third:].mean()
    ratio = final_mean / first_mean if first_mean and pd.notna(first_mean) else float("nan")
    qualifies = pd.notna(ratio) and ratio < DB_LEG_VOLUME_DECLINE_RATIO
    return bool(qualifies), f"Leg-one volume declined to {ratio:.2f}x its opening-third average."


def classify_second_low(first: Pivot, second: Pivot, atr_value: float) -> tuple[str, str]:
    """Classify and narrate the second foot relative to the first."""
    dead_zone = DB_EQUAL_LOW_ATR * atr_value
    if second.price < first.price - dead_zone:
        behavior = "undercut"
        detail = "briefly undercut the first low in a shakeout"
    elif second.price > first.price + dead_zone:
        behavior = "higher"
        detail = "held above the first low, signaling aggressive institutional accumulation"
    else:
        behavior = "equal"
        detail = "matched the first low as the floor was retested and held"
    evidence = (
        f"The second low ({second.date} at {second.price:.2f}) {detail} "
        f"({first.date} at {first.price:.2f})."
    )
    return behavior, evidence


def undercut_is_valid(
    df: pd.DataFrame, first: Pivot, second: Pivot, atr_value: float
) -> bool:
    """Require a shallow undercut and a close above L1 within ten bars."""
    tail_limit = max(DB_MAX_UNDERCUT_RATIO * first.price, DB_MAX_UNDERCUT_ATR * atr_value)
    if first.price - second.price > tail_limit:
        return False
    reclaim = pd.to_numeric(
        df["Close"].iloc[second.index + 1 : second.index + 1 + DB_UNDERCUT_MAX_BARS],
        errors="coerce",
    )
    return bool((reclaim > first.price).any())


def halves_are_valid(peak: Pivot, first: Pivot, middle: Pivot, second: Pivot) -> bool:
    """Require the W's middle in the upper half and both feet in the lower half."""
    base_low = min(first.price, second.price)
    base_mid = peak.price - 0.5 * (peak.price - base_low)
    return bool(
        middle.price < peak.price
        and middle.price >= base_mid
        and first.price < base_mid
        and second.price < base_mid
    )


def right_side_volume_evidence(df: pd.DataFrame, second: Pivot) -> str:
    """Narrate up-close versus down-close volume after the second foot."""
    segment = df.iloc[second.index + 1 :].copy()
    if segment.empty:
        return "Right-side up/down-day volume is unavailable after the second low."
    prior_close = pd.to_numeric(df["Close"], errors="coerce").shift().loc[segment.index]
    close = pd.to_numeric(segment["Close"], errors="coerce")
    volume = pd.to_numeric(segment["Volume"], errors="coerce")
    up_mean = volume[close > prior_close].mean()
    down_mean = volume[close < prior_close].mean()
    start_date = pd.Timestamp(segment["Date"].iloc[0]).date()
    end_date = pd.Timestamp(segment["Date"].iloc[-1]).date()
    if pd.isna(up_mean) or pd.isna(down_mean) or down_mean <= 0:
        return f"Right-side up/down-day volume from {start_date} to {end_date} is unavailable."
    ratio = up_mean / down_mean
    reading = "up-days dominate (accumulation)" if ratio > 1 else "up-days do not dominate (drift)"
    return (
        f"Right-side up/down-day volume from {start_date} to {end_date} was "
        f"{ratio:.2f}x; {reading}."
    )
