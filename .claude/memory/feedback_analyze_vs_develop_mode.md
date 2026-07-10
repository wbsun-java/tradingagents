---
name: feedback-analyze-vs-develop-mode
description: "How to disambiguate \"analyze a stock\" (run the product) vs \"develop the software\" (Claude-architect workflow) requests"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: f07f425b-eaa0-4cc2-b863-a414877be25f
---

Every request in this repo falls into one of two modes, and they must not be conflated:

**Mode A — "Analyze a stock" (using the product).** Signals: a ticker symbol, a date,
words like "analyze," "what's your view on," "run a trade recommendation for," "should I
buy X." Means: actually execute `TradingAgentsGraph.propagate(ticker, date, ...)` or the
`tradingagents` CLI. No brainstorming, no plan, no Codex, no Antigravity — that machinery
is for changing the software, not running it. The interactive `tradingagents` CLI has the
same TUI limitation as Antigravity ([[feedback_agy_interactive_tui]]) — I can't drive its
questionary prompts myself, so for an actual run either call `TradingAgentsGraph.propagate()`
directly in a script (non-interactive, I can do this myself) or hand the user the
interactive CLI to run themselves for the full guided experience.

**Mode B — "Develop the software" ([[project_claude_architect_workflow]]).** Signals: "add,"
"fix," "implement," "refactor," "build," "the win-rate calc is wrong," "let's change how the
trader agent decides X" — anything about the codebase's behavior, not a specific ticker's
outcome. Triggers brainstorm -> plan -> codex-delegate -> verify.

**The disambiguator:** does the request name a ticker/date and want a market opinion out the
other end (Mode A), or does it describe a change to code/behavior (Mode B)?

**Why:** Picking wrong is costly in both directions — either burning expensive LLM calls for
what was really a code question, or opening a whole dev workflow for what was just "run it
and show me." The user drew this distinction explicitly on 2026-07-08 after we finished
building the Mode-B workflow, to make sure it isn't mistakenly applied to Mode-A requests.

**How to apply:** If genuinely ambiguous (e.g. "check how the risk agents handle NVDA" could
mean either "run it and see" or "investigate/fix the risk-agent code"), ask which the user
means rather than guessing.
