---
name: feedback-codex-background-stdin-hang
description: "codex-delegate background invocations must close stdin and avoid buffering pipes, plus actively monitor for silent hangs"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 9105cb75-a53a-47f6-9576-64a948e8a2bb
---

When invoking `codex exec` via Bash `run_in_background` (as `codex-delegate` stage-3
does), always redirect stdin from `/dev/null` (`< /dev/null`) and avoid piping
through `tail` (which buffers all output until the process exits, hiding whether
it's making progress). Without `< /dev/null`, `codex exec` can silently sit
forever "Reading additional input from stdin..." even though a prompt argument
was already supplied — zero CPU usage, no network connection, and no session
log file ever gets created in `~/.codex/sessions/`, so it looks superficially
like it's "still working" rather than hung.

**Why:** In [[project_claude_architect_workflow]]'s stage-3 (`codex-delegate`), a
background Codex run hung for ~55 minutes with zero CPU, zero network
connections, and no session rollout file — indistinguishable from "slow" until
checked carefully (`ps -p <pid>` state/CPU%, `/proc/<pid>/fd` for open sockets,
and critically whether a `~/.codex/sessions/**/*.jsonl` file exists near the
process's start time). The root cause was stdin never being closed in the
background bash invocation.

**How to apply:** Every future `codex exec` background invocation should (1)
include `< /dev/null` and stream to a file directly (`2>&1 | cat`, not `| tail`,
so the output file fills incrementally instead of only at process exit), and
(2) after launching, proactively verify real progress within the first minute
or two — check for a new `~/.codex/sessions/**/*.jsonl` file near the process
start time and rising CPU time — rather than passively waiting on a
long `ScheduleWakeup` and assuming "still running" means "still working."

**Recurrence (2026-07-09, Wyckoff calibration Task 1):** Forgot `< /dev/null`
again on the first dispatch — it hung on stdin exactly as described above,
and the user had to prompt "check is the job still running" before it was
caught, rather than me checking proactively. The user then explicitly said:
"in the future, when you delegate, you should check periodically to ensure
the task in the back is actually working." Treat this as a hard checklist
item at dispatch time, not a background habit to remember loosely: (1) never
submit a backgrounded `codex exec` without `< /dev/null` in the same command
— check the command text for it before running, every time; (2) after any
background delegation (Codex or a subagent), proactively check on it after
~20-30s even though the harness will notify on completion — a notification
only fires if the process *does* finish, which does not help if it's hung.
