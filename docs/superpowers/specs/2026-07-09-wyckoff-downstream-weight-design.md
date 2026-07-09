# Wyckoff Weight-Rule Extension into Bull/Bear/Risk Debate

Date: 2026-07-09

## Purpose

Per `WYCKOFF_ANALYSIS_PLAN.md`'s "后续迭代" item 4: extend the Wyckoff structural
read's weight/precedence rule (today only enforced inside the Market
Analyst's own report-writing prompt) into the downstream bull/bear
researcher debate and the aggressive/neutral/conservative risk debate, so
those agents treat a non-neutral `phase_bias` as a weighted signal rather
than one undifferentiated line inside `market_report`.

Investigation before designing: all five downstream agents already receive
the full `market_report` text, which reliably contains a Wyckoff
`phase_bias`/`dominant_weight` row because of `market_analyst.py`'s own
prefetch-and-embed pattern (the same fix class used for the earlier
sentiment-analyst tool-skipping bug — prefetch deterministic data into the
prompt directly rather than trusting an LLM to call a tool or transcribe
faithfully). So the data is already present; the gap is that none of the
five prompts tell the agent how to weight it. This is a prompt-guidance
change, not a data-plumbing change.

Separately, today's earlier invalidation feature (`docs/superpowers/specs/2026-07-09-wyckoff-invalidation-design.md`)
means `phase_bias` can now read `"neutral"` specifically because a prior
breakout failed — but `market_analyst.py`'s prompt predates that feature and
never mentions `invalidated`/`range_failure`, so the report would silently
present that case identically to "no structure found at all". This design
also closes that gap so the five downstream prompts have something to
reference.

## Scope

- Applies to: `tradingagents/agents/analysts/market_analyst.py` (project-custom,
  prompt-text addition only) and these 5 upstream files, user-approved for this
  exact purpose (see project memory `project_wyckoff_downstream_approval`):
  `tradingagents/agents/researchers/bull_researcher.py`,
  `tradingagents/agents/researchers/bear_researcher.py`,
  `tradingagents/agents/risk_mgmt/aggressive_debator.py`,
  `tradingagents/agents/risk_mgmt/neutral_debator.py`,
  `tradingagents/agents/risk_mgmt/conservative_debator.py`. Plus their test
  files (new: one small test each for the 5 debate files; existing: one
  addition to `tests/test_market_analyst_prefetch.py`).
- Does not apply to: `AgentState`/`agent_states.py` (no new state keys — the
  data already flows through `market_report`), `trading_graph.py`,
  `wyckoff_bias.py` or any other Wyckoff detection file (no detection logic
  changes), `research_manager.py`/`trader` (out of scope — the plan item
  names bull/bear researcher and risk debate specifically).
- Out of scope (not part of this design): independently re-fetching
  `analyze_wyckoff_structure` inside each of the 5 nodes (rejected during
  brainstorming — the data is already reliably present in `market_report`;
  re-fetching would be redundant plumbing for a problem that doesn't exist
  here, unlike the original sentiment-analyst case where the underlying
  problem was an LLM skipping a tool call it needed to make itself);
  applying any analogous weighting language to the O'Neil `setup_bias`/
  `secondary_weight` signal (not requested by this plan item; O'Neil already
  has its own three-tier precedence documented in `market_analyst.py`, and
  extending that downstream too is a separate decision the user hasn't made).

## Approaches considered

1. **Prompt-guidance-only extension, reusing `market_report`'s existing
   content** (chosen). Minimal, matches what the plan item literally asks
   for ("extend the weight *rule*"), and avoids adding redundant compute or
   a new AgentState key for data that's already reachable.
2. Independent re-fetch + injected summary block in each of the 5 nodes.
   Rejected: over-engineered relative to the actual gap (a missing
   instruction, not missing data), and would introduce five more places that
   call `analyze_wyckoff_structure`, redundant with `market_analyst.py`'s
   existing prefetch.
3. Add a dedicated `wyckoff_summary` `AgentState` key populated once by
   `market_analyst.py`, consumed by all 5 downstream nodes instead of
   parsing free text. Rejected for this pass: a reasonable idea in the
   abstract, but changes the typed `AgentState` (a cross-cutting contract
   CLAUDE.md calls out as needing care) for a problem prompt guidance
   already solves; revisit only if in practice the downstream agents are
   observed to ignore the free-text signal.

## Design

### `market_analyst.py` prompt update

The existing paragraph (around the current `<wyckoff_structure>` block)
gains one additional sentence after "Do not invent Wyckoff events beyond
what this JSON reports.":

> If the JSON's `invalidated` field is `true`, the `phase_bias` has been
> forced to neutral because the breakout implied by the reached phase later
> reversed back through the range boundary (see the `range_failure` event
> for its date and price) — state this explicitly as an invalidated
> breakout, not as "no clear structure found", and do not cite the
> pre-invalidation phase or events as still-live directional support.

The existing Markdown-table instruction line gains "invalidated flag":
"...including a row for the Wyckoff phase, phase_bias, dominant_weight, and
invalidated flag, and a separate row for..."

### Per-agent guidance paragraphs

Each paragraph is inserted directly before that function's closing "Use
this information..." / "Engage..." sentence, so it reads as part of the
existing instructions rather than a bolted-on appendix. Exact wording:

**`bull_researcher.py`** (`bull_node`):
> When the market research report includes a Wyckoff `phase_bias` reading
> with a `dominant_weight`, treat a bullish `phase_bias` as strong,
> code-verified supporting evidence for your case — cite the specific phase
> and events by date. If `phase_bias` is bearish, you must still build the
> strongest bull case you can, but explicitly address why your evidence
> outweighs it rather than ignoring it. If the report notes the Wyckoff read
> was invalidated (a breakout that failed), do not treat the earlier
> directional history as live support — argue from the remaining evidence
> instead.

**`bear_researcher.py`** (`bear_node`), mirrored:
> When the market research report includes a Wyckoff `phase_bias` reading
> with a `dominant_weight`, treat a bearish `phase_bias` as strong,
> code-verified supporting evidence for your case — cite the specific phase
> and events by date. If `phase_bias` is bullish, you must still build the
> strongest bear case you can, but explicitly address why your evidence
> outweighs it rather than ignoring it. If the report notes the Wyckoff read
> was invalidated (a breakout that failed), do not treat the earlier
> directional history as live support — argue from the remaining evidence
> instead.

**`aggressive_debator.py`** (`aggressive_node`):
> If the market research report's Wyckoff `phase_bias` agrees with the
> direction implied by the trader's decision, cite it as reinforcing,
> code-verified evidence for backing the aggressive stance. If it conflicts,
> or the report notes the Wyckoff read was invalidated (a breakout that
> failed), acknowledge the added uncertainty but argue the potential reward
> still justifies the risk.

**`conservative_debator.py`** (`conservative_node`):
> Treat a Wyckoff `phase_bias` in the market research report that conflicts
> with the trader's decision, or a report noting the Wyckoff read was
> invalidated (a breakout that failed), as concrete, code-verified grounds
> for caution — cite it explicitly when arguing for a more conservative
> approach.

**`neutral_debator.py`** (`neutral_node`):
> Weigh the market research report's Wyckoff `phase_bias` and
> `dominant_weight` (and any noted invalidation) as one factor among several
> — avoid overweighting it in either direction, and call out if the
> aggressive or conservative analysts are over- or under-weighting it
> relative to the report's own `dominant_weight`.

## Testing plan

New tests, one per debate file (`tests/test_bull_researcher.py`,
`tests/test_bear_researcher.py`, `tests/test_aggressive_debator.py`,
`tests/test_neutral_debator.py`, `tests/test_conservative_debator.py` — new
files since none currently exist for these agents): a minimal stub LLM
object (`invoke(prompt) -> object with .content`, no `bind_tools`/
`ChatPromptTemplate` needed since these nodes call `llm.invoke(prompt)`
directly) captures the prompt string; the test builds a minimal state dict
and asserts the new guidance sentence's distinguishing phrase (e.g.
`"dominant_weight"` and `"invalidated"`) is present in the captured prompt.

Addition to the existing `tests/test_market_analyst_prefetch.py`: one new
test asserting that when the prefetched Wyckoff JSON has
`"invalidated": true`, the captured system prompt contains the word
`"invalidated"` (confirming the new sentence is wired into the f-string,
not just present in the source file).

## Acceptance criteria

- No `AgentState` key changes; `market_report`/`trader_investment_plan`/etc.
  remain the only data channel into the 5 debate nodes.
- Each of the 5 files' new paragraph is present in the actual prompt string
  sent to the LLM (verified by test, not just by reading the source).
- `market_analyst.py`'s Wyckoff paragraph explicitly explains `invalidated`
  before the 5 downstream prompts reference it.
- No behavior change to `wyckoff_bias.py` or any other detection file.
- Existing tests for `market_analyst.py` still pass unmodified aside from
  the one planned addition.

> This module is for research and analysis support only; it does not
> constitute investment advice and does not place trades.
