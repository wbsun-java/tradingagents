---
name: codex-delegate
description: Use when implementing a plan task for TradingAgents backend/agent code (stage 3 of the Claude-architect workflow) - drives Codex CLI non-interactively to write the module and its tests, self-verify, and iterate via resume before escalating to the user.
---

# Codex Delegate

Drives a single Codex CLI turn per plan task. Codex writes the implementation
and its tests together and self-verifies before returning; this skill's job is
constructing the prompt, invoking Codex, independently re-verifying, and
capping retries.

Reference: `docs/superpowers/specs/2026-07-06-codex-delegate-workflow-design.md`
(stage 3).

## Preconditions

- An approved implementation plan task exists with: a description, acceptance
  criteria, and an explicit verification command (e.g.
  `pytest -q tests/test_X.py`, `ruff check <files>`).
- You are NOT going to hand-edit the files this task covers. Any disagreement
  with Codex's output becomes feedback in a resume prompt, never a direct
  edit.

## Procedure

1. **Build the task prompt.** Include, verbatim:
   - The task's description and acceptance criteria from the plan.
   - A pointer to the design spec file for this feature.
   - Repo conventions that apply: 150-line file cap per new file; do not edit
     files that came from the original upstream repo without explicit
     approval; route market-data access through `tradingagents/dataflows/`;
     preserve typed `AgentState` keys; when adding an analyst, update its
     factory, tool node, execution plan, conditional route, CLI display
     mapping, and tests together.
   - An explicit instruction: "Write the module and its tests together, then
     run `<verification command>` yourself and iterate until it passes
     before finishing. Do not return a first draft for someone else to
     test."

2. **Invoke Codex:**
   ```bash
   codex exec -s workspace-write -C <repo-root> \
     --output-last-message /tmp/codex-last-message.txt \
     "<task prompt from step 1>"
   ```
   Never add `--dangerously-bypass-approvals-and-sandbox`.

3. **Re-verify independently.** Run the task's verification command
   yourself:
   ```bash
   <verification command from the plan, e.g. pytest -q tests/test_X.py>
   ```
   Do not rely on Codex's own claim that it passed — its summary describes
   what it intended, not necessarily what happened.

4. **Review the diff.** Run `git diff` and check for convention adherence
   (file-size cap, no unapproved upstream edits, vendor routing, `AgentState`
   keys) in addition to the verification command's pass/fail.

5. **Decide:**
   - **Pass** (your re-run is green and the diff looks correct) -> task done,
     move to the next plan task.
   - **Fail** -> resume the same Codex session with concrete feedback:
     ```bash
     codex exec resume --last "<exact failure output or review feedback>"
     ```
     Repeat steps 3-5. Cap at 3 total attempts for this task.
   - **Still failing after 3 attempts** -> stop. Show the user the diff and
     the failure output, and ask for direction. Do not keep retrying and do
     not escalate the sandbox mode to work around a failure.

## Guardrails

- Sandbox is always `-s workspace-write`.
- Retry cap is 3 attempts per task, not per feature.
- Never hand-edit files inside Codex's scope for this task.
- Never bypass approvals/sandbox to "get it working."
