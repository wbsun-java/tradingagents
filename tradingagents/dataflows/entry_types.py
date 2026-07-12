"""EntryAssessment dataclass, state names, and tuning constants for the entry layer (SP3).

Every numeric constant is an interim placeholder pending SP4 backtest calibration
(docs/superpowers/specs/2026-07-12-entry-taxonomy-design.md).
"""

from __future__ import annotations

from dataclasses import dataclass

PREDICTIVE_BOTTOM = "predictive_bottom"
BREAKOUT_ENTRY = "breakout_entry"
BREAKOUT_RETEST_ENTRY = "breakout_retest_entry"
OBSERVE = "observe"
AVOID = "avoid"
FALSE_BREAKOUT_SHORT = "false_breakout_short"
FALSE_BREAKDOWN_LONG = "false_breakdown_long"

ENTRY_PROXIMITY_ATR = 0.5
RETEST_WINDOW_BARS = 15
PREDICTIVE_UNDERSHOOT_ATR = 0.25

LONG_ELIGIBLE = frozenset(
    {
        "double_bottom",
        "ascending_triangle",
        "symmetrical_triangle",
        "rectangle",
        "resistance_breakout",
    }
)
BEARISH_TYPES = frozenset({"double_top", "descending_triangle", "support_breakdown"})


@dataclass
class EntryAssessment:
    state: str
    direction: str  # "long" | "short" | "none"
    entry_zone_low: float | None
    entry_zone_high: float | None
    trigger_price: float | None
    invalidation_price: float | None
    confirmation: str
    volume_role: str
