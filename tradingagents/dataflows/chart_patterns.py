"""Deterministic price-pattern detection on historical OHLCV data.

The market analyst is an LLM, but chart geometry should not depend on an LLM
eyeballing a CSV.  This module detects a deliberately small set of classical
patterns from price data that has already been cut off at the requested
analysis date.  Results include the evidence and invalidation levels needed by
the analyst to distinguish a forming setup from a confirmed one.

These are heuristic research signals, not guarantees.  A pattern is only as
useful as its confirmation, liquidity, and surrounding market context.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import pandas as pd

from tradingagents.dataflows.double_bottom_emerging import find_emerging_double_bottom
from tradingagents.dataflows.entry_assessment import assess_entry
from tradingagents.dataflows.entry_types import EntryAssessment
from tradingagents.dataflows.false_break_patterns import (
    apply_parent_side_effects,
    build_false_break_signal,
)
from tradingagents.dataflows.false_break_types import FalseBreakContext
from tradingagents.dataflows.stockstats_utils import load_ohlcv
from tradingagents.dataflows.trendline_fit import resistance_line, support_line
from tradingagents.dataflows.triangle_breakout import classify_triangle_breakout
from tradingagents.dataflows.triangle_post_apex import post_apex_window_bars

PatternStatus = Literal["forming", "confirmed", "emerging", "failed"]
PatternDirection = Literal["bullish", "bearish", "neutral"]


@dataclass(frozen=True)
class Pivot:
    index: int
    date: str
    price: float
    kind: Literal["high", "low"]


@dataclass
class PricePattern:
    pattern: str
    status: PatternStatus
    direction: PatternDirection
    confidence: float
    start_date: str
    end_date: str
    levels: dict[str, float | None]
    target_price: float | None
    invalidation_price: float | None
    volume_confirmed: bool | None
    evidence: list[str]
    risk_flags: list[str] = field(default_factory=list)
    entry_assessment: EntryAssessment | None = None


def _round(value: float | None) -> float | None:
    return None if value is None or not math.isfinite(value) else round(float(value), 4)


def _prepare_ohlcv(data: pd.DataFrame, curr_date: str, look_back_days: int) -> pd.DataFrame:
    required = {"Date", "Open", "High", "Low", "Close", "Volume"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"OHLCV data is missing required columns: {sorted(missing)}")

    df = data.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    for column in required - {"Date"}:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = (
        df.dropna(subset=["Date", "High", "Low", "Close"])
        .loc[lambda frame: frame["Date"] <= pd.Timestamp(curr_date)]
        .sort_values("Date")
        .drop_duplicates("Date", keep="last")
        .tail(max(40, int(look_back_days)))
        .reset_index(drop=True)
    )
    if len(df) < 20:
        raise ValueError("At least 20 OHLCV rows are required for chart-pattern analysis.")
    return df


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    previous_close = df["Close"].shift(1)
    true_range = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - previous_close).abs(),
            (df["Low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(period, min_periods=1).mean()


def find_pivots(df: pd.DataFrame, span: int = 3) -> list[Pivot]:
    """Return unique centered swing highs and lows.

    A centered pivot is confirmed only after ``span`` later rows exist.  That
    deliberately avoids treating the still-forming final bar as a swing point.
    """
    if span < 1:
        raise ValueError("pivot span must be at least 1")

    pivots: list[Pivot] = []
    for index in range(span, len(df) - span):
        high_window = df["High"].iloc[index - span : index + span + 1]
        low_window = df["Low"].iloc[index - span : index + span + 1]
        high = float(df.at[index, "High"])
        low = float(df.at[index, "Low"])
        date = df.at[index, "Date"].strftime("%Y-%m-%d")

        if high == float(high_window.max()) and int((high_window == high).sum()) == 1:
            pivots.append(Pivot(index, date, high, "high"))
        if low == float(low_window.min()) and int((low_window == low).sum()) == 1:
            pivots.append(Pivot(index, date, low, "low"))
    return sorted(pivots, key=lambda pivot: (pivot.index, pivot.kind))


def _cluster_levels(pivots: list[Pivot], tolerance: float) -> list[dict[str, Any]]:
    """Cluster pivots by price proximity and retain their touch metadata."""
    clusters: list[dict[str, Any]] = []
    for pivot in sorted(pivots, key=lambda item: item.price):
        matching = next(
            (cluster for cluster in clusters if abs(pivot.price - cluster["price"]) <= tolerance),
            None,
        )
        if matching is None:
            clusters.append({"price": pivot.price, "pivots": [pivot]})
            continue
        matching["pivots"].append(pivot)
        matching["price"] = sum(item.price for item in matching["pivots"]) / len(matching["pivots"])
    return clusters


def _volume_confirmation(df: pd.DataFrame, index: int, multiple: float = 1.3) -> bool:
    if index < 1 or pd.isna(df.at[index, "Volume"]):
        return False
    start = max(0, index - 20)
    baseline = pd.to_numeric(df["Volume"].iloc[start:index], errors="coerce").mean()
    return bool(baseline and float(df.at[index, "Volume"]) >= float(baseline) * multiple)


def _breakout_after(
    df: pd.DataFrame,
    start_index: int,
    level: float,
    buffer: float,
    direction: Literal["above", "below"],
) -> int | None:
    closes = df["Close"].iloc[start_index:]
    mask = closes > level + buffer if direction == "above" else closes < level - buffer
    matches = mask[mask].index
    return int(matches[0]) if len(matches) else None


def _recent_failed_breakout(
    df: pd.DataFrame,
    upper: float,
    lower: float,
    buffer: float,
    recent_rows: int = 5,
) -> bool:
    recent = df.tail(recent_rows)
    current = float(df["Close"].iloc[-1])
    returned_inside = lower - buffer <= current <= upper + buffer
    breached = bool(
        (recent["Close"] > upper + buffer).any() or (recent["Close"] < lower - buffer).any()
    )
    return returned_inside and breached


def _level_breakout_patterns(
    df: pd.DataFrame,
    clusters: list[dict[str, Any]],
    atr_value: float,
) -> list[PricePattern]:
    """Find the most recent confirmed or failed break of a repeated level."""
    buffer = atr_value * 0.2
    candidates: list[tuple[int, FalseBreakContext | None, PricePattern]] = []
    for cluster in clusters:
        touches = cluster["pivots"]
        if len(touches) < 2:
            continue
        level = float(cluster["price"])
        last_touch = max(pivot.index for pivot in touches)
        search_start = max(last_touch + 1, len(df) - 15, 1)
        for direction in ("above", "below"):
            crossing_index = None
            for index in range(search_start, len(df)):
                previous = float(df.at[index - 1, "Close"])
                current = float(df.at[index, "Close"])
                if direction == "above" and previous <= level + buffer < current:
                    crossing_index = index
                    break
                if direction == "below" and previous >= level - buffer > current:
                    crossing_index = index
                    break
            if crossing_index is None:
                continue

            current = float(df["Close"].iloc[-1])
            held = current > level + buffer if direction == "above" else current < level - buffer
            status: PatternStatus = "confirmed" if held else "failed"
            pattern_name = "resistance_breakout" if direction == "above" else "support_breakdown"
            pattern_direction: PatternDirection = "bullish" if direction == "above" else "bearish"
            volume_confirmed = _volume_confirmation(df, crossing_index)
            false_break_ctx = None
            if status == "failed":
                false_break_ctx = FalseBreakContext(
                    breakout_index=crossing_index,
                    direction="bullish" if direction == "above" else "bearish",
                    high_slope=0.0,
                    high_intercept=level,
                    low_slope=0.0,
                    low_intercept=level,
                    apex_index=math.inf,
                    buffer=buffer,
                    window_bars=0,
                    parent_pattern=pattern_name,
                )
            candidates.append(
                (
                    crossing_index,
                    false_break_ctx,
                    PricePattern(
                        pattern=pattern_name,
                        status=status,
                        direction=pattern_direction,
                        confidence=round(
                            min(
                                0.92,
                                0.58
                                + min(len(touches), 5) * 0.05
                                + (0.08 if volume_confirmed else 0.0),
                            ),
                            2,
                        ),
                        start_date=min(pivot.date for pivot in touches),
                        end_date=df.at[crossing_index, "Date"].strftime("%Y-%m-%d"),
                        levels={
                            "broken_level": _round(level),
                            "breakout_price": _round(float(df.at[crossing_index, "Close"])),
                        },
                        target_price=None,
                        invalidation_price=_round(
                            level - buffer if direction == "above" else level + buffer
                        ),
                        volume_confirmed=volume_confirmed,
                        evidence=[
                            f"The level was established by {len(touches)} confirmed pivot touches.",
                            "A buffered close crossed the level on "
                            f"{df.at[crossing_index, 'Date']:%Y-%m-%d}.",
                            (
                                "Price remains beyond the broken level."
                                if held
                                else (
                                    "Price returned through the broken level, "
                                    "marking a failed break."
                                )
                            ),
                        ],
                    ),
                )
            )

    if not candidates:
        return []
    # One most-recent signal in each direction is enough for the analyst.
    output: list[PricePattern] = []
    for name in ("resistance_breakout", "support_breakdown"):
        matching = [item for item in candidates if item[2].pattern == name]
        if not matching:
            continue
        _, ctx, parent = max(matching, key=lambda item: item[0])
        output.append(parent)
        if ctx is not None:
            apply_parent_side_effects(parent)
            signal = build_false_break_signal(df, ctx)
            if signal is not None:
                output.append(signal)
    return output


def _double_patterns(
    df: pd.DataFrame,
    pivots: list[Pivot],
    atr_value: float,
    span: int,
) -> list[PricePattern]:
    patterns: list[PricePattern] = []
    for kind, name, direction in (
        ("low", "double_bottom", "bullish"),
        ("high", "double_top", "bearish"),
    ):
        candidates = [pivot for pivot in pivots if pivot.kind == kind]
        best: PricePattern | None = None
        best_ctx: FalseBreakContext | None = None
        best_second_index = -1
        for first_index, first in enumerate(candidates):
            for second in candidates[first_index + 1 :]:
                gap = second.index - first.index
                if gap < max(5, span * 2) or gap > 80:
                    continue
                average = (first.price + second.price) / 2
                tolerance = max(atr_value, average * 0.03)
                difference = abs(first.price - second.price)
                if difference > tolerance:
                    continue

                between = df.iloc[first.index : second.index + 1]
                neckline = float(between["High"].max() if kind == "low" else between["Low"].min())
                depth = neckline - average if kind == "low" else average - neckline
                if depth < max(atr_value * 1.25, average * 0.02):
                    continue

                buffer = atr_value * 0.2
                breakout_direction = "above" if kind == "low" else "below"
                breakout_index = _breakout_after(
                    df, second.index + 1, neckline, buffer, breakout_direction
                )
                failure_level = (
                    min(first.price, second.price) - buffer
                    if kind == "low"
                    else max(first.price, second.price) + buffer
                )
                failed_index = _breakout_after(
                    df,
                    second.index + 1,
                    failure_level,
                    0.0,
                    "below" if kind == "low" else "above",
                )
                breakout_failed = bool(
                    breakout_index is not None
                    and (
                        (kind == "low" and float(df["Close"].iloc[-1]) < neckline - buffer)
                        or (kind == "high" and float(df["Close"].iloc[-1]) > neckline + buffer)
                    )
                )
                if breakout_failed:
                    status: PatternStatus = "failed"
                    end_index = len(df) - 1
                elif breakout_index is not None:
                    status = "confirmed"
                    end_index = breakout_index
                elif failed_index is not None:
                    status = "failed"
                    end_index = failed_index
                else:
                    status = "forming"
                    end_index = len(df) - 1

                volume_confirmed = (
                    _volume_confirmation(df, breakout_index) if breakout_index is not None else None
                )
                similarity_score = max(0.0, 1.0 - difference / tolerance)
                depth_score = min(1.0, depth / max(atr_value * 3, average * 0.06))
                confidence = 0.5 + similarity_score * 0.2 + depth_score * 0.15
                if status == "confirmed":
                    confidence += 0.1 + (0.05 if volume_confirmed else 0.0)
                elif status == "failed":
                    confidence = min(confidence, 0.55)

                target = neckline + depth if kind == "low" else neckline - depth
                if status == "failed":
                    target = None
                pattern = PricePattern(
                    pattern=name,
                    status=status,
                    direction=direction,
                    confidence=round(min(confidence, 0.95), 2),
                    start_date=first.date,
                    end_date=df.at[end_index, "Date"].strftime("%Y-%m-%d"),
                    levels={
                        "first_extreme": _round(first.price),
                        "second_extreme": _round(second.price),
                        "neckline": _round(neckline),
                        "breakout_price": (
                            _round(float(df.at[breakout_index, "Close"]))
                            if breakout_index is not None
                            else None
                        ),
                    },
                    target_price=_round(target),
                    invalidation_price=_round(failure_level),
                    volume_confirmed=volume_confirmed,
                    evidence=[
                        f"Extremes differ by {difference / average:.2%} across {gap} bars.",
                        f"Pattern depth is {depth / atr_value:.2f} ATR.",
                        (
                            "Close confirmed the neckline on "
                            f"{df.at[breakout_index, 'Date']:%Y-%m-%d}."
                            if breakout_index is not None
                            else "The neckline has not been confirmed by a buffered close."
                        ),
                    ],
                )
                candidate_ctx = None
                if breakout_failed and breakout_index is not None:
                    candidate_ctx = FalseBreakContext(
                        breakout_index=breakout_index,
                        direction="bullish" if kind == "low" else "bearish",
                        high_slope=0.0,
                        high_intercept=neckline,
                        low_slope=0.0,
                        low_intercept=neckline,
                        apex_index=math.inf,
                        buffer=buffer,
                        window_bars=0,
                        parent_pattern=name,
                        target_price=(
                            min(first.price, second.price)
                            if kind == "low"
                            else max(first.price, second.price)
                        ),
                    )
                if second.index > best_second_index:
                    best = pattern
                    best_ctx = candidate_ctx
                    best_second_index = second.index

        if best is not None:
            # At most one recent signal of each double-pattern type keeps the
            # tool output compact enough for downstream LLM context.
            patterns.append(best)
            if best_ctx is not None:
                apply_parent_side_effects(best)
                signal = build_false_break_signal(df, best_ctx)
                if signal is not None:
                    patterns.append(signal)
    return patterns


def _rectangle_pattern(
    df: pd.DataFrame,
    pivots: list[Pivot],
    atr_value: float,
) -> list[PricePattern]:
    window_start = max(0, len(df) - 80)
    recent_pivots = [pivot for pivot in pivots if pivot.index >= window_start]
    tolerance = max(atr_value * 0.6, float(df["Close"].iloc[-1]) * 0.006)
    high_clusters = _cluster_levels(
        [pivot for pivot in recent_pivots if pivot.kind == "high"], tolerance
    )
    low_clusters = _cluster_levels(
        [pivot for pivot in recent_pivots if pivot.kind == "low"], tolerance
    )
    high_clusters = [cluster for cluster in high_clusters if len(cluster["pivots"]) >= 2]
    low_clusters = [cluster for cluster in low_clusters if len(cluster["pivots"]) >= 2]
    if not high_clusters or not low_clusters:
        return []

    resistance = max(high_clusters, key=lambda cluster: (len(cluster["pivots"]), cluster["price"]))
    support = max(low_clusters, key=lambda cluster: (len(cluster["pivots"]), -cluster["price"]))
    upper = float(resistance["price"])
    lower = float(support["price"])
    width = upper - lower
    middle = (upper + lower) / 2
    if width < atr_value * 2 or width / middle > 0.18:
        return []

    all_touches = sorted(resistance["pivots"] + support["pivots"], key=lambda pivot: pivot.index)
    start_index = all_touches[0].index
    if all_touches[-1].index - start_index < 12:
        return []

    buffer = atr_value * 0.2
    up_break = _breakout_after(df, all_touches[-1].index + 1, upper, buffer, "above")
    down_break = _breakout_after(df, all_touches[-1].index + 1, lower, buffer, "below")
    breakout_index = up_break if up_break is not None else down_break
    if up_break is not None and down_break is not None:
        breakout_index = min(up_break, down_break)
    current_close = float(df["Close"].iloc[-1])
    breakout_held = bool(
        breakout_index is not None
        and (
            (breakout_index == up_break and current_close > upper + buffer)
            or (breakout_index == down_break and current_close < lower - buffer)
        )
    )
    if breakout_index is not None and breakout_held:
        bullish = float(df.at[breakout_index, "Close"]) > upper
        status: PatternStatus = "confirmed"
        direction: PatternDirection = "bullish" if bullish else "bearish"
    elif breakout_index is not None or _recent_failed_breakout(df, upper, lower, buffer):
        status = "failed"
        direction = "neutral"
    else:
        status = "forming"
        direction = "neutral"

    volume_confirmed = (
        _volume_confirmation(df, breakout_index) if breakout_index is not None else None
    )
    target = None
    invalidation = None
    if direction == "bullish":
        target, invalidation = upper + width, lower
    elif direction == "bearish":
        target, invalidation = lower - width, upper

    touch_count = len(resistance["pivots"]) + len(support["pivots"])
    confidence = min(0.9, 0.48 + min(touch_count, 8) * 0.04 + (0.1 if status == "confirmed" else 0))
    parent = PricePattern(
        pattern="rectangle",
        status=status,
        direction=direction,
        confidence=round(confidence, 2),
        start_date=df.at[start_index, "Date"].strftime("%Y-%m-%d"),
        end_date=df.at[
            breakout_index if breakout_index is not None else len(df) - 1, "Date"
        ].strftime("%Y-%m-%d"),
        levels={
            "support": _round(lower),
            "resistance": _round(upper),
            "breakout_price": (
                _round(float(df.at[breakout_index, "Close"]))
                if breakout_index is not None
                else None
            ),
        },
        target_price=_round(target),
        invalidation_price=_round(invalidation),
        volume_confirmed=volume_confirmed,
        evidence=[
            f"Support was touched {len(support['pivots'])} times.",
            f"Resistance was touched {len(resistance['pivots'])} times.",
            f"Range width is {width / middle:.2%} ({width / atr_value:.2f} ATR).",
        ],
    )
    results = [parent]
    if breakout_index is not None and status == "failed":
        ctx = FalseBreakContext(
            breakout_index=breakout_index,
            direction="bullish" if breakout_index == up_break else "bearish",
            high_slope=0.0,
            high_intercept=upper,
            low_slope=0.0,
            low_intercept=lower,
            apex_index=math.inf,
            buffer=buffer,
            window_bars=0,
            parent_pattern="rectangle",
            target_price=lower if breakout_index == up_break else upper,
        )
        apply_parent_side_effects(parent)
        signal = build_false_break_signal(df, ctx)
        if signal is not None:
            results.append(signal)
    return results


def _triangle_pattern(
    df: pd.DataFrame,
    pivots: list[Pivot],
    atr_value: float,
) -> list[PricePattern]:
    highs = [pivot for pivot in pivots if pivot.kind == "high"]
    lows = [pivot for pivot in pivots if pivot.kind == "low"]
    if len(highs) < 3 or len(lows) < 3:
        return []

    resistance = resistance_line([(pivot.index, pivot.price) for pivot in highs])
    support = support_line([(pivot.index, pivot.price) for pivot in lows])
    if resistance is None or support is None:
        return []
    high_slope, high_intercept = resistance.slope, resistance.intercept
    low_slope, low_intercept = support.slope, support.intercept
    price = float(df["Close"].iloc[-1])
    flat_threshold = price * 0.0007
    trend_threshold = price * 0.00035

    if high_slope < -trend_threshold and low_slope > trend_threshold:
        name = "symmetrical_triangle"
        bias: PatternDirection = "neutral"
    elif abs(high_slope) <= flat_threshold and low_slope > trend_threshold:
        name = "ascending_triangle"
        bias = "bullish"
    elif high_slope < -trend_threshold and abs(low_slope) <= flat_threshold:
        name = "descending_triangle"
        bias = "bearish"
    else:
        return []

    start_index = min(resistance.start_index, support.start_index)
    formation_end = max(resistance.end_index, support.end_index)
    start_upper = high_slope * start_index + high_intercept
    start_lower = low_slope * start_index + low_intercept
    formation_upper = high_slope * formation_end + high_intercept
    formation_lower = low_slope * formation_end + low_intercept
    start_gap = start_upper - start_lower
    formation_gap = formation_upper - formation_lower
    if start_gap <= 0 or formation_gap <= 0 or formation_gap >= start_gap * 0.85:
        return []

    slope_difference = high_slope - low_slope
    if abs(slope_difference) < 1e-12:
        return []
    apex_index = (low_intercept - high_intercept) / slope_difference
    if apex_index <= formation_end or apex_index <= start_index:
        return []

    buffer = atr_value * 0.2
    breakout = classify_triangle_breakout(
        df,
        high_slope=high_slope,
        high_intercept=high_intercept,
        low_slope=low_slope,
        low_intercept=low_intercept,
        start_index=start_index,
        formation_end=formation_end,
        apex_index=apex_index,
        bias=bias,
        buffer=buffer,
    )
    status = breakout.status
    direction = breakout.direction
    breakout_index = breakout.breakout_index
    signal_end_index = breakout.signal_end_index
    breakout_progress = breakout.breakout_progress
    upper_level = breakout.upper_level
    lower_level = breakout.lower_level
    risk_flags = breakout.risk_flags
    timing_evidence = breakout.timing_evidence

    volume_confirmed = (
        _volume_confirmation(df, breakout_index) if breakout_index is not None else None
    )
    target = None
    invalidation = None
    breakout_price = float(df.at[breakout_index, "Close"]) if breakout_index is not None else None
    # Post-apex breakouts anchor the measured move at the apex price (both frozen
    # levels equal it); extending from the breakout close would inflate the target.
    if direction == "bullish" and status == "confirmed" and breakout_price is not None:
        anchor = upper_level if "post_apex_breakout" in risk_flags else breakout_price
        target, invalidation = anchor + start_gap, lower_level
    elif direction == "bearish" and status == "confirmed" and breakout_price is not None:
        anchor = lower_level if "post_apex_breakout" in risk_flags else breakout_price
        target, invalidation = anchor - start_gap, upper_level

    convergence = 1 - formation_gap / start_gap
    confidence = 0.55 + convergence * 0.15 + breakout.timing_adjustment
    if status == "confirmed":
        confidence += 0.1 + (0.03 if volume_confirmed else 0.0)
    elif status == "failed":
        confidence = min(confidence, 0.5)
    confidence = max(0.2, min(0.95, confidence))
    parent = PricePattern(
        pattern=name,
        status=status,
        direction=direction,
        confidence=round(confidence, 2),
        start_date=df.at[start_index, "Date"].strftime("%Y-%m-%d"),
        end_date=df.at[signal_end_index, "Date"].strftime("%Y-%m-%d"),
        levels={
            "upper_trendline": _round(upper_level),
            "lower_trendline": _round(lower_level),
            "breakout_price": _round(breakout_price),
            "apex_bar_index": _round(apex_index),
            "breakout_progress": _round(breakout_progress),
        },
        target_price=_round(target),
        invalidation_price=_round(invalidation),
        volume_confirmed=volume_confirmed,
        evidence=[
            f"Upper trendline slope is {high_slope:.4f} price units per bar.",
            f"Lower trendline slope is {low_slope:.4f} price units per bar.",
            f"Trendline gap contracted by {convergence:.1%}.",
            timing_evidence,
        ],
        risk_flags=risk_flags,
    )
    results = [parent]
    if "breakout_reversed_back_through_triangle" in risk_flags and breakout_index is not None:
        ctx = FalseBreakContext(
            breakout_index=breakout_index,
            direction=direction,
            high_slope=high_slope,
            high_intercept=high_intercept,
            low_slope=low_slope,
            low_intercept=low_intercept,
            apex_index=apex_index,
            buffer=buffer,
            window_bars=post_apex_window_bars(start_index, apex_index),
            parent_pattern=name,
            parent_risk_flags=tuple(risk_flags),
            target_price=lower_level if direction == "bullish" else upper_level,
        )
        apply_parent_side_effects(parent)
        signal = build_false_break_signal(df, ctx)
        if signal is not None:
            results.append(signal)
    return results


def analyze_chart_patterns_from_data(
    data: pd.DataFrame,
    curr_date: str,
    look_back_days: int = 252,
    pivot_span: int = 3,
) -> dict[str, Any]:
    """Analyze an OHLCV frame and return a JSON-serializable result."""
    df = _prepare_ohlcv(data, curr_date, look_back_days)
    atr_series = _atr(df)
    atr_value = float(atr_series.iloc[-1])
    if not math.isfinite(atr_value) or atr_value <= 0:
        atr_value = max(float((df["High"] - df["Low"]).median()), 0.01)

    pivots = find_pivots(df, pivot_span)
    current = float(df["Close"].iloc[-1])
    level_tolerance = max(atr_value * 0.5, current * 0.005)
    clusters = _cluster_levels(pivots, level_tolerance)
    significant = [cluster for cluster in clusters if len(cluster["pivots"]) >= 2]
    supports = sorted(
        (
            {
                "price": _round(cluster["price"]),
                "touches": len(cluster["pivots"]),
                "last_touch": max(pivot.date for pivot in cluster["pivots"]),
            }
            for cluster in significant
            if cluster["price"] <= current + level_tolerance
        ),
        key=lambda level: level["price"],
        reverse=True,
    )[:4]
    resistances = sorted(
        (
            {
                "price": _round(cluster["price"]),
                "touches": len(cluster["pivots"]),
                "last_touch": max(pivot.date for pivot in cluster["pivots"]),
            }
            for cluster in significant
            if cluster["price"] > current + level_tolerance
        ),
        key=lambda level: level["price"],
    )[:4]

    patterns = _level_breakout_patterns(df, significant, atr_value)
    patterns.extend(_double_patterns(df, pivots, atr_value, pivot_span))
    patterns.extend(_rectangle_pattern(df, pivots, atr_value))
    patterns.extend(_triangle_pattern(df, pivots, atr_value))

    if not any(pattern.pattern == "double_bottom" for pattern in patterns):
        emerging = find_emerging_double_bottom(df, pivots, atr_value, pivot_span)
        if emerging is not None:
            patterns.append(emerging)

    for pattern in patterns:
        pattern.entry_assessment = assess_entry(df, pattern, atr_value, current)

    # Keep current/recent setups first and avoid flooding the analyst context.
    status_order = {"confirmed": 0, "forming": 1, "emerging": 2, "failed": 3}
    patterns.sort(key=lambda pattern: (status_order[pattern.status], -pattern.confidence))

    return {
        "symbol": "",
        "analysis_date": curr_date,
        "latest_row": df["Date"].iloc[-1].strftime("%Y-%m-%d"),
        "latest_close": _round(current),
        "atr_14": _round(atr_value),
        "window_rows": len(df),
        "pivot_span": pivot_span,
        "support_levels": supports,
        "resistance_levels": resistances,
        "patterns": [asdict(pattern) for pattern in patterns],
        "method_note": (
            "Deterministic heuristic using confirmed swing pivots, ATR-scaled tolerances, "
            "trendline regression, buffered closes, and optional volume confirmation. "
            "Treat forming patterns as watchlist conditions, not completed signals."
        ),
    }


def analyze_chart_patterns(
    symbol: str,
    curr_date: str,
    look_back_days: int = 252,
    pivot_span: int = 3,
) -> str:
    """Load cutoff-safe OHLCV and return a formatted JSON pattern report."""
    data = load_ohlcv(symbol, curr_date)
    result = analyze_chart_patterns_from_data(data, curr_date, look_back_days, pivot_span)
    result["symbol"] = symbol.upper()
    return json.dumps(result, indent=2, ensure_ascii=False)
