"""Per-bar Volume Spread Analysis (VSA) detectors: classic effort-vs-result
signals scored against ATR (spread) and 20-day average volume, each tagged
with the market direction it natively supports. wyckoff_vsa.py decides which
bars to scan and whether a hit confirms or contradicts the active Wyckoff
phase_bias; this module only answers "does this bar match this pattern."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from tradingagents.dataflows.wyckoff_range import volume_ratio

NativeDirection = Literal["bullish", "bearish"]

NARROW_SPREAD_ATR = 0.5
STOPPING_VOLUME_SPREAD_ATR = 1.5
STOPPING_VOLUME_RATIO = 2.0
LOW_VOLUME_RATIO = 1.0


@dataclass
class VsaSignal:
    signal: str
    native_direction: NativeDirection
    volume_ratio: float | None
    evidence: str


def _spread(df: pd.DataFrame, i: int) -> float:
    return float(df.at[i, "High"] - df.at[i, "Low"])


def _prev_close(df: pd.DataFrame, i: int) -> float | None:
    return float(df.at[i - 1, "Close"]) if i >= 1 else None


def no_demand(df: pd.DataFrame, i: int, atr_value: float) -> VsaSignal | None:
    prev = _prev_close(df, i)
    vr = volume_ratio(df, i)
    if prev is None or vr is None:
        return None
    close, spread = float(df.at[i, "Close"]), _spread(df, i)
    if close > prev and spread < NARROW_SPREAD_ATR * atr_value and vr < LOW_VOLUME_RATIO:
        return VsaSignal(
            "no_demand",
            "bearish",
            vr,
            f"up bar on {vr:.1f}x avg volume with a spread of only {spread:.2f} — weak buying interest",
        )
    return None


def no_supply(df: pd.DataFrame, i: int, atr_value: float) -> VsaSignal | None:
    prev = _prev_close(df, i)
    vr = volume_ratio(df, i)
    if prev is None or vr is None:
        return None
    close, spread = float(df.at[i, "Close"]), _spread(df, i)
    if close < prev and spread < NARROW_SPREAD_ATR * atr_value and vr < LOW_VOLUME_RATIO:
        return VsaSignal(
            "no_supply",
            "bullish",
            vr,
            f"down bar on {vr:.1f}x avg volume with a spread of only {spread:.2f} — weak selling pressure",
        )
    return None


def stopping_volume(df: pd.DataFrame, i: int, atr_value: float) -> VsaSignal | None:
    prev = _prev_close(df, i)
    vr = volume_ratio(df, i)
    if prev is None or vr is None:
        return None
    close = float(df.at[i, "Close"])
    high, low = float(df.at[i, "High"]), float(df.at[i, "Low"])
    spread = high - low
    if (
        close < prev
        and spread > STOPPING_VOLUME_SPREAD_ATR * atr_value
        and vr > STOPPING_VOLUME_RATIO
        and close >= (high + low) / 2
    ):
        return VsaSignal(
            "stopping_volume",
            "bullish",
            vr,
            f"wide-range down bar on {vr:.1f}x avg volume, closed in the upper half of its range — absorption of selling",
        )
    return None
