---
name: feedback-agy-interactive-tui
description: "Never route interactive/TUI CLI scenarios through agy --print — it hangs, can't hold multi-turn sessions"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: f07f425b-eaa0-4cc2-b863-a414877be25f
---

Never route an interactive/TUI scenario (e.g. the `tradingagents` questionary CLI) through
Antigravity's `agy --print` mode. It cannot hold a multi-turn TUI session and will loop
until `--print-timeout` fires, hanging the run.

**Why:** Discovered during the first full pilot of the Claude-architect 5-stage workflow
(memory-log-stats-cli feature) when stage 4 verification hung. Root cause diagnosed via
`~/.gemini/antigravity-cli/cli.log`. Fixed by re-running Antigravity against the actual
non-interactive script/fixture instead of the interactive CLI entry point.

**How to apply:** This is now a hard rule baked into the [[project_claude_architect_workflow]]
and the `antigravity-verify` skill. When a verification scenario involves an interactive/TUI
flow or requires human judgment, hand it to the user directly (stage 4 default) rather than
driving it through `agy`. Only route non-interactive, high-stakes/judgment-heavy checks to
Antigravity, and only opt-in (not default), to save tokens.
