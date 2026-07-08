# Workflow amendment: Gemini intake + stage-4 finalization

Date: 2026-07-08

## Purpose

Amends the Claude-architect / Codex-implementer workflow
(`docs/superpowers/specs/2026-07-06-codex-delegate-workflow-design.md`) with
two changes learned from running it end-to-end on the memory-log-stats-cli
pilot feature:

1. A new situational pre-step where Gemini (via `agy --print`) turns messy
   raw input (logs, notes, external docs) into a structured brief before
   Claude's brainstorming stage, instead of Claude brainstorming from raw
   material directly.
2. Finalizes stage 4 (end-to-end verify): default is the user runs the
   verification scenario themselves; Antigravity becomes an opt-in fallback
   rather than the default, and is never used for scenarios requiring
   interactive CLI/TUI driving — the exact failure mode diagnosed during the
   pilot (Antigravity's terminal tool cannot hold a multi-turn interactive
   session; it loops on planner turns until `--print-timeout` and never
   completes).

## Scope

- Applies to: the workflow's own documentation
  (`docs/superpowers/specs/2026-07-06-codex-delegate-workflow-design.md`) and
  one of its two existing skills (`.claude/skills/antigravity-verify/SKILL.md`),
  plus one new skill (`.claude/skills/gemini-intake/SKILL.md`).
- Does not apply to: TradingAgents backend/agent code. This is workflow
  tooling, written directly by Claude per the original spec's own carve-out
  ("Does not apply to: the tooling that implements this workflow itself...
  which Claude writes directly, same as any other skill").
- Does not change stages 2 (plan) or 3 (Codex delegate) at all.

## Architecture

```
[Gemini intake]  ->  1. Brainstorm  ->  2. Plan  ->  3. Delegate  ->  4. Verify  ->  5. Report
   situational           (Claude)         (Claude)      (Codex)      (finalized)     (Claude)
```

Gemini intake is not a numbered pipeline stage — it's an optional pre-step
that only runs when the input to stage 1 is messy enough to need cleaning.
When the user's request is already clear and concise (the common case), it's
skipped entirely and stage 1 starts directly from the request, same as
today.

## Components

### Gemini intake (new)

- **Trigger:** user hands Claude raw material that is messy — pasted logs,
  an error dump, a rambling note, an external doc/ticket — rather than an
  already-clear, actionable request.
- **Input:** the raw material, verbatim.
- **Output:** a three-section structured brief:
  1. **Problem** — what is actually being asked for, in plain terms.
  2. **Facts/constraints** — key concrete details extracted from the
     material.
  3. **Open questions** — anything ambiguous, contradictory, or missing that
     needs clarifying.
- **Invocation:**
  ```bash
  agy --print "Summarize the following into a structured brief with three
  sections: 1. Problem ... 2. Facts/constraints ... 3. Open questions ...

  <raw material>" \
    --add-dir <repo-root> \
    --model "Gemini 3.1 Pro (High)"
  ```
  Same non-interactive `agy --print` pattern already proven in stage 4 —
  bounded, single-shot, text-in/text-out, which is exactly the shape `agy`
  handles reliably (per the pilot's findings).
- **Handoff:** the brief becomes Claude's starting material for
  `superpowers:brainstorming`'s normal flow. Claude still asks clarifying
  questions one at a time and proposes approaches — the brief replaces "raw
  notes," it does not skip brainstorming or pre-decide the design.
- **Guardrail:** Gemini only summarizes/structures; it never proposes
  architecture or makes design decisions. Decision-making stays with Claude,
  unchanged from the original workflow.

### Stage 4 (end-to-end verify) — finalized

- **Default:** Claude builds the verification scenario (exact commands to
  run, exact expected output, drawn from the feature's design-spec
  acceptance criteria) and hands it to the user. The user runs it and
  reports back pass/fail plus any discrepancy.
- **Opt-in fallback:** only on explicit user request, Claude invokes
  Antigravity the same way as the original spec (`agy --print ... --model
  "..."`, never `--dangerously-skip-permissions`) — for cases where the user
  is unavailable, or wants an independent model's read on something
  non-interactive and higher-stakes.
- **Hard rule:** any scenario requiring driving an interactive CLI/TUI (e.g.
  `tradingagents`' questionary prompts for ticker/date/analyst selection)
  always goes to the user, never to `agy`, regardless of whether the opt-in
  was requested for the rest of the check. This is the one finding from the
  pilot that isn't a preference — it's a confirmed capability gap: routing
  such a scenario through `agy --print` reliably hangs until the 5-minute
  `--print-timeout`, evidenced by `~/.gemini/antigravity-cli/cli.log` showing
  repeated `PlannerResponse without ModifiedResponse encountered` with no
  convergence.
- Everything downstream of pass/fail is unchanged: a real bug becomes a new
  stage-3 task routed through Codex; inconclusive or environmental failures
  are resolved directly, not looped.

## Data flow

1. (Situational) User hands Claude messy raw material -> Claude invokes
   Gemini intake -> structured brief.
2. Claude brainstorms from the brief (or from the user's direct request, if
   intake was skipped) -> design spec, same as the unamended workflow.
3. Claude plans -> numbered implementation plan with per-task verification
   commands, unchanged.
4. Codex implements each task via `codex-delegate`, unchanged.
5. Once all tasks pass stage 3, Claude builds the stage-4 scenario and hands
   it to the user by default; Antigravity only if the user opts in, and
   never for interactive-CLI scenarios.
6. Claude reports the assembled result; nothing commits without explicit
   user approval, unchanged.

## Error handling

- Gemini intake producing a brief that's still ambiguous is not an error —
  that's exactly what the "Open questions" section is for; Claude resolves
  those during the normal brainstorming clarifying-questions step.
- If the user declines to run a stage-4 scenario themselves and does not
  request the Antigravity fallback, Claude asks directly rather than
  guessing which path to take.

## Testing

No new automated tests — this amendment only changes documentation
(the workflow spec and skill files). Validation is: the two skill files read
correctly, are internally consistent with the amended spec, and the new
`gemini-intake` skill file matches the existing two skills' structure
(frontmatter, Preconditions/Procedure/Guardrails sections).

## Out of scope / deferred

- Making Gemini intake mandatory for every feature: rejected — most requests
  arrive already clear, and forcing a Gemini call on every one spends tokens
  for no benefit.
- Merging stages 1 and 2 (brainstorm + plan) into one architect stage:
  considered during brainstorming discussion but not adopted — the existing
  two-stage split (spec, then plan) stays as-is; only the new intake pre-step
  and stage-4 finalization are in scope for this amendment.
- Re-litigating stages 2/3 (plan, Codex delegate): unchanged, not revisited
  here.
