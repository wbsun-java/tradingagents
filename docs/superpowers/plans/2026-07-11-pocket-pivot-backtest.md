# Pocket Pivot Walk-Forward Hit-Rate Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Note for this repo specifically:** this project's established workflow runs each task through the `codex-delegate` skill. When executing, use `codex-delegate` per task; the review-gate structure below still applies. Codex prompts must open with the "YOU are the implementer" paragraph (see feedback_codex_nested_delegation memory).

**Goal:** A read-only walk-forward hit-rate report for pocket pivot signals — baseline by
MA period plus a per-flag lift table — that a human reads to hand-tune the constants in
`pocket_pivot_signals.py`/`pocket_pivot_context.py`. No auto-tuning, no P&L.

**Architecture:** `tradingagents/dataflows/pocket_pivot_backtest.py` holds the testable
logic (`collect_events` walk-forward collection with production-fidelity as-of ATR and
first-sighting dedupe, `aggregate` into baseline + per-flag buckets, `format_report`).
`scripts/backtest_pocket_pivot.py` is a thin argparse CLI mirroring
`backtest_wyckoff.py`'s interface. No existing file is modified.

**Tech Stack:** Python 3.14, pandas, pytest (`@pytest.mark.unit`), ruff.

**Design source of truth:** `docs/superpowers/specs/2026-07-11-pocket-pivot-backtest-design.md`.

## Global Constraints

- No existing file is modified — three new files only.
- Every new file ≤150 lines, tests included (verified budgets: logic ~95, CLI ~50,
  tests ~130).
- `hit = forward_return > 0`; forward return is close-to-close from the **event date's**
  bar (never the walk date's) to `holding_days` bars later; events without a full forward
  window produce no record.
- Dedupe by `(date, ma_period)`, keeping the **first** sighting across walk dates.
- Per-flag lift buckets: flags are `v_shape_risk`, `extended_from_ma`,
  `multi_month_downtrend`, `above_sma200` (from the event's `context` dict) and `gap_up`
  (from the event itself). `None` values count only in `n_na`, never as `False`.
- Walk warm-up: 60 bars (`WARMUP_BARS = 60`); per-walk-date `ValueError` from short
  windows is caught and skipped; nothing else is swallowed.
- All tests `@pytest.mark.unit`, synthetic OHLCV, no network. The manual CLI smoke run on
  a real ticker is performed by the reviewer after the task, NOT inside the Codex sandbox
  (network is not guaranteed there).
- Do NOT `git add`/`git commit` — commits require separate explicit user approval.

**Empirically validated fixture (2026-07-11, prototyped against the live detector — do not
alter its numbers):** the `_fixture()` frame below produces, at any walk date ≥ its bar
100, exactly two events dated `2024-05-21`: `(ma_period=10, v_shape_risk=True,
extended_from_ma=False, multi_month_downtrend=None, above_sma200=None, gap_up=True)` and
`(ma_period=50, v_shape_risk=False, extended_from_ma=None, multi_month_downtrend=None,
above_sma200=None, gap_up=True)`. Forward 20-bar return from the event bar is ≈ +0.0286.
The pre-dip regime's down days deliberately carry HIGHER volume (1.2M) than up days (1.0M)
so routine rebounds fail the pocket pivot volume rule and only bar 100 (1.5M) qualifies.

---

### Task 1: Backtest logic module and tests

**Files:**
- Create: `tradingagents/dataflows/pocket_pivot_backtest.py`
- Test: `tests/test_pocket_pivot_backtest.py`

**Interfaces:**
- Consumes: `analyze_pocket_pivots_from_data(data, curr_date, look_back_days=320)` from
  `tradingagents.dataflows.pocket_pivot_bias` (existing).
- Produces (Task 2 relies on these exact names):
  `collect_events(df: pd.DataFrame, step: int, holding_days: int) -> list[dict]`;
  `new_stats() -> dict`; `aggregate(records: list[dict], stats: dict) -> None`;
  `format_report(stats: dict) -> str`; constant `CONTEXT_FLAGS`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_pocket_pivot_backtest.py
"""Unit tests for the pocket pivot walk-forward hit-rate report logic."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.pocket_pivot_backtest import (
    aggregate,
    collect_events,
    format_report,
    new_stats,
)


def _fixture(total: int = 140, pivot_at: int = 100) -> pd.DataFrame:
    closes: list[float] = []
    vols: list[float] = []
    for i in range(total):
        if i < pivot_at - 6:
            base = 100.0 + 0.05 * i
            if i % 5 == 2:
                closes.append(base - 0.4)
                vols.append(1_200_000.0)
            else:
                closes.append(base)
                vols.append(1_000_000.0)
        elif i < pivot_at:
            closes.append(closes[-1] - 0.35)
            vols.append(700_000.0)
        elif i == pivot_at:
            closes.append(closes[-1] + 2.5)
            vols.append(1_500_000.0)
        else:
            closes.append(closes[-1] + 0.15)
            vols.append(1_000_000.0)
    prices = np.asarray(closes)
    return pd.DataFrame({
        "Date": pd.bdate_range("2024-01-02", periods=total),
        "Open": prices - 0.1,
        "High": prices + 0.5,
        "Low": prices - 0.5,
        "Close": prices,
        "Volume": vols,
    })


@pytest.mark.unit
def test_dedupe_keeps_one_record_per_event_and_ma_period():
    records = collect_events(_fixture(), step=5, holding_days=20)
    assert [(r["date"], r["ma_period"]) for r in records] == [
        ("2024-05-21", 10), ("2024-05-21", 50),
    ]


@pytest.mark.unit
def test_forward_return_anchored_to_event_date():
    records = collect_events(_fixture(), step=5, holding_days=20)
    assert records[0]["forward_return"] == pytest.approx(0.0286, abs=0.001)
    assert records[0]["hit"] is True


@pytest.mark.unit
def test_event_without_full_forward_window_is_dropped():
    assert collect_events(_fixture(), step=5, holding_days=50) == []


@pytest.mark.unit
def test_flag_lift_none_never_counts_as_false():
    records = [
        {"date": "2024-01-10", "ma_period": 10, "gap_up": True,
         "context": {"v_shape_risk": True, "extended_from_ma": None,
                     "multi_month_downtrend": False, "above_sma200": None},
         "forward_return": 0.05, "hit": True},
        {"date": "2024-02-10", "ma_period": 50, "gap_up": False,
         "context": {"v_shape_risk": False, "extended_from_ma": None,
                     "multi_month_downtrend": None, "above_sma200": True},
         "forward_return": -0.02, "hit": False},
    ]
    stats = new_stats()
    aggregate(records, stats)
    assert stats["flags"][("v_shape_risk", True)]["count"] == 1
    assert stats["flags"][("v_shape_risk", False)]["count"] == 1
    assert stats["flags"][("extended_from_ma", None)]["count"] == 2
    assert ("extended_from_ma", False) not in stats["flags"]
    assert stats["flags"][("gap_up", True)]["count"] == 1
    assert stats["baseline"][10]["hits"] == 1
    assert stats["baseline"][50]["hits"] == 0


@pytest.mark.unit
def test_end_to_end_report_contains_expected_buckets():
    records = collect_events(_fixture(), step=5, holding_days=20)
    stats = new_stats()
    aggregate(records, stats)
    report = format_report(stats)
    assert "ma_period" in report and "flag" in report
    assert "v_shape_risk" in report and "gap_up" in report
    # one 10dma event, hit: baseline row shows 100.0%
    assert "100.0%" in report
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pocket_pivot_backtest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tradingagents.dataflows.pocket_pivot_backtest'`

- [ ] **Step 3: Implement the logic module**

```python
# tradingagents/dataflows/pocket_pivot_backtest.py
"""Walk-forward collection and per-flag lift aggregation for pocket pivots.

Not a trading backtest -- no position sizing, execution, or P&L. Feeds
scripts/backtest_pocket_pivot.py; a human reads the report against the
constants in pocket_pivot_signals.py and pocket_pivot_context.py. This
module tunes nothing itself.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd

from tradingagents.dataflows.pocket_pivot_bias import analyze_pocket_pivots_from_data

WARMUP_BARS = 60
CONTEXT_FLAGS = (
    "v_shape_risk",
    "extended_from_ma",
    "multi_month_downtrend",
    "above_sma200",
    "gap_up",
)


def _forward_return(df: pd.DataFrame, event_date: str, holding_days: int) -> float | None:
    matches = df.index[df["Date"] == pd.Timestamp(event_date)]
    if not len(matches):
        return None
    start = int(matches[0])
    target = start + holding_days
    if target >= len(df):
        return None
    entry = float(df["Close"].iloc[start])
    return (float(df["Close"].iloc[target]) - entry) / entry


def collect_events(df: pd.DataFrame, step: int, holding_days: int) -> list[dict[str, Any]]:
    """Walk forward every ``step`` bars; keep each event's first sighting only."""
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for as_of in df["Date"].iloc[WARMUP_BARS::step]:
        window = df[df["Date"] <= as_of]
        try:
            result = analyze_pocket_pivots_from_data(window, as_of.strftime("%Y-%m-%d"))
        except ValueError:
            continue
        for event in result["events"]:
            key = (event["date"], event["ma_period"])
            if key in seen:
                continue
            seen.add(key)
            forward = _forward_return(df, event["date"], holding_days)
            if forward is None:
                continue
            records.append({
                "date": event["date"],
                "ma_period": event["ma_period"],
                "context": dict(event["context"]),
                "gap_up": event["gap_up"],
                "forward_return": forward,
                "hit": forward > 0,
            })
    return records


def _new_bucket() -> dict[str, Any]:
    return {"count": 0, "hits": 0, "return_sum": 0.0}


def new_stats() -> dict[str, Any]:
    return {"baseline": defaultdict(_new_bucket), "flags": defaultdict(_new_bucket)}


def _flag_value(record: dict[str, Any], flag: str) -> bool | None:
    if flag == "gap_up":
        return record["gap_up"]
    return record["context"].get(flag)


def aggregate(records: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    """Fold records into baseline (by ma_period) and per-flag lift buckets."""
    for record in records:
        targets = [stats["baseline"][record["ma_period"]]]
        for flag in CONTEXT_FLAGS:
            value = _flag_value(record, flag)
            targets.append(stats["flags"][(flag, None if value is None else bool(value))])
        for bucket in targets:
            bucket["count"] += 1
            bucket["hits"] += int(record["hit"])
            bucket["return_sum"] += record["forward_return"]


def _cells(stats: dict[str, Any], flag: str, value: bool) -> tuple[int, float, float]:
    bucket = stats["flags"].get((flag, value), {"count": 0, "hits": 0, "return_sum": 0.0})
    n = bucket["count"]
    return n, (bucket["hits"] / n if n else 0.0), (bucket["return_sum"] / n if n else 0.0)


def format_report(stats: dict[str, Any]) -> str:
    lines = [f"\n{'ma_period':<11}{'n':>5}{'hit_rate':>10}{'avg_fwd_ret':>13}"]
    for period in sorted(stats["baseline"]):
        bucket = stats["baseline"][period]
        n = bucket["count"]
        lines.append(
            f"{period:<11}{n:>5}{bucket['hits'] / n:>10.1%}{bucket['return_sum'] / n:>13.2%}"
        )
    lines.append(
        f"\n{'flag':<24}{'n_true':>8}{'hit_true':>10}{'ret_true':>10}"
        f"{'n_false':>9}{'hit_false':>11}{'ret_false':>11}{'n_na':>6}"
    )
    for flag in CONTEXT_FLAGS:
        n_true, hit_true, ret_true = _cells(stats, flag, True)
        n_false, hit_false, ret_false = _cells(stats, flag, False)
        n_na = stats["flags"].get((flag, None), {"count": 0})["count"]
        lines.append(
            f"{flag:<24}{n_true:>8}{hit_true:>10.1%}{ret_true:>10.2%}"
            f"{n_false:>9}{hit_false:>11.1%}{ret_false:>11.2%}{n_na:>6}"
        )
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pocket_pivot_backtest.py -v`
Expected: 5 passed

- [ ] **Step 5: Ruff check**

Run: `ruff check tradingagents/dataflows/pocket_pivot_backtest.py tests/test_pocket_pivot_backtest.py`
Expected: clean. Confirm both files ≤150 lines (`wc -l`). Do NOT commit.

---

### Task 2: CLI script

**Files:**
- Create: `scripts/backtest_pocket_pivot.py`

**Interfaces:**
- Consumes: `collect_events(df, step, holding_days)`, `new_stats()`,
  `aggregate(records, stats)`, `format_report(stats)` from
  `tradingagents.dataflows.pocket_pivot_backtest` (Task 1);
  `load_ohlcv(symbol, curr_date)` from `tradingagents.dataflows.stockstats_utils`
  (existing).
- Produces: the runnable report script; no downstream consumers.

- [ ] **Step 1: Write the script**

```python
# scripts/backtest_pocket_pivot.py
"""Walk-forward hit-rate check for the Pocket Pivot module.

Not a trading backtest -- no position sizing, execution, or P&L. It answers a
narrower question: when analyze_pocket_pivots_from_data reports a pocket
pivot as of some historical date, how often does price rise over the next N
trading days, and how does each context flag (v-shape risk, extension,
downtrend, MA position, gap-up) shift that hit rate? Use this to sanity
check (and eventually manually calibrate) CROSS_BUFFER_ATR and
DOWN_VOLUME_LOOKBACK in tradingagents/dataflows/pocket_pivot_signals.py and
the V_SHAPE_* / EXTENSION_ATR_THRESHOLD / DOWNTREND_LOOKBACK_BARS constants
in tradingagents/dataflows/pocket_pivot_context.py -- this script does not
tune anything itself.

Usage:
    python scripts/backtest_pocket_pivot.py AAPL MSFT NVDA \
        --start 2023-01-01 --end 2026-01-01 --step 5 --holding-days 20
"""

from __future__ import annotations

import argparse

import pandas as pd

from tradingagents.dataflows.pocket_pivot_backtest import (
    aggregate,
    collect_events,
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
    records = collect_events(full, step, holding_days)
    print(f"{symbol}: {len(records)} pocket pivot events with a full forward window")
    aggregate(records, stats)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbols", nargs="+")
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end", default=pd.Timestamp.today().strftime("%Y-%m-%d"))
    parser.add_argument("--step", type=int, default=5, help="business days between walk-forward checks")
    parser.add_argument("--holding-days", type=int, default=20)
    args = parser.parse_args()

    stats = new_stats()
    for symbol in args.symbols:
        print(f"Backtesting {symbol}...")
        backtest_symbol(symbol, args.start, args.end, args.step, args.holding_days, stats)

    print(format_report(stats))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it wires up without network**

Run: `python scripts/backtest_pocket_pivot.py --help`
Expected: usage text prints, exit 0 (proves imports and argparse wiring; no data fetched).

- [ ] **Step 3: Ruff check and regression slice**

```bash
ruff check scripts/backtest_pocket_pivot.py
pytest -q tests/test_pocket_pivot_backtest.py
```

Expected: clean; 5 passed. Confirm the script ≤150 lines. Do NOT commit.

- [ ] **Step 4 (reviewer, outside the Codex sandbox): manual smoke on real data**

Run: `python scripts/backtest_pocket_pivot.py AAPL --start 2024-01-01 --step 5`
Expected: per-symbol event count line, then both report sections with plausible numbers.
This step is performed by the reviewing session, not by Codex (network is not guaranteed
in the sandbox).

---

## Codex model tier per task

Per the design spec: Task 1 (logic + tests) **terra**; Task 2 (CLI) **luna**. Always pass
`-m gpt-5.6-<tier>` explicitly.

## Acceptance criteria (from spec)

- `pytest -q tests/test_pocket_pivot_backtest.py` passes; ruff clean on all three new
  files; every new file ≤150 lines.
- The manual CLI smoke run prints both report sections against real data.
- No modification to any existing file.

> Research/analysis support only; not investment advice; no trade execution.
