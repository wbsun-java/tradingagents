---
name: feedback-no-auto-commit-specs
description: "Don't git-commit design specs, plans, or other artifacts automatically, even when a skill's default procedure says to commit them"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 631ebc6d-72bf-4b5e-9dd8-5136bd74e7e2
---

Do not run `git commit` on design specs, plans, or other generated artifacts until the user explicitly says to commit. This applies even when a skill's documented process (e.g. `superpowers:brainstorming`'s "Write design doc" step) says to commit as part of its normal flow.

**Why:** User corrected this in the tradingagents repo after a spec doc (`docs/superpowers/specs/2026-07-08-memory-log-stats-cli-design.md`) was auto-committed following the brainstorming skill's default procedure. The user wants control over when commits happen, independent of what a skill's default steps say.

**How to apply:** When a skill instructs "commit the file," write/save the file as instructed but stop short of the actual `git commit` — tell the user the file is ready and ask them to confirm before committing, or wait for explicit "commit this" / "go ahead and commit" language. This is a general git-safety principle already ([[git-safety]] if that memory exists) but is worth calling out specifically for the brainstorming/writing-plans workflow since those skills' own instructions say to commit, which could otherwise override the general caution.
