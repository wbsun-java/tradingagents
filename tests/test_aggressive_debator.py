"""Prompt-content test for the aggressive risk debator's Wyckoff weighting guidance."""

from __future__ import annotations

import pytest

from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator


class _StubResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _StubLLM:
    def __init__(self) -> None:
        self.last_prompt: str | None = None

    def invoke(self, prompt: str) -> _StubResponse:
        self.last_prompt = prompt
        return _StubResponse("Aggressive argument.")


def _make_state() -> dict:
    return {
        "risk_debate_state": {
            "history": "",
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "count": 0,
        },
        "market_report": "Wyckoff phase_bias: bullish, dominant_weight: 0.6",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
        "trader_investment_plan": "Buy.",
        "company_of_interest": "AAPL",
        "asset_type": "stock",
    }


@pytest.mark.unit
def test_prompt_tells_aggressive_analyst_how_to_weight_wyckoff_phase_bias():
    llm = _StubLLM()

    create_aggressive_debator(llm)(_make_state())

    assert llm.last_prompt is not None
    assert "phase_bias" in llm.last_prompt
    assert "invalidated" in llm.last_prompt
