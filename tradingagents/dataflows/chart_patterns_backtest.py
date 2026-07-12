"""Walk-forward calibration report for the SP1/SP2/SP3 chart-pattern constants.

Not a trading backtest -- no position sizing, execution, or P&L. State-sampled (no dedupe;
overlapping windows autocorrelate) so it evaluates the signal a trader reads each day.
Feeds scripts/backtest_chart_patterns.py; a human reads the report against the interim
constants in triangle_post_apex.py (SP1), false_break_types.py (SP2), and entry_types.py
(SP3). This module tunes nothing itself.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd

from tradingagents.dataflows.chart_patterns import analyze_chart_patterns_from_data

WARMUP_BARS = 60
TRIANGLE_PATTERNS = ("symmetrical_triangle", "ascending_triangle", "descending_triangle")
FALSE_BREAK_SIGNALS = ("false_breakout_short", "false_breakdown_long")
ENTRY_STATES = (
    "predictive_bottom", "breakout_entry", "breakout_retest_entry", "observe", "avoid",
    "false_breakout_short", "false_breakdown_long",
)


def _forward_return(df: pd.DataFrame, as_of, holding_days: int) -> float | None:
    matches = df.index[df["Date"] == pd.Timestamp(as_of)]
    if not len(matches):
        return None
    start = int(matches[0])
    target = start + holding_days
    if target >= len(df):
        return None
    entry = float(df["Close"].iloc[start])
    return (float(df["Close"].iloc[target]) - entry) / entry


def _pattern_direction_word(direction: str) -> str:
    if direction == "bullish":
        return "long"
    if direction == "bearish":
        return "short"
    return "none"


def _edge(forward_return: float, direction: str) -> float:
    return -forward_return if direction == "short" else forward_return


def _apex_bucket(risk_flags: tuple[str, ...]) -> str:
    if "post_apex_breakout" in risk_flags:
        return "post_apex_breakout"
    if "late_apex_breakout" in risk_flags:
        return "late_apex_breakout"
    return "normal"


def collect_samples(df: pd.DataFrame, step: int, holding_days: int) -> list[dict[str, Any]]:
    """State-sample every ``step`` bars: one record per pattern per walk-forward date."""
    records: list[dict[str, Any]] = []
    for as_of in df["Date"].iloc[WARMUP_BARS::step]:
        window = df[df["Date"] <= as_of]
        try:
            result = analyze_chart_patterns_from_data(window, as_of.strftime("%Y-%m-%d"))
        except ValueError:
            continue
        forward = _forward_return(df, as_of, holding_days)
        if forward is None:
            continue
        for pattern in result["patterns"]:
            entry = pattern.get("entry_assessment") or {}
            records.append(
                {
                    "state": entry.get("state"),
                    "entry_direction": entry.get("direction", "none"),
                    "pattern": pattern["pattern"],
                    "pattern_direction": _pattern_direction_word(pattern["direction"]),
                    "status": pattern["status"],
                    "risk_flags": tuple(pattern.get("risk_flags", [])),
                    "forward_return": forward,
                }
            )
    return records


def _new_bucket() -> dict[str, Any]:
    return {"count": 0, "hits": 0, "edge_sum": 0.0}


def new_stats() -> dict[str, Any]:
    return {
        "entry_state": defaultdict(_new_bucket),
        "apex": defaultdict(_new_bucket),
        "tier": defaultdict(_new_bucket),
    }


def _add(bucket: dict[str, Any], edge: float) -> None:
    bucket["count"] += 1
    bucket["hits"] += int(edge > 0)
    bucket["edge_sum"] += edge


def aggregate(records: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    """Fold each record into the entry_state, apex, and tier bucket families."""
    for record in records:
        forward = record["forward_return"]
        if record["state"] is not None:
            _add(stats["entry_state"][record["state"]], _edge(forward, record["entry_direction"]))
        if record["pattern"] in TRIANGLE_PATTERNS and record["status"] == "confirmed":
            _add(stats["apex"][_apex_bucket(record["risk_flags"])],
                 _edge(forward, record["pattern_direction"]))
        if record["pattern"] in FALSE_BREAK_SIGNALS:
            aggressive = "aggressive_confirmation" in record["risk_flags"]
            _add(stats["tier"][(record["pattern"], aggressive)],
                 _edge(forward, record["pattern_direction"]))


def _row(bucket: dict[str, Any]) -> tuple[int, float, float]:
    n = bucket["count"]
    return n, (bucket["hits"] / n if n else 0.0), (bucket["edge_sum"] / n if n else 0.0)


def format_report(stats: dict[str, Any], symbols: list[str], holding_days: int) -> str:
    total = sum(bucket["count"] for bucket in stats["entry_state"].values())
    lines = [
        f"\nChart-pattern calibration backtest -- {', '.join(symbols)}",
        f"holding_days={holding_days}, entry_state samples n={total}",
        "State-sampled (no dedupe); overlapping windows autocorrelate -- read gradients.",
        f"\nTABLE 1  entry_state (SP3)\n{'state':<24}{'n':>6}{'hit%':>8}{'avg_edge':>11}",
    ]
    for state in ENTRY_STATES:
        n, hit, edge = _row(stats["entry_state"][state])
        if n:
            lines.append(f"{state:<24}{n:>6}{hit:>8.1%}{edge:>11.2%}")
    lines.append(f"\nTABLE 2  apex timing, confirmed triangles (SP1)\n"
                 f"{'apex_bucket':<24}{'n':>6}{'hit%':>8}{'avg_edge':>11}")
    for name in ("normal", "late_apex_breakout", "post_apex_breakout"):
        n, hit, edge = _row(stats["apex"][name])
        if n:
            lines.append(f"{name:<24}{n:>6}{hit:>8.1%}{edge:>11.2%}")
    lines.append(f"\nTABLE 3  SP2 tier (false-break signals)\n{'signal':<22}"
                 f"{'n_agg':>6}{'hit_agg':>9}{'edge_agg':>10}{'n_std':>7}{'hit_std':>9}{'edge_std':>10}")
    for signal in FALSE_BREAK_SIGNALS:
        na, hita, ea = _row(stats["tier"].get((signal, True), _new_bucket()))
        ns, hits, es = _row(stats["tier"].get((signal, False), _new_bucket()))
        lines.append(f"{signal:<22}{na:>6}{hita:>9.1%}{ea:>10.2%}{ns:>7}{hits:>9.1%}{es:>10.2%}")
    return "\n".join(lines)
