# Codex-Delegate & Antigravity-Verify Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build two Claude Code project skills, `codex-delegate` and
`antigravity-verify`, that codify stages 3 and 4 of the Claude-architect
workflow described in
`docs/superpowers/specs/2026-07-06-codex-delegate-workflow-design.md`.

**Architecture:** Two independent, single-purpose skill files, each wrapping
one external CLI's non-interactive invocation contract (Codex CLI for
implement-and-self-test, Antigravity CLI for end-to-end behavioral
verification). Each skill's documented command pattern is proven with a real
smoke-test run in a throwaway scratch git repo before being written into the
skill file, so the instructions describe behavior that was actually observed,
not just plausible flags.

**Tech Stack:** Codex CLI (`codex exec`, `codex exec resume`), Antigravity CLI
(`agy --print`), bash, git, pytest (inside the smoke tests only).

## Global Constraints

- Every newly created file must be at most 150 lines (repo-wide convention).
- Codex is always invoked with `-s workspace-write`; never
  `--dangerously-bypass-approvals-and-sandbox`.
- Antigravity is always invoked without `--dangerously-skip-permissions`.
- Retry cap for the delegate loop is 3 attempts per task, not per feature.
- Neither skill hand-edits files in the other tool's scope; disagreements
  become resume prompts (Codex) or new plan tasks (Antigravity), never direct
  edits.
- Final commit/PR/push actions always require explicit user approval — these
  skills only prepare and review changes, they don't commit or push.

---

## Task 1: Validate the Codex invocation pattern and write `codex-delegate`

**Files:**
- Create: `.claude/skills/codex-delegate/SKILL.md`
- Scratch (not committed): a throwaway git repo at a fixed `/tmp` path, used
  only to prove the command pattern before it's documented and deleted at
  the end of the task.

**Interfaces:**
- Consumes: nothing from other tasks (first task).
- Produces: the `.claude/skills/codex-delegate/SKILL.md` skill file, which
  Task 2 references by path in `antigravity-verify`'s "Reference" line and
  which future feature work invokes directly by name (`codex-delegate`).

- [ ] **Step 1: Create a throwaway scratch repo to smoke-test Codex in**

Use a fixed, deterministic path (not this session's scratchpad UUID, and not
`mktemp`'s random output) — each step below runs as an independent shell
invocation with no persisted shell state between them (only the working
directory persists), so every step that needs this path repeats the same
literal string rather than referencing a variable set in an earlier step.

```bash
mkdir -p /tmp/tradingagents-codex-delegate-smoke
cd /tmp/tradingagents-codex-delegate-smoke
git init -q
git config user.email "smoke@test.local"
git config user.name "Smoke Test"
echo "# codex smoke test scratch repo" > README.md
git add README.md
git commit -q -m "init"
```

Expected: no errors; `git log --oneline` shows one commit.

- [ ] **Step 2: Run the Codex smoke invocation**

```bash
codex exec -s workspace-write -C /tmp/tradingagents-codex-delegate-smoke \
  --output-last-message /tmp/tradingagents-codex-delegate-smoke/last-message.txt \
  "Create a file named greeting.py with a function greet(name: str) -> str that returns f'Hello, {name}!'. Also create tests/test_greeting.py with a pytest test for it. Run pytest yourself inside this sandbox and confirm it passes before you finish. Do not touch any files or directories outside this workspace."
```

Expected: Codex exits, `/tmp/tradingagents-codex-delegate-smoke/greeting.py`
and `/tmp/tradingagents-codex-delegate-smoke/tests/test_greeting.py` both
exist.

- [ ] **Step 3: Independently re-verify the smoke test's own claim**

```bash
cd /tmp/tradingagents-codex-delegate-smoke
python3 -m pytest -q tests/test_greeting.py
```

Expected: PASS. If it fails, do not proceed to Step 4 — adjust the prompt
wording from Step 2 (e.g. be more explicit about running pytest before
finishing) and repeat Steps 2-3 until it passes. This confirms the
"self-verify before returning" behavior the skill will document is real, not
assumed.

- [ ] **Step 4: Write `.claude/skills/codex-delegate/SKILL.md`**

```markdown
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
```

- [ ] **Step 5: Verify the skill file itself**

```bash
wc -l .claude/skills/codex-delegate/SKILL.md
head -4 .claude/skills/codex-delegate/SKILL.md
```

Expected: line count <= 150; the first four lines are exactly
`---`, `name: codex-delegate`, a `description:` line, `---`.

- [ ] **Step 6: Clean up the scratch repo**

```bash
rm -rf /tmp/tradingagents-codex-delegate-smoke
```

- [ ] **Step 7: Commit**

The working tree may already have unrelated files staged from other work.
Scope this commit to only the new file so it doesn't sweep in unrelated
staged changes:

```bash
git commit -m "feat(skills): add codex-delegate skill for stage-3 implementation delegation" \
  -- .claude/skills/codex-delegate/SKILL.md
```

Expected: `git status` afterward still shows the pre-existing unrelated
staged files as staged (untouched), and the new SKILL.md is no longer
listed (it's committed).

---

## Task 2: Validate the Antigravity invocation pattern and write `antigravity-verify`

**Files:**
- Create: `.claude/skills/antigravity-verify/SKILL.md`
- Scratch (not committed): a throwaway directory at a fixed `/tmp` path, used
  only to prove the command pattern before it's documented and deleted at
  the end of the task.

**Interfaces:**
- Consumes: the existence and path of `.claude/skills/codex-delegate/SKILL.md`
  from Task 1 (referenced by name in this skill's "route back" guidance).
- Produces: the `.claude/skills/antigravity-verify/SKILL.md` skill file.

- [ ] **Step 1: Confirm the `agy` flags this task relies on still exist**

```bash
agy --help | grep -E -- '--print|--add-dir|--model'
```

Expected: all three flags listed. If any is missing (CLI version changed),
stop and re-check `agy --help` in full before adjusting Step 3 below.

- [ ] **Step 2: Create a throwaway scratch directory to smoke-test Antigravity in**

Same reasoning as Task 1 Step 1: use a fixed, deterministic path, since shell
state (including variables) does not persist between steps in this plan —
only the working directory does.

```bash
mkdir -p /tmp/tradingagents-antigravity-verify-smoke
cd /tmp/tradingagents-antigravity-verify-smoke
cat > check_version.py << 'EOF'
import sys
print(f"python-version:{sys.version_info.major}.{sys.version_info.minor}")
EOF
```

Expected: `check_version.py` exists in
`/tmp/tradingagents-antigravity-verify-smoke`.

- [ ] **Step 3: Run the Antigravity smoke invocation**

```bash
agy --print "Run 'python3 check_version.py' in this directory and tell me the exact string it printed, verbatim, on its own line prefixed with RESULT:." \
  --add-dir /tmp/tradingagents-antigravity-verify-smoke \
  --model "Gemini 3.5 Flash (Medium)"
```

Expected: Antigravity's response contains a line starting with `RESULT:`
followed by a string matching `python-version:3.<minor>`, matching the
Python version actually installed (compare against `python3 --version`
output run locally).

- [ ] **Step 4: Independently confirm the reported value**

```bash
python3 --version
```

Expected: the major.minor version matches what Antigravity reported in Step
3. If Antigravity's report doesn't match or is malformed, adjust the prompt
wording (e.g. be more explicit about the exact output format requested) and
repeat Steps 3-4 until it matches. This confirms Antigravity can actually
execute a command in the target directory and report real, verifiable
output — the core assumption stage 4 depends on.

- [ ] **Step 5: Write `.claude/skills/antigravity-verify/SKILL.md`**

```markdown
---
name: antigravity-verify
description: Use after all of a feature's plan tasks have passed codex-delegate (stage 4 of the Claude-architect workflow) - drives Antigravity CLI (agy) to run the feature end-to-end and confirm real behavior, before reporting the feature done.
---

# Antigravity Verify

Runs once per feature, after every plan task for that feature has passed
`codex-delegate`. Confirms the assembled feature actually works end-to-end,
not just that its unit tests pass. Findings become new plan tasks routed back
through `codex-delegate` — this skill never edits code directly.

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

2. **Invoke Antigravity:**
   ```bash
   agy --print "<verification prompt from step 1>" \
     --add-dir <repo-root> \
     --model "<explicitly chosen model, e.g. Gemini 3.1 Pro (High)>"
   ```
   Never add `--dangerously-skip-permissions`. Choose the model explicitly
   each run rather than accepting the CLI default — this stage's value comes
   from an independent read on the behavior.

3. **Review the findings.** Antigravity reports pass/fail and any
   discrepancies from expected behavior.

4. **Decide:**
   - **Pass** -> proceed to reporting the feature done to the user.
   - **Fail, and it's a real bug** -> write a new plan task describing the
     bug and its fix criteria, and run it through `codex-delegate`. Then
     re-run this skill once that task passes.
   - **Fail, but inconclusive or environmental** (e.g. missing API key,
     unrelated flake) -> resolve the ambiguity yourself or ask the user. Do
     not loop this skill repeatedly on the same check.

## Guardrails

- Antigravity only observes behavior in this workflow; it does not edit
  repository files here even though `agy` itself is capable of more.
- Never use `--dangerously-skip-permissions`.
- A failure here always produces a stage-3 task (via `codex-delegate`), never
  a direct edit by Claude or Antigravity.
```

- [ ] **Step 6: Verify the skill file itself**

```bash
wc -l .claude/skills/antigravity-verify/SKILL.md
head -4 .claude/skills/antigravity-verify/SKILL.md
```

Expected: line count <= 150; the first four lines are exactly
`---`, `name: antigravity-verify`, a `description:` line, `---`.

- [ ] **Step 7: Clean up the scratch directory**

```bash
rm -rf /tmp/tradingagents-antigravity-verify-smoke
```

- [ ] **Step 8: Commit**

Scope this commit to only the new file, same reason as Task 1 Step 7:

```bash
git commit -m "feat(skills): add antigravity-verify skill for stage-4 end-to-end verification" \
  -- .claude/skills/antigravity-verify/SKILL.md
```

Expected: `git status` afterward still shows the pre-existing unrelated
staged files as staged (untouched), and the new SKILL.md is no longer
listed (it's committed).
