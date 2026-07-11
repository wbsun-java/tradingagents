"""Synthetic OHLCV builders for O'Neil flat-base continuation-chain tests."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _frame(closes: list[float], volumes: list[float]) -> pd.DataFrame:
    prices = np.asarray(closes, dtype=float)
    return pd.DataFrame({
        "Date": pd.bdate_range("2024-01-02", periods=len(prices)),
        "Open": prices,
        "High": prices + 0.5,
        "Low": prices - 0.5,
        "Close": prices,
        "Volume": volumes,
    })


def _flat_base_segment(
    start_price: float, ramp_gain: float, tight_days: int = 30, depth: float = 0.08
) -> tuple[list[float], list[float], float]:
    ramp = np.linspace(start_price, start_price + ramp_gain, 60).tolist()
    peak = start_price + ramp_gain + 3.0
    angles = np.linspace(0, 6 * np.pi, tight_days - 1)
    range_closes = (peak * (1 - depth * (0.55 + 0.45 * np.sin(angles)))).tolist()
    closes = ramp + [peak] + range_closes
    vols = [1_000_000.0] * 61 + [700_000.0] * (tight_days - 1)
    return closes, vols, peak


def chained_flat_bases(advance_target_ratio: float) -> tuple[pd.DataFrame, int, float, float]:
    """Two flat bases chained by a confirmed breakout and an advance.

    ``advance_target_ratio`` sets the second base's gain over the first base's
    pivot: 1.25 yields a confirmed continuation (+25%); 1.08 yields a
    premature one (+8%). Returns (df, before_index, peak1, peak2) where
    ``before_index`` is the second base's peak index (its start_index).
    """
    closes1, vols1, peak1 = _flat_base_segment(100.0, 40.0)
    breakout_price = peak1 * 1.05
    post = [breakout_price, breakout_price * 1.01, breakout_price * 1.02]
    postv = [1_600_000.0] * 3
    advance = np.linspace(post[-1], peak1 * advance_target_ratio, 20).tolist()
    post += advance
    postv += [1_000_000.0] * 20
    peak2 = post[-1] + 3.0
    angles2 = np.linspace(0, 6 * np.pi, 29)
    range2 = (peak2 * (1 - 0.08 * (0.55 + 0.45 * np.sin(angles2)))).tolist()
    closes2 = [peak2] + range2
    vols2 = [1_000_000.0] + [700_000.0] * 29
    df = _frame(closes1 + post + closes2, vols1 + postv + vols2)
    before_index = len(closes1) + len(post)
    return df, before_index, peak1, peak2


def single_flat_base() -> pd.DataFrame:
    """One flat base with no earlier stage in its available history."""
    closes, vols, _ = _flat_base_segment(100.0, 40.0)
    return _frame(closes, vols)
