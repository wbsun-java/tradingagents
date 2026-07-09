from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.oneil_bias import analyze_oneil_setup


@tool
def get_oneil_setup(
    symbol: Annotated[str, "ticker symbol of the instrument"],
    curr_date: Annotated[str, "current analysis date in YYYY-mm-dd format"],
    look_back_days: Annotated[int, "lookback window in trading days"] = 420,
) -> str:
    """Deterministically read the stock's O'Neil cup-with-handle setup.

    Detects a rounded consolidation base (cup) following a meaningful prior
    uptrend, a shallower pullback in its upper half (handle) with lower
    volume than the cup, and a breakout above the cup's left-side high
    confirmed by above-average volume. Reports status
    (none/forming/developing/confirmed/failed), setup_bias, confidence, and a
    fixed `secondary_weight` policy constant. This read ranks below the
    Wyckoff structural read but above chart patterns, the trend template, and
    ordinary indicators: when Wyckoff's phase_bias is neutral, this result's
    setup_bias becomes the directional anchor for the technical verdict, but
    Wyckoff wins if both are non-neutral and conflict. Returns
    `setup_bias: "neutral"` with no cup when no valid structure is present in
    the lookback window.
    """
    return analyze_oneil_setup(symbol, curr_date, look_back_days)
