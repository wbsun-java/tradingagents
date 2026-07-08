# Memory-log stats CLI utility

Date: 2026-07-08

## Purpose

A small pilot feature for the Claude-architect / Codex-implementer /
Antigravity-verify workflow (see
`docs/superpowers/specs/2026-07-06-codex-delegate-workflow-design.md`). Adds a
standalone script that reads the decision log
(`~/.tradingagents/memory/trading_memory.md` by default) and prints summary
statistics: resolved-decision count, win rate, average alpha, average holding
days.

## Scope

- Applies to: one new script (`scripts/memory_stats.py`) and its test
  (`tests/test_memory_stats.py`).
- Does not apply to: any change to `tradingagents/agents/utils/memory.py`,
  `default_config.py`, or any other existing file. This is a purely additive
  pilot — no upstream files are touched, so the workflow can run stage 3
  (codex-delegate) and stage 4 (antigravity-verify) without any approval gate
  for editing existing files.
- Out of scope: per-rating breakdown (BUY/SELL/HOLD), `--log-path` CLI
  override, ticker filtering, non-text output formats. These were considered
  and deliberately deferred — see "Approaches considered" below.

## Approaches considered

1. **Reuse `TradingMemoryLog.load_entries()`** (chosen). This method already
   parses each markdown block into a dict with `date`, `ticker`, `rating`,
   `pending`, `raw`, `alpha`, `holding`, `decision`, `reflection`. The script
   only needs to filter and aggregate — no new parsing logic.
2. Write a standalone regex parser directly in the script. Rejected: it would
   duplicate `TradingMemoryLog`'s parsing logic in a second place that has to
   stay in sync with the log format.
3. Load entries into a pandas DataFrame for aggregation. Rejected: an
   unjustified dependency for four scalar aggregates over what will typically
   be a small number of log entries.

## Architecture

Single script, `scripts/memory_stats.py`, following the existing convention
in `scripts/` (e.g. `scripts/smoke_structured_output.py`): a `main() -> int`
entry point guarded by `if __name__ == "__main__": sys.exit(main())`, no
`argparse` needed since the script takes no arguments.

Two functions:

- `compute_stats(entries: list[dict]) -> dict | None` — pure function, takes
  the output of `TradingMemoryLog.load_entries()`, returns a dict of computed
  stats or `None` if there are no resolved entries. Kept separate from
  `main()` so tests can call it directly without going through process
  stdout.
- `main() -> int` — builds `TradingMemoryLog(DEFAULT_CONFIG)`, calls
  `load_entries()`, calls `compute_stats()`, prints the result (or the
  "no resolved decisions yet" message), returns exit code 0.

## Data flow

1. `TradingMemoryLog(DEFAULT_CONFIG).load_entries()` — reads from the
   config-default log path (`DEFAULT_CONFIG["memory_log_path"]`, itself
   sourced from `TRADINGAGENTS_MEMORY_LOG_PATH` or
   `~/.tradingagents/memory/trading_memory.md`), returns all entries
   (pending and resolved).
2. Filter to `not entry["pending"]`. Pending entries have no realized
   `raw`/`alpha`/`holding` values yet.
3. For each resolved entry, parse `raw` (e.g. `"+3.2%"`) and `alpha`
   (e.g. `"-1.0%"`) by stripping `%` and `float()`; parse `holding`
   (e.g. `"6d"`) by stripping the trailing `d` and `int()`/`float()`. If an
   individual entry's field fails to parse, skip that entry for the
   aggregates it would contribute to (defensive; `TradingMemoryLog` always
   writes these in this format via `update_with_outcome`/
   `batch_update_with_outcomes`, so this should not occur in practice).
4. Compute:
   - `count` = number of resolved entries.
   - `win_rate` = (entries with parsed `raw > 0`) / `count`.
   - `avg_alpha` = mean of parsed `alpha` values.
   - `avg_holding` = mean of parsed `holding` values.
5. Print as a simple labeled text block:
   ```
   Decisions: 12
   Win rate: 58.3%
   Avg alpha: +2.1%
   Avg holding: 6.4 days
   ```

## Error handling

- Log file missing, or exists but has zero resolved entries (empty log, or
  pending-only) → print `"No resolved decisions yet."` and return exit code
  0. This is expected state for a fresh install, not an error.
- Entry with an unparseable `raw`/`alpha`/`holding` field → excluded from the
  aggregates that field feeds (does not crash the whole run).

## Testing

`tests/test_memory_stats.py`:

- Build a synthetic log in `tmp_path` using the real write path —
  `TradingMemoryLog.store_decision()` followed by
  `TradingMemoryLog.update_with_outcome()` — rather than hand-written
  fixture text, so the test tracks the actual on-disk log format instead of
  an assumption about it.
- Test 1: two or three resolved entries with known `raw_return`,
  `alpha_return`, `holding_days` → assert `compute_stats()` returns the
  expected `count`, `win_rate`, `avg_alpha`, `avg_holding`.
- Test 2: a log with only a pending entry (never resolved) → assert
  `compute_stats()` returns `None`.
- Test 3: no log file at all (fresh `TradingMemoryLog` pointed at a
  nonexistent path) → assert `compute_stats()` (called with `[]`, matching
  `load_entries()`'s return for a missing file) returns `None`.

Verification command for the plan task:
`pytest -q tests/test_memory_stats.py`.

## End-to-end verification (stage 4 / antigravity-verify)

Scenario: from the repo root, run `python scripts/memory_stats.py` twice —
once against a temporary `TRADINGAGENTS_MEMORY_LOG_PATH` pointed at a
freshly created empty directory (expect `"No resolved decisions yet."`), and
once against a small fixture log file (2-3 resolved entries with known
numbers, same as the pytest fixture) written to a temp path via the same env
var override (expect the printed stats to match the known numbers by hand
calculation). This exercises the actual script as a subprocess, not just the
pure `compute_stats()` function.

## Out of scope / deferred

- `--log-path` CLI override: deferred; the config/env-var path is sufficient
  for a first pass and keeps the script argument-free.
- Per-rating (BUY/SELL/HOLD) breakdown: deferred; adds a second aggregation
  dimension and more test fixtures for a pilot feature whose primary goal is
  exercising the workflow, not maximizing analytical depth.
- Wiring this into the `tradingagents` CLI itself: explicitly out of scope —
  this stays a standalone script in `scripts/`, matching the existing
  pattern, and requires no changes to `cli/main.py` (an upstream-origin
  file).
