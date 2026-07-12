"""Signal dataclasses and calibration constants for the false-breakout machine (SP2).

Every numeric constant here is an interim placeholder pending SP4 backtest calibration
(docs/superpowers/specs/2026-07-11-false-breakout-machine-design.md).
"""

from __future__ import annotations

from dataclasses import dataclass

REENTRY_WINDOW_BARS = 10
CONFIRM_WINDOW_BARS = 8
NO_NEW_LOW_GRACE_BARS = 2
VOLUME_MULTIPLE = 1.3

FORMING_CONFIDENCE = 0.45
CONFIRMED_STANDARD_CONFIDENCE = 0.60
CONFIRMED_AGGRESSIVE_CONFIDENCE = 0.55
VOLUME_CONFIDENCE_BONUS = 0.05
CONFIDENCE_FLOOR = 0.2
CONFIDENCE_CEILING = 0.9


@dataclass(frozen=True)
class FalseBreakContext:
    """One failed parent breakout described generically for the machine."""

    breakout_index: int
    direction: str  # original breakout direction: "bullish" | "bearish"
    high_slope: float
    high_intercept: float
    low_slope: float
    low_intercept: float
    apex_index: float
    buffer: float
    window_bars: int
    parent_pattern: str
    parent_risk_flags: tuple[str, ...] = ()
    target_price: float | None = None


@dataclass
class FalseBreakSignal:
    """The machine's verdict before it is rendered as a PricePattern."""

    signal_type: str  # "false_breakout_short" | "false_breakdown_long"
    direction: str  # "bearish" | "bullish"
    status: str  # "forming" | "confirmed"
    aggressive: bool
    boundary_price: float
    false_break_extreme: float
    reentry_index: int
    reentry_close: float
    trigger_index: int | None
    trigger_price: float | None
    volume_expanded: bool
    confidence: float
    target_price: float | None
    invalidation_price: float
    start_index: int
    end_index: int
    parent_pattern: str
