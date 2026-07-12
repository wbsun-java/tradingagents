# Chart-Pattern Calibration Backtest (SP4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Note for this repo specifically:** execute each task through the `codex-delegate` skill. Codex prompts must open with the "YOU are the implementer" paragraph (feedback_codex_nested_delegation memory).

**Goal:** A read-only walk-forward report that buckets forward returns by the SP1 apex
flags, SP2 confirmation tier, and SP3 entry state, so a human can judge whether the
SP1–SP3 constants are justified. It tunes nothing itself.

**Architecture:** A new dataflow module `chart_patterns_backtest.py` holds the report
logic (state-sampled collect → aggregate into three bucket families → format three
tables); `scripts/backtest_chart_patterns.py` is refactored into a thin CLI over it,
mirroring `backtest_pocket_pivot.py`. No detection code changes — it reads
`analyze_chart_patterns_from_data` output only.

**Tech Stack:** Python 3.14, pandas, pytest (`@pytest.mark.unit`), ruff.

**Design source of truth:** `docs/superpowers/specs/2026-07-12-chart-pattern-backtest-design.md`.

## Global Constraints

- **New files ≤150 lines each**, verified budgets: `chart_patterns_backtest.py` ~130,
  `tests/test_chart_patterns_backtest.py` ~120. The refactored
  `scripts/backtest_chart_patterns.py` stays ~55 lines. If `format_report` pushes the
  module past 150, split the per-table renderers into module-level helpers (still one
  file) — do not split into a second file unless still over.
- **Scoring — directional `edge`, verbatim:** `_edge(forward_return, direction)` returns
  `forward_return` when `direction in ("long", "none")` and `-forward_return` when
  `direction == "short"`; `hit = edge > 0`. Table 1 feeds `entry_direction`, Tables 2–3
  feed `pattern_direction`.
- **Constants, exact names:** `WARMUP_BARS = 60`. Pattern-direction words map
  `bullish→"long"`, `bearish→"short"`, `neutral→"none"`.
- **State-sampled, no dedupe** — the report header must carry the autocorrelation caveat.
- **Reads only** `analyze_chart_patterns_from_data`; imports nothing from detection to
  mutate. Not a trading backtest (no P&L / sizing / execution). Tunes nothing.
- All tests `@pytest.mark.unit`, synthetic frames only, no network/LLM calls.
- Do NOT `git add`/`git commit` — commits need separate explicit user approval.

---

### Task 1: The backtest module

**Files:**
- Create: `tradingagents/dataflows/chart_patterns_backtest.py`
- Test: `tests/test_chart_patterns_backtest.py`

**Interfaces:**
- Consumes: `analyze_chart_patterns_from_data` from `chart_patterns`.
- Produces: `collect_samples(df, step, holding_days) -> list[dict]`;
  `new_stats() -> dict`; `aggregate(records, stats) -> None`;
  `format_report(stats, symbols, holding_days) -> str`; plus module constants
  `WARMUP_BARS`, `TRIANGLE_PATTERNS`, `FALSE_BREAK_SIGNALS`, `ENTRY_STATES` and helpers
  `_forward_return`, `_pattern_direction_word`, `_edge`, `_apex_bucket`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_chart_patterns_backtest.py
"""Walk-forward calibration report for the chart-pattern constants (SP4)."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows import chart_patterns_backtest as bt


def _interp(anchors):
    values = []
    for (s, sv), (e, ev) in zip(anchors, anchors[1:]):
        values += [sv + (ev - sv) * o / (e - s) for o in range(e - s)]
    values.append(anchors[-1][1])
    return values


def _osc_df():
    closes = _interp(
        [(0, 100), (10, 112), (22, 94), (34, 110), (46, 92), (58, 111), (70, 95),
         (82, 113), (94, 116)]
    )
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2026-01-02", periods=len(closes)),
            "Open": closes, "High": [c + 0.8 for c in closes], "Low": [c - 0.8 for c in closes],
            "Close": closes, "Volume": [1_000_000.0] * len(closes),
        }
    )


def _record(state, entry_direction, pattern, pattern_direction, status, risk_flags, fwd):
    return {
        "state": state, "entry_direction": entry_direction, "pattern": pattern,
        "pattern_direction": pattern_direction, "status": status,
        "risk_flags": tuple(risk_flags), "forward_return": fwd,
    }


@pytest.mark.unit
def test_edge_signs_by_direction():
    assert bt._edge(0.05, "long") == pytest.approx(0.05)
    assert bt._edge(0.05, "none") == pytest.approx(0.05)
    assert bt._edge(0.05, "short") == pytest.approx(-0.05)


@pytest.mark.unit
def test_pattern_direction_word_mapping():
    assert bt._pattern_direction_word("bullish") == "long"
    assert bt._pattern_direction_word("bearish") == "short"
    assert bt._pattern_direction_word("neutral") == "none"


@pytest.mark.unit
def test_apex_bucket_precedence():
    assert bt._apex_bucket(("post_apex_breakout", "late_apex_breakout")) == "post_apex_breakout"
    assert bt._apex_bucket(("late_apex_breakout",)) == "late_apex_breakout"
    assert bt._apex_bucket(()) == "normal"


@pytest.mark.unit
def test_forward_return_none_past_frame():
    df = _osc_df()
    assert bt._forward_return(df, df["Date"].iloc[-1], 3) is None
    val = bt._forward_return(df, df["Date"].iloc[10], 3)
    assert val == pytest.approx(
        (float(df["Close"].iloc[13]) - float(df["Close"].iloc[10])) / float(df["Close"].iloc[10])
    )


@pytest.mark.unit
def test_aggregate_routes_records_to_the_three_tables():
    records = [
        # entry_state only (a long entry that worked)
        _record("breakout_entry", "long", "rectangle", "long", "confirmed", [], 0.04),
        # confirmed triangle with a post-apex flag -> Table 1 + Table 2
        _record("observe", "none", "symmetrical_triangle", "long", "confirmed",
                ["post_apex_breakout"], -0.02),
        # false-break short, aggressive -> Table 1 + Table 3 (edge = -fwd)
        _record("false_breakout_short", "short", "false_breakout_short", "short", "confirmed",
                ["aggressive_confirmation"], -0.03),
    ]
    stats = bt.new_stats()
    bt.aggregate(records, stats)

    assert stats["entry_state"]["breakout_entry"]["count"] == 1
    assert stats["entry_state"]["breakout_entry"]["hits"] == 1  # +0.04 long edge
    assert stats["apex"]["post_apex_breakout"]["count"] == 1
    assert stats["apex"]["post_apex_breakout"]["hits"] == 0  # -0.02 long edge
    tier = stats["tier"][("false_breakout_short", True)]
    assert tier["count"] == 1
    assert tier["hits"] == 1  # short edge = -(-0.03) = +0.03
    # a false-break signal must NOT land in the apex (triangle) table
    assert sum(b["count"] for b in stats["apex"].values()) == 1


@pytest.mark.unit
def test_format_report_has_the_three_table_headers():
    stats = bt.new_stats()
    bt.aggregate(
        [_record("avoid", "none", "double_top", "short", "confirmed", [], -0.01)], stats
    )
    text = bt.format_report(stats, ["AAPL"], 10)
    assert "TABLE 1" in text and "entry_state" in text
    assert "TABLE 2" in text and "apex" in text
    assert "TABLE 3" in text
    assert "autocorrelate" in text  # the state-sampling caveat


@pytest.mark.unit
def test_collect_samples_returns_well_formed_records():
    records = bt.collect_samples(_osc_df(), step=5, holding_days=3)
    assert isinstance(records, list) and len(records) >= 1
    keys = {"state", "entry_direction", "pattern", "pattern_direction", "status",
            "risk_flags", "forward_return"}
    for r in records:
        assert set(r) == keys
        assert isinstance(r["forward_return"], float)
        assert r["state"] in bt.ENTRY_STATES or r["state"] is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest -q tests/test_chart_patterns_backtest.py`
Expected: FAIL with `ModuleNotFoundError: ... chart_patterns_backtest`.

- [ ] **Step 3: Write the module**

```python
# tradingagents/dataflows/chart_patterns_backtest.py
"""Walk-forward calibration report for the SP1/SP2/SP3 chart-pattern constants.

Not a trading backtest -- no position sizing, execution, or P&L. State-sampled (no dedupe;
overlapping windows autocorrelate) so it evaluates the signal a trader reads each day.
Feeds scripts/backtest_chart_patterns.py; a human reads the report against the interim
constants in triangle_post_apex.py (SP1), false_break_types.py (SP2), and entry_types.py
(SP3). This module tunes nothing itself.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd

from tradingagents.dataflows.chart_patterns import analyze_chart_patterns_from_data

WARMUP_BARS = 60
TRIANGLE_PATTERNS = ("symmetrical_triangle", "ascending_triangle", "descending_triangle")
FALSE_BREAK_SIGNALS = ("false_breakout_short", "false_breakdown_long")
ENTRY_STATES = (
    "predictive_bottom", "breakout_entry", "breakout_retest_entry", "observe", "avoid",
    "false_breakout_short", "false_breakdown_long",
)


def _forward_return(df: pd.DataFrame, as_of, holding_days: int) -> float | None:
    matches = df.index[df["Date"] == pd.Timestamp(as_of)]
    if not len(matches):
        return None
    start = int(matches[0])
    target = start + holding_days
    if target >= len(df):
        return None
    entry = float(df["Close"].iloc[start])
    return (float(df["Close"].iloc[target]) - entry) / entry


def _pattern_direction_word(direction: str) -> str:
    if direction == "bullish":
        return "long"
    if direction == "bearish":
        return "short"
    return "none"


def _edge(forward_return: float, direction: str) -> float:
    return -forward_return if direction == "short" else forward_return


def _apex_bucket(risk_flags: tuple[str, ...]) -> str:
    if "post_apex_breakout" in risk_flags:
        return "post_apex_breakout"
    if "late_apex_breakout" in risk_flags:
        return "late_apex_breakout"
    return "normal"


def collect_samples(df: pd.DataFrame, step: int, holding_days: int) -> list[dict[str, Any]]:
    """State-sample every ``step`` bars: one record per pattern per walk-forward date."""
    records: list[dict[str, Any]] = []
    for as_of in df["Date"].iloc[WARMUP_BARS::step]:
        window = df[df["Date"] <= as_of]
        try:
            result = analyze_chart_patterns_from_data(window, as_of.strftime("%Y-%m-%d"))
        except ValueError:
            continue
        forward = _forward_return(df, as_of, holding_days)
        if forward is None:
            continue
        for pattern in result["patterns"]:
            entry = pattern.get("entry_assessment") or {}
            records.append(
                {
                    "state": entry.get("state"),
                    "entry_direction": entry.get("direction", "none"),
                    "pattern": pattern["pattern"],
                    "pattern_direction": _pattern_direction_word(pattern["direction"]),
                    "status": pattern["status"],
                    "risk_flags": tuple(pattern.get("risk_flags", [])),
                    "forward_return": forward,
                }
            )
    return records


def _new_bucket() -> dict[str, Any]:
    return {"count": 0, "hits": 0, "edge_sum": 0.0}


def new_stats() -> dict[str, Any]:
    return {
        "entry_state": defaultdict(_new_bucket),
        "apex": defaultdict(_new_bucket),
        "tier": defaultdict(_new_bucket),
    }


def _add(bucket: dict[str, Any], edge: float) -> None:
    bucket["count"] += 1
    bucket["hits"] += int(edge > 0)
    bucket["edge_sum"] += edge


def aggregate(records: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    """Fold each record into the entry_state, apex, and tier bucket families."""
    for record in records:
        forward = record["forward_return"]
        if record["state"] is not None:
            _add(stats["entry_state"][record["state"]], _edge(forward, record["entry_direction"]))
        if record["pattern"] in TRIANGLE_PATTERNS and record["status"] == "confirmed":
            _add(stats["apex"][_apex_bucket(record["risk_flags"])],
                 _edge(forward, record["pattern_direction"]))
        if record["pattern"] in FALSE_BREAK_SIGNALS:
            aggressive = "aggressive_confirmation" in record["risk_flags"]
            _add(stats["tier"][(record["pattern"], aggressive)],
                 _edge(forward, record["pattern_direction"]))


def _row(bucket: dict[str, Any]) -> tuple[int, float, float]:
    n = bucket["count"]
    return n, (bucket["hits"] / n if n else 0.0), (bucket["edge_sum"] / n if n else 0.0)


def format_report(stats: dict[str, Any], symbols: list[str], holding_days: int) -> str:
    total = sum(bucket["count"] for bucket in stats["entry_state"].values())
    lines = [
        f"\nChart-pattern calibration backtest -- {', '.join(symbols)}",
        f"holding_days={holding_days}, entry_state samples n={total}",
        "State-sampled (no dedupe); overlapping windows autocorrelate -- read gradients.",
        f"\nTABLE 1  entry_state (SP3)\n{'state':<24}{'n':>6}{'hit%':>8}{'avg_edge':>11}",
    ]
    for state in ENTRY_STATES:
        n, hit, edge = _row(stats["entry_state"][state])
        if n:
            lines.append(f"{state:<24}{n:>6}{hit:>8.1%}{edge:>11.2%}")
    lines.append(f"\nTABLE 2  apex timing, confirmed triangles (SP1)\n"
                 f"{'apex_bucket':<24}{'n':>6}{'hit%':>8}{'avg_edge':>11}")
    for name in ("normal", "late_apex_breakout", "post_apex_breakout"):
        n, hit, edge = _row(stats["apex"][name])
        if n:
            lines.append(f"{name:<24}{n:>6}{hit:>8.1%}{edge:>11.2%}")
    lines.append(f"\nTABLE 3  SP2 tier (false-break signals)\n{'signal':<22}"
                 f"{'n_agg':>6}{'hit_agg':>9}{'edge_agg':>10}{'n_std':>7}{'hit_std':>9}{'edge_std':>10}")
    for signal in FALSE_BREAK_SIGNALS:
        na, hita, ea = _row(stats["tier"].get((signal, True), _new_bucket()))
        ns, hits, es = _row(stats["tier"].get((signal, False), _new_bucket()))
        lines.append(f"{signal:<22}{na:>6}{hita:>9.1%}{ea:>10.2%}{ns:>7}{hits:>9.1%}{es:>10.2%}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest -q tests/test_chart_patterns_backtest.py`
Expected: PASS (6 passed). If `test_collect_samples_returns_well_formed_records` finds
zero records, widen the oscillation anchors in `_osc_df` (more/steeper swings) until the
walk yields at least one pattern — do not weaken the assertion.

- [ ] **Step 5: Budget + ruff, then STOP for review** (do not commit)

Run: `wc -l tradingagents/dataflows/chart_patterns_backtest.py` (expect ~130, ≤150)
Run: `ruff check tradingagents/dataflows/chart_patterns_backtest.py tests/test_chart_patterns_backtest.py`
Expected: `All checks passed!`

---

### Task 2: Refactor the CLI script over the module

**Files:**
- Modify (rewrite): `scripts/backtest_chart_patterns.py`

**Interfaces:**
- Consumes: `collect_samples`, `new_stats`, `aggregate`, `format_report` from
  `chart_patterns_backtest`; `load_ohlcv` from `stockstats_utils`.
- Produces: a thin CLI; `backtest_symbol(symbol, start, end, step, holding_days, stats)`.

- [ ] **Step 1: Rewrite the script** (replace the whole file)

```python
# scripts/backtest_chart_patterns.py
"""Walk-forward calibration report for the deterministic chart-pattern signals.

Not a trading backtest -- no position sizing, execution, or P&L. It buckets forward
returns by SP3 entry state, SP1 apex-timing flags, and SP2 confirmation tier so a human
can judge whether the interim constants in triangle_post_apex.py, false_break_types.py,
and entry_types.py are justified. State-sampled (no dedupe); this script tunes nothing.

Usage:
    python scripts/backtest_chart_patterns.py AAPL MSFT NVDA \
        --start 2022-01-01 --end 2026-01-01 --step 5 --holding-days 10
"""

from __future__ import annotations

import argparse

import pandas as pd

from tradingagents.dataflows.chart_patterns_backtest import (
    aggregate,
    collect_samples,
    format_report,
    new_stats,
)
from tradingagents.dataflows.stockstats_utils import load_ohlcv

MIN_BARS = 80


def backtest_symbol(
    symbol: str, start: str, end: str, step: int, holding_days: int, stats: dict
) -> None:
    full = load_ohlcv(symbol, end)
    full = full[full["Date"] >= pd.Timestamp(start)].reset_index(drop=True)
    if len(full) < MIN_BARS:
        print(f"{symbol}: not enough history in range, skipping")
        return
    records = collect_samples(full, step, holding_days)
    print(f"{symbol}: {len(records)} state-sampled pattern observations")
    aggregate(records, stats)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbols", nargs="+")
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end", default=pd.Timestamp.today().strftime("%Y-%m-%d"))
    parser.add_argument("--step", type=int, default=5, help="business days between checks")
    parser.add_argument("--holding-days", type=int, default=10)
    args = parser.parse_args()

    stats = new_stats()
    for symbol in args.symbols:
        print(f"Backtesting {symbol}...")
        backtest_symbol(symbol, args.start, args.end, args.step, args.holding_days, stats)

    print(format_report(stats, args.symbols, args.holding_days))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the CLI wires up**

Run: `python scripts/backtest_chart_patterns.py --help`
Expected: exit 0, usage text listing `symbols`, `--start`, `--end`, `--step`,
`--holding-days`.

- [ ] **Step 3: Ruff + confirm no detection files changed, then STOP for review** (do not commit)

Run: `ruff check scripts/backtest_chart_patterns.py`
Run: `git status --short` — expect only `chart_patterns_backtest.py`,
`test_chart_patterns_backtest.py`, and `scripts/backtest_chart_patterns.py`; NO change to
`chart_patterns.py` or any SP1/SP2/SP3 detection module.
Expected: `All checks passed!`; the diff touches only the three backtest files.

---

## Self-Review

**Spec coverage:** ✔ three lift tables — entry_state (Table 1), apex-timing (Table 2), SP2
tier (Table 3) — in `format_report` + `aggregate` (Task 1); ✔ state-sampled no-dedupe walk
with autocorrelation caveat in the header (Task 1); ✔ directional `_edge`, Table 1 uses
`entry_direction`, Tables 2–3 use `pattern_direction`, `none`=long-reference (Task 1,
`test_edge_signs`/`test_aggregate_routes`); ✔ None-tier as its own bucket via
`.get((signal, True/False))` (Table 3); ✔ refactor to module + thin CLI mirroring
pocket-pivot, defaults `--start 2022-01-01`/`--step 5`/`--holding-days 10` (Task 2); ✔ no
detection changes, reads `analyze_chart_patterns_from_data` only (Task 1 imports + Task 2
git-status check); ✔ non-goals honored (no sweep, no auto-tune, no P&L).

**Placeholder scan:** no TBD/"handle edge cases"/"similar to Task N"; every code step is
complete and copy-pasteable.

**Type consistency:** `collect_samples`/`new_stats`/`aggregate`/`format_report` signatures
match between Task 1 (definition), the tests, and Task 2 (call sites — note
`format_report(stats, args.symbols, args.holding_days)` matches the 3-arg definition). The
record dict's seven keys are identical in `collect_samples`, the test `_record` helper,
and `aggregate`'s reads. Direction vocab is uniform: `entry_direction` and
`_pattern_direction_word` both yield `long`/`short`/`none`, which `_edge` consumes.
