---
name: codex-resume-flags
description: codex exec resume rejects -s/-C; use -c sandbox_mode and cwd instead
metadata: 
  node_type: memory
  type: reference
  originSessionId: fc8faf11-79a3-4580-9066-5b4be720e03d
---

`codex exec resume` (codex 0.144.0) does NOT accept `-s` or `-C` (exit code 2,
"unexpected argument"). Supported: `--last`, `-m <model>`, `-o <last-message-file>`,
`--disable <feature>`, `-c key=value` overrides.

**How to apply:** For retry loops in the codex-delegate skill, run resume as:
`codex exec resume --last -m <tier> --disable code_mode_host -c 'sandbox_mode="workspace-write"' -o <file> "<feedback>"`
with the shell already cd'd to the repo (resume filters sessions by cwd).
Related: [[codex-code-mode-host-missing]]
