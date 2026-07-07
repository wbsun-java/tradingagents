from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.chart_patterns import analyze_chart_patterns


@tool
def get_chart_patterns(
    symbol: Annotated[str, "ticker symbol of the instrument"],
    curr_date: Annotated[str, "current analysis date in YYYY-mm-dd format"],
    look_back_days: Annotated[int, "number of recent OHLCV rows to analyze"] = 252,
    pivot_span: Annotated[int, "bars on each side required to confirm a swing pivot"] = 3,
) -> str:
    """Detect classical price patterns from cutoff-safe OHLCV data.

    Returns support and resistance levels plus W bottoms, M tops, rectangles,
    and ascending, descending, or symmetrical triangles. Every pattern is
    labelled forming, confirmed, or failed and includes evidence, target,
    invalidation, and volume confirmation where available. Triangle results
    also quantify where the break occurred between the base and theoretical
    apex, flagging late apex breaks that carry elevated false-break risk. Treat
    this tool as the source of truth for chart-pattern claims; do not infer
    additional patterns by visually guessing from raw CSV data.
    """
    return analyze_chart_patterns(symbol, curr_date, look_back_days, pivot_span)
