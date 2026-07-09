"""Prompt-content test for the bear researcher's Wyckoff weighting guidance."""

from __future__ import annotations

import pytest

from tradingagents.agents.researchers.bear_researcher import create_bear_researcher


class _StubResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _StubLLM:
    def __init__(self) -> None:
        self.last_prompt: str | None = None

    def invoke(self, prompt: str) -> _StubResponse:
        self.last_prompt = prompt
        return _StubResponse("Bear argument.")


def _make_state() -> dict:
    return {
        "investment_debate_state": {
            "history": "", "bull_history": "", "bear_history": "",
            "current_response": "", "count": 0,
        },
        "market_report": "Wyckoff phase_bias: bullish, dominant_weight: 0.6",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
        "company_of_interest": "AAPL",
        "asset_type": "stock",
    }


@pytest.mark.unit
def test_prompt_tells_bear_analyst_how_to_weight_wyckoff_phase_bias():
    llm = _StubLLM()

    create_bear_researcher(llm)(_make_state())

    assert llm.last_prompt is not None
    assert "dominant_weight" in llm.last_prompt
    assert "invalidated" in llm.last_prompt
