"""Detection of O'Neil-style ascending bases."""

from __future__ import annotations

import pandas as pd

from tradingagents.dataflows.chart_patterns import Pivot, find_pivots
from tradingagents.dataflows.oneil_base_types import BaseCandidate, prior_uptrend

ASC_MIN_DAYS = 40
ASC_MAX_DAYS = 100
ASC_MIN_PULLBACK_RATIO = 0.05
ASC_MIN_PULLBACK_ATR = 1.5
ASC_MAX_PULLBACK_RATIO = 0.20
ASC_MAX_PULLBACK_ATR = 5.0


def _alternating_runs(pivots: list[Pivot]) -> list[list[Pivot]]:
    """Split settled pivots into maximal high/low alternating runs."""
    runs: list[list[Pivot]] = []
    run: list[Pivot] = []
    for pivot in pivots:
        if run and pivot.kind == run[-1].kind:
            if len(run) >= 4:
                runs.append(run)
            run = [pivot]
        else:
            run.append(pivot)
    if len(run) >= 4:
        runs.append(run)
    return runs


def _pullbacks_valid(pairs: list[tuple[Pivot, Pivot]], atr_value: float) -> bool:
    highs = [high.price for high, _ in pairs]
    lows = [low.price for _, low in pairs]
    if highs != sorted(set(highs)) or lows != sorted(set(lows)):
        return False
    for high, low in pairs:
        depth = (high.price - low.price) / high.price
        minimum = max(
            ASC_MIN_PULLBACK_RATIO,
            ASC_MIN_PULLBACK_ATR * atr_value / high.price,
        )
        maximum = max(
            ASC_MAX_PULLBACK_RATIO,
            ASC_MAX_PULLBACK_ATR * atr_value / high.price,
        )
        if not minimum <= depth <= maximum:
            return False
    return True


def _volume_note(df: pd.DataFrame, pairs: list[tuple[Pivot, Pivot]]) -> str:
    means = [float(df["Volume"].iloc[high.index : low.index + 1].mean()) for high, low in pairs]
    contracted = all(
        current < previous for previous, current in zip(means, means[1:], strict=False)
    )
    values = "; ".join(
        f"{high.date} high at {high.price:.2f} to {low.date} low at {low.price:.2f}: {mean:,.0f}"
        for (high, low), mean in zip(pairs, means, strict=True)
    )
    behavior = "contracted successively" if contracted else "did not contract successively"
    return f"Mean volume across the pullbacks {behavior} ({values}); contraction strengthens the read but is not required."


def _build(
    df: pd.DataFrame,
    pairs: list[tuple[Pivot, Pivot]],
    atr_value: float,
) -> BaseCandidate | None:
    duration = pairs[-1][1].index - pairs[0][0].index
    if not ASC_MIN_DAYS <= duration <= ASC_MAX_DAYS:
        return None
    if not _pullbacks_valid(pairs, atr_value):
        return None
    first_high = pairs[0][0]
    uptrend, uptrend_note = prior_uptrend(df, first_high.index, atr_value)
    if not uptrend:
        return None
    pullbacks = []
    evidence = [
        f"The prior-uptrend gate passed into H1 on {first_high.date} at {first_high.price:.2f}: "
        f"{uptrend_note}"
    ]
    for number, (high, low) in enumerate(pairs, 1):
        depth_pct = (high.price - low.price) / high.price * 100
        pullbacks.append(
            {
                "high": {"date": high.date, "price": high.price},
                "low": {"date": low.date, "price": low.price},
                "depth_pct": depth_pct,
            }
        )
        evidence.append(
            f"Pullback {number} ran from the {high.date} high at {high.price:.2f} to "
            f"the {low.date} low at {low.price:.2f}, a {depth_pct:.1f}% decline."
        )
    points = "; ".join(
        f"H{number} {high.date} at {high.price:.2f} and L{number} {low.date} at {low.price:.2f}"
        for number, (high, low) in enumerate(pairs, 1)
    )
    evidence.extend(
        [f"The strictly ascending high-and-low structure is {points}.", _volume_note(df, pairs)]
    )
    pivot = pairs[-1][0]
    return BaseCandidate(
        pattern_type="ascending_base",
        complete=len(pairs) == 3,
        pivot_price=pivot.price,
        pivot_date=pivot.date,
        complete_index=pairs[-1][1].index,
        geometry={
            "pullbacks": pullbacks,
            "pullbacks_completed": len(pairs),
            "duration_days": duration,
        },
        evidence=evidence,
    )


def detect_ascending_base(df: pd.DataFrame, atr_value: float) -> BaseCandidate | None:
    """Return the most recent complete or two-pullback ascending base."""
    candidates: list[BaseCandidate] = []
    for run in _alternating_runs(find_pivots(df)):
        sequence = run[1:] if run[0].kind == "low" else run
        complete_windows = [sequence[index : index + 6] for index in range(len(sequence) - 5)]
        for window in complete_windows:
            if [pivot.kind for pivot in window] == ["high", "low"] * 3:
                candidate = _build(
                    df, list(zip(window[::2], window[1::2], strict=True)), atr_value
                )
                if candidate is not None:
                    candidates.append(candidate)
        if sum(pivot.kind == "low" for pivot in sequence) == 2:
            window = sequence[:4]
            if [pivot.kind for pivot in window] == ["high", "low"] * 2:
                candidate = _build(
                    df, list(zip(window[::2], window[1::2], strict=True)), atr_value
                )
                if candidate is not None:
                    candidates.append(candidate)
    return max(candidates, key=lambda item: item.complete_index) if candidates else None
