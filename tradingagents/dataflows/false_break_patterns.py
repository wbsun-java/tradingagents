"""Render false-break signals as PricePattern entries and mutate the failed parent (SP2)."""

from __future__ import annotations

import math

import pandas as pd

from tradingagents.dataflows.false_break_machine import detect_false_break
from tradingagents.dataflows.false_break_types import FalseBreakContext, FalseBreakSignal


def _round(value: float | None) -> float | None:
    return None if value is None or not math.isfinite(value) else round(float(value), 4)


def _date(df: pd.DataFrame, index: int) -> str:
    return df.at[index, "Date"].strftime("%Y-%m-%d")


def apply_parent_side_effects(parent) -> None:
    """A reversed-breakout parent stays failed but its target is void and structure may expand."""
    parent.target_price = None
    if "structure_may_be_expanding" not in parent.risk_flags:
        parent.risk_flags.append("structure_may_be_expanding")


def _evidence(df: pd.DataFrame, signal: FalseBreakSignal) -> list[str]:
    short = signal.signal_type == "false_breakout_short"
    lines = [
        (
            f"The {signal.parent_pattern} broke {'out above' if short else 'down below'} "
            f"{_round(signal.boundary_price)} on {_date(df, signal.start_index)} then reversed."
        ),
        (
            f"The false break extended to {_round(signal.false_break_extreme)} "
            "before price closed back through the boundary."
        ),
        (
            f"Re-entry closed at {_round(signal.reentry_close)} on "
            f"{_date(df, signal.reentry_index)}, inside the re-entry window."
        ),
    ]
    if signal.aggressive:
        lines.append(
            "Confirmed aggressively at re-entry (aggressive_confirmation): less structural proof."
        )
    elif signal.trigger_index is not None:
        verb = "a close below the pullback low" if short else "price taking out the rebound high"
        lines.append(
            f"Confirmed by {verb} {_round(signal.trigger_price)} on "
            f"{_date(df, signal.trigger_index)}."
        )
    else:
        lines.append(
            f"Forming: awaiting a close below the pullback low {_round(signal.trigger_price)}."
        )
    if signal.volume_expanded:
        lines.append("Volume expanded on the confirming bar, strengthening the reversal.")
    elif short:
        lines.append("Volume did not expand; price structure alone carries the signal.")
    else:
        lines.append("Volume contracted, which may reflect exhausted selling pressure.")
    lines.append(
        f"Reverses the failed {signal.parent_pattern} breakout of {_date(df, signal.start_index)}."
    )
    return lines


def false_break_to_pattern(df: pd.DataFrame, signal: FalseBreakSignal):
    """Convert a FalseBreakSignal into a PricePattern (lazy import breaks the cycle)."""
    from tradingagents.dataflows.chart_patterns import PricePattern

    return PricePattern(
        pattern=signal.signal_type,
        status=signal.status,
        direction=signal.direction,
        confidence=signal.confidence,
        start_date=_date(df, signal.start_index),
        end_date=_date(df, signal.end_index),
        levels={
            "boundary_price": _round(signal.boundary_price),
            "false_break_extreme": _round(signal.false_break_extreme),
            "reentry_close": _round(signal.reentry_close),
            "trigger_price": _round(signal.trigger_price),
        },
        target_price=_round(signal.target_price),
        invalidation_price=_round(signal.invalidation_price),
        volume_confirmed=signal.volume_expanded,
        evidence=_evidence(df, signal),
        risk_flags=["aggressive_confirmation"] if signal.aggressive else [],
    )


def build_false_break_signal(df: pd.DataFrame, ctx: FalseBreakContext):
    """Run the machine and render a PricePattern, or return None."""
    signal = detect_false_break(df, ctx)
    if signal is None:
        return None
    return false_break_to_pattern(df, signal)
