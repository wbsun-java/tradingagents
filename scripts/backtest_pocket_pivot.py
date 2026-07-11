"""Walk-forward hit-rate check for the Pocket Pivot module.

Not a trading backtest -- no position sizing, execution, or P&L. It answers a
narrower question: when analyze_pocket_pivots_from_data reports a pocket
pivot as of some historical date, how often does price rise over the next N
trading days, and how does each context flag (v-shape risk, extension,
downtrend, MA position, gap-up) shift that hit rate? Use this to sanity
check (and eventually manually calibrate) CROSS_BUFFER_ATR and
DOWN_VOLUME_LOOKBACK in tradingagents/dataflows/pocket_pivot_signals.py and
the V_SHAPE_* / EXTENSION_ATR_THRESHOLD / DOWNTREND_LOOKBACK_BARS constants
in tradingagents/dataflows/pocket_pivot_context.py -- this script does not
tune anything itself.

Usage:
    python scripts/backtest_pocket_pivot.py AAPL MSFT NVDA \
        --start 2023-01-01 --end 2026-01-01 --step 5 --holding-days 20
"""

from __future__ import annotations

import argparse

import pandas as pd

from tradingagents.dataflows.pocket_pivot_backtest import (
    aggregate,
    collect_events,
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
    records = collect_events(full, step, holding_days)
    print(f"{symbol}: {len(records)} pocket pivot events with a full forward window")
    aggregate(records, stats)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbols", nargs="+")
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end", default=pd.Timestamp.today().strftime("%Y-%m-%d"))
    parser.add_argument("--step", type=int, default=5, help="business days between walk-forward checks")
    parser.add_argument("--holding-days", type=int, default=20)
    args = parser.parse_args()

    stats = new_stats()
    for symbol in args.symbols:
        print(f"Backtesting {symbol}...")
        backtest_symbol(symbol, args.start, args.end, args.step, args.holding_days, stats)

    print(format_report(stats))


if __name__ == "__main__":
    main()
