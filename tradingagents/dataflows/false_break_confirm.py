"""Stage-2 direction-asymmetric confirmation builders for false breakouts (SP2)."""

from __future__ import annotations

import pandas as pd

from tradingagents.dataflows.false_break_rules import (
    long_upgrade_index,
    no_new_low_guard,
    pullback_low,
    rebound_high,
    short_trigger_index,
    volume_expanded,
)
from tradingagents.dataflows.false_break_types import (
    CONFIDENCE_CEILING,
    CONFIDENCE_FLOOR,
    CONFIRM_WINDOW_BARS,
    CONFIRMED_AGGRESSIVE_CONFIDENCE,
    CONFIRMED_STANDARD_CONFIDENCE,
    FORMING_CONFIDENCE,
    NO_NEW_LOW_GRACE_BARS,
    VOLUME_CONFIDENCE_BONUS,
    FalseBreakContext,
    FalseBreakSignal,
)
from tradingagents.dataflows.triangle_post_apex import (
    ASYMMETRIC_REVERSAL_FLAGS,
    line_before_apex,
)


def _confidence(status: str, aggressive: bool, expanded: bool) -> float:
    if status == "forming":
        base = FORMING_CONFIDENCE
    else:
        base = CONFIRMED_AGGRESSIVE_CONFIDENCE if aggressive else CONFIRMED_STANDARD_CONFIDENCE
    if expanded:
        base += VOLUME_CONFIDENCE_BONUS
    return round(max(CONFIDENCE_FLOOR, min(CONFIDENCE_CEILING, base)), 2)


def build_short(
    df: pd.DataFrame, ctx: FalseBreakContext, reentry: int, extreme: float
) -> FalseBreakSignal:
    boundary = line_before_apex(ctx.high_slope, ctx.high_intercept, reentry, ctx.apex_index)
    pullback = pullback_low(df, ctx.breakout_index, reentry)
    trigger: int | None
    if ASYMMETRIC_REVERSAL_FLAGS & set(ctx.parent_risk_flags):
        status, aggressive, trigger = "confirmed", True, reentry
    else:
        trig = short_trigger_index(
            df, reentry_index=reentry, boundary_price=boundary,
            pullback_low_price=pullback, buffer=ctx.buffer, confirm_window=CONFIRM_WINDOW_BARS,
        )
        if trig is not None:
            status, aggressive, trigger = "confirmed", False, trig
        else:
            status, aggressive, trigger = "forming", False, None
    vol_index = trigger if trigger is not None else reentry
    expanded = volume_expanded(df, vol_index)
    return FalseBreakSignal(
        signal_type="false_breakout_short", direction="bearish", status=status,
        aggressive=aggressive, boundary_price=boundary, false_break_extreme=extreme,
        reentry_index=reentry, reentry_close=float(df.at[reentry, "Close"]),
        trigger_index=trigger, trigger_price=pullback, volume_expanded=expanded,
        confidence=_confidence(status, aggressive, expanded), target_price=ctx.target_price,
        invalidation_price=extreme + ctx.buffer, start_index=ctx.breakout_index,
        end_index=trigger if trigger is not None else reentry, parent_pattern=ctx.parent_pattern,
    )


def build_long(
    df: pd.DataFrame, ctx: FalseBreakContext, reentry: int, extreme: float
) -> FalseBreakSignal | None:
    if not no_new_low_guard(
        df, breakdown_index=ctx.breakout_index, reentry_index=reentry,
        grace_bars=NO_NEW_LOW_GRACE_BARS,
    ):
        return None
    boundary = line_before_apex(ctx.low_slope, ctx.low_intercept, reentry, ctx.apex_index)
    rebound = rebound_high(df, ctx.breakout_index, reentry)
    upgrade = long_upgrade_index(
        df, reentry_index=reentry, boundary_price=boundary,
        rebound_high_price=rebound, buffer=ctx.buffer,
    )
    aggressive, trigger = (False, upgrade) if upgrade is not None else (True, reentry)
    expanded = volume_expanded(df, trigger)
    return FalseBreakSignal(
        signal_type="false_breakdown_long", direction="bullish", status="confirmed",
        aggressive=aggressive, boundary_price=boundary, false_break_extreme=extreme,
        reentry_index=reentry, reentry_close=float(df.at[reentry, "Close"]),
        trigger_index=trigger, trigger_price=rebound, volume_expanded=expanded,
        confidence=_confidence("confirmed", aggressive, expanded), target_price=ctx.target_price,
        invalidation_price=extreme - ctx.buffer, start_index=ctx.breakout_index,
        end_index=trigger, parent_pattern=ctx.parent_pattern,
    )
