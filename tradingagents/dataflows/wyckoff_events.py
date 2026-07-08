"""Direction-parameterized Wyckoff event/phase detection.

Accumulation and distribution are mirror-image processes: the same climax ->
reaction -> test -> spring/upthrust -> break -> last-point sequence, just
flipped around the opposite boundary. Implemented once here, keyed by
``direction``, so wyckoff_accumulation.py / wyckoff_distribution.py stay thin.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from tradingagents.dataflows.wyckoff_range import TradingRange, volume_ratio

Direction = Literal["accumulation", "distribution"]
Phase = Literal["A", "B", "C", "D", "E", "undetermined"]

_NAMES = {
    "accumulation": {
        "preliminary": "preliminary_support", "climax": "selling_climax", "rally": "automatic_rally",
        "test1": "secondary_test", "spring": "spring", "test2": "test", "strength": "sign_of_strength",
        "last_point": "last_point_of_support", "backup": "back_up",
    },
    "distribution": {
        "preliminary": "preliminary_supply", "climax": "buying_climax", "rally": "automatic_reaction",
        "test1": "secondary_test", "spring": "upthrust_after_distribution", "test2": "test",
        "strength": "sign_of_weakness", "last_point": "last_point_of_supply", "backup": "upthrust",
    },
}


@dataclass
class WyckoffEvent:
    event: str
    date: str
    price: float
    volume_ratio: float | None
    evidence: list[str] = field(default_factory=list)


def _bar(df: pd.DataFrame, index: int) -> tuple[str, float]:
    return df.at[index, "Date"].strftime("%Y-%m-%d"), float(df.at[index, "Close"])


def detect_events(
    df: pd.DataFrame, atr_value: float, rng: TradingRange, direction: Direction
) -> tuple[list[WyckoffEvent], Phase]:
    names = _NAMES[direction]
    accum = direction == "accumulation"
    sign = 1 if accum else -1
    boundary = rng.range_low if accum else rng.range_high
    opposite = rng.range_high if accum else rng.range_low
    width = abs(opposite - boundary)
    buffer = atr_value * 0.2
    tolerance = max(atr_value * 0.6, boundary * 0.02)
    events: list[WyckoffEvent] = []

    # A real capitulation bar often prints a bit away from where the range
    # eventually settles (price keeps drifting before finding support), so it
    # can fall outside the boundary cluster's tight price tolerance and outside
    # rng's own touch pivots. Scan raw bars across the whole touch span instead
    # of only the pivots that happen to define the boundary.
    last_touch = max(p.index for p in rng.high_touches + rng.low_touches)
    climax_window = range(max(0, rng.start_index - 20), min(len(df), last_touch + 20))
    climax_candidates = [
        i for i in climax_window
        if (volume_ratio(df, i) or 0) >= 1.8
        and abs(float(df.at[i, "Low" if accum else "High"]) - boundary) <= width
    ]
    # Earliest qualifying bar, not the single loudest one: a climax is what
    # kicks the range off, so a later, even-louder bar (e.g. a violent Spring
    # deep into Phase C) must not be mistaken for it.
    climax_idx = climax_candidates[0] if climax_candidates else None
    if climax_idx is None:
        return events, "undetermined"
    for i in range(max(0, climax_idx - 15), climax_idx):
        side = float(df.at[i, "Low" if accum else "High"])
        if (volume_ratio(df, i) or 0) >= 1.3 and abs(side - boundary) <= tolerance * 2:
            date, close = _bar(df, i)
            events.append(WyckoffEvent(names["preliminary"], date, close, volume_ratio(df, i), ["An early elevated-volume approach to the boundary preceded the climax."]))
            break
    climax_date, _climax_close = _bar(df, climax_idx)
    climax_price = float(df.at[climax_idx, "Low" if accum else "High"])
    climax_vr = volume_ratio(df, climax_idx)
    events.append(WyckoffEvent(names["climax"], climax_date, climax_price, climax_vr, [f"Volume was {climax_vr:.1f}x the 20-day average as price reached {climax_price:.2f}, near the boundary."]))

    reaction = df.iloc[climax_idx + 1 : min(len(df), climax_idx + 40)]
    if reaction.empty:
        return events, "A"
    rally_idx = int((reaction["Close"] * sign).idxmax())
    rally_date, rally_close = _bar(df, rally_idx)
    events.append(WyckoffEvent(names["rally"], rally_date, rally_close, volume_ratio(df, rally_idx), [f"Price swung to {rally_close:.2f} within {rally_idx - climax_idx} bars after the climax."]))

    st = next((i for i in range(rally_idx + 1, min(len(df), rally_idx + 60)) if abs(float(df.at[i, "Low" if accum else "High"]) - boundary) <= tolerance and (float(df.at[i, "Low"]) >= boundary - buffer if accum else float(df.at[i, "High"]) <= boundary + buffer) and (volume_ratio(df, i) or 0) < (climax_vr or 999)), None)
    if st is None:
        return events, "A"
    date, _ = _bar(df, st)
    events.append(WyckoffEvent(names["test1"], date, float(df.at[st, "Low" if accum else "High"]), volume_ratio(df, st), [f"Price returned near {boundary:.2f} on lighter volume than the climax, without breaking it."]))

    spring = next((i for i in range(st + 1, len(df)) if (float(df.at[i, "Low"]) < rng.range_low - buffer if accum else float(df.at[i, "High"]) > rng.range_high + buffer) and (float(df.at[i, "Close"]) >= rng.range_low if accum else float(df.at[i, "Close"]) <= rng.range_high)), None)
    if spring is None:
        return events, "B"
    date, close = _bar(df, spring)
    spring_vr = volume_ratio(df, spring)
    volume_note = (
        f"on heavy volume ({spring_vr:.1f}x average), consistent with a violent terminal shakeout rather than quiet absorption"
        if spring_vr is not None and spring_vr >= 1.5
        else f"on light volume ({spring_vr:.1f}x average), consistent with a classic quiet spring" if spring_vr is not None
        else "with no volume data available"
    )
    events.append(WyckoffEvent(names["spring"], date, close, spring_vr, [f"Price pierced the range boundary intrabar and closed back inside it, undermining the breakout, {volume_note}."]))

    test2 = next((i for i in range(spring + 1, min(len(df), spring + 60)) if abs(float(df.at[i, "Low" if accum else "High"]) - boundary) <= tolerance * 1.5 and (float(df.at[i, "Low"]) >= float(df.at[spring, "Low"]) if accum else float(df.at[i, "High"]) <= float(df.at[spring, "High"]))), None)
    if test2 is not None:
        date, close = _bar(df, test2)
        events.append(WyckoffEvent(names["test2"], date, close, volume_ratio(df, test2), ["Price retested the extreme without breaking it, on quieter volume."]))

    sos = next((i for i in range((test2 or spring) + 1, len(df)) if (float(df.at[i, "Close"]) > rng.range_high + buffer if accum else float(df.at[i, "Close"]) < rng.range_low - buffer)), None)
    if sos is None:
        return events, "C"
    date, close = _bar(df, sos)
    sos_vr = volume_ratio(df, sos)
    events.append(WyckoffEvent(names["strength"], date, close, sos_vr, [f"Price closed beyond {opposite:.2f} with {'confirming' if (sos_vr or 0) >= 1.3 else 'unremarkable'} volume."]))

    lps = next((i for i in range(sos + 1, min(len(df), sos + 40)) if (float(df.at[i, "Low"]) >= rng.range_high - buffer if accum else float(df.at[i, "High"]) <= rng.range_low + buffer) and abs(float(df.at[i, "Close"]) - opposite) <= tolerance * 1.5), None)
    if lps is None:
        return events, "D"
    date, close = _bar(df, lps)
    events.append(WyckoffEvent(names["last_point"], date, close, volume_ratio(df, lps), ["The pullback held the former boundary, now acting as support/resistance in the new direction."]))

    backup = next((i for i in range(lps + 1, min(len(df), lps + 40)) if (float(df.at[i, "Close"]) > close if accum else float(df.at[i, "Close"]) < close)), None)
    if backup is None:
        return events, "D"
    date, close = _bar(df, backup)
    events.append(WyckoffEvent(names["backup"], date, close, volume_ratio(df, backup), ["Price extended past the last point of support/supply, confirming the new trend is underway."]))
    return events, "E"


_PHASE_SCORE: dict[Phase, float] = {"undetermined": 0.0, "A": 0.0, "B": 0.15, "C": 0.3, "D": 0.45, "E": 0.55}


def confidence_for(events: list[WyckoffEvent], phase: Phase) -> float:
    """Data-driven confidence: more corroborating events and a later phase raise it."""
    base = 0.35
    event_score = min(len(events), 8) * 0.04
    quality_score = sum(1 for e in events if e.volume_ratio is not None and (e.volume_ratio >= 1.3 or e.volume_ratio <= 0.8)) * 0.02
    return round(min(0.95, base + _PHASE_SCORE.get(phase, 0.0) + event_score + quality_score), 2)
