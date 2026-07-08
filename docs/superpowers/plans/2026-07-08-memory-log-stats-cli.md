# Memory-log stats CLI utility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: This plan is executed via the
> project's `codex-delegate` skill (stage 3 of the Claude-architect workflow,
> see `docs/superpowers/specs/2026-07-06-codex-delegate-workflow-design.md`),
> not `superpowers:subagent-driven-development` or
> `superpowers:executing-plans`. Each task below carries its own verification
> command per `codex-delegate`'s precondition. After this task passes,
> `antigravity-verify` (stage 4) runs once for the whole feature.

**Goal:** Add a standalone script that prints decision-log summary
statistics (resolved-entry count, win rate, average alpha, average holding
days) by reading the existing `TradingMemoryLog`.

**Architecture:** One new script (`scripts/memory_stats.py`) with a pure
`compute_stats()` aggregation function plus a thin `main()` CLI entry point,
and one new test file. No existing files are modified.

**Tech Stack:** Python stdlib only (`sys`), reuses
`tradingagents.agents.utils.memory.TradingMemoryLog` and
`tradingagents.default_config.DEFAULT_CONFIG`. Tests use `pytest` +
`pytest`'s `tmp_path` fixture.

## Global Constraints

- Every newly created file must be at most 150 lines (repo-wide convention).
- Do not modify any existing file — this plan only creates
  `scripts/memory_stats.py` and `tests/test_memory_stats.py`. No import,
  registration, or wiring change to any upstream-origin file.
- Verification command for this task: `pytest -q tests/test_memory_stats.py`.
- `ruff check scripts/memory_stats.py tests/test_memory_stats.py` must be
  clean (repo's ruff config: `E, W, F, I, B, UP, C4, SIM`, `E501` ignored).
- No step in this plan commits anything. `codex-delegate` does not commit as
  part of its own procedure (see that skill's guardrails); any commit
  happens later, only with the user's explicit go-ahead.

---

### Task 1: `scripts/memory_stats.py` — decision-log stats script + tests

**Files:**
- Create: `scripts/memory_stats.py`
- Create: `tests/test_memory_stats.py`

**Interfaces:**
- Consumes: `TradingMemoryLog(config: dict)` and
  `TradingMemoryLog.load_entries() -> list[dict]` from
  `tradingagents/agents/utils/memory.py` (existing, unmodified). Each entry
  dict has keys `date`, `ticker`, `rating`, `pending: bool`,
  `raw: str | None` (e.g. `"+5.0%"`), `alpha: str | None` (e.g. `"-1.0%"`),
  `holding: str | None` (e.g. `"5d"`), `decision`, `reflection`.
  `DEFAULT_CONFIG` from `tradingagents/default_config.py` (existing,
  unmodified) — has key `"memory_log_path"`.
- Produces: `compute_stats(entries: list[dict]) -> dict | None` — returns
  `None` if no resolved (non-pending) entries exist, else a dict with keys
  `count: int`, `win_rate: float | None`, `avg_alpha: float | None`,
  `avg_holding: float | None`. `main() -> int` — prints the report, always
  returns `0`. Nothing outside this task depends on these names yet (this
  is the only task).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_memory_stats.py`:

```python
import pytest

from scripts.memory_stats import compute_stats
from tradingagents.agents.utils.memory import TradingMemoryLog


def _make_log(tmp_path):
    return TradingMemoryLog({"memory_log_path": str(tmp_path / "trading_memory.md")})


def test_compute_stats_resolved_entries(tmp_path):
    log = _make_log(tmp_path)
    log.store_decision("NVDA", "2026-01-05", "Rating: Buy\nGo long.")
    log.update_with_outcome(
        "NVDA", "2026-01-05",
        raw_return=0.05, alpha_return=0.02, holding_days=5,
        reflection="Worked out.",
    )
    log.store_decision("TSLA", "2026-01-06", "Rating: Sell\nExit position.")
    log.update_with_outcome(
        "TSLA", "2026-01-06",
        raw_return=-0.03, alpha_return=-0.01, holding_days=8,
        reflection="Missed the bounce.",
    )

    stats = compute_stats(log.load_entries())

    assert stats["count"] == 2
    assert stats["win_rate"] == pytest.approx(0.5)
    assert stats["avg_alpha"] == pytest.approx(0.5, abs=0.01)
    assert stats["avg_holding"] == pytest.approx(6.5, abs=0.01)


def test_compute_stats_pending_only(tmp_path):
    log = _make_log(tmp_path)
    log.store_decision("NVDA", "2026-01-05", "Rating: Buy\nGo long.")

    stats = compute_stats(log.load_entries())

    assert stats is None


def test_compute_stats_empty_list():
    assert compute_stats([]) is None
```

Note: `scripts/` has no `__init__.py` (matches the existing
`scripts/backtest_chart_patterns.py` / `scripts/smoke_structured_output.py`
layout, run as standalone scripts) — `pytest` still collects
`from scripts.memory_stats import compute_stats` correctly as long as it's
invoked from the repo root (`rootdir`-relative import), same as any other
`tests/` module importing from a top-level package directory in this repo.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest -q tests/test_memory_stats.py`
Expected: FAIL / collection error — `scripts/memory_stats.py` does not
exist yet (`ModuleNotFoundError: No module named 'scripts.memory_stats'`).

- [ ] **Step 3: Write the implementation**

Create `scripts/memory_stats.py`:

```python
"""Print summary statistics from the trading decision log.

Reads the decision log at the configured memory_log_path (default
~/.tradingagents/memory/trading_memory.md, or TRADINGAGENTS_MEMORY_LOG_PATH)
and prints resolved-decision count, win rate, average alpha, and average
holding days. Pending (not-yet-resolved) entries are excluded.

Usage:
    python scripts/memory_stats.py
"""

from __future__ import annotations

import sys

from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.default_config import DEFAULT_CONFIG


def compute_stats(entries: list[dict]) -> dict | None:
    """Aggregate resolved decision-log entries into summary stats.

    Returns None if there are no resolved entries. Entries whose raw/alpha/
    holding fields fail to parse are skipped from the aggregates they would
    contribute to, rather than failing the whole computation.
    """
    resolved = [e for e in entries if not e.get("pending")]
    if not resolved:
        return None

    wins = 0
    win_eligible = 0
    alphas: list[float] = []
    holdings: list[float] = []

    for e in resolved:
        raw_str = e.get("raw")
        if raw_str:
            try:
                raw_val = float(raw_str.rstrip("%"))
            except ValueError:
                raw_val = None
            if raw_val is not None:
                win_eligible += 1
                if raw_val > 0:
                    wins += 1

        alpha_str = e.get("alpha")
        if alpha_str:
            try:
                alphas.append(float(alpha_str.rstrip("%")))
            except ValueError:
                pass

        holding_str = e.get("holding")
        if holding_str:
            try:
                holdings.append(float(holding_str.rstrip("d")))
            except ValueError:
                pass

    return {
        "count": len(resolved),
        "win_rate": (wins / win_eligible) if win_eligible else None,
        "avg_alpha": (sum(alphas) / len(alphas)) if alphas else None,
        "avg_holding": (sum(holdings) / len(holdings)) if holdings else None,
    }


def main() -> int:
    memory_log = TradingMemoryLog(DEFAULT_CONFIG)
    stats = compute_stats(memory_log.load_entries())

    if stats is None:
        print("No resolved decisions yet.")
        return 0

    print(f"Decisions: {stats['count']}")
    print(
        f"Win rate: {stats['win_rate'] * 100:.1f}%"
        if stats["win_rate"] is not None
        else "Win rate: n/a"
    )
    print(
        f"Avg alpha: {stats['avg_alpha']:+.1f}%"
        if stats["avg_alpha"] is not None
        else "Avg alpha: n/a"
    )
    print(
        f"Avg holding: {stats['avg_holding']:.1f} days"
        if stats["avg_holding"] is not None
        else "Avg holding: n/a"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest -q tests/test_memory_stats.py`
Expected: PASS (3 passed).

- [ ] **Step 5: Lint**

Run: `ruff check scripts/memory_stats.py tests/test_memory_stats.py`
Expected: clean (no output, exit code 0).

- [ ] **Step 6: Manual smoke of the CLI output**

Run: `TRADINGAGENTS_MEMORY_LOG_PATH=/tmp/nonexistent-memory-log.md python scripts/memory_stats.py`
Expected: prints exactly `No resolved decisions yet.` and exits 0 — proves
the empty/missing-file path works as a real subprocess, matching what
`antigravity-verify` (stage 4) will check with a fixture log next.

Do not commit. This task's diff is reviewed and re-verified by
`codex-delegate` (independent `pytest`/`ruff` re-run + `git diff` review);
the actual `git commit` waits for the user's explicit approval.
