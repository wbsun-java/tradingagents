"""Walk-forward calibration report for the deterministic chart-pattern signals.

Not a trading backtest -- no position sizing, execution, or P&L. It buckets forward
returns by SP3 entry state, SP1 apex-timing flags, and SP2 confirmation tier so a human
can judge whether the interim constants in triangle_post_apex.py, false_break_types.py,
and entry_types.py are justified. State-sampled (no dedupe); this script tunes nothing.

Usage:
    python scripts/backtest_chart_patterns.py AAPL MSFT NVDA \
        --start 2022-01-01 --end 2026-01-01 --step 5 --holding-days 10
"""

from __future__ import annotations

import argparse

import pandas as pd

from tradingagents.dataflows.chart_patterns_backtest import (
    aggregate,
    collect_samples,
    format_report,
    new_stats,
)
from tradingagents.dataflows.stockstats_utils import load_ohlcv

MIN_BARS = 80


def backtest_symbol(
    symbol: str, start: str, end: str, step: int, holding_days: int, stats: dict
) -> None:
    full = load_ohlcv(symbol, end)
    full = full[full["Date"] >= pd.Timestamp(start)].reset_index(drop=True)
    if len(full) < MIN_BARS:
        print(f"{symbol}: not enough history in range, skipping")
        return
    records = collect_samples(full, step, holding_days)
    print(f"{symbol}: {len(records)} state-sampled pattern observations")
    aggregate(records, stats)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbols", nargs="+")
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end", default=pd.Timestamp.today().strftime("%Y-%m-%d"))
    parser.add_argument("--step", type=int, default=5, help="business days between checks")
    parser.add_argument("--holding-days", type=int, default=10)
    args = parser.parse_args()

    stats = new_stats()
    for symbol in args.symbols:
        print(f"Backtesting {symbol}...")
        backtest_symbol(symbol, args.start, args.end, args.step, args.holding_days, stats)

    print(format_report(stats, args.symbols, args.holding_days))


if __name__ == "__main__":
    main()
