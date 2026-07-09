import json

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    get_chart_patterns,
    get_indicators,
    get_instrument_context_from_state,
    get_language_instruction,
    get_stock_data,
    get_trend_template,
    get_verified_market_snapshot,
)
from tradingagents.dataflows.oneil_bias import analyze_oneil_setup
from tradingagents.dataflows.wyckoff_bias import analyze_wyckoff_structure


def _fetch_wyckoff_block(ticker: str, current_date: str) -> str:
    try:
        return analyze_wyckoff_structure(ticker, current_date)
    except Exception as exc:
        return json.dumps(
            {
                "phase_bias": "neutral",
                "current_phase": "undetermined",
                "events": [],
                "dominant_weight": 0.6,
                "error": f"Wyckoff read unavailable: {exc}",
            }
        )


def _fetch_oneil_block(ticker: str, current_date: str) -> str:
    try:
        return analyze_oneil_setup(ticker, current_date)
    except Exception as exc:
        return json.dumps(
            {
                "status": "none",
                "setup_bias": "neutral",
                "secondary_weight": 0.4,
                "cup": None,
                "handle": None,
                "breakout": None,
                "evidence": [],
                "error": f"O'Neil read unavailable: {exc}",
            }
        )


def create_market_analyst(llm):

    def market_analyst_node(state):
        ticker = state["company_of_interest"]
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)
        wyckoff_block = _fetch_wyckoff_block(ticker, current_date)
        oneil_block = _fetch_oneil_block(ticker, current_date)

        tools = [
            get_stock_data,
            get_indicators,
            get_verified_market_snapshot,
            get_chart_patterns,
            get_trend_template,
        ]

        system_message = (
            f"""You are a trading assistant tasked with analyzing financial markets. Your role is to select the **most relevant indicators** for a given market condition or trading strategy from the following list. The goal is to choose up to **8 indicators** that provide complementary insights without redundancy. Categories and each category's indicators are:

Moving Averages:
- close_50_sma: 50 SMA: A medium-term trend indicator. Usage: Identify trend direction and serve as dynamic support/resistance. Tips: It lags price; combine with faster indicators for timely signals.
- close_200_sma: 200 SMA: A long-term trend benchmark. Usage: Confirm overall market trend and identify golden/death cross setups. Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries.
- close_10_ema: 10 EMA: A responsive short-term average. Usage: Capture quick shifts in momentum and potential entry points. Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals.

MACD Related:
- macd: MACD: Computes momentum via differences of EMAs. Usage: Look for crossovers and divergence as signals of trend changes. Tips: Confirm with other indicators in low-volatility or sideways markets.
- macds: MACD Signal: An EMA smoothing of the MACD line. Usage: Use crossovers with the MACD line to trigger trades. Tips: Should be part of a broader strategy to avoid false positives.
- macdh: MACD Histogram: Shows the gap between the MACD line and its signal. Usage: Visualize momentum strength and spot divergence early. Tips: Can be volatile; complement with additional filters in fast-moving markets.

Momentum Indicators:
- rsi: RSI: Measures momentum to flag overbought/oversold conditions. Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis.

Volatility Indicators:
- boll: Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. Usage: Acts as a dynamic benchmark for price movement. Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals.
- boll_ub: Bollinger Upper Band: Typically 2 standard deviations above the middle line. Usage: Signals potential overbought conditions and breakout zones. Tips: Confirm signals with other tools; prices may ride the band in strong trends.
- boll_lb: Bollinger Lower Band: Typically 2 standard deviations below the middle line. Usage: Indicates potential oversold conditions. Tips: Use additional analysis to avoid false reversal signals.
- atr: ATR: Averages true range to measure volatility. Usage: Set stop-loss levels and adjust position sizes based on current market volatility. Tips: It's a reactive measure, so use it as part of a broader risk management strategy.

Volume-Based Indicators:
- vwma: VWMA: A moving average weighted by volume. Usage: Confirm trends by integrating price action with volume data. Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses.

- Select indicators that provide diverse and complementary information. Avoid redundancy (e.g., do not select both rsi and stochrsi). Also briefly explain why they are suitable for the given market context. When you tool call, please use the exact name of the indicators provided above as they are defined parameters, otherwise your call will fail. Please make sure to call get_stock_data first to retrieve the CSV that is needed to generate indicators. Then use get_indicators with the specific indicator names.

Before writing the final report, call get_verified_market_snapshot for this ticker and the current date, and treat it as the source of truth for any exact OHLCV, price-level, or indicator-value claim. If another tool's output conflicts with the verified snapshot, flag the discrepancy rather than inventing a reconciled number. Do not claim historical validation, support/resistance bounces, or exact percentage moves unless they are directly supported by tool output with concrete dates and prices.

Also call get_chart_patterns for the ticker and current date before the final report. Treat its deterministic output as the source of truth for W bottoms (double bottoms), M tops (double tops), rectangles, triangles, support/resistance, and breakouts. Clearly distinguish `forming`, `confirmed`, and `failed` patterns. A forming pattern is a watch condition, not a trade signal. Report the calculated confirmation, target, and invalidation levels; do not invent additional visual patterns from the raw CSV. For triangles, report `breakout_progress`: the preferred breakout zone is roughly 55%-75% of the base-to-apex distance (around two-thirds), while a `late_apex_breakout` above 85% carries elevated false-break risk and must reduce conviction. Do not penalize an earlier breakout solely for its timing; note that the structure may evolve into a different pattern and should be re-evaluated. Use volume confirmation and other indicators as supporting context rather than as substitutes for geometric confirmation.

Also call get_trend_template for the ticker and current date. It scores the stock against Minervini's 8-point trend template (moving-average stacking, 52-week high/low position, and a relative-strength proxy versus a benchmark index) and reports how many of the 8 criteria pass. This is a technical-stage filter, not a buy signal: a stock passing all 8 is in what Minervini calls a "stage 2" uptrend, which is a favorable backdrop for bullish setups, while failing most criteria signals a weak or declining stage. Report the pass count and which specific criteria failed; do not treat a high pass count alone as a trade recommendation.

The stock's Wyckoff accumulation/distribution structure has already been deterministically read for you below -- do not call any tool to re-derive it. It reports the current consolidation range, the classical events found inside it (selling/buying climax, automatic rally/reaction, secondary test, spring/upthrust, sign of strength/weakness, last point of support/supply), the resulting phase (A through E), and a `phase_bias` (bullish/bearish/neutral). Treat this as the primary technical read and write it as its own section before other technical evidence: state the phase, cite the specific events with their dates and prices, and give the `dominant_weight` value. Apply this rule when synthesizing the report's overall technical conclusion: when `phase_bias` is bullish or bearish, the chart-pattern, trend-template, and indicator evidence may only adjust conviction within that same direction — they must not flip the technical conclusion to the opposite direction. If that other evidence strongly conflicts with the Wyckoff read, say so explicitly, but still lead the technical conclusion with the Wyckoff direction. When `phase_bias` is neutral (including no clear range in the lookback window), treat the other technical evidence normally, without this constraint. Do not invent Wyckoff events beyond what this JSON reports.

<wyckoff_structure>
{wyckoff_block}
</wyckoff_structure>

"""
            + f"""The stock's William O'Neil cup-with-handle setup has already been deterministically read for you below -- do not call any tool to re-derive it. It reports whether the stock has formed a rounded consolidation base (cup) following a meaningful prior uptrend, a shallower pullback in the cup's upper half on lower volume (handle), and a breakout above the cup's left-side high confirmed by above-average volume. Report its `status` (forming/developing/confirmed/failed), the specific cup/handle/breakout dates and prices, and the `secondary_weight` value. Apply this three-tier precedence rule when synthesizing the report's overall technical conclusion: (1) if the Wyckoff `phase_bias` is bullish or bearish, it remains the final direction as already stated above; (2) if Wyckoff is neutral and this JSON's `setup_bias` is bullish, `setup_bias` becomes the directional anchor instead -- chart-pattern, trend-template, and indicator evidence may only adjust conviction within that direction, not flip it to the opposite direction; if Wyckoff is instead non-neutral and conflicts with this JSON's direction, say so explicitly ("conflicts with the O'Neil cup-with-handle structure") but still lead with the Wyckoff direction; (3) if both Wyckoff and this JSON are neutral, weigh the remaining technical evidence normally. Do not invent cup, handle, or breakout events beyond what this JSON reports.

<oneil_setup>
{oneil_block}
</oneil_setup>"""
            + """

Write a very detailed and nuanced report of the trends you observe. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."""
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read, including a row for the Wyckoff phase, phase_bias, and dominant_weight, and a separate row for the O'Neil cup-with-handle status, setup_bias, and secondary_weight."""
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}."
                    " Today's date is {current_date}; treat it as 'now' for all analysis and tool-call date ranges. {instrument_context}\n"
                    "{system_message}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "market_report": report,
        }

    return market_analyst_node
