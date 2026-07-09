from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.pocket_pivot_bias import analyze_pocket_pivots


@tool
def get_pocket_pivot(
    symbol: Annotated[str, "ticker symbol of the instrument"],
    curr_date: Annotated[str, "current analysis date in YYYY-mm-dd format"],
    look_back_days: Annotated[int, "lookback window in trading days"] = 320,
) -> str:
    """Deterministically read the stock's Pocket Pivot signals (Kacher & Morales).

    A pocket pivot fires when price closes decisively back above its 10-day
    or 50-day moving average on an up day, with volume exceeding the highest
    down-volume day of the prior 10 sessions. This is an independent
    volume/accumulation signal -- it is NOT part of the Wyckoff/O'Neil
    precedence chain used elsewhere in this report, and a pocket pivot can
    fire outside a cup-with-handle base. Each event includes contextual
    guideline flags (multi-month downtrend, position vs. 50/200dma, V-shape
    reversal risk, extension from the 10dma) that inform buyability but never
    suppress a detected event -- code reports structure, you judge
    buyability. Fundamentals strength and wedge-pattern geometry are NOT
    evaluated here; combine with the Fundamentals Analyst's read and visual
    chart review. Returns `events: []` and `active: false` when no pocket
    pivot fired within the scan window.
    """
    return analyze_pocket_pivots(symbol, curr_date, look_back_days)
