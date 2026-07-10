---
name: feedback-avoid-upfront-tooling-scaffolds
description: User prefers growing the Claude-architect dev workflow incrementally from a validated pain point over adopting large speculative multi-role framework scaffolds
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 75c57e5d-6cdf-4687-bc54-99e8f52df6bd
---

On 2026-07-08 the user sketched an elaborate `ai-agent/` framework (roles/, skills/,
schemas/, gates/, pipelines/, memory/, prompts/, examples/, runs/ — ~67 files across 6 roles
and 7 concept categories) as a possible evolution of [[project_claude_architect_workflow]]'s
3-skill pipeline (gemini-intake, codex-delegate, antigravity-verify). After a walkthrough of
concrete overlaps (requirement-analyst role duplicating gemini-intake/brainstorming, review/
and testing/ subfolders over-decomposing what codex-delegate already does in two steps,
schemas/gates being unenforceable without a real validator script, config split across two
folders) the user agreed it was "too redundant for this project" and dropped it.

This happened right after the user separately floated three "mega-prompt" templates
(quantum-computing-visionary spec generator, PR-generator, and the same spec generator
again) for evaluation — all rejected for the same underlying reason: generic, maximalist,
comprehensive-looking structure that doesn't correspond to a validated need in this specific
repo.

**Why:** This matches the project's own CLAUDE.md philosophy (no premature abstraction, no
designing for hypothetical future requirements) — the user holds tooling/workflow decisions
to the same bar as product code, even though CLAUDE.md text itself only formally governs
product code.

**How to apply:** When the user proposes a new elaborate framework, config taxonomy, or
process scaffold for how development work gets done in this repo (not a product feature),
push back early with concrete overlap/redundancy analysis against what already exists
(`.claude/skills/`, `tradingagents/graph/`) rather than building it as specified. Recommend
adding one narrowly-scoped piece at a time, only once a specific pain point has actually been
hit in a real run — not a new folder/taxonomy up front.
