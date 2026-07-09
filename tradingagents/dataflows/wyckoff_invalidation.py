"""Detects a Phase D/E Wyckoff breakout that later reversed.

`detect_events` (wyckoff_events.py) only checks whether Sign-of-Strength /
Last-Point / Back-Up occurred in sequence — it never checks whether that
breakout held. This module adds that check as a separate pass so
wyckoff_events.py (already at the 150-line cap) doesn't have to grow.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd

from tradingagents.dataflows.wyckoff_events import Phase, WyckoffEvent
from tradingagents.dataflows.wyckoff_range import TradingRange, volume_ratio

Direction = Literal["accumulation", "distribution"]


def check_invalidation(
    df: pd.DataFrame,
    atr_value: float,
    rng: TradingRange,
    direction: Direction,
    events: list[WyckoffEvent],
    phase: Phase,
) -> WyckoffEvent | None:
    """Return a ``range_failure`` event if the Phase D/E breakout reversed, else None."""
    if phase not in ("D", "E") or not events:
        return None
    accum = direction == "accumulation"
    buffer = atr_value * 0.2
    last_index = df.index[df["Date"] == pd.Timestamp(events[-1].date)]
    if not len(last_index):
        return None
    start = int(last_index[0]) + 1
    for i in range(start, len(df)):
        close = float(df.at[i, "Close"])
        failed = close < rng.range_low - buffer if accum else close > rng.range_high + buffer
        if not failed:
            continue
        date = df.at[i, "Date"].strftime("%Y-%m-%d")
        boundary = rng.range_low if accum else rng.range_high
        noun = "accumulation" if accum else "distribution"
        side = "below the original range low" if accum else "above the original range high"
        evidence = (
            f"Price closed back {side} of {boundary:.2f} on {date}, giving back the "
            f"prior breakout — this {noun} read no longer holds."
        )
        return WyckoffEvent(
            event="range_failure", date=date, price=close,
            volume_ratio=volume_ratio(df, i), evidence=[evidence],
        )
    return None
