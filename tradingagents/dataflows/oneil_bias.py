"""Synthesizes O'Neil base-pattern analysis into tool-facing JSON."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from tradingagents.dataflows.oneil_base_patterns import (
    PatternDetection,
    arbitrate,
    detect_all,
    evaluate_candidates,
)
from tradingagents.dataflows.oneil_cup import atr, prepare_ohlcv
from tradingagents.dataflows.stockstats_utils import load_ohlcv
from tradingagents.dataflows.trend_template import relative_strength_score

SECONDARY_WEIGHT = 0.4
WEIGHT_NOTE = (
    "O'Neil base-pattern read ranks below Wyckoff but above chart patterns, trend "
    "template, and indicators; if Wyckoff phase_bias is non-neutral, it takes "
    "precedence over this result."
)
LIVE_STATUSES = {"forming", "developing", "confirmed"}


def _handle_payload(detection: PatternDetection) -> dict[str, Any] | None:
    handle = detection.candidate.handle
    if detection.candidate.pattern_type != "cup_with_handle" or handle is None:
        return None
    return {
        "start_date": handle.start_date,
        "end_date": handle.end_date,
        "low_price": round(handle.low_price, 4),
        "volume_ratio_vs_cup": (
            round(handle.volume_ratio_vs_cup, 2)
            if handle.volume_ratio_vs_cup is not None
            else None
        ),
    }


def _breakout_payload(detection: PatternDetection) -> dict[str, Any] | None:
    breakout = detection.breakout
    if breakout is None:
        return None
    return {
        "index": breakout.index,
        "date": breakout.date,
        "pivot_price": breakout.pivot_price,
        "close": breakout.close,
        "volume_ratio": breakout.volume_ratio,
        "volume_confirmed": breakout.volume_confirmed,
    }


def _primary_payload(detection: PatternDetection) -> dict[str, Any]:
    candidate = detection.candidate
    return {
        "pattern_type": candidate.pattern_type,
        "status": detection.status,
        "pivot_price": candidate.pivot_price,
        "pivot_date": candidate.pivot_date,
        "geometry": candidate.geometry,
        "handle": _handle_payload(detection),
        "breakout": _breakout_payload(detection),
    }


def _result(primary: PatternDetection | None, others: list[PatternDetection], curr_date: str) -> dict[str, Any]:
    if primary is None:
        return {
            "primary_pattern": None,
            "other_detections": [],
            "setup_bias": "neutral",
            "confidence": 0.0,
            "secondary_weight": SECONDARY_WEIGHT,
            "weight_note": WEIGHT_NOTE,
            "evidence": [],
            "analysis_date": curr_date,
        }
    evidence = list(primary.candidate.evidence)
    if primary.breakout is not None:
        breakout = primary.breakout
        volume = "volume-confirmed" if breakout.volume_confirmed else "low-volume"
        evidence.append(
            f"{volume.capitalize()} breakout on {breakout.date} at {breakout.close:.2f} "
            f"versus pivot {breakout.pivot_price:.2f}, with {breakout.volume_ratio:.2f}x average volume."
        )
    return {
        "primary_pattern": _primary_payload(primary),
        "other_detections": [
            {"pattern_type": item.candidate.pattern_type, "status": item.status, "confidence": item.confidence}
            for item in others
        ],
        "setup_bias": "bullish" if primary.status in LIVE_STATUSES else "neutral",
        "confidence": primary.confidence,
        "secondary_weight": SECONDARY_WEIGHT,
        "weight_note": WEIGHT_NOTE,
        "evidence": evidence,
        "analysis_date": curr_date,
    }


def analyze_oneil_setup_from_data(data: pd.DataFrame, curr_date: str, look_back_days: int = 420, rs_score: float | None = None) -> dict[str, Any]:
    """Analyze an OHLCV frame and return a JSON-serializable O'Neil setup read."""
    df = prepare_ohlcv(data, curr_date, look_back_days)
    atr_value = float(atr(df).iloc[-1])
    candidates = detect_all(df, atr_value)
    primary, others = arbitrate(evaluate_candidates(df, candidates, atr_value, rs_score))
    return _result(primary, others, curr_date)


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
