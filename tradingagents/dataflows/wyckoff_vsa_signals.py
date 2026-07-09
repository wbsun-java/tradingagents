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
WIDE_SPREAD_ATR = 1.2
CLIMAX_VOLUME_RATIO = 3.0
ELEVATED_VOLUME_RATIO = 1.5
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


def climax_bar(df: pd.DataFrame, i: int, atr_value: float, window: int = 10) -> VsaSignal | None:
    vr = volume_ratio(df, i)
    if vr is None or vr < CLIMAX_VOLUME_RATIO or _spread(df, i) <= WIDE_SPREAD_ATR * atr_value:
        return None
    lo = max(0, i - window)
    low_i, high_i = float(df.at[i, "Low"]), float(df.at[i, "High"])
    if low_i <= df["Low"].iloc[lo : i + 1].min():
        return VsaSignal(
            "climax_bar",
            "bullish",
            vr,
            f"{vr:.1f}x avg volume on a wide-range bar making a new {window}-bar low — capitulation",
        )
    if high_i >= df["High"].iloc[lo : i + 1].max():
        return VsaSignal(
            "climax_bar",
            "bearish",
            vr,
            f"{vr:.1f}x avg volume on a wide-range bar making a new {window}-bar high — blow-off",
        )
    return None


def effort_no_result_up(df: pd.DataFrame, i: int, atr_value: float) -> VsaSignal | None:
    vr = volume_ratio(df, i)
    spread = _spread(df, i)
    if vr is None or vr < ELEVATED_VOLUME_RATIO or not 0 < spread < NARROW_SPREAD_ATR * atr_value:
        return None
    close, low = float(df.at[i, "Close"]), float(df.at[i, "Low"])
    if (close - low) <= 0.3 * spread:
        return VsaSignal(
            "effort_no_result_up",
            "bearish",
            vr,
            f"{vr:.1f}x avg volume but closed near the bar's low — buying effort failed to produce a result",
        )
    return None


def effort_no_result_down(df: pd.DataFrame, i: int, atr_value: float) -> VsaSignal | None:
    vr = volume_ratio(df, i)
    spread = _spread(df, i)
    if vr is None or vr < ELEVATED_VOLUME_RATIO or not 0 < spread < NARROW_SPREAD_ATR * atr_value:
        return None
    close, high = float(df.at[i, "Close"]), float(df.at[i, "High"])
    if (high - close) <= 0.3 * spread:
        return VsaSignal(
            "effort_no_result_down",
            "bullish",
            vr,
            f"{vr:.1f}x avg volume but closed near the bar's high — selling effort failed to produce a result",
        )
    return None
