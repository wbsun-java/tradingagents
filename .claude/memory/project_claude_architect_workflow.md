---
name: project-claude-architect-workflow
description: "Status and design of the user's 5-stage Claude-architect development workflow (brainstorm -> plan -> subagent dev cycle)"
metadata: 
  node_type: memory
  type: project
  originSessionId: f07f425b-eaa0-4cc2-b863-a414877be25f
---

The user's core mental model for this workflow, in his own words: **"Claude as the
architect, Codex as the executor, Gemini as the input taker."** Concretely, a custom 5-stage
workflow for building features in this repo: Gemini intake (optional pre-step, cleans up
messy raw input) -> Claude brainstorming -> Claude plan -> Codex-driven execution (stage 3,
gpt-5.5, sandboxed workspace-write) -> Antigravity/Gemini verification (stage 4, Gemini 3.1
Pro, opt-in). Claude owns architecture/planning/orchestration throughout; it does not expect
to hand-write the feature code itself once a plan exists — that's Codex's job.

Completed its first full end-to-end pilot on 2026-07-08 with the memory-log-stats-cli
feature (`scripts/memory_stats.py`, `tests/test_memory_stats.py`). Landed as commit 95c6f19;
the workflow spec itself (gemini-intake skill + finalized antigravity-verify + amended
workflow doc) landed as commit 87344cb. Both pushed to origin/main.

Second pilot, same day (2026-07-08): the O'Neil CANSLIM cup-with-handle feature, a much
bigger 6-task plan (see [[project_oneil_canslim_feature_status]] for full detail and
resume-point). All 6 `codex-delegate` tasks passed independent re-verification; paused
before stage 4 (`antigravity-verify`) at the user's request, uncommitted.

Two environment facts discovered/fixed while running `codex-delegate` on this pilot, worth
knowing before diagnosing a similar failure again on this same VM:
- Codex's sandbox (`bwrap`) was blocked by Ubuntu 24.04's
  `kernel.apparmor_restrict_unprivileged_userns` security default (confirmed via `dmesg`
  audit denials on `setpcap`/`net_admin`). Fixed by disabling that sysctl, persisted via
  `/etc/sysctl.d/99-unprivileged-userns.conf`, after explicit user confirmation — this is a
  standing security trade-off on this VM, not a one-off tweak, so don't casually suggest
  re-enabling it without checking whether Codex/bwrap still needs it disabled.
- This repo's own `.venv` was missing dev dependencies (`pytest`, `ruff` weren't installed,
  despite `CLAUDE.md` documenting `pip install -e ".[dev]"` as the setup step) — installed
  now, should persist for the life of this venv.

Current model-role split (informed by the [[feedback_agy_interactive_tui]] hang diagnosis):
- Interactive/TUI or judgment-heavy checks -> the user, directly.
- Deterministic single-command checks -> Codex, or a quick manual check.
- Non-interactive but high-stakes/judgment checks -> Antigravity, kept **opt-in** (not
  default) specifically to save tokens, per the user's explicit preference.

Stage 4 (`antigravity-verify` skill) now defaults to the user running verification
themselves; Antigravity is opt-in only.

**Why:** The user is iterating on this workflow itself as a meta-project — treat requests
to modify `codex-delegate`, `antigravity-verify`, or `gemini-intake` skills as changes to
active tooling they rely on daily, not one-off scripts.

**How to apply:** When asked to implement a plan task in this repo, check whether the user
wants to run it through this staged workflow (stage 3 Codex delegation, stage 4 verification)
rather than assuming a direct Claude-only implementation. Default new stage-4 verification
work to "hand the user a scenario to run," not Antigravity, unless they opt in.
