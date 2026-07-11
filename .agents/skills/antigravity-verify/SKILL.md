---
name: antigravity-verify
description: Use after all of a feature's plan tasks have passed codex-delegate (stage 4 of the Codex-architect workflow) - hands the user an end-to-end verification scenario to run themselves (default), or drives Antigravity CLI (agy) as an opt-in independent check, before reporting the feature done.
---

# Antigravity Verify

Runs once per feature, after every plan task for that feature has passed
`codex-delegate`. Confirms the assembled feature actually works end-to-end,
not just that its unit tests pass. Findings become new plan tasks routed back
through `codex-delegate` — this skill never edits code directly.

Default path is user-run (saves the token cost of driving `agy`);
Antigravity is an opt-in fallback, not the default, since driving it from
Codex costs tokens on both sides and — per the workflow's first real
run — an agent's terminal tool struggles specifically with scenarios that
require holding an interactive TUI conversation (e.g. `tradingagents`'
questionary prompts), which a human runs trivially.

Reference: `docs/superpowers/specs/2026-07-06-codex-delegate-workflow-design.md`
(stage 4).

## Preconditions

- All plan tasks for this feature have passed `codex-delegate`'s per-task
  verification.
- You have the feature's design spec's acceptance criteria at hand — this is
  what "correct behavior" means for this run.

## Procedure

1. **Build the verification prompt.** State, verbatim:
   - The exact scenario to exercise, e.g. "Run `tradingagents` for ticker
     <TICKER> on date <YYYY-MM-DD> with <analyst> enabled" or "Call
     `TradingAgentsGraph(config=...).propagate(<ticker>, <date>, ...)`
     directly for a faster check."
   - What output to inspect (CLI output, generated report file, specific
     fields/values).
   - What "correct" means, taken directly from the design spec's acceptance
     criteria.

2. **Hand off, by default, to the user.** Present the scenario from step 1
   as exact commands to run and exact expected output, and ask the user to
   run it and report back what they observed (pass/fail plus any
   discrepancy). This is the default path.

   **Opt-in fallback — invoke Antigravity instead**, only when the user asks
   for it (e.g. they're unavailable to run it themselves, or want an
   independent AI's read):
   ```bash
   agy --print "<verification prompt from step 1>" \
     --add-dir <repo-root> \
     --model "<explicitly chosen model, e.g. Gemini 3.1 Pro (High)>"
   ```
   Never add `--dangerously-skip-permissions`. Choose the model explicitly
   each run rather than accepting the CLI default. Do not route scenarios
   that require driving an interactive CLI/TUI through `agy` — hand those to
   the user instead, since `agy`'s terminal tool cannot reliably hold a
   multi-turn interactive prompt session (confirmed: it loops on planner
   turns until `--print-timeout` and never completes).

3. **Review the findings.** Whichever path ran, get back pass/fail and any
   discrepancies from expected behavior.

4. **Decide:**
   - **Pass** -> proceed to reporting the feature done to the user.
   - **Fail, and it's a real bug** -> write a new plan task describing the
     bug, its fix criteria, and its own verification command (same
     requirement `codex-delegate` expects of any task), and run it through
     `codex-delegate`. Then re-run this skill once that task passes.
   - **Fail, but inconclusive or environmental** (e.g. missing API key,
     unrelated flake) -> resolve the ambiguity yourself or ask the user. Do
     not loop this skill repeatedly on the same check.

## Guardrails

- User-run is the default for stage 4; Antigravity is opt-in, invoked only
  on explicit user request.
- When Antigravity is used, it only observes behavior in this workflow; it
  does not edit repository files here even though `agy` itself is capable of
  more.
- Never use `--dangerously-skip-permissions`.
- Never route a scenario that requires driving an interactive CLI/TUI
  through `agy` — hand those to the user regardless of whether Antigravity
  was requested for the rest of the check.
- A failure that indicates a real bug always produces a stage-3 task (via
  `codex-delegate`), never a direct edit by Codex, the user, or Antigravity;
  inconclusive or environmental failures are resolved directly instead (see
  Procedure step 4), not routed anywhere.
- This skill never commits or pushes on its own — same rule as
  `codex-delegate`.
