"""Prompt-content test for the bull researcher's Wyckoff weighting guidance."""

from __future__ import annotations

import pytest

from tradingagents.agents.researchers.bull_researcher import create_bull_researcher


class _StubResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _StubLLM:
    def __init__(self) -> None:
        self.last_prompt: str | None = None

    def invoke(self, prompt: str) -> _StubResponse:
        self.last_prompt = prompt
        return _StubResponse("Bull argument.")


def _make_state() -> dict:
    return {
        "investment_debate_state": {
            "history": "", "bull_history": "", "bear_history": "",
            "current_response": "", "count": 0,
        },
        "market_report": "Wyckoff phase_bias: bearish",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
        "company_of_interest": "AAPL",
        "asset_type": "stock",
    }


@pytest.mark.unit
def test_prompt_tells_bull_analyst_how_to_weight_wyckoff_phase_bias():
    llm = _StubLLM()

    create_bull_researcher(llm)(_make_state())

    assert llm.last_prompt is not None
    assert "dominant_weight" in llm.last_prompt
    assert "invalidated" in llm.last_prompt
