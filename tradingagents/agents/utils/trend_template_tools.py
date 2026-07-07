from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.trend_template import analyze_trend_template


@tool
def get_trend_template(
    symbol: Annotated[str, "ticker symbol of the instrument"],
    curr_date: Annotated[str, "current analysis date in YYYY-mm-dd format"],
    benchmark: Annotated[str, "index ticker to compare relative strength against"] = "SPY",
) -> str:
    """Score the stock against Minervini's 8-point trend template.

    Checks moving-average stacking (50/150/200-day), whether the 200-day MA
    is rising, position versus the 52-week high/low, and whether the stock's
    price ratio against `benchmark` is at a new high (a relative-strength
    proxy). Returns which of the 8 criteria pass and the underlying values.
    A stock passing all 8 is in a Minervini "stage 2" uptrend; this is a
    technical-stage filter, not a buy signal on its own.
    """
    return analyze_trend_template(symbol, curr_date, benchmark)
