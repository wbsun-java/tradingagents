"""Pocket Pivot qualitative context flags, per Kacher & Morales's buyability
guidelines. These never suppress a detected event -- code reports structure,
the LLM/user judges buyability. See
docs/superpowers/specs/2026-07-09-pocket-pivot-design.md.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from tradingagents.dataflows.pocket_pivot_signals import sma

DOWNTREND_LOOKBACK_BARS = 105
V_SHAPE_LOOKBACK = 10
V_SHAPE_UNDERCUT_ATR = 1.0
V_SHAPE_REVERSAL_BARS = 3
EXTENSION_ATR_THRESHOLD = 1.5


def multi_month_downtrend(df: pd.DataFrame, i: int) -> bool | None:
    if i < DOWNTREND_LOOKBACK_BARS:
        return None
    return float(df.at[i, "Close"]) < float(df.at[i - DOWNTREND_LOOKBACK_BARS, "Close"])


def ma_position(df: pd.DataFrame, i: int) -> dict[str, Any]:
    close = float(df.at[i, "Close"])
    sma50, sma200 = sma(df["Close"], 50), sma(df["Close"], 200)
    sma50_now = float(sma50.iloc[i]) if not pd.isna(sma50.iloc[i]) else None
    sma200_now = float(sma200.iloc[i]) if not pd.isna(sma200.iloc[i]) else None
    return {
        "above_sma50": close > sma50_now if sma50_now is not None else None,
        "above_sma200": close > sma200_now if sma200_now is not None else None,
        "sma50": sma50_now,
        "sma200": sma200_now,
    }


def v_shape_risk(df: pd.DataFrame, i: int, ma_period: int, atr_value: float) -> bool:
    ma_series = sma(df["Close"], ma_period)
    lo = max(0, i - V_SHAPE_LOOKBACK)
    trough_idx, trough_close = None, None
    for j in range(lo, i):
        if pd.isna(ma_series.iloc[j]):
            continue
        close = float(df.at[j, "Close"])
        if trough_close is None or close < trough_close:
            trough_close, trough_idx = close, j
    if trough_idx is None:
        return False
    undercut = float(ma_series.iloc[trough_idx]) - trough_close
    reversal_bars = i - trough_idx
    return undercut > V_SHAPE_UNDERCUT_ATR * atr_value and reversal_bars <= V_SHAPE_REVERSAL_BARS


def extended_from_ma(df: pd.DataFrame, i: int, ma_period: int, atr_value: float) -> bool | None:
    if ma_period != 10:
        return None
    sma10 = sma(df["Close"], 10)
    if pd.isna(sma10.iloc[i]) or atr_value == 0:
        return None
    close = float(df.at[i, "Close"])
    return (close - float(sma10.iloc[i])) / atr_value > EXTENSION_ATR_THRESHOLD


def build_context(df: pd.DataFrame, i: int, ma_period: int, atr_value: float) -> dict[str, Any]:
    context: dict[str, Any] = {"multi_month_downtrend": multi_month_downtrend(df, i)}
    context.update(ma_position(df, i))
    context["v_shape_risk"] = v_shape_risk(df, i, ma_period, atr_value)
    context["extended_from_ma"] = extended_from_ma(df, i, ma_period, atr_value)
    return context
