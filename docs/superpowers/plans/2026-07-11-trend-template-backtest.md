# Minervini Trend Template Walk-Forward Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Note for this repo specifically:** execute each task through the `codex-delegate` skill. Codex prompts must open with the "YOU are the implementer" paragraph (feedback_codex_nested_delegation memory).

**Goal:** A read-only walk-forward hit-rate report for the Minervini trend template,
bucketed by pass-count bands and rs_score bands, so a human can judge whether the
template's gradient predicts outcomes and whether `rs_score` adds lift beyond it.

**Architecture:** `tradingagents/dataflows/trend_template_backtest.py` holds the logic
(`collect_readings` state-sampling with both frames truncated per walk date, band
functions, aggregation, report formatting); `scripts/backtest_trend_template.py` is a thin
CLI that requires a benchmark and skips symbols when it is unavailable. No existing file
is modified.

**Tech Stack:** Python 3.14, pandas, pytest (`@pytest.mark.unit`), ruff.

**Design source of truth:** `docs/superpowers/specs/2026-07-11-trend-template-backtest-design.md`.

## Global Constraints

- No existing file is modified — three new files only, each ≤150 lines (tests included;
  verified budgets: logic ~130, CLI ~75, tests ~125).
- State sampling, **no dedupe**: one record per walk date; docstrings must state that
  adjacent samples overlap and autocorrelate (tendencies, not independent trials).
- `WARMUP_BARS = 260`. Forward return is close-to-close from the walk date's bar to
  `holding_days` bars later; walk dates without a full forward window produce no record.
  `hit = forward_return > 0`.
- Bands (exact): `pass_band` → `"0-4"`, `"5-6"`, `"7"`, `"8"`; `rs_band` → `"rs<0"`
  (`score < 0`), `"0<=rs<=0.10"` (`0 <= score <= 0.10`), `"rs>0.10"` (`score > 0.10`),
  `"n/a"` (None). 0 and 0.10 both belong to the middle band.
- Benchmark is required at the CLI layer: a symbol is skipped with a printed message when
  the benchmark frame cannot be loaded; `collect_readings` itself takes the benchmark
  frame as a required argument and asserts nothing about availability.
- Report prints every band row in fixed order even when `n = 0`.
- All tests `@pytest.mark.unit`, synthetic frames, no network. The real-data smoke run is
  performed by the reviewer outside the Codex sandbox.
- Do NOT `git add`/`git commit` — commits require separate explicit user approval.

**Empirically validated fixture (2026-07-11, prototyped against the live
`evaluate_trend_template` — do not alter):** with a 320-bar linear ramp 100→220 as the
stock and a flat-100 benchmark, truncation at any walk bar ≥260 yields
`passed_count = 8/8`, `stage_2_uptrend = True`, `rs_score ≈ 0.15–0.17` (the `rs>0.10`
band). The mirrored 220→100 downtrend yields `0/8` with negative rs. Forward 20-bar
return from bar 260 on the strong stock ≈ `+0.038`. `relative_strength_score` returns
`None` below 253 aligned bars.

---

### Task 1: Backtest logic module and tests

**Files:**
- Create: `tradingagents/dataflows/trend_template_backtest.py`
- Test: `tests/test_trend_template_backtest.py`

**Interfaces:**
- Consumes: `evaluate_trend_template(df, benchmark_df)` from
  `tradingagents.dataflows.trend_template` (existing; returns `TrendTemplateResult` with
  `.passed_count`, `.total_criteria`, `.stage_2_uptrend`, `.values["rs_score"]`).
- Produces (Task 2 relies on these exact names):
  `collect_readings(df: pd.DataFrame, benchmark_df: pd.DataFrame, step: int,
  holding_days: int) -> list[dict]`; `pass_band(passed_count: int) -> str`;
  `rs_band(rs_score: float | None) -> str`; `new_stats() -> dict`;
  `aggregate(records: list[dict], stats: dict) -> None`;
  `format_report(stats: dict) -> str`; constants `WARMUP_BARS`, `PASS_BANDS`, `RS_BANDS`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_trend_template_backtest.py
"""Unit tests for the trend-template walk-forward hit-rate report logic."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.trend_template_backtest import (
    WARMUP_BARS,
    aggregate,
    collect_readings,
    format_report,
    new_stats,
    pass_band,
    rs_band,
)


def _frame(closes) -> pd.DataFrame:
    prices = np.asarray(closes, dtype=float)
    return pd.DataFrame({
        "Date": pd.bdate_range("2024-01-02", periods=len(prices)),
        "Open": prices,
        "High": prices + 0.5,
        "Low": prices - 0.5,
        "Close": prices,
        "Volume": 1_000_000.0,
    })


def _strong() -> pd.DataFrame:
    return _frame(np.linspace(100.0, 220.0, 320))


def _flat_benchmark() -> pd.DataFrame:
    return _frame(np.full(320, 100.0))


@pytest.mark.unit
def test_pass_band_edges():
    assert pass_band(0) == "0-4"
    assert pass_band(4) == "0-4"
    assert pass_band(5) == "5-6"
    assert pass_band(6) == "5-6"
    assert pass_band(7) == "7"
    assert pass_band(8) == "8"


@pytest.mark.unit
def test_rs_band_edges():
    assert rs_band(-0.001) == "rs<0"
    assert rs_band(0.0) == "0<=rs<=0.10"
    assert rs_band(0.10) == "0<=rs<=0.10"
    assert rs_band(0.101) == "rs>0.10"
    assert rs_band(None) == "n/a"


@pytest.mark.unit
def test_collect_samples_strong_uptrend_as_stage_2():
    records = collect_readings(_strong(), _flat_benchmark(), step=10, holding_days=20)
    assert records, "expected records past the warm-up"
    first = records[0]
    assert first["passed_count"] == 8
    assert first["stage_2_uptrend"] is True
    assert first["rs_score"] > 0.10
    assert first["forward_return"] == pytest.approx(0.038, abs=0.005)
    assert first["hit"] is True
    # warm-up respected: first sampled date is at/after bar WARMUP_BARS
    assert first["date"] >= _strong()["Date"].iloc[WARMUP_BARS].strftime("%Y-%m-%d")


@pytest.mark.unit
def test_no_records_without_full_forward_window():
    # holding window longer than the bars remaining after warm-up
    assert collect_readings(_strong(), _flat_benchmark(), step=10, holding_days=80) == []


@pytest.mark.unit
def test_aggregate_routes_bands_and_none_rs():
    records = [
        {"date": "2025-01-02", "passed_count": 8, "total_criteria": 8,
         "stage_2_uptrend": True, "rs_score": 0.15, "forward_return": 0.04, "hit": True},
        {"date": "2025-02-03", "passed_count": 5, "total_criteria": 8,
         "stage_2_uptrend": False, "rs_score": None, "forward_return": -0.01, "hit": False},
    ]
    stats = new_stats()
    aggregate(records, stats)
    assert stats["baseline"]["8"]["hits"] == 1
    assert stats["baseline"]["5-6"]["count"] == 1
    assert stats["lift"][("8", "rs>0.10")]["count"] == 1
    assert stats["lift"][("5-6", "n/a")]["count"] == 1
    assert ("5-6", "rs<0") not in stats["lift"]


@pytest.mark.unit
def test_end_to_end_report_contains_expected_rows():
    records = collect_readings(_strong(), _flat_benchmark(), step=10, holding_days=20)
    stats = new_stats()
    aggregate(records, stats)
    report = format_report(stats)
    assert "pass_band" in report and "rs_band" in report
    assert "rs>0.10" in report
    assert "100.0%" in report  # every strong-uptrend sample is a hit
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_trend_template_backtest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tradingagents.dataflows.trend_template_backtest'`

- [ ] **Step 3: Implement the logic module**

```python
# tradingagents/dataflows/trend_template_backtest.py
"""Walk-forward sampling and band aggregation for the Minervini trend template.

Not a trading backtest -- no position sizing, execution, or P&L. The trend
template is a state read, so one record is sampled per walk date with no
dedupe: adjacent samples overlap and autocorrelate, and hit rates should be
read as tendencies over correlated samples, not independent trials. Feeds
scripts/backtest_trend_template.py; a human reads the report against the
thresholds and _QUARTER_WEIGHTS in trend_template.py. Tunes nothing itself.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd

from tradingagents.dataflows.trend_template import evaluate_trend_template

WARMUP_BARS = 260
PASS_BANDS = ("0-4", "5-6", "7", "8")
RS_BANDS = ("rs<0", "0<=rs<=0.10", "rs>0.10", "n/a")


def pass_band(passed_count: int) -> str:
    if passed_count <= 4:
        return "0-4"
    if passed_count <= 6:
        return "5-6"
    return str(passed_count)


def rs_band(rs_score: float | None) -> str:
    if rs_score is None:
        return "n/a"
    if rs_score < 0:
        return "rs<0"
    if rs_score <= 0.10:
        return "0<=rs<=0.10"
    return "rs>0.10"


def _forward_return(df: pd.DataFrame, start: int, holding_days: int) -> float | None:
    target = start + holding_days
    if target >= len(df):
        return None
    entry = float(df["Close"].iloc[start])
    return (float(df["Close"].iloc[target]) - entry) / entry


def collect_readings(
    df: pd.DataFrame, benchmark_df: pd.DataFrame, step: int, holding_days: int
) -> list[dict[str, Any]]:
    """Sample the template every ``step`` bars; one record per walk date, no dedupe."""
    records: list[dict[str, Any]] = []
    for position in range(WARMUP_BARS, len(df), step):
        forward = _forward_return(df, position, holding_days)
        if forward is None:
            break
        as_of = df["Date"].iloc[position]
        window = df[df["Date"] <= as_of]
        benchmark_window = benchmark_df[benchmark_df["Date"] <= as_of]
        result = evaluate_trend_template(window, benchmark_window)
        records.append({
            "date": as_of.strftime("%Y-%m-%d"),
            "passed_count": result.passed_count,
            "total_criteria": result.total_criteria,
            "stage_2_uptrend": result.stage_2_uptrend,
            "rs_score": result.values.get("rs_score"),
            "forward_return": forward,
            "hit": forward > 0,
        })
    return records


def _new_bucket() -> dict[str, Any]:
    return {"count": 0, "hits": 0, "return_sum": 0.0}


def new_stats() -> dict[str, Any]:
    return {"baseline": defaultdict(_new_bucket), "lift": defaultdict(_new_bucket)}


def aggregate(records: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    """Fold records into baseline (by pass band) and lift (pass band x rs band) buckets."""
    for record in records:
        bands = (pass_band(record["passed_count"]), rs_band(record["rs_score"]))
        for bucket in (stats["baseline"][bands[0]], stats["lift"][bands]):
            bucket["count"] += 1
            bucket["hits"] += int(record["hit"])
            bucket["return_sum"] += record["forward_return"]


def _row(bucket: dict[str, Any]) -> tuple[int, float, float]:
    n = bucket["count"]
    return n, (bucket["hits"] / n if n else 0.0), (bucket["return_sum"] / n if n else 0.0)


def format_report(stats: dict[str, Any]) -> str:
    lines = [f"\n{'pass_band':<11}{'n':>6}{'hit_rate':>10}{'avg_fwd_ret':>13}"]
    for band in PASS_BANDS:
        n, hit, ret = _row(stats["baseline"].get(band, _new_bucket()))
        lines.append(f"{band:<11}{n:>6}{hit:>10.1%}{ret:>13.2%}")
    lines.append(f"\n{'pass_band':<11}{'rs_band':<14}{'n':>6}{'hit_rate':>10}{'avg_fwd_ret':>13}")
    for band in PASS_BANDS:
        for rs in RS_BANDS:
            n, hit, ret = _row(stats["lift"].get((band, rs), _new_bucket()))
            lines.append(f"{band:<11}{rs:<14}{n:>6}{hit:>10.1%}{ret:>13.2%}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_trend_template_backtest.py -v`
Expected: 6 passed

- [ ] **Step 5: Ruff check**

Run: `ruff check tradingagents/dataflows/trend_template_backtest.py tests/test_trend_template_backtest.py`
Expected: clean. Confirm both files ≤150 lines (`wc -l`). Do NOT commit.

---

### Task 2: CLI script

**Files:**
- Create: `scripts/backtest_trend_template.py`

**Interfaces:**
- Consumes: `collect_readings(df, benchmark_df, step, holding_days)`, `new_stats()`,
  `aggregate(records, stats)`, `format_report(stats)` from
  `tradingagents.dataflows.trend_template_backtest` (Task 1);
  `load_ohlcv(symbol, curr_date)` from `tradingagents.dataflows.stockstats_utils`
  (existing; raises `ValueError` on unusable data).
- Produces: the runnable report script; no downstream consumers.

- [ ] **Step 1: Write the script**

```python
# scripts/backtest_trend_template.py
"""Walk-forward hit-rate check for the Minervini trend-template module.

Not a trading backtest -- no position sizing, execution, or P&L. The template
is a state read sampled every --step bars, so adjacent samples overlap and
autocorrelate: read hit rates as tendencies, not independent trials. It
answers two questions: does the pass-count gradient predict forward returns,
and does rs_score add lift beyond the pass count? Use it to sanity check
(and eventually manually calibrate) the criteria thresholds and
_QUARTER_WEIGHTS in tradingagents/dataflows/trend_template.py -- this script
does not tune anything itself.

A benchmark is required: without one the RS criterion drops out and
passed_count's denominator silently changes from 8 to 7, corrupting the
pass-band semantics; symbols are skipped instead.

Usage:
    python scripts/backtest_trend_template.py AAPL MSFT NVDA \
        --benchmark SPY --start 2023-01-01 --step 5 --holding-days 20
"""

from __future__ import annotations

import argparse

import pandas as pd

from tradingagents.dataflows.stockstats_utils import load_ohlcv
from tradingagents.dataflows.trend_template_backtest import (
    WARMUP_BARS,
    aggregate,
    collect_readings,
    format_report,
    new_stats,
)


def backtest_symbol(
    symbol: str,
    benchmark_df: pd.DataFrame,
    start: str,
    end: str,
    step: int,
    holding_days: int,
    stats: dict,
) -> None:
    full = load_ohlcv(symbol, end)
    full = full[full["Date"] >= pd.Timestamp(start)].reset_index(drop=True)
    if len(full) < WARMUP_BARS + holding_days:
        print(f"{symbol}: not enough history in range, skipping")
        return
    records = collect_readings(full, benchmark_df, step, holding_days)
    print(f"{symbol}: {len(records)} sampled readings with a full forward window")
    aggregate(records, stats)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbols", nargs="+")
    parser.add_argument("--benchmark", default="SPY")
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end", default=pd.Timestamp.today().strftime("%Y-%m-%d"))
    parser.add_argument("--step", type=int, default=5, help="business days between walk-forward checks")
    parser.add_argument("--holding-days", type=int, default=20)
    args = parser.parse_args()

    try:
        benchmark_df = load_ohlcv(args.benchmark, args.end)
        benchmark_df = benchmark_df[benchmark_df["Date"] >= pd.Timestamp(args.start)].reset_index(drop=True)
    except ValueError as exc:
        print(f"benchmark {args.benchmark} unavailable ({exc}); cannot run — all symbols skipped")
        return

    stats = new_stats()
    for symbol in args.symbols:
        print(f"Backtesting {symbol}...")
        backtest_symbol(symbol, benchmark_df, args.start, args.end, args.step, args.holding_days, stats)

    print(format_report(stats))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify wiring without network**

Run: `python scripts/backtest_trend_template.py --help`
Expected: usage text prints, exit 0.

- [ ] **Step 3: Ruff check and regression slice**

```bash
ruff check scripts/backtest_trend_template.py
pytest -q tests/test_trend_template_backtest.py
```

Expected: clean; 6 passed. Confirm the script ≤150 lines. Do NOT commit.

- [ ] **Step 4 (reviewer, outside the Codex sandbox): manual smoke on real data**

Run: `python scripts/backtest_trend_template.py AAPL NVDA --start 2024-01-01 --step 5`
Expected: per-symbol reading counts, then both report sections with plausible numbers.
Performed by the reviewing session, not Codex.

---

## Codex model tier per task

Per the design spec: Task 1 (logic + tests) **terra**; Task 2 (CLI) **luna**. Always pass
`-m gpt-5.6-<tier>` explicitly.

## Acceptance criteria (from spec)

- `pytest -q tests/test_trend_template_backtest.py` passes; ruff clean on all three new
  files; every new file ≤150 lines.
- Manual reviewer smoke prints both sections against real data.
- No modification to any existing file.

> Research/analysis support only; not investment advice; no trade execution.
