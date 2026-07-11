---
name: gemini-intake
description: Use when the user hands you messy raw material (a log dump, a rambling note, an external doc/ticket) that needs cleaning before superpowers:brainstorming can start - situational pre-step of the Codex-architect workflow, not a mandatory stage. Turns raw input into a structured brief via Gemini (agy --print).
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
  Codex, unchanged from the rest of the workflow.
- Never treat this as a mandatory first step — invoke only when the
  Preconditions are actually met.
- This skill never commits or pushes on its own — same rule as
  `codex-delegate` and `antigravity-verify`.
