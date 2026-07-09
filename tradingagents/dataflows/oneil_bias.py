"""Synthesizes the O'Neil cup-with-handle read into the tool-facing JSON.

secondary_weight is a fixed project policy constant (deliberately below
Wyckoff's dominant_weight of 0.6), not derived from this call's data.
See ONEIL_CANSLIM_ANALYSIS_PLAN.md.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from tradingagents.dataflows.oneil_breakout import (
    BreakoutEvent,
    compute_confidence,
    determine_status,
    find_breakout,
)
from tradingagents.dataflows.oneil_cup import CupCandidate, atr, detect_cup, prepare_ohlcv
from tradingagents.dataflows.oneil_handle import HandleCandidate, detect_handle
from tradingagents.dataflows.stockstats_utils import load_ohlcv
from tradingagents.dataflows.trend_template import relative_strength_score

SECONDARY_WEIGHT = 0.4
WEIGHT_NOTE = (
    "O'Neil cup-with-handle read ranks below Wyckoff but above chart patterns, trend "
    "template, and indicators; if Wyckoff phase_bias is non-neutral, it takes "
    "precedence over this result."
)


def _payload(cup: CupCandidate | None, handle: HandleCandidate | None, breakout: BreakoutEvent | None, status: str, bias: str, confidence: float) -> dict[str, Any]:
    evidence: list[str] = []
    cup_dict = None
    if cup is not None:
        evidence.extend(cup.evidence)
        cup_dict = {
            "start_date": cup.left_high_date, "left_high": round(cup.left_high_price, 4),
            "low_date": cup.low_date, "low_price": round(cup.low_price, 4),
            "right_high_date": cup.right_high_date,
            "depth_pct": round(cup.depth_pct * 100, 2), "duration_days": cup.duration_days,
        }
    handle_dict = None
    if handle is not None:
        evidence.extend(handle.evidence)
        handle_dict = {
            "start_date": handle.start_date, "end_date": handle.end_date,
            "low_price": round(handle.low_price, 4),
            "volume_ratio_vs_cup": round(handle.volume_ratio_vs_cup, 2) if handle.volume_ratio_vs_cup is not None else None,
        }
    breakout_dict = None
    if breakout is not None:
        confirmed_word = "Volume-confirmed" if breakout.volume_confirmed else "Unconfirmed (low-volume)"
        evidence.append(f"{confirmed_word} breakout on {breakout.date}: close {breakout.close:.2f} vs. pivot {breakout.pivot_price:.2f}, volume {breakout.volume_ratio:.2f}x average.")
        breakout_dict = {"date": breakout.date, "pivot_price": breakout.pivot_price, "close": breakout.close, "volume_ratio": breakout.volume_ratio}
    return {
        "cup": cup_dict, "handle": handle_dict, "breakout": breakout_dict,
        "status": status, "setup_bias": bias, "confidence": confidence,
        "secondary_weight": SECONDARY_WEIGHT, "weight_note": WEIGHT_NOTE, "evidence": evidence,
    }


def analyze_oneil_setup_from_data(data: pd.DataFrame, curr_date: str, look_back_days: int = 420, rs_score: float | None = None) -> dict[str, Any]:
    """Analyze an OHLCV frame and return a JSON-serializable O'Neil setup read."""
    df = prepare_ohlcv(data, curr_date, look_back_days)
    atr_value = float(atr(df).iloc[-1])
    cup = detect_cup(df, atr_value)
    handle = detect_handle(df, cup, atr_value) if cup is not None else None
    breakout = find_breakout(df, cup, handle, atr_value) if handle is not None and handle.valid else None
    status = determine_status(cup, handle, breakout, df, atr_value)
    bias = "bullish" if status in ("forming", "developing", "confirmed") else "neutral"
    confidence = compute_confidence(status, handle, breakout, rs_score)
    result = _payload(cup, handle, breakout, status, bias, confidence)
    result["analysis_date"] = curr_date
    return result


def analyze_oneil_setup(symbol: str, curr_date: str, look_back_days: int = 420, benchmark: str = "SPY") -> str:
    """Load cutoff-safe OHLCV and return a formatted JSON O'Neil setup report."""
    data = load_ohlcv(symbol, curr_date)
    prepared = prepare_ohlcv(data, curr_date, look_back_days)
    try:
        benchmark_data = load_ohlcv(benchmark, curr_date) if benchmark else None
        benchmark_df = prepare_ohlcv(benchmark_data, curr_date, look_back_days) if benchmark_data is not None else None
    except ValueError:
        benchmark_df = None
    rs_score = relative_strength_score(prepared, benchmark_df) if benchmark_df is not None else None
    result = analyze_oneil_setup_from_data(data, curr_date, look_back_days, rs_score)
    result["symbol"] = symbol.upper()
    return json.dumps(result, indent=2, ensure_ascii=False)
