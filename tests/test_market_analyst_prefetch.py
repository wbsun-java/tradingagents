from typing import ClassVar

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

from tradingagents.agents.analysts.market_analyst import create_market_analyst


class _CapturingFakeLLM(GenericFakeChatModel):
    """Records the tools bound and the final messages sent to the model."""

    captured_tool_names: ClassVar[list[str]] = []
    captured_messages: ClassVar[list[object]] = []

    def bind_tools(self, tools, **kwargs):
        type(self).captured_tool_names = [t.name for t in tools]
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        type(self).captured_messages = messages
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def _make_state():
    return {
        "company_of_interest": "NVDA",
        "trade_date": "2026-01-15",
        "asset_type": "stock",
        "messages": [],
    }


def _fake_llm():
    _CapturingFakeLLM.captured_tool_names = []
    _CapturingFakeLLM.captured_messages = []
    return _CapturingFakeLLM(messages=iter(["Market report."]))


def _system_content():
    return "\n".join(
        m.content
        for m in _CapturingFakeLLM.captured_messages
        if getattr(m, "type", None) == "system"
    )


@pytest.mark.unit
def test_prefetched_wyckoff_and_oneil_blocks_reach_llm(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.agents.analysts.market_analyst.analyze_wyckoff_structure",
        lambda *_args: '{"phase_bias":"bullish","sentinel":"SENTINEL_WYCKOFF_PAYLOAD"}',
    )
    monkeypatch.setattr(
        "tradingagents.agents.analysts.market_analyst.analyze_oneil_setup",
        lambda *_args: '{"primary_pattern":{"pattern_type":"flat_base"},"setup_bias":"bullish","sentinel":"SENTINEL_ONEIL_PAYLOAD"}',
    )

    create_market_analyst(_fake_llm())(_make_state())

    system_content = _system_content()
    assert "SENTINEL_WYCKOFF_PAYLOAD" in system_content
    assert "SENTINEL_ONEIL_PAYLOAD" in system_content


@pytest.mark.unit
def test_prefetched_reads_are_not_bound_as_tools(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.agents.analysts.market_analyst.analyze_wyckoff_structure",
        lambda *_args: '{"phase_bias":"neutral"}',
    )
    monkeypatch.setattr(
        "tradingagents.agents.analysts.market_analyst.analyze_oneil_setup",
        lambda *_args: '{"primary_pattern":null,"setup_bias":"neutral","other_detections":[]}',
    )

    create_market_analyst(_fake_llm())(_make_state())

    tool_names = _CapturingFakeLLM.captured_tool_names
    assert "get_wyckoff_structure" not in tool_names
    assert "get_oneil_setup" not in tool_names
    assert {
        "get_stock_data",
        "get_indicators",
        "get_verified_market_snapshot",
        "get_chart_patterns",
        "get_trend_template",
    }.issubset(tool_names)


@pytest.mark.unit
def test_prefetch_failures_degrade_gracefully(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.agents.analysts.market_analyst.analyze_wyckoff_structure",
        lambda *_args: '{"phase_bias":"bullish"}',
    )

    def raise_oneil(*_args):
        raise ValueError("boom")

    monkeypatch.setattr(
        "tradingagents.agents.analysts.market_analyst.analyze_oneil_setup",
        raise_oneil,
    )

    result = create_market_analyst(_fake_llm())(_make_state())

    assert "market_report" in result
    assert '"setup_bias": "neutral"' in _system_content()

    def raise_wyckoff(*_args):
        raise ValueError("boom")

    monkeypatch.setattr(
        "tradingagents.agents.analysts.market_analyst.analyze_wyckoff_structure",
        raise_wyckoff,
    )
    monkeypatch.setattr(
        "tradingagents.agents.analysts.market_analyst.analyze_oneil_setup",
        lambda *_args: '{"primary_pattern":null,"setup_bias":"bullish","other_detections":[]}',
    )

    result = create_market_analyst(_fake_llm())(_make_state())

    assert "market_report" in result
    assert '"phase_bias": "neutral"' in _system_content()


@pytest.mark.unit
def test_invalidated_wyckoff_read_is_explained_in_the_prompt(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.agents.analysts.market_analyst.analyze_wyckoff_structure",
        lambda *_args: '{"phase_bias":"neutral","invalidated":true}',
    )
    monkeypatch.setattr(
        "tradingagents.agents.analysts.market_analyst.analyze_oneil_setup",
        lambda *_args: '{"primary_pattern":null,"setup_bias":"neutral","other_detections":[]}',
    )

    create_market_analyst(_fake_llm())(_make_state())

    assert "range_failure" in _system_content()


@pytest.mark.unit
def test_base_pattern_paragraph_reaches_the_prompt(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.agents.analysts.market_analyst.analyze_wyckoff_structure",
        lambda *_args: '{"phase_bias":"neutral"}',
    )
    monkeypatch.setattr(
        "tradingagents.agents.analysts.market_analyst.analyze_oneil_setup",
        lambda *_args: '{"primary_pattern":{"pattern_type":"flat_base"},"setup_bias":"bullish"}',
    )

    create_market_analyst(_fake_llm())(_make_state())

    assert "second_low_behavior" in _system_content()


@pytest.mark.unit
def test_double_bottom_supersede_rule_present(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.agents.analysts.market_analyst.analyze_wyckoff_structure",
        lambda *_args: '{"phase_bias":"neutral"}',
    )
    monkeypatch.setattr(
        "tradingagents.agents.analysts.market_analyst.analyze_oneil_setup",
        lambda *_args: '{"primary_pattern":{"pattern_type":"flat_base"},"setup_bias":"neutral"}',
    )

    create_market_analyst(_fake_llm())(_make_state())

    assert "single structure" in _system_content()
