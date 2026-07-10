---
name: project-model-role-split
description: "User's model-role assignment (set 2026-07-10): Claude Fable 5 = orchestrator/architect only; all coding/scripts/tests delegated to Codex 5.6 tiers (sol/terra/luna)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 05d522f3-0e18-46f9-9b7f-26bbb604f3f0
---

Set 2026-07-10, refining [[project_claude_architect_workflow]]:

- **Claude Fable 5** (this session's model, user-switched via `/model`) is the
  orchestrator/architect ONLY — brainstorming, specs, plans, review, verification
  coordination. It should not hand-write feature code, scripts, or tests.
- **Codex CLI** does all implementation, invoked via the `codex-delegate` skill with an
  explicit per-task model tier (`codex exec -m <model> ...`):
  - `gpt-5.6-sol` — most powerful; novel/hard algorithm work
  - `gpt-5.6-terra` — balanced; standard feature tasks
  - `gpt-5.6-luna` — cheapest; mechanical wiring/labeling/scaffolding tasks
- Model IDs confirmed from `~/.codex/models_cache.json` (codex-cli 0.144.0); the config
  default is still `model = "gpt-5.5"`, so the `-m` flag must be passed explicitly.

**Why:** the user wants cost/capability matched per task and Claude kept at the
architecture altitude — same "Claude architects, Codex executes" principle as before, now
with an explicit three-tier Codex model choice per plan task.

**How to apply:** when writing implementation plans in tradingagents, annotate each task
with its Codex tier; when running codex-delegate, always pass `-m gpt-5.6-{sol|terra|luna}`.
