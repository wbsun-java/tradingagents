"""Entry-state trading layer (SP3): classify one pattern into an EntryAssessment.

Runs as a post-pass over already-detected patterns. Deterministic; the LLM only explains
the resulting state (see market_analyst.py). Import-cycle free (duck-types the pattern).
"""

from __future__ import annotations

import math

import pandas as pd

from tradingagents.dataflows.entry_rules import extract_levels, near, retest_hold
from tradingagents.dataflows.entry_types import (
    AVOID,
    BEARISH_TYPES,
    BREAKOUT_ENTRY,
    BREAKOUT_RETEST_ENTRY,
    ENTRY_PROXIMITY_ATR,
    FALSE_BREAKDOWN_LONG,
    FALSE_BREAKOUT_SHORT,
    OBSERVE,
    PREDICTIVE_BOTTOM,
    PREDICTIVE_UNDERSHOOT_ATR,
    RETEST_WINDOW_BARS,
    EntryAssessment,
)


def _round(value):
    return None if value is None or not math.isfinite(value) else round(float(value), 4)


def _make(state, direction, low, high, trigger, invalidation, confirmation, volume_role):
    return EntryAssessment(
        state=state, direction=direction, entry_zone_low=_round(low), entry_zone_high=_round(high),
        trigger_price=_round(trigger), invalidation_price=_round(invalidation),
        confirmation=confirmation, volume_role=volume_role,
    )


def _from_signal(pattern) -> EntryAssessment:
    lv = pattern.levels
    short = pattern.pattern == FALSE_BREAKOUT_SHORT
    bounds = sorted(x for x in (lv.get("boundary_price"), lv.get("reentry_close")) if x is not None)
    return _make(
        pattern.pattern, "short" if short else "long",
        bounds[0] if bounds else None, bounds[-1] if bounds else None,
        lv.get("trigger_price"), pattern.invalidation_price,
        f"SP2 {pattern.pattern} reversal signal at the failed boundary.",
        "supporting_not_required",
    )


def assess_entry(df: pd.DataFrame, pattern, atr: float, current_close: float) -> EntryAssessment:
    """Classify one PricePattern into an entry state based on price position."""
    name = pattern.pattern
    if name in (FALSE_BREAKOUT_SHORT, FALSE_BREAKDOWN_LONG):
        return _from_signal(pattern)
    if name in BEARISH_TYPES or pattern.direction == "bearish":
        return _make(AVOID, "none", None, None, None, None, f"{name} offers no long entry.", "not_applicable")
    levels = extract_levels(pattern, atr)
    if levels is None:
        return _make(OBSERVE, "none", None, None, None, None, "No long-eligible structure.", "not_applicable")
    prox = ENTRY_PROXIMITY_ATR * atr
    if pattern.status == "emerging":
        bottom = levels["bottom_boundary"]
        return _make(PREDICTIVE_BOTTOM, "long", bottom - PREDICTIVE_UNDERSHOOT_ATR * atr,
                     bottom + prox, bottom, levels["failure_level"],
                     "Emerging second bottom with a nascent turn-up.", "supporting_not_required")
    if pattern.status == "failed":
        return _make(AVOID, "none", None, None, None, None,
                     f"{name} breakout failed; former boundary no longer reliable.", "not_applicable")
    if pattern.status == "confirmed":
        level = levels["breakout_level"]
        if retest_hold(df, level, prox, RETEST_WINDOW_BARS):
            return _make(BREAKOUT_RETEST_ENTRY, "long", level, level + prox, level,
                         levels["failure_level"], "Low-volume retest held above the former resistance.",
                         "low_volume_preferred")
        if current_close <= level + prox:
            return _make(BREAKOUT_ENTRY, "long", level, level + prox, level, levels["failure_level"],
                         "Price sits at a fresh valid breakout of the boundary.", "expansion_preferred")
        return _make(OBSERVE, "none", None, None, None, None,
                     f"{name} confirmed but price is extended above the breakout with no retest.",
                     "not_applicable")
    if pattern.status == "forming":
        bottom = levels["bottom_boundary"]
        failure = levels["failure_level"]
        if near(current_close, bottom, prox) and (failure is None or current_close > failure):
            return _make(PREDICTIVE_BOTTOM, "long", bottom - PREDICTIVE_UNDERSHOOT_ATR * atr,
                         bottom + prox, bottom, failure,
                         "Price sits at the confirmed bottom boundary of a forming structure.",
                         "supporting_not_required")
        return _make(OBSERVE, "none", None, None, None, None,
                     f"{name} forming; price is mid-structure with no positional edge.", "not_applicable")
    return _make(OBSERVE, "none", None, None, None, None, "No actionable position.", "not_applicable")
