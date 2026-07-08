from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.wyckoff_bias import analyze_wyckoff_structure


@tool
def get_wyckoff_structure(
    symbol: Annotated[str, "ticker symbol of the instrument"],
    curr_date: Annotated[str, "current analysis date in YYYY-mm-dd format"],
    look_back_days: Annotated[int, "lookback window in trading days"] = 504,
) -> str:
    """Deterministically read the stock's Wyckoff accumulation/distribution structure.

    Detects the current consolidation range and classical Wyckoff events
    (selling/buying climax, automatic rally/reaction, secondary test,
    spring/upthrust, sign of strength/weakness, last point of support/supply)
    inside it, then reports the resulting phase (A-E), directional bias, and
    a fixed `dominant_weight` policy constant. This structural read should
    anchor the technical verdict: other technical tools may adjust confidence
    within its direction but must not override it unless `phase_bias` is
    neutral. Returns `phase_bias: "neutral"` with no events when no clear
    Wyckoff structure is present in the lookback window.
    """
    return analyze_wyckoff_structure(symbol, curr_date, look_back_days)
