"""Range-aware VSA detectors: test_bar and upthrust/shakeout-on-volume need
the active Wyckoff trading range's boundaries, unlike the bar-only detectors
in wyckoff_vsa_signals.py. Split out to keep both files under the
150-line-per-file cap.
"""

from __future__ import annotations

import pandas as pd

from tradingagents.dataflows.wyckoff_range import TradingRange, volume_ratio
from tradingagents.dataflows.wyckoff_vsa_signals import (
    LOW_VOLUME_RATIO,
    NARROW_SPREAD_ATR,
    WIDE_SPREAD_ATR,
    VsaSignal,
    _spread,
)

ABOVE_AVERAGE_VOLUME_RATIO = 1.3


def test_bar(df: pd.DataFrame, i: int, atr_value: float, rng: TradingRange) -> VsaSignal | None:
    vr = volume_ratio(df, i)
    spread = _spread(df, i)
    if vr is None or vr >= LOW_VOLUME_RATIO or spread >= NARROW_SPREAD_ATR * atr_value:
        return None
    tolerance = max(atr_value * 0.6, rng.range_low * 0.02)
    low, high, close = float(df.at[i, "Low"]), float(df.at[i, "High"]), float(df.at[i, "Close"])
    if abs(low - rng.range_low) <= tolerance and (close - low) <= 0.3 * spread:
        return VsaSignal(
            "test_bar", "bullish", vr,
            f"quiet retest near {rng.range_low:.2f} on {vr:.1f}x avg volume, closed off the low",
        )
    if abs(high - rng.range_high) <= tolerance and (high - close) <= 0.3 * spread:
        return VsaSignal(
            "test_bar", "bearish", vr,
            f"quiet retest near {rng.range_high:.2f} on {vr:.1f}x avg volume, closed off the high",
        )
    return None


def upthrust_shakeout_on_volume(df: pd.DataFrame, i: int, atr_value: float, rng: TradingRange) -> VsaSignal | None:
    vr = volume_ratio(df, i)
    if vr is None or vr < ABOVE_AVERAGE_VOLUME_RATIO or _spread(df, i) <= WIDE_SPREAD_ATR * atr_value:
        return None
    buffer = atr_value * 0.2
    low, high, close = float(df.at[i, "Low"]), float(df.at[i, "High"]), float(df.at[i, "Close"])
    if low < rng.range_low - buffer and close >= rng.range_low:
        return VsaSignal(
            "upthrust_shakeout_on_volume", "bullish", vr,
            f"pierced {rng.range_low:.2f} intrabar on {vr:.1f}x avg volume and closed back inside the range — shakeout, not a breakdown",
        )
    if high > rng.range_high + buffer and close <= rng.range_high:
        return VsaSignal(
            "upthrust_shakeout_on_volume", "bearish", vr,
            f"pierced {rng.range_high:.2f} intrabar on {vr:.1f}x avg volume and closed back inside the range — upthrust, not a breakout",
        )
    return None
