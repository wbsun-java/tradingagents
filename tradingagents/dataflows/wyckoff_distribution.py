"""Distribution-side Wyckoff event/phase detection.

Mirror of wyckoff_accumulation.py: only runs when the shared trading range
formed after an uptrend (a precondition for distribution), and turns the
generic event/phase result into a scored, direction-labeled result the bias
synthesizer can compare against the accumulation side.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from tradingagents.dataflows.wyckoff_events import WyckoffEvent, confidence_for, detect_events
from tradingagents.dataflows.wyckoff_range import TradingRange


@dataclass
class DistributionResult:
    events: list[WyckoffEvent]
    phase: str
    confidence: float


def analyze_distribution(
    df: pd.DataFrame, atr_value: float, rng: TradingRange | None
) -> DistributionResult | None:
    """Try to read ``rng`` as a distribution range; None if it doesn't qualify."""
    if rng is None or rng.prior_trend != "up":
        return None
    events, phase = detect_events(df, atr_value, rng, "distribution")
    if phase == "undetermined":
        return None
    return DistributionResult(events=events, phase=phase, confidence=confidence_for(events, phase))
