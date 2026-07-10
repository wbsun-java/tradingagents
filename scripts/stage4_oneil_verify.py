"""Stage-4 verification runner for the O'Neil base-pattern expansion.

Runs the market analyst only and prints the market report:

    python scripts/stage4_oneil_verify.py CRWD 2026-07-10

Research/analysis support only; not investment advice; no trade execution.
"""

import sys

from dotenv import load_dotenv

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: python scripts/stage4_oneil_verify.py <TICKER> <YYYY-MM-DD>")
    ticker, date = sys.argv[1], sys.argv[2]
    load_dotenv()
    config = DEFAULT_CONFIG.copy()
    graph = TradingAgentsGraph(config=config, selected_analysts=["market"])
    final_state, _signal = graph.propagate(ticker, date)
    print(final_state["market_report"])


if __name__ == "__main__":
    main()
