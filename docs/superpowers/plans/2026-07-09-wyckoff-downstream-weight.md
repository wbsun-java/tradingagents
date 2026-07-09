# Wyckoff Weight-Rule Extension Into Bull/Bear/Risk Debate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the Wyckoff structural read's weight rule from the Market Analyst's own report into the bull/bear researcher debate and the aggressive/neutral/conservative risk debate, and make `market_analyst.py`'s prompt explain the `invalidated` field those five prompts reference.

**Architecture:** Prompt-text-only change. `market_report` already reliably carries a Wyckoff `phase_bias`/`dominant_weight` row (via `market_analyst.py`'s existing prefetch). Each of the 5 downstream agent prompts gets one new paragraph telling it how to weight that signal; `market_analyst.py` gets one new sentence explaining `invalidated`/`range_failure` plus an updated Markdown-table instruction. No `AgentState` changes, no new data plumbing.

**Tech Stack:** Python, LangChain (`ChatPromptTemplate` for `market_analyst.py`, raw f-string + `llm.invoke` for the 5 debate files), pytest (`@pytest.mark.unit`), `langchain_core.language_models.fake_chat_models.GenericFakeChatModel` for prompt-capture tests.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-09-wyckoff-downstream-weight-design.md`.
- The 5 files below are upstream (confirmed via `git log --follow` tracing to the original public release) — the user has given explicit, scoped approval to edit exactly these files for exactly this purpose (see project memory `project_wyckoff_downstream_approval`): `tradingagents/agents/researchers/bull_researcher.py`, `tradingagents/agents/researchers/bear_researcher.py`, `tradingagents/agents/risk_mgmt/aggressive_debator.py`, `tradingagents/agents/risk_mgmt/neutral_debator.py`, `tradingagents/agents/risk_mgmt/conservative_debator.py`.
- `tradingagents/agents/analysts/market_analyst.py` is project-custom (already repeatedly edited for Wyckoff/O'Neil integration) — no approval gate applies to it.
- No `AgentState`/`agent_states.py` changes. No changes to `wyckoff_bias.py` or any other Wyckoff detection file — this plan only touches agent prompts.
- Default verification per CLAUDE.md for an isolated additive change: run each task's own test file(s) plus `ruff check` on touched files.

---

### Task 1: `market_analyst.py` — explain `invalidated` in its own prompt

**Files:**
- Modify: `tradingagents/agents/analysts/market_analyst.py`
- Test: `tests/test_market_analyst_prefetch.py`

**Interfaces:**
- Consumes: no new interfaces — reads the same prefetched `wyckoff_block` JSON string it already embeds via `{wyckoff_block}` in its prompt.
- Produces: no new interfaces — this only changes prompt text. Tasks 2 and 3's guidance paragraphs assume `market_report` explains `invalidated`/`range_failure`, but they don't call any function this task defines; they just reference the same English text a reader of `market_report` would see.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_market_analyst_prefetch.py` (append at the end of the file):

```python
@pytest.mark.unit
def test_invalidated_wyckoff_read_is_explained_in_the_prompt(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.agents.analysts.market_analyst.analyze_wyckoff_structure",
        lambda *_args: '{"phase_bias":"neutral","invalidated":true}',
    )
    monkeypatch.setattr(
        "tradingagents.agents.analysts.market_analyst.analyze_oneil_setup",
        lambda *_args: '{"setup_bias":"neutral"}',
    )

    create_market_analyst(_fake_llm())(_make_state())

    assert "range_failure" in _system_content()
```

(`"range_failure"` — not `"invalidated"` — is the assertion anchor because the fake JSON payload above already contains the literal substring `"invalidated"` in its raw text; asserting on `"range_failure"`, which only appears in the new instructional sentence, proves that sentence actually reached the prompt rather than just the raw JSON blob being echoed.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_market_analyst_prefetch.py -k invalidated_wyckoff -v`
Expected: FAIL — `AssertionError` (`"range_failure"` not yet present anywhere in the prompt).

- [ ] **Step 3: Update the prompt text**

In `tradingagents/agents/analysts/market_analyst.py`, find this exact sentence (part of a larger f-string, ends the Wyckoff paragraph):

```
Do not invent Wyckoff events beyond what this JSON reports.
```

Replace it with:

```
Do not invent Wyckoff events beyond what this JSON reports. If the JSON's `invalidated` field is true, the `phase_bias` has been forced to neutral because the breakout implied by the reached phase later reversed back through the range boundary (see the `range_failure` event for its date and price) -- state this explicitly as an invalidated breakout, not as "no clear structure found", and do not cite the pre-invalidation phase or events as still-live directional support.
```

Then find this exact sentence (later in the same function, the Markdown-table instruction):

```
Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read, including a row for the Wyckoff phase, phase_bias, and dominant_weight, and a separate row for the O'Neil cup-with-handle status, setup_bias, and secondary_weight.
```

Replace it with:

```
Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read, including a row for the Wyckoff phase, phase_bias, dominant_weight, and invalidated flag, and a separate row for the O'Neil cup-with-handle status, setup_bias, and secondary_weight.
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_market_analyst_prefetch.py -v`
Expected: PASS, all tests in the file (the 3 pre-existing plus the 1 new one).

- [ ] **Step 5: Ruff check**

Run: `ruff check tradingagents/agents/analysts/market_analyst.py tests/test_market_analyst_prefetch.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/agents/analysts/market_analyst.py tests/test_market_analyst_prefetch.py
git commit -m "feat(wyckoff): explain invalidated breakouts in the market analyst prompt"
```

---

### Task 2: Bull/bear researcher weighting guidance

**Files:**
- Modify: `tradingagents/agents/researchers/bull_researcher.py`
- Modify: `tradingagents/agents/researchers/bear_researcher.py`
- Test: `tests/test_bull_researcher.py` (new)
- Test: `tests/test_bear_researcher.py` (new)

**Interfaces:**
- Consumes: no new interfaces — both functions already read `state["market_report"]` unchanged.
- Produces: no new interfaces — prompt text only. `bull_node`/`bear_node`'s existing return shape (`{"investment_debate_state": ...}`) is unchanged.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bull_researcher.py`:

```python
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
        "market_report": "Wyckoff phase_bias: bearish, dominant_weight: 0.6",
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
```

Create `tests/test_bear_researcher.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_bull_researcher.py tests/test_bear_researcher.py -v`
Expected: FAIL — `AssertionError` (`"invalidated"` not yet present in either prompt; `market_report` in both fixtures deliberately omits that word so the assertion only passes once the new guidance paragraph is added).

- [ ] **Step 3: Update `bull_researcher.py`**

In `tradingagents/agents/researchers/bull_researcher.py`, find this exact line inside the prompt f-string:

```
Use this information to deliver a compelling bull argument, refute the bear's concerns, and engage in a dynamic debate that demonstrates the strengths of the bull position.
```

Replace it with:

```
When the market research report includes a Wyckoff phase_bias reading with a dominant_weight, treat a bullish phase_bias as strong, code-verified supporting evidence for your case -- cite the specific phase and events by date. If phase_bias is bearish, you must still build the strongest bull case you can, but explicitly address why your evidence outweighs it rather than ignoring it. If the report notes the Wyckoff read was invalidated (a breakout that failed), do not treat the earlier directional history as live support -- argue from the remaining evidence instead.
Use this information to deliver a compelling bull argument, refute the bear's concerns, and engage in a dynamic debate that demonstrates the strengths of the bull position.
```

- [ ] **Step 4: Update `bear_researcher.py`**

In `tradingagents/agents/researchers/bear_researcher.py`, find this exact line inside the prompt f-string:

```
Use this information to deliver a compelling bear argument, refute the bull's claims, and engage in a dynamic debate that demonstrates the risks and weaknesses of investing in the {target_label}.
```

Replace it with:

```
When the market research report includes a Wyckoff phase_bias reading with a dominant_weight, treat a bearish phase_bias as strong, code-verified supporting evidence for your case -- cite the specific phase and events by date. If phase_bias is bullish, you must still build the strongest bear case you can, but explicitly address why your evidence outweighs it rather than ignoring it. If the report notes the Wyckoff read was invalidated (a breakout that failed), do not treat the earlier directional history as live support -- argue from the remaining evidence instead.
Use this information to deliver a compelling bear argument, refute the bull's claims, and engage in a dynamic debate that demonstrates the risks and weaknesses of investing in the {target_label}.
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_bull_researcher.py tests/test_bear_researcher.py -v`
Expected: PASS, 2 passed.

- [ ] **Step 6: Ruff check**

Run: `ruff check tradingagents/agents/researchers/bull_researcher.py tradingagents/agents/researchers/bear_researcher.py tests/test_bull_researcher.py tests/test_bear_researcher.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add tradingagents/agents/researchers/bull_researcher.py tradingagents/agents/researchers/bear_researcher.py tests/test_bull_researcher.py tests/test_bear_researcher.py
git commit -m "feat(wyckoff): add Wyckoff weighting guidance to bull/bear researcher prompts"
```

---

### Task 3: Aggressive/neutral/conservative risk debate weighting guidance

**Files:**
- Modify: `tradingagents/agents/risk_mgmt/aggressive_debator.py`
- Modify: `tradingagents/agents/risk_mgmt/neutral_debator.py`
- Modify: `tradingagents/agents/risk_mgmt/conservative_debator.py`
- Test: `tests/test_aggressive_debator.py` (new)
- Test: `tests/test_neutral_debator.py` (new)
- Test: `tests/test_conservative_debator.py` (new)

**Interfaces:**
- Consumes: no new interfaces — all three functions already read `state["market_report"]` and `state["trader_investment_plan"]` unchanged.
- Produces: no new interfaces — prompt text only. Each function's existing return shape (`{"risk_debate_state": ...}`) is unchanged.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_aggressive_debator.py`:

```python
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
            "history": "", "aggressive_history": "", "conservative_history": "",
            "neutral_history": "", "current_aggressive_response": "",
            "current_conservative_response": "", "current_neutral_response": "",
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
```

Create `tests/test_conservative_debator.py`:

```python
"""Prompt-content test for the conservative risk debator's Wyckoff weighting guidance."""

from __future__ import annotations

import pytest

from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator


class _StubResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _StubLLM:
    def __init__(self) -> None:
        self.last_prompt: str | None = None

    def invoke(self, prompt: str) -> _StubResponse:
        self.last_prompt = prompt
        return _StubResponse("Conservative argument.")


def _make_state() -> dict:
    return {
        "risk_debate_state": {
            "history": "", "aggressive_history": "", "conservative_history": "",
            "neutral_history": "", "current_aggressive_response": "",
            "current_conservative_response": "", "current_neutral_response": "",
            "count": 0,
        },
        "market_report": "Wyckoff phase_bias: bearish, dominant_weight: 0.6",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
        "trader_investment_plan": "Buy.",
        "company_of_interest": "AAPL",
        "asset_type": "stock",
    }


@pytest.mark.unit
def test_prompt_tells_conservative_analyst_how_to_weight_wyckoff_phase_bias():
    llm = _StubLLM()

    create_conservative_debator(llm)(_make_state())

    assert llm.last_prompt is not None
    assert "phase_bias" in llm.last_prompt
    assert "invalidated" in llm.last_prompt
```

Create `tests/test_neutral_debator.py`:

```python
"""Prompt-content test for the neutral risk debator's Wyckoff weighting guidance."""

from __future__ import annotations

import pytest

from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator


class _StubResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _StubLLM:
    def __init__(self) -> None:
        self.last_prompt: str | None = None

    def invoke(self, prompt: str) -> _StubResponse:
        self.last_prompt = prompt
        return _StubResponse("Neutral argument.")


def _make_state() -> dict:
    return {
        "risk_debate_state": {
            "history": "", "aggressive_history": "", "conservative_history": "",
            "neutral_history": "", "current_aggressive_response": "",
            "current_conservative_response": "", "current_neutral_response": "",
            "count": 0,
        },
        "market_report": "Wyckoff phase_bias: neutral, dominant_weight: 0.6",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
        "trader_investment_plan": "Buy.",
        "company_of_interest": "AAPL",
        "asset_type": "stock",
    }


@pytest.mark.unit
def test_prompt_tells_neutral_analyst_how_to_weight_wyckoff_phase_bias():
    llm = _StubLLM()

    create_neutral_debator(llm)(_make_state())

    assert llm.last_prompt is not None
    assert "over- or under-weighting" in llm.last_prompt
```

(`"over- or under-weighting"` is the assertion anchor rather than `"dominant_weight"` — that word already appears in this test's own `market_report` fixture string, so asserting on it alone would pass even without the new paragraph. `"over- or under-weighting"` only exists in the new guidance sentence, so it genuinely proves the paragraph was added.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_aggressive_debator.py tests/test_neutral_debator.py tests/test_conservative_debator.py -v`
Expected: FAIL — `AssertionError` in all three (none of `"invalidated"`/`"over- or under-weighting"` appear in any fixture's `market_report` text, only in the not-yet-added guidance paragraphs).

- [ ] **Step 3: Update `aggressive_debator.py`**

In `tradingagents/agents/risk_mgmt/aggressive_debator.py`, find this exact line inside the prompt f-string:

```
Engage actively by addressing any specific concerns raised, refuting the weaknesses in their logic, and asserting the benefits of risk-taking to outpace market norms. Maintain a focus on debating and persuading, not just presenting data. Challenge each counterpoint to underscore why a high-risk approach is optimal. Output conversationally as if you are speaking without any special formatting.""" + get_language_instruction()
```

Replace it with:

```
If the market research report's Wyckoff phase_bias agrees with the direction implied by the trader's decision, cite it as reinforcing, code-verified evidence for backing the aggressive stance. If it conflicts, or the report notes the Wyckoff read was invalidated (a breakout that failed), acknowledge the added uncertainty but argue the potential reward still justifies the risk.

Engage actively by addressing any specific concerns raised, refuting the weaknesses in their logic, and asserting the benefits of risk-taking to outpace market norms. Maintain a focus on debating and persuading, not just presenting data. Challenge each counterpoint to underscore why a high-risk approach is optimal. Output conversationally as if you are speaking without any special formatting.""" + get_language_instruction()
```

- [ ] **Step 4: Update `conservative_debator.py`**

In `tradingagents/agents/risk_mgmt/conservative_debator.py`, find this exact line inside the prompt f-string:

```
Engage by questioning their optimism and emphasizing the potential downsides they may have overlooked. Address each of their counterpoints to showcase why a conservative stance is ultimately the safest path for the firm's assets. Focus on debating and critiquing their arguments to demonstrate the strength of a low-risk strategy over their approaches. Output conversationally as if you are speaking without any special formatting.""" + get_language_instruction()
```

Replace it with:

```
Treat a Wyckoff phase_bias in the market research report that conflicts with the trader's decision, or a report noting the Wyckoff read was invalidated (a breakout that failed), as concrete, code-verified grounds for caution -- cite it explicitly when arguing for a more conservative approach.

Engage by questioning their optimism and emphasizing the potential downsides they may have overlooked. Address each of their counterpoints to showcase why a conservative stance is ultimately the safest path for the firm's assets. Focus on debating and critiquing their arguments to demonstrate the strength of a low-risk strategy over their approaches. Output conversationally as if you are speaking without any special formatting.""" + get_language_instruction()
```

- [ ] **Step 5: Update `neutral_debator.py`**

In `tradingagents/agents/risk_mgmt/neutral_debator.py`, find this exact line inside the prompt f-string:

```
Engage actively by analyzing both sides critically, addressing weaknesses in the aggressive and conservative arguments to advocate for a more balanced approach. Challenge each of their points to illustrate why a moderate risk strategy might offer the best of both worlds, providing growth potential while safeguarding against extreme volatility. Focus on debating rather than simply presenting data, aiming to show that a balanced view can lead to the most reliable outcomes. Output conversationally as if you are speaking without any special formatting.""" + get_language_instruction()
```

Replace it with:

```
Weigh the market research report's Wyckoff phase_bias and dominant_weight (and any noted invalidation) as one factor among several -- avoid overweighting it in either direction, and call out if the aggressive or conservative analysts are over- or under-weighting it relative to the report's own dominant_weight.

Engage actively by analyzing both sides critically, addressing weaknesses in the aggressive and conservative arguments to advocate for a more balanced approach. Challenge each of their points to illustrate why a moderate risk strategy might offer the best of both worlds, providing growth potential while safeguarding against extreme volatility. Focus on debating rather than simply presenting data, aiming to show that a balanced view can lead to the most reliable outcomes. Output conversationally as if you are speaking without any special formatting.""" + get_language_instruction()
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/test_aggressive_debator.py tests/test_neutral_debator.py tests/test_conservative_debator.py -v`
Expected: PASS, 3 passed.

- [ ] **Step 7: Ruff check**

Run: `ruff check tradingagents/agents/risk_mgmt/aggressive_debator.py tradingagents/agents/risk_mgmt/neutral_debator.py tradingagents/agents/risk_mgmt/conservative_debator.py tests/test_aggressive_debator.py tests/test_neutral_debator.py tests/test_conservative_debator.py`
Expected: no errors.

- [ ] **Step 8: Full regression check across all 6 touched agent files' tests plus market_analyst**

Run: `pytest -q tests/test_market_analyst_prefetch.py tests/test_bull_researcher.py tests/test_bear_researcher.py tests/test_aggressive_debator.py tests/test_neutral_debator.py tests/test_conservative_debator.py`
Expected: PASS, 9 passed (`test_market_analyst_prefetch.py`'s 3 pre-existing tests + Task 1's 1 new test = 4, plus 1 new test in each of the 5 debate files = 5, for 9 total).

- [ ] **Step 9: Commit**

```bash
git add tradingagents/agents/risk_mgmt/aggressive_debator.py tradingagents/agents/risk_mgmt/neutral_debator.py tradingagents/agents/risk_mgmt/conservative_debator.py tests/test_aggressive_debator.py tests/test_neutral_debator.py tests/test_conservative_debator.py
git commit -m "feat(wyckoff): add Wyckoff weighting guidance to risk debate prompts"
```

---

## Acceptance Criteria (from spec)

- No `AgentState` key changes; `market_report`/`trader_investment_plan`/etc. remain the only data channel into the 5 debate nodes.
- Each of the 5 files' new paragraph is present in the actual prompt string sent to the LLM (verified by test, not just by reading the source).
- `market_analyst.py`'s Wyckoff paragraph explicitly explains `invalidated` before the 5 downstream prompts reference it.
- No behavior change to `wyckoff_bias.py` or any other detection file.
- Existing tests for `market_analyst.py` still pass unmodified aside from the one planned addition.

> This module is for research and analysis support only; it does not constitute investment advice and does not place trades.
