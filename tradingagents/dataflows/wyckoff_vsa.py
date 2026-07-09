"""Stage 2 VSA orchestration: scores per-bar effort-vs-result signals across
the Stage 1 trading range and folds them into a bounded confidence
adjustment, without altering phase_bias or current_phase (plan principles
1 and 6 -- VSA aids an existing structural read, it never stands alone).
"""

from __future__ import annotations

from typing import Literal

import pandas as pd

from tradingagents.dataflows.wyckoff_range import TradingRange
from tradingagents.dataflows.wyckoff_vsa_range_signals import (
    test_bar,
    upthrust_shakeout_on_volume,
)
from tradingagents.dataflows.wyckoff_vsa_signals import (
    climax_bar,
    effort_no_result_down,
    effort_no_result_up,
    no_demand,
    no_supply,
    stopping_volume,
)

PhaseBias = Literal["bullish", "bearish"]

PER_SIGNAL_DELTA = 0.05
MAX_TOTAL_DELTA = 0.15

_BAR_ONLY_DETECTORS = (
    no_demand,
    no_supply,
    stopping_volume,
    climax_bar,
    effort_no_result_up,
    effort_no_result_down,
)
_RANGE_AWARE_DETECTORS = (test_bar, upthrust_shakeout_on_volume)


def analyze_vsa(
    df: pd.DataFrame,
    atr_value: float,
    rng: TradingRange,
    phase_bias: PhaseBias,
    curr_date: str,
) -> tuple[list[dict], float]:
    """Score VSA signals from rng.start_index through curr_date.

    Returns (vsa_signals, confidence_delta); delta is bounded to
    [-MAX_TOTAL_DELTA, +MAX_TOTAL_DELTA].
    """
    end_ts = pd.Timestamp(curr_date)
    signals: list[dict] = []
    delta = 0.0
    for i in range(rng.start_index, len(df)):
        if df.at[i, "Date"] > end_ts:
            break
        hits = [d(df, i, atr_value) for d in _BAR_ONLY_DETECTORS]
        hits += [d(df, i, atr_value, rng) for d in _RANGE_AWARE_DETECTORS]
        for hit in hits:
            if hit is None:
                continue
            direction = "confirming" if hit.native_direction == phase_bias else "contradicting"
            delta += PER_SIGNAL_DELTA if direction == "confirming" else -PER_SIGNAL_DELTA
            signals.append(
                {
                    "signal": hit.signal,
                    "date": df.at[i, "Date"].strftime("%Y-%m-%d"),
                    "direction": direction,
                    "volume_ratio": round(hit.volume_ratio, 2) if hit.volume_ratio is not None else None,
                    "evidence": [hit.evidence],
                }
            )
    bounded_delta = max(-MAX_TOTAL_DELTA, min(MAX_TOTAL_DELTA, delta))
    return signals, bounded_delta
