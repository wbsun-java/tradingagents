# Claude-architect / Codex-implementer workflow

Date: 2026-07-06

## Purpose

Formalize a repeatable process for developing TradingAgents where Claude acts as
architect (specs, plans, review), Codex CLI writes all backend implementation code
and tests, and Antigravity CLI (`agy`) independently exercises the feature
end-to-end before it's reported as done. This replaces the "Claude implements the
plan" step of the existing `superpowers:writing-plans` -> implementation flow with
a delegate-then-verify loop, for feature/backend work in this repository
specifically.

## Scope

- Applies to: TradingAgents feature/backend Python code (agents, dataflows, graph
  wiring, scripts) and its tests.
- Does not apply to: the tooling that implements this workflow itself (e.g. the new
  skill file described below), which Claude writes directly, same as any other skill.
- Does not change existing repo conventions (150-line file cap, no editing upstream
  files without approval, vendor routing through `tradingagents/dataflows/`, etc.) —
  those are inputs to the workflow, not replaced by it.

## Architecture

Five numbered stages, plus one situational pre-step. Stages 1 and 2 reuse
existing superpowers skills unchanged; stage 3 is the delegate loop; stage
4 is finalized below; stage 5 is the existing git-safety reporting
behavior.

**Gemini intake** (situational, not a numbered stage) -> only runs when
the input to stage 1 is messy raw material (a log dump, a rambling note,
an external doc/ticket) rather than an already-clear request. Gemini
(via `agy --print`) turns it into a structured brief — Problem,
Facts/constraints, Open questions — which becomes stage 1's starting
material instead of the raw input. Gemini never proposes architecture or
makes design decisions; decision-making stays with Claude. See
`.claude/skills/gemini-intake/SKILL.md`.

1. **Brainstorm** (`superpowers:brainstorming`) -> design spec under
   `docs/superpowers/specs/`.
2. **Plan** (`superpowers:writing-plans`) -> numbered implementation plan, where each
   task carries its own verification command (`pytest -q tests/test_X.py`,
   `ruff check <files>`), per this repo's existing conventions.
3. **Delegate** (new) -> for each plan task, Claude drives a Codex CLI turn that
   writes the module and its tests and self-verifies, then Claude independently
   re-verifies and reviews.
4. **End-to-end verify** (finalized) -> once all plan tasks for the
   feature pass stage 3, Claude builds a verification scenario and hands
   it to the user by default (Antigravity is an opt-in fallback) — see the
   rewritten stage-4 section below for the full rule.
5. **Report** -> Claude summarizes the diff and both verification results (unit +
   end-to-end) to the user. Nothing is committed without explicit user
   approval (existing git safety protocol is unchanged).

## Delegate loop (stage 3 detail)

For each task in the plan, in task order:

1. Claude constructs a task prompt containing: the task's description and
   acceptance criteria from the plan, a pointer to the design spec file, and the
   relevant repo conventions that apply to this task (150-line cap, upstream-file
   restriction, vendor routing, `AgentState` key preservation, etc. — reinforced
   directly in the prompt as belt-and-suspenders alongside `AGENTS.md`, which Codex
   already reads automatically).
2. Claude invokes:
   ```
   codex exec -s workspace-write -C <repo-root> --output-last-message <tmp-file> "<task prompt>"
   ```
   Instructing Codex to write the module **and** its tests together, then run
   `pytest`/`ruff` itself inside the sandbox and iterate until green before
   returning, rather than handing back a first-draft for Claude to test.
3. When Codex returns, Claude independently re-runs the task's verification
   command itself (does not trust Codex's self-report alone) and reads the
   resulting `git diff` for correctness and convention adherence.
4. **Pass** (Claude's own re-run is green and the diff looks correct) -> move to
   the next plan task.
   **Fail** -> Claude runs `codex exec resume --last "<specific failure output /
   review feedback>"` and retries, capped at 3 rounds for a given task. If still
   failing after 3 rounds, Claude stops, surfaces the diff and failures, and asks
   the user for direction rather than looping further or escalating sandbox
   permissions.
5. Claude never hand-edits files inside Codex's scope (implementation or test
   code) — disagreements become resume-prompt feedback, not direct edits.

## End-to-end verify loop (stage 4 detail)

Runs once, after all of a feature's plan tasks have passed stage 3 (not
per-task — unit-level correctness is already covered there; this stage
checks the assembled feature actually works end-to-end).

1. Claude constructs a verification scenario: what to run (e.g. "run
   `tradingagents` for ticker X on date Y with the relevant analyst
   enabled" or "invoke `TradingAgentsGraph.propagate(...)` directly for a
   faster check"), what output to inspect, and what "correct" looks like
   per the original design spec's acceptance criteria.
2. **Default: hand off to the user.** Claude presents the exact commands
   to run and exact expected output, and asks the user to run it and
   report back pass/fail plus any discrepancy.
3. **Opt-in fallback: Antigravity.** Only on explicit user request, Claude
   invokes Antigravity non-interactively:
   ```
   agy --print "<verification prompt>" --add-dir <repo-root> --model "<model>"
   ```
   Never with `--dangerously-skip-permissions`. A specific model is chosen
   deliberately rather than left to default. **Hard rule:** never route a
   scenario requiring interactive CLI/TUI driving (e.g. `tradingagents`'
   questionary prompts) through `agy`, even if the opt-in was requested —
   confirmed capability gap, not a preference: `agy --print` loops on
   planner turns (`PlannerResponse without ModifiedResponse encountered`)
   until `--print-timeout` and never completes such a scenario. Hand those
   to the user regardless.
4. **Pass** -> proceed to stage 5 (report to user).
   **Fail** -> Claude reviews the findings; if they point to a real bug,
   that becomes a new task fed back into stage 3 (Codex fixes it,
   re-verify), carrying its own verification command like any stage-3
   task. If findings are inconclusive or environment-related (e.g.
   missing API key), Claude resolves the ambiguity itself or asks the
   user, rather than looping stage 4 indefinitely.
5. Claude does not hand-edit code based on findings from this stage —
   findings become plan tasks routed back through Codex.

## Guardrails

- Codex sandbox is always `-s workspace-write`. Never
  `--dangerously-bypass-approvals-and-sandbox`.
- Stage 4's default path is the user running the scenario themselves;
  Antigravity is opt-in, invoked only on explicit user request.
- When Antigravity is used, it's invoked without
  `--dangerously-skip-permissions`, and only to *observe* behavior (run the
  app, read output) — it does not edit repository files as part of this
  workflow. Its model is chosen explicitly per invocation rather than left
  as whatever the CLI defaults to.
- Never route an interactive-CLI/TUI-driving scenario through `agy`,
  regardless of whether the Antigravity opt-in was requested — hand those
  to the user. This is a confirmed capability gap (see stage 4 detail),
  not a style preference.
- Retry cap of 3 per task prevents runaway loops in stage 3; failures beyond that
  surface to the user. Stage 4 does not loop on itself — a genuine-bug failure
  there always produces a new stage-3 task (routed through Codex) rather than
  repeated Antigravity attempts at the same check; inconclusive or
  environment-related failures are resolved directly per stage 4 step 4, not
  routed at all.
- Existing repo rules (150-line cap, no unapproved upstream edits, vendor routing,
  `AgentState` key preservation, full-suite-only-for-cross-cutting-changes) apply
  unchanged and are restated in each task prompt.
- Final commit/PR/push actions still require explicit user approval — this
  workflow does not change that. Neither skill commits or pushes as part of its
  own procedure (that's stage 5, outside both skills' scope), so this rule is
  stated once here rather than duplicated into each skill's guardrails.

## Artifact to build

Two new project skills, both written directly by Claude (workflow tooling, not
TradingAgents backend code):

- `.claude/skills/codex-delegate/SKILL.md` — codifies the stage-3 delegate loop
  (prompt construction, the `codex exec` / `resume` invocation pattern, the
  re-verify-and-cap-at-3 logic).
- `.claude/skills/antigravity-verify/SKILL.md` — codifies the stage-4 end-to-end
  verify loop (`agy --print` invocation pattern, model selection, and the
  route-failures-back-to-stage-3 rule).

Kept as two skills rather than one so each stays focused on a single tool's
invocation contract; the future top-level workflow (or a thin orchestrating skill)
calls both in sequence.

**Validation scope:** each skill's smoke test proved its base invocation (Codex
writing a module + test and self-verifying; Antigravity executing a command and
reporting real output) and the CLI flags each depends on. It did not separately
exercise `codex exec resume` or every documented example model string (e.g.
"Gemini 3.1 Pro (High)") — those follow the same CLI syntax already confirmed to
exist via `--help`/`agy models`, but weren't independently smoke-tested end to
end. Treat them as documented-per-CLI-contract, not smoke-tested, until a real
retry/resume case exercises them.

## Out of scope / deferred

- Isolated git worktrees/branches for Codex's work: considered, but the user chose
  direct-working-tree edits for simplicity. Can be revisited later if a bad Codex
  run proves hard to back out of.
- Automated CI integration of this loop: not addressed here: this is a local,
  Claude-driven development workflow, not a CI pipeline change.
