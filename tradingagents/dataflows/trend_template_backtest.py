"""Walk-forward sampling and band aggregation for the Minervini trend template.

Not a trading backtest -- no position sizing, execution, or P&L. The trend
template is a state read, so one record is sampled per walk date with no
dedupe: adjacent samples overlap and autocorrelate, and hit rates should be
read as tendencies over correlated samples, not independent trials. Feeds
scripts/backtest_trend_template.py; a human reads the report against the
thresholds and _QUARTER_WEIGHTS in trend_template.py. Tunes nothing itself.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd

from tradingagents.dataflows.trend_template import evaluate_trend_template

WARMUP_BARS = 260
PASS_BANDS = ("0-4", "5-6", "7", "8")
RS_BANDS = ("rs<0", "0<=rs<=0.10", "rs>0.10", "n/a")


def pass_band(passed_count: int) -> str:
    if passed_count <= 4:
        return "0-4"
    if passed_count <= 6:
        return "5-6"
    return str(passed_count)


def rs_band(rs_score: float | None) -> str:
    if rs_score is None:
        return "n/a"
    if rs_score < 0:
        return "rs<0"
    if rs_score <= 0.10:
        return "0<=rs<=0.10"
    return "rs>0.10"


def _forward_return(df: pd.DataFrame, start: int, holding_days: int) -> float | None:
    target = start + holding_days
    if target >= len(df):
        return None
    entry = float(df["Close"].iloc[start])
    return (float(df["Close"].iloc[target]) - entry) / entry


def collect_readings(
    df: pd.DataFrame, benchmark_df: pd.DataFrame, step: int, holding_days: int
) -> list[dict[str, Any]]:
    """Sample the template every ``step`` bars; one record per walk date, no dedupe."""
    records: list[dict[str, Any]] = []
    for position in range(WARMUP_BARS, len(df), step):
        forward = _forward_return(df, position, holding_days)
        if forward is None:
            break
        as_of = df["Date"].iloc[position]
        window = df[df["Date"] <= as_of]
        benchmark_window = benchmark_df[benchmark_df["Date"] <= as_of]
        result = evaluate_trend_template(window, benchmark_window)
        records.append({
            "date": as_of.strftime("%Y-%m-%d"),
            "passed_count": result.passed_count,
            "total_criteria": result.total_criteria,
            "stage_2_uptrend": result.stage_2_uptrend,
            "rs_score": result.values.get("rs_score"),
            "forward_return": forward,
            "hit": forward > 0,
        })
    return records


def _new_bucket() -> dict[str, Any]:
    return {"count": 0, "hits": 0, "return_sum": 0.0}


def new_stats() -> dict[str, Any]:
    return {"baseline": defaultdict(_new_bucket), "lift": defaultdict(_new_bucket)}


def aggregate(records: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    """Fold records into baseline (by pass band) and lift (pass band x rs band) buckets."""
    for record in records:
        bands = (pass_band(record["passed_count"]), rs_band(record["rs_score"]))
        for bucket in (stats["baseline"][bands[0]], stats["lift"][bands]):
            bucket["count"] += 1
            bucket["hits"] += int(record["hit"])
            bucket["return_sum"] += record["forward_return"]


def _row(bucket: dict[str, Any]) -> tuple[int, float, float]:
    n = bucket["count"]
    return n, (bucket["hits"] / n if n else 0.0), (bucket["return_sum"] / n if n else 0.0)


def format_report(stats: dict[str, Any]) -> str:
    lines = [f"\n{'pass_band':<11}{'n':>6}{'hit_rate':>10}{'avg_fwd_ret':>13}"]
    for band in PASS_BANDS:
        n, hit, ret = _row(stats["baseline"].get(band, _new_bucket()))
        lines.append(f"{band:<11}{n:>6}{hit:>10.1%}{ret:>13.2%}")
    lines.append(f"\n{'pass_band':<11}{'rs_band':<14}{'n':>6}{'hit_rate':>10}{'avg_fwd_ret':>13}")
    for band in PASS_BANDS:
        for rs in RS_BANDS:
            n, hit, ret = _row(stats["lift"].get((band, rs), _new_bucket()))
            lines.append(f"{band:<11}{rs:<14}{n:>6}{hit:>10.1%}{ret:>13.2%}")
    return "\n".join(lines)
