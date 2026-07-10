"""Detection of tight O'Neil flat-base consolidations."""

from __future__ import annotations

import pandas as pd

from tradingagents.dataflows.oneil_base_types import BaseCandidate, prior_uptrend

FLAT_MIN_DAYS = 25
FLAT_FORMING_MIN_DAYS = 15
FLAT_MAX_DAYS = 120
FLAT_DEPTH_RATIO = 0.15
FLAT_DEPTH_ATR = 4.0
BREAKOUT_BUFFER_ATR = 0.1


def _base_end(df: pd.DataFrame, start: int, atr_value: float) -> int:
    """Stop immediately before the first ATR-buffered close above the base high."""
    end = min(len(df) - 1, start + FLAT_MAX_DAYS - 1)
    range_high = float(df.at[start, "High"])
    for index in range(start + 1, end + 1):
        if float(df.at[index, "Close"]) > range_high + BREAKOUT_BUFFER_ATR * atr_value:
            return index - 1
        range_high = max(range_high, float(df.at[index, "High"]))
    return end


def detect_flat_base(df: pd.DataFrame, atr_value: float) -> BaseCandidate | None:
    """Return the latest shallow, post-uptrend consolidation in ``df``."""
    candidates: list[BaseCandidate] = []
    for start in range(len(df)):
        uptrend, uptrend_note = prior_uptrend(df, start, atr_value)
        if not uptrend:
            continue
        end = _base_end(df, start, atr_value)
        duration = end - start + 1
        if duration < FLAT_FORMING_MIN_DAYS:
            continue
        window = df.iloc[start : end + 1]
        range_high = float(window["High"].max())
        range_low = float(window["Low"].min())
        depth = (range_high - range_low) / range_high if range_high else 0.0
        depth_limit = max(FLAT_DEPTH_RATIO, FLAT_DEPTH_ATR * atr_value / range_high)
        if depth > depth_limit:
            continue
        high_index = int(window["High"].idxmax())
        start_date = pd.Timestamp(df.at[start, "Date"]).strftime("%Y-%m-%d")
        end_date = pd.Timestamp(df.at[end, "Date"]).strftime("%Y-%m-%d")
        pivot_date = pd.Timestamp(df.at[high_index, "Date"]).strftime("%Y-%m-%d")
        complete = duration >= FLAT_MIN_DAYS
        candidates.append(
            BaseCandidate(
                pattern_type="flat_base",
                complete=complete,
                pivot_price=range_high,
                pivot_date=pivot_date,
                complete_index=end,
                geometry={
                    "start_date": start_date,
                    "end_date": end_date,
                    "range_high": range_high,
                    "range_low": range_low,
                    "depth_pct": depth * 100,
                    "duration_days": duration,
                },
                evidence=[
                    f"Flat base held a tight {depth:.1%} range from {start_date} to {end_date} "
                    f"over {duration} trading days, with a {range_high:.2f} pivot.",
                    uptrend_note,
                ],
            )
        )
    return (
        max(
            candidates,
            key=lambda candidate: (
                candidate.complete,
                candidate.complete_index,
                candidate.geometry["start_date"],
            ),
        )
        if candidates
        else None
    )
