---
name: project-wyckoff-downstream-approval
description: "User's explicit approval to edit 5 upstream agent-prompt files for the Wyckoff downstream weight-rule extension"
metadata: 
  node_type: memory
  type: project
  originSessionId: e0df2028-5f40-489b-b879-e32ad5dee1d3
---

On 2026-07-09 the user explicitly approved editing these 5 upstream files (confirmed via
`git log --follow` to trace back to the original public release, not this project's own
commits) to extend the Wyckoff weight rule into the bull/bear/risk debate — item 4 of
`WYCKOFF_ANALYSIS_PLAN.md`'s "后续迭代", see [[project_market_analyst_ta_modules]]:

- `tradingagents/agents/researchers/bull_researcher.py`
- `tradingagents/agents/researchers/bear_researcher.py`
- `tradingagents/agents/risk_mgmt/aggressive_debator.py`
- `tradingagents/agents/risk_mgmt/neutral_debator.py`
- `tradingagents/agents/risk_mgmt/conservative_debator.py`

**Why:** CLAUDE.md requires stopping and getting the user's explicit approval for the exact
file(s) before touching anything from the original upstream repo. This is the one durable
record of that approval having been granted, and for exactly this purpose.

**How to apply:** Approval is scoped to this specific Wyckoff-weight-extension feature, not a
blanket permission to edit these files for unrelated future work — if a later task touches
these same files for a different reason, treat that as needing its own fresh approval per
CLAUDE.md, don't assume this record covers it.
