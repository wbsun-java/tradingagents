"""Stage-1 re-entry detection + dispatch for the false-breakout state machine (SP2).

Reuses SP1's find_reversal_index as the universal re-entry detector, caps signal emission
at REENTRY_WINDOW_BARS, and dispatches to the Stage-2 builders in false_break_confirm.
"""

from __future__ import annotations

import pandas as pd

from tradingagents.dataflows.false_break_confirm import build_long, build_short
from tradingagents.dataflows.false_break_rules import false_break_extreme
from tradingagents.dataflows.false_break_types import (
    REENTRY_WINDOW_BARS,
    FalseBreakContext,
    FalseBreakSignal,
)
from tradingagents.dataflows.triangle_post_apex import find_reversal_index


def detect_false_break(df: pd.DataFrame, ctx: FalseBreakContext) -> FalseBreakSignal | None:
    """Return a false-break signal for a reversed parent breakout, or None."""
    reentry = find_reversal_index(
        df, high_slope=ctx.high_slope, high_intercept=ctx.high_intercept,
        low_slope=ctx.low_slope, low_intercept=ctx.low_intercept, apex_index=ctx.apex_index,
        breakout_index=ctx.breakout_index, breakout_direction=ctx.direction,
        risk_flags=list(ctx.parent_risk_flags), buffer=ctx.buffer, window_bars=ctx.window_bars,
    )
    if reentry is None or reentry - ctx.breakout_index > REENTRY_WINDOW_BARS:
        return None
    extreme = false_break_extreme(df, ctx.breakout_index, reentry, ctx.direction)
    if ctx.direction == "bullish":
        return build_short(df, ctx, reentry, extreme)
    return build_long(df, ctx, reentry, extreme)
