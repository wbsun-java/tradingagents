"""Emerging double-bottom detection (SP3b): the W's second bottom before it confirms.

find_pivots only confirms a swing low `span` bars later, so a fresh second bottom is
invisible to _double_patterns. This module recognizes it early -- guarded by a conservative
turn-up so a still-falling low never qualifies -- and emits a status="emerging" double
bottom that feeds predictive_bottom. Constants are interim, pending a future backtest read
(docs/superpowers/specs/2026-07-12-emerging-double-bottom-design.md).
"""

from __future__ import annotations

import math

import pandas as pd

EMERGING_WINDOW_BARS_MARGIN = 2
EMERGING_TURN_UP_ATR = 0.5
EMERGING_CONFIDENCE = 0.4


def _round(value: float | None) -> float | None:
    return None if value is None or not math.isfinite(value) else round(float(value), 4)


def _match_first_bottom(df, pivots, atr, span, candidate_index, candidate_low):
    """Most-recent confirmed low pivot that forms a valid double with the candidate."""
    lows = sorted(
        (p for p in pivots if p.kind == "low" and p.index < candidate_index),
        key=lambda p: p.index, reverse=True,
    )
    for first in lows:
        gap = candidate_index - first.index
        if gap < max(5, span * 2) or gap > 80:
            continue
        average = (first.price + candidate_low) / 2
        tolerance = max(atr, average * 0.03)
        if abs(first.price - candidate_low) > tolerance or candidate_low < first.price - tolerance:
            continue
        neckline = float(df["High"].iloc[first.index : candidate_index + 1].max())
        depth = neckline - average
        if depth < max(atr * 1.25, average * 0.02):
            continue
        return first, average, neckline, depth
    return None


def find_emerging_double_bottom(df: pd.DataFrame, pivots, atr: float, span: int):
    """Return an emerging double_bottom PricePattern, or None if any gate fails."""
    if atr <= 0 or len(df) < span + 5:
        return None
    window = span + EMERGING_WINDOW_BARS_MARGIN
    candidate_index = int(df["Low"].iloc[len(df) - window :].idxmin())
    candidate_low = float(df.at[candidate_index, "Low"])
    last_index = len(df) - 1
    if candidate_index >= last_index:
        return None
    if float(df["Close"].iloc[-1]) < candidate_low + EMERGING_TURN_UP_ATR * atr:
        return None
    if float(df["Low"].iloc[candidate_index + 1 :].min()) < candidate_low:
        return None
    match = _match_first_bottom(df, pivots, atr, span, candidate_index, candidate_low)
    if match is None:
        return None
    first, average, neckline, depth = match

    from tradingagents.dataflows.chart_patterns import PricePattern

    return PricePattern(
        pattern="double_bottom",
        status="emerging",
        direction="bullish",
        confidence=EMERGING_CONFIDENCE,
        start_date=df.at[first.index, "Date"].strftime("%Y-%m-%d"),
        end_date=df.at[last_index, "Date"].strftime("%Y-%m-%d"),
        levels={
            "first_extreme": _round(first.price),
            "second_extreme": _round(candidate_low),
            "neckline": _round(neckline),
            "breakout_price": None,
        },
        target_price=_round(neckline + depth),
        invalidation_price=_round(candidate_low - atr * 0.2),
        volume_confirmed=None,
        evidence=[
            f"First bottom near {_round(first.price)} on {df.at[first.index, 'Date']:%Y-%m-%d}.",
            f"An emerging second bottom printed at {_round(candidate_low)} on "
            f"{df.at[candidate_index, 'Date']:%Y-%m-%d}, not yet a confirmed pivot.",
            f"Price turned up at least {EMERGING_TURN_UP_ATR} ATR off that low.",
            f"Neckline resistance {_round(neckline)}; measured target {_round(neckline + depth)}.",
        ],
    )
