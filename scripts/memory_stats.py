"""Print summary statistics from the trading decision log.

Reads the decision log at the configured memory_log_path (default
~/.tradingagents/memory/trading_memory.md, or TRADINGAGENTS_MEMORY_LOG_PATH)
and prints resolved-decision count, win rate, average alpha, and average
holding days. Pending (not-yet-resolved) entries are excluded.

Usage:
    python scripts/memory_stats.py
"""

from __future__ import annotations

import sys
from contextlib import suppress

from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.default_config import DEFAULT_CONFIG


def compute_stats(entries: list[dict]) -> dict | None:
    """Aggregate resolved decision-log entries into summary stats.

    Returns None if there are no resolved entries. Entries whose raw/alpha/
    holding fields fail to parse are skipped from the aggregates they would
    contribute to, rather than failing the whole computation.
    """
    resolved = [e for e in entries if not e.get("pending")]
    if not resolved:
        return None

    wins = 0
    win_eligible = 0
    alphas: list[float] = []
    holdings: list[float] = []

    for e in resolved:
        raw_str = e.get("raw")
        if raw_str:
            try:
                raw_val = float(raw_str.rstrip("%"))
            except ValueError:
                raw_val = None
            if raw_val is not None:
                win_eligible += 1
                if raw_val > 0:
                    wins += 1

        alpha_str = e.get("alpha")
        if alpha_str:
            with suppress(ValueError):
                alphas.append(float(alpha_str.rstrip("%")))

        holding_str = e.get("holding")
        if holding_str:
            with suppress(ValueError):
                holdings.append(float(holding_str.rstrip("d")))

    return {
        "count": len(resolved),
        "win_rate": (wins / win_eligible) if win_eligible else None,
        "avg_alpha": (sum(alphas) / len(alphas)) if alphas else None,
        "avg_holding": (sum(holdings) / len(holdings)) if holdings else None,
    }


def main() -> int:
    memory_log = TradingMemoryLog(DEFAULT_CONFIG)
    stats = compute_stats(memory_log.load_entries())

    if stats is None:
        print("No resolved decisions yet.")
        return 0

    print(f"Decisions: {stats['count']}")
    print(
        f"Win rate: {stats['win_rate'] * 100:.1f}%"
        if stats["win_rate"] is not None
        else "Win rate: n/a"
    )
    print(
        f"Avg alpha: {stats['avg_alpha']:+.1f}%"
        if stats["avg_alpha"] is not None
        else "Avg alpha: n/a"
    )
    print(
        f"Avg holding: {stats['avg_holding']:.1f} days"
        if stats["avg_holding"] is not None
        else "Avg holding: n/a"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
