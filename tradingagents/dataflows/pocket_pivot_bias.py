"""Pocket Pivot orchestrator: assembles the tool-facing JSON from the core
detector and context flags. Standalone from Wyckoff/O'Neil -- no precedence
wiring. See docs/superpowers/specs/2026-07-09-pocket-pivot-design.md.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from tradingagents.dataflows.pocket_pivot_context import build_context
from tradingagents.dataflows.pocket_pivot_signals import (
    MA_PERIODS,
    PocketPivotEvent,
    atr,
    find_pocket_pivots,
    prepare_ohlcv,
)
from tradingagents.dataflows.stockstats_utils import load_ohlcv

ACTIVE_WINDOW_DAYS = 10
LIMITATIONS = (
    "Fundamentals strength and wedge-pattern geometry are not evaluated by "
    "this tool; combine with the Fundamentals Analyst's read and visual "
    "chart review."
)


def _event_dict(df: pd.DataFrame, event: PocketPivotEvent, atr_value: float) -> dict[str, Any]:
    return {
        "date": event.date,
        "ma_period": event.ma_period,
        "close": round(event.close, 4),
        "ma_value": round(event.ma_value, 4),
        "volume": event.volume,
        "highest_down_volume_10d": event.highest_down_volume_10d,
        "gap_up": event.gap_up,
        "context": build_context(df, event.index, event.ma_period, atr_value),
        "evidence": event.evidence,
    }


def analyze_pocket_pivots_from_data(
    data: pd.DataFrame, curr_date: str, look_back_days: int = 320
) -> dict[str, Any]:
    """Analyze an OHLCV frame and return a JSON-serializable pocket pivot read."""
    df = prepare_ohlcv(data, curr_date, look_back_days)
    atr_value = float(atr(df).iloc[-1])
    events = find_pocket_pivots(df, atr_value, MA_PERIODS)
    event_dicts = [_event_dict(df, e, atr_value) for e in events]
    most_recent = event_dicts[-1]["date"] if event_dicts else None
    active = bool(events) and (len(df) - 1 - events[-1].index) <= ACTIVE_WINDOW_DAYS
    return {
        "analysis_date": curr_date,
        "events": event_dicts,
        "active": active,
        "most_recent_event_date": most_recent,
        "limitations": LIMITATIONS,
    }


def analyze_pocket_pivots(symbol: str, curr_date: str, look_back_days: int = 320) -> str:
    """Load cutoff-safe OHLCV and return a formatted JSON pocket pivot report."""
    data = load_ohlcv(symbol, curr_date)
    result = analyze_pocket_pivots_from_data(data, curr_date, look_back_days)
    return json.dumps({"symbol": symbol.upper(), **result}, indent=2, ensure_ascii=False)
