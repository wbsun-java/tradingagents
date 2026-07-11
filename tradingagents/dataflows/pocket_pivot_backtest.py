"""Walk-forward collection and per-flag lift aggregation for pocket pivots.

Not a trading backtest -- no position sizing, execution, or P&L. Feeds
scripts/backtest_pocket_pivot.py; a human reads the report against the
constants in pocket_pivot_signals.py and pocket_pivot_context.py. This
module tunes nothing itself.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd

from tradingagents.dataflows.pocket_pivot_bias import analyze_pocket_pivots_from_data

WARMUP_BARS = 60
CONTEXT_FLAGS = (
    "v_shape_risk",
    "extended_from_ma",
    "multi_month_downtrend",
    "above_sma200",
    "gap_up",
)


def _forward_return(df: pd.DataFrame, event_date: str, holding_days: int) -> float | None:
    matches = df.index[df["Date"] == pd.Timestamp(event_date)]
    if not len(matches):
        return None
    start = int(matches[0])
    target = start + holding_days
    if target >= len(df):
        return None
    entry = float(df["Close"].iloc[start])
    return (float(df["Close"].iloc[target]) - entry) / entry


def collect_events(df: pd.DataFrame, step: int, holding_days: int) -> list[dict[str, Any]]:
    """Walk forward every ``step`` bars; keep each event's first sighting only."""
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for as_of in df["Date"].iloc[WARMUP_BARS::step]:
        window = df[df["Date"] <= as_of]
        try:
            result = analyze_pocket_pivots_from_data(window, as_of.strftime("%Y-%m-%d"))
        except ValueError:
            continue
        for event in result["events"]:
            key = (event["date"], event["ma_period"])
            if key in seen:
                continue
            seen.add(key)
            forward = _forward_return(df, event["date"], holding_days)
            if forward is None:
                continue
            records.append({
                "date": event["date"],
                "ma_period": event["ma_period"],
                "context": dict(event["context"]),
                "gap_up": event["gap_up"],
                "forward_return": forward,
                "hit": forward > 0,
            })
    return records


def _new_bucket() -> dict[str, Any]:
    return {"count": 0, "hits": 0, "return_sum": 0.0}


def new_stats() -> dict[str, Any]:
    return {"baseline": defaultdict(_new_bucket), "flags": defaultdict(_new_bucket)}


def _flag_value(record: dict[str, Any], flag: str) -> bool | None:
    if flag == "gap_up":
        return record["gap_up"]
    return record["context"].get(flag)


def aggregate(records: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    """Fold records into baseline (by ma_period) and per-flag lift buckets."""
    for record in records:
        targets = [stats["baseline"][record["ma_period"]]]
        for flag in CONTEXT_FLAGS:
            value = _flag_value(record, flag)
            targets.append(stats["flags"][(flag, None if value is None else bool(value))])
        for bucket in targets:
            bucket["count"] += 1
            bucket["hits"] += int(record["hit"])
            bucket["return_sum"] += record["forward_return"]


def _cells(stats: dict[str, Any], flag: str, value: bool) -> tuple[int, float, float]:
    bucket = stats["flags"].get((flag, value), {"count": 0, "hits": 0, "return_sum": 0.0})
    n = bucket["count"]
    return n, (bucket["hits"] / n if n else 0.0), (bucket["return_sum"] / n if n else 0.0)


def format_report(stats: dict[str, Any]) -> str:
    lines = [f"\n{'ma_period':<11}{'n':>5}{'hit_rate':>10}{'avg_fwd_ret':>13}"]
    for period in sorted(stats["baseline"]):
        bucket = stats["baseline"][period]
        n = bucket["count"]
        lines.append(
            f"{period:<11}{n:>5}{bucket['hits'] / n:>10.1%}{bucket['return_sum'] / n:>13.2%}"
        )
    lines.append(
        f"\n{'flag':<24}{'n_true':>8}{'hit_true':>10}{'ret_true':>10}"
        f"{'n_false':>9}{'hit_false':>11}{'ret_false':>11}{'n_na':>6}"
    )
    for flag in CONTEXT_FLAGS:
        n_true, hit_true, ret_true = _cells(stats, flag, True)
        n_false, hit_false, ret_false = _cells(stats, flag, False)
        n_na = stats["flags"].get((flag, None), {"count": 0})["count"]
        lines.append(
            f"{flag:<24}{n_true:>8}{hit_true:>10.1%}{ret_true:>10.2%}"
            f"{n_false:>9}{hit_false:>11.1%}{ret_false:>11.2%}{n_na:>6}"
        )
    return "\n".join(lines)
