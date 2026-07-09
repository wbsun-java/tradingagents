"""Synthesizes the accumulation/distribution reads into the tool-facing JSON.

Because ``wyckoff_range.detect_trading_range`` returns a single range with a
single ``prior_trend``, at most one of accumulation/distribution can ever
qualify for it (accumulation requires a prior downtrend, distribution a prior
uptrend) — so there is no tie to break, only "found a read" or "neutral".
``dominant_weight`` is a fixed project policy constant, not derived from this
call's data; see WYCKOFF_ANALYSIS_PLAN.md.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Literal

import pandas as pd

from tradingagents.dataflows.stockstats_utils import load_ohlcv
from tradingagents.dataflows.wyckoff_accumulation import AccumulationResult, analyze_accumulation
from tradingagents.dataflows.wyckoff_distribution import DistributionResult, analyze_distribution
from tradingagents.dataflows.wyckoff_range import atr, detect_trading_range, prepare_ohlcv
from tradingagents.dataflows.wyckoff_vsa import analyze_vsa

DOMINANT_WEIGHT = 0.6
WEIGHT_NOTE = (
    "Wyckoff structural reading anchors the technical verdict; other technical "
    "evidence may adjust confidence within this direction but must not override "
    "it unless phase_bias is neutral/undetermined."
)
_STATUS_BY_PHASE = {
    "undetermined": "forming", "A": "forming", "B": "forming",
    "C": "developing", "D": "confirmed", "E": "confirmed",
}


def _neutral() -> dict[str, Any]:
    return {
        "symbol": "",
        "trading_range": {
            "kind": "none", "range_high": None, "range_low": None,
            "start_date": None, "status": "forming",
        },
        "events": [],
        "current_phase": "undetermined",
        "phase_bias": "neutral",
        "confidence": 0.0,
        "dominant_weight": DOMINANT_WEIGHT,
        "weight_note": WEIGHT_NOTE,
    }


def _payload(kind: Literal["accumulation", "distribution"], rng, result: AccumulationResult | DistributionResult) -> dict[str, Any]:
    return {
        "symbol": "",
        "trading_range": {
            "kind": kind,
            "range_high": round(rng.range_high, 4),
            "range_low": round(rng.range_low, 4),
            "start_date": rng.start_date,
            "status": _STATUS_BY_PHASE.get(result.phase, "forming"),
        },
        "events": [asdict(e) for e in result.events],
        "current_phase": result.phase,
        "phase_bias": "bullish" if kind == "accumulation" else "bearish",
        "confidence": result.confidence,
        "dominant_weight": DOMINANT_WEIGHT,
        "weight_note": WEIGHT_NOTE,
    }


def analyze_wyckoff_structure_from_data(
    data: pd.DataFrame, curr_date: str, look_back_days: int = 504
) -> dict[str, Any]:
    """Analyze an OHLCV frame and return a JSON-serializable Wyckoff structure read."""
    df = prepare_ohlcv(data, curr_date, look_back_days)
    atr_value = float(atr(df).iloc[-1])
    rng = detect_trading_range(df, atr_value)
    accumulation = analyze_accumulation(df, atr_value, rng)
    distribution = analyze_distribution(df, atr_value, rng)

    result = {"analysis_date": curr_date}
    if accumulation is not None:
        result.update(_payload("accumulation", rng, accumulation))
    elif distribution is not None:
        result.update(_payload("distribution", rng, distribution))
    else:
        result.update(_neutral())
        return result

    vsa_signals, delta = analyze_vsa(df, atr_value, rng, result["phase_bias"], curr_date)
    result["vsa_signals"] = vsa_signals
    result["vsa_confidence_delta"] = round(delta, 4)
    result["confidence"] = round(max(0.0, min(1.0, result["confidence"] + delta)), 2)
    return result


def analyze_wyckoff_structure(symbol: str, curr_date: str, look_back_days: int = 504) -> str:
    """Load cutoff-safe OHLCV and return a formatted JSON Wyckoff structure report."""
    data = load_ohlcv(symbol, curr_date)
    result = analyze_wyckoff_structure_from_data(data, curr_date, look_back_days)
    result["symbol"] = symbol.upper()
    return json.dumps(result, indent=2, ensure_ascii=False)
