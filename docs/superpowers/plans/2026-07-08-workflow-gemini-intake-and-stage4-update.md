# Workflow amendment: Gemini intake + stage-4 finalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. This plan edits workflow-tooling
> documentation only (spec + skill files) — it does NOT go through
> `codex-delegate`, per the original workflow spec's own carve-out that
> workflow tooling is written directly, same as any other skill.

**Goal:** Amend the Claude-architect / Codex-implementer workflow's
documentation to add a situational Gemini-intake pre-step and finalize
stage 4 (end-to-end verify) as user-default / Antigravity-opt-in, per
`docs/superpowers/specs/2026-07-08-workflow-gemini-intake-and-stage4-update-design.md`.

**Architecture:** Three markdown edits, no code: amend the existing workflow
design spec's stage list and stage-4 section, add one new skill file
(`gemini-intake`) parallel to the existing two skills, and update
`antigravity-verify`'s procedure/guardrails to the finalized version.

**Tech Stack:** Markdown only. No tests to run — verification is a
self-consistency read-through across the three edited/created files.

## Global Constraints

- New skill file (`gemini-intake/SKILL.md`) stays under 150 lines, matching
  its sibling skills (`antigravity-verify` is 69 lines, `codex-delegate` is
  89 lines) and the repo's file-size convention.
- Do not touch TradingAgents backend/agent code — this plan is scoped to
  workflow-tooling docs only, per the design spec's Scope section.
- No step in this plan commits anything without the user's explicit
  go-ahead first (standing preference — do not auto-commit specs/plans/docs
  even though the source `writing-plans`/`brainstorming` skills default to
  committing).

---

### Task 1: Amend the workflow design spec

**Files:**
- Modify: `docs/superpowers/specs/2026-07-06-codex-delegate-workflow-design.md`

**Interfaces:**
- Consumes: nothing (this is the top-level reference doc).
- Produces: the updated stage list and stage-4 wording that
  `gemini-intake/SKILL.md` (Task 2) and `antigravity-verify/SKILL.md`
  (Task 3) both point back to via their "Reference:" line — so this task
  must land first.

- [ ] **Step 1: Update the "Architecture" section's stage list**

  In `docs/superpowers/specs/2026-07-06-codex-delegate-workflow-design.md`,
  find the "## Architecture" section (currently starts "Five stages. Stages
  1 and 2 reuse existing superpowers skills unchanged..."). Replace that
  paragraph and the numbered list with:

  ```markdown
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
  ```

- [ ] **Step 2: Rewrite the "End-to-end verify loop (stage 4 detail)" section**

  Replace the entire "## End-to-end verify loop (stage 4 detail)" section
  (the numbered list currently starting "Runs once, after all of a
  feature's plan tasks have passed stage 3...") with:

  ```markdown
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
  ```

- [ ] **Step 3: Update the "Guardrails" section's Antigravity bullets**

  In the "## Guardrails" section, replace the two bullets:
  ```markdown
  - Antigravity is invoked without `--dangerously-skip-permissions`, and only to
    *observe* behavior (run the app, read output) — it does not edit repository
    files as part of this workflow, so its role stays verification-only even though
    `agy` itself is capable of more.
  - Antigravity's model is chosen explicitly per invocation rather than left as
    whatever the CLI defaults to, since stage 4's value depends on getting a
    meaningfully independent read on the feature (available options include Gemini
    3.5/3.1 and non-Gemini models via the same CLI, so "independent" is a real
    choice, not just cosmetic).
  ```
  with:
  ```markdown
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
  ```

- [ ] **Step 4: Read the whole file back and check consistency**

  Read `docs/superpowers/specs/2026-07-06-codex-delegate-workflow-design.md`
  top to bottom. Confirm: the "Purpose" section's mention of Antigravity
  still makes sense given the opt-in default (it does — Purpose describes
  what Antigravity is *for*, not when it's invoked, so no edit needed
  there), and no other section still says "Claude drives an Antigravity CLI
  turn" as if it were the default.

- [ ] **Step 5: Do not commit**

  Leave the file modified but unstaged. Move to Task 2.

---

### Task 2: Create the `gemini-intake` skill

**Files:**
- Create: `.claude/skills/gemini-intake/SKILL.md`

**Interfaces:**
- Consumes: the stage list and Gemini-intake description written in Task 1,
  Step 1 (this file's content must match that description exactly — same
  trigger condition, same three-section brief format, same guardrail that
  Gemini never designs).
- Produces: nothing consumed by a later task in this plan; this is a
  leaf file.

- [ ] **Step 1: Write the skill file**

  Create `.claude/skills/gemini-intake/SKILL.md`:

  ```markdown
  ---
  name: gemini-intake
  description: Use when the user hands you messy raw material (a log dump, a rambling note, an external doc/ticket) that needs cleaning before superpowers:brainstorming can start - situational pre-step of the Claude-architect workflow, not a mandatory stage. Turns raw input into a structured brief via Gemini (agy --print).
  ---

  # Gemini Intake

  Situational pre-step before `superpowers:brainstorming`. Only runs when the
  input to brainstorming is messy enough to need cleaning — a clear, already
  concise request skips this entirely and goes straight to brainstorming, same
  as before this skill existed.

  Reference: `docs/superpowers/specs/2026-07-06-codex-delegate-workflow-design.md`
  (Architecture section, "Gemini intake").

  ## Preconditions

  - The user has handed you raw material that is genuinely messy: a pasted
    log, an error dump, a rambling note, an external doc or ticket — not
    just a topic that happens to be complex.
  - If the request is already clear and short, do not invoke this skill —
    go directly to `superpowers:brainstorming`.

  ## Procedure

  1. **Invoke Gemini via `agy --print`:**
     ```bash
     agy --print "Summarize the following into a structured brief with
     three sections:
     1. Problem - what is actually being asked for, in plain terms
     2. Facts/constraints - key concrete details extracted from the material below
     3. Open questions - anything ambiguous, contradictory, or missing that needs clarifying

     <raw material, verbatim>" \
       --add-dir <repo-root> \
       --model "Gemini 3.1 Pro (High)"
     ```
  2. **Hand the resulting brief to `superpowers:brainstorming`** as its
     starting material, in place of the raw input. Brainstorming still runs
     its full flow (clarifying questions one at a time, 2-3 proposed
     approaches, section-by-section design presentation) — the brief only
     replaces "raw notes," it does not skip any brainstorming step or
     pre-decide the design.

  ## Guardrails

  - Gemini only summarizes and structures here; it never proposes
    architecture or makes design decisions. Decision-making stays with
    Claude, unchanged from the rest of the workflow.
  - Never treat this as a mandatory first step — invoke only when the
    Preconditions are actually met.
  - This skill never commits or pushes on its own — same rule as
    `codex-delegate` and `antigravity-verify`.
  ```

- [ ] **Step 2: Verify line count**

  Run: `wc -l .claude/skills/gemini-intake/SKILL.md`
  Expected: under 150 lines (matches the sibling skills' convention).

- [ ] **Step 3: Do not commit**

  Leave the file created but unstaged. Move to Task 3.

---

### Task 3: Update `antigravity-verify` to the finalized stage-4 behavior

**Files:**
- Modify: `.claude/skills/antigravity-verify/SKILL.md` (currently 69 lines)

**Interfaces:**
- Consumes: the finalized stage-4 wording from Task 1, Step 2 — this file's
  Procedure/Guardrails sections must match that wording (default user-run,
  Antigravity opt-in, interactive-CLI hard rule).
- Produces: nothing consumed by a later task; leaf file.

- [ ] **Step 1: Replace the frontmatter description**

  Change:
  ```markdown
  description: Use after all of a feature's plan tasks have passed codex-delegate (stage 4 of the Claude-architect workflow) - drives Antigravity CLI (agy) to run the feature end-to-end and confirm real behavior, before reporting the feature done.
  ```
  to:
  ```markdown
  description: Use after all of a feature's plan tasks have passed codex-delegate (stage 4 of the Claude-architect workflow) - hands the user an end-to-end verification scenario to run themselves (default), or drives Antigravity CLI (agy) as an opt-in independent check, before reporting the feature done.
  ```

- [ ] **Step 2: Add the default/opt-in framing after the intro paragraph**

  After the existing paragraph ending "...this skill never edits code
  directly." and before the "Reference:" line, insert:
  ```markdown
  Default path is user-run (saves the token cost of driving `agy`);
  Antigravity is an opt-in fallback, not the default, since driving it from
  Claude costs tokens on both sides and — per the workflow's first real
  run — an agent's terminal tool struggles specifically with scenarios that
  require holding an interactive TUI conversation (e.g. `tradingagents`'
  questionary prompts), which a human runs trivially.
  ```

- [ ] **Step 3: Replace step 2 of the Procedure**

  Change the existing:
  ```markdown
  2. **Invoke Antigravity:**
     ```bash
     agy --print "<verification prompt from step 1>" \
       --add-dir <repo-root> \
       --model "<explicitly chosen model, e.g. Gemini 3.1 Pro (High)>"
     ```
     Never add `--dangerously-skip-permissions`. Choose the model explicitly
     each run rather than accepting the CLI default — this stage's value comes
     from an independent read on the behavior.
  ```
  to:
  ```markdown
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
  ```

  Renumber the remaining Procedure steps (old 3 -> 3, old 4 -> 4; text
  unchanged except old step 3's opening "Antigravity reports" becomes
  "Whichever path ran, get back" since either the user or Antigravity may
  have produced the result):
  ```markdown
  3. **Review the findings.** Whichever path ran, get back pass/fail and any
     discrepancies from expected behavior.
  ```

- [ ] **Step 4: Replace the Guardrails section**

  Change:
  ```markdown
  ## Guardrails

  - Antigravity only observes behavior in this workflow; it does not edit
    repository files here even though `agy` itself is capable of more.
  - Never use `--dangerously-skip-permissions`.
  - A failure that indicates a real bug always produces a stage-3 task (via
    `codex-delegate`), never a direct edit by Claude or Antigravity;
    inconclusive or environmental failures are resolved directly instead (see
    Procedure step 4), not routed anywhere.
  - This skill never commits or pushes on its own — same rule as
    `codex-delegate`.
  ```
  to:
  ```markdown
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
    `codex-delegate`), never a direct edit by Claude, the user, or Antigravity;
    inconclusive or environmental failures are resolved directly instead (see
    Procedure step 4), not routed anywhere.
  - This skill never commits or pushes on its own — same rule as
    `codex-delegate`.
  ```

- [ ] **Step 5: Read the whole file back and check consistency**

  Read `.claude/skills/antigravity-verify/SKILL.md` top to bottom. Confirm
  numbering is sequential (1-4 in Procedure), no leftover reference to
  Antigravity as "the" verification method (only as the opt-in), and the
  wording matches Task 1's stage-4 rewrite (same hard rule phrasing for
  interactive CLI/TUI).

- [ ] **Step 6: Do not commit**

  Leave the file modified but unstaged. This plan's diff (Tasks 1-3
  together) waits for the user's explicit go-ahead before any `git commit`.

---

## Self-review notes

- **Spec coverage:** Task 1 covers the design spec's "Architecture" section
  update (both the stage-list and stage-4 rewrite) and the Guardrails
  section; Task 2 covers the new `gemini-intake` skill; Task 3 covers the
  `antigravity-verify` finalization. All three of the design spec's
  "Artifacts to build" are covered.
- **Placeholder scan:** none found — every step shows exact replacement text.
- **Consistency:** the three-section brief format (Problem /
  Facts/constraints / Open questions) and the interactive-CLI hard rule are
  worded identically across Task 1's spec edit, Task 2's new skill, and
  Task 3's skill update.
