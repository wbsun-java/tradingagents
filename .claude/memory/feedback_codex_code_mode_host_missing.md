---
name: feedback-codex-code-mode-host-missing
description: "codex-cli 0.144.0 (brew) fails all shell commands with 'cannot start codex-code-mode-host' — pass --disable code_mode_host on every codex exec until the brew package ships the helper binary"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 05d522f3-0e18-46f9-9b7f-26bbb604f3f0
---

Discovered 2026-07-10 running codex-delegate Task 1 (O'Neil base patterns): `codex exec`
on codex-cli 0.144.0 (Homebrew) exits 0 but does nothing — its final message says the
command runner "cannot start `codex-code-mode-host` (No such file or directory)". The
`code_mode_host` feature is stable+enabled by default, but the brew package only installs
the `codex` binary, not the helper.

**Why:** an exit-0 run with zero repo changes looks like success at the process level;
without reading `--output-last-message` you'd think the task silently produced nothing.

**How to apply:** add `--disable code_mode_host` to every `codex exec` invocation in
[[project-model-role-split]]-style delegation until a codex upgrade ships the helper
(check: `ls /home/linuxbrew/.linuxbrew/bin | grep codex` should show more than one
binary, or re-test without the flag after `brew upgrade codex`). Also always read the
last-message file before trusting exit 0.
