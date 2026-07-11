"""Walk-forward hit-rate check for the Minervini trend-template module.

Not a trading backtest -- no position sizing, execution, or P&L. The template
is a state read sampled every --step bars, so adjacent samples overlap and
autocorrelate: read hit rates as tendencies, not independent trials. It
answers two questions: does the pass-count gradient predict forward returns,
and does rs_score add lift beyond the pass count? Use it to sanity check
(and eventually manually calibrate) the criteria thresholds and
_QUARTER_WEIGHTS in tradingagents/dataflows/trend_template.py -- this script
does not tune anything itself.

A benchmark is required: without one the RS criterion drops out and
passed_count's denominator silently changes from 8 to 7, corrupting the
pass-band semantics; symbols are skipped instead.

Usage:
    python scripts/backtest_trend_template.py AAPL MSFT NVDA \
        --benchmark SPY --start 2023-01-01 --step 5 --holding-days 20
"""

from __future__ import annotations

import argparse

import pandas as pd

from tradingagents.dataflows.stockstats_utils import load_ohlcv
from tradingagents.dataflows.trend_template_backtest import (
    WARMUP_BARS,
    aggregate,
    collect_readings,
    format_report,
    new_stats,
)


def backtest_symbol(
    symbol: str,
    benchmark_df: pd.DataFrame,
    start: str,
    end: str,
    step: int,
    holding_days: int,
    stats: dict,
) -> None:
    full = load_ohlcv(symbol, end)
    full = full[full["Date"] >= pd.Timestamp(start)].reset_index(drop=True)
    if len(full) < WARMUP_BARS + holding_days:
        print(f"{symbol}: not enough history in range, skipping")
        return
    records = collect_readings(full, benchmark_df, step, holding_days)
    print(f"{symbol}: {len(records)} sampled readings with a full forward window")
    aggregate(records, stats)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbols", nargs="+")
    parser.add_argument("--benchmark", default="SPY")
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end", default=pd.Timestamp.today().strftime("%Y-%m-%d"))
    parser.add_argument("--step", type=int, default=5, help="business days between walk-forward checks")
    parser.add_argument("--holding-days", type=int, default=20)
    args = parser.parse_args()

    try:
        benchmark_df = load_ohlcv(args.benchmark, args.end)
        benchmark_df = benchmark_df[benchmark_df["Date"] >= pd.Timestamp(args.start)].reset_index(drop=True)
    except ValueError as exc:
        print(f"benchmark {args.benchmark} unavailable ({exc}); cannot run — all symbols skipped")
        return

    stats = new_stats()
    for symbol in args.symbols:
        print(f"Backtesting {symbol}...")
        backtest_symbol(symbol, benchmark_df, args.start, args.end, args.step, args.holding_days, stats)

    print(format_report(stats))


if __name__ == "__main__":
    main()
