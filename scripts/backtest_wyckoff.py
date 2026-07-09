"""Walk-forward hit-rate check for the Wyckoff structure module.

Not a trading backtest — no position sizing, execution, or P&L. It answers a
narrower question: when analyze_wyckoff_structure_from_data reports a
confirmed (Phase D/E) directional read as of some historical date, how often
does price actually move in that direction over the next N trading days?
Use this to sanity check (and eventually manually calibrate) DOMINANT_WEIGHT,
the confidence formula, and the VSA constants in
tradingagents/dataflows/wyckoff_bias.py and wyckoff_vsa*.py — this script
does not tune anything itself.

Usage:
    python scripts/backtest_wyckoff.py AAPL MSFT NVDA \
        --start 2023-01-01 --end 2026-01-01 --step 5 --holding-days 20
"""

from __future__ import annotations

import argparse
from collections import defaultdict

import pandas as pd

from tradingagents.dataflows.stockstats_utils import load_ohlcv
from tradingagents.dataflows.wyckoff_bias import analyze_wyckoff_structure_from_data


def _walk_dates(df: pd.DataFrame, step: int) -> list[pd.Timestamp]:
    """Sample one date every `step` bars, skipping the initial warm-up window."""
    return list(df["Date"].iloc[60::step])


def _forward_return(df: pd.DataFrame, as_of: pd.Timestamp, holding_days: int) -> float | None:
    matches = df.index[df["Date"] == as_of]
    if not len(matches):
        return None
    start = matches[0]
    target = start + holding_days
    if target >= len(df):
        return None
    entry = float(df["Close"].iloc[start])
    exit_price = float(df["Close"].iloc[target])
    return (exit_price - entry) / entry


def _direction_hit(phase_bias: str, forward_return: float) -> bool | None:
    if phase_bias == "bullish":
        return forward_return > 0
    if phase_bias == "bearish":
        return forward_return < 0
    return None


def _vsa_effect(result: dict) -> str:
    delta = result.get("vsa_confidence_delta")
    if not delta:
        return "none"
    return "positive" if delta > 0 else "negative"


def backtest_symbol(
    symbol: str, start: str, end: str, step: int, holding_days: int, stats: dict
) -> None:
    full = load_ohlcv(symbol, end)
    full = full[full["Date"] >= pd.Timestamp(start)].reset_index(drop=True)
    if len(full) < 80:
        print(f"{symbol}: not enough history in range, skipping")
        return

    seen: set[tuple] = set()
    for as_of in _walk_dates(full, step):
        as_of_str = as_of.strftime("%Y-%m-%d")
        window = full[full["Date"] <= as_of]
        try:
            result = analyze_wyckoff_structure_from_data(window, as_of_str)
        except ValueError:
            continue

        if result["trading_range"]["status"] != "confirmed":
            continue
        if result["phase_bias"] == "neutral":
            continue

        key = (result["phase_bias"], result["current_phase"], result["trading_range"]["start_date"])
        if key in seen:
            continue
        seen.add(key)

        forward = _forward_return(full, as_of, holding_days)
        if forward is None:
            continue
        hit = _direction_hit(result["phase_bias"], forward)
        if hit is None:
            continue

        bucket = stats[(result["current_phase"], _vsa_effect(result))]
        bucket["count"] += 1
        bucket["hits"] += int(hit)
        bucket["confidence_sum"] += result["confidence"]
        bucket["return_sum"] += forward


def print_report(stats: dict) -> None:
    print(f"\n{'phase':<8}{'vsa_effect':<12}{'n':>5}{'hit_rate':>10}{'avg_conf':>10}{'avg_fwd_ret':>13}")
    for (phase, vsa_effect), bucket in sorted(stats.items()):
        n = bucket["count"]
        if n == 0:
            continue
        print(
            f"{phase:<8}{vsa_effect:<12}{n:>5}"
            f"{bucket['hits'] / n:>10.1%}{bucket['confidence_sum'] / n:>10.2f}"
            f"{bucket['return_sum'] / n:>13.2%}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbols", nargs="+")
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end", default=pd.Timestamp.today().strftime("%Y-%m-%d"))
    parser.add_argument("--step", type=int, default=5, help="business days between walk-forward checks")
    parser.add_argument("--holding-days", type=int, default=20)
    args = parser.parse_args()

    stats: dict = defaultdict(lambda: {"count": 0, "hits": 0, "confidence_sum": 0.0, "return_sum": 0.0})
    for symbol in args.symbols:
        print(f"Backtesting {symbol}...")
        backtest_symbol(symbol, args.start, args.end, args.step, args.holding_days, stats)

    print_report(stats)


if __name__ == "__main__":
    main()
