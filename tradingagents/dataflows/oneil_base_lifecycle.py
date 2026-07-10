"""Lifecycle checks shared by O'Neil base-pattern evaluation."""

import pandas as pd

from tradingagents.dataflows.oneil_base_types import BASE_MAX_AGE_DAYS, BaseCandidate
from tradingagents.dataflows.oneil_breakout import BREAKOUT_BUFFER_ATR


def base_is_stale(candidate: BaseCandidate, last_bar: int) -> bool:
    """Return whether a candidate exceeds O'Neil's 65-week age cap."""
    return bool(
        candidate.start_index is not None
        and last_bar - candidate.start_index > BASE_MAX_AGE_DAYS
    )


def base_structure_broken(
    df: pd.DataFrame, candidate: BaseCandidate, atr_value: float
) -> bool:
    """Return whether a completed base later closed below its defining low."""
    return bool(
        candidate.complete
        and candidate.base_low_price is not None
        and any(
            float(df.at[index, "Close"])
            < candidate.base_low_price - BREAKOUT_BUFFER_ATR * atr_value
            for index in range(candidate.complete_index + 1, len(df))
        )
    )
