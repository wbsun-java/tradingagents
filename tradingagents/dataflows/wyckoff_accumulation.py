"""Accumulation-side Wyckoff event/phase detection.

Thin wrapper around wyckoff_events.detect_events: only runs when the shared
trading range formed after a downtrend (a precondition for accumulation),
and turns the generic event/phase result into a scored, direction-labeled
result the bias synthesizer can compare against the distribution side.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from tradingagents.dataflows.wyckoff_events import WyckoffEvent, confidence_for, detect_events
from tradingagents.dataflows.wyckoff_invalidation import check_invalidation
from tradingagents.dataflows.wyckoff_range import TradingRange


@dataclass
class AccumulationResult:
    events: list[WyckoffEvent]
    phase: str
    confidence: float
    invalidated: bool = False


def analyze_accumulation(
    df: pd.DataFrame, atr_value: float, rng: TradingRange | None
) -> AccumulationResult | None:
    """Try to read ``rng`` as an accumulation range; None if it doesn't qualify."""
    if rng is None or rng.prior_trend != "down":
        return None
    events, phase = detect_events(df, atr_value, rng, "accumulation")
    if phase == "undetermined":
        return None
    failure = check_invalidation(df, atr_value, rng, "accumulation", events, phase)
    if failure is not None:
        events = [*events, failure]
    return AccumulationResult(
        events=events, phase=phase, confidence=confidence_for(events, phase), invalidated=failure is not None
    )
