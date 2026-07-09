# Wyckoff Walk-Forward Calibration Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only walk-forward hit-rate report for the Wyckoff structure module (`scripts/backtest_wyckoff.py`), mirroring the existing `scripts/backtest_chart_patterns.py`, plus the one additive field it needs from `wyckoff_bias.py`.

**Architecture:** `analyze_wyckoff_structure_from_data` gains a `vsa_confidence_delta` field on its result dict (the signed VSA confidence adjustment, currently computed but discarded). A new standalone script walks OHLCV history date-by-date, calls that function on each truncated window, buckets `status == "confirmed"` reads by `(current_phase, vsa_effect)`, and prints hit-rate/avg-confidence/avg-forward-return per bucket. No auto-tuning; a human reads the table and edits constants by hand.

**Tech Stack:** Python, pandas, pytest (`@pytest.mark.unit`), ruff.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-09-wyckoff-calibration-design.md`.
- `scripts/backtest_wyckoff.py` is a new file — CLAUDE.md's 150-line cap applies. If bucket/report logic pushes it over, split report printing into a second file rather than compressing past readability.
- `wyckoff_bias.py` is project-custom (not upstream) — no upstream-approval gate applies to editing it.
- No detection/scoring logic changes anywhere else (`wyckoff_range.py`, `wyckoff_accumulation.py`, `wyckoff_distribution.py`, `wyckoff_vsa*.py`, `market_analyst.py`, `trading_graph.py` are all out of scope).
- Default verification per CLAUDE.md for an isolated additive change: `pytest -q tests/test_wyckoff_bias.py` and `ruff check` on touched files — no full-suite run needed.

---

### Task 1: Add `vsa_confidence_delta` to the Wyckoff bias payload

**Files:**
- Modify: `tradingagents/dataflows/wyckoff_bias.py`
- Test: `tests/test_wyckoff_bias.py`

**Interfaces:**
- Consumes: existing `analyze_vsa(df, atr_value, rng, phase_bias, curr_date) -> tuple[list[dict], float]` from `tradingagents/dataflows/wyckoff_vsa.py` (unchanged).
- Produces: `analyze_wyckoff_structure_from_data(...)` result dict now includes `"vsa_confidence_delta": float` (rounded to 4 decimals) whenever `"vsa_signals"` is present (i.e. on any non-neutral read). Absent on neutral reads, same condition as `vsa_signals`. Later tasks (Task 2's backtest script) read this field to bucket by VSA effect sign.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_wyckoff_bias.py` (append after `test_neutral_result_has_no_vsa_signals_key`):

```python
@pytest.mark.unit
def test_accumulation_result_includes_vsa_confidence_delta_as_float():
    df = _accumulation_df()
    result = analyze_wyckoff_structure_from_data(df, df["Date"].iloc[-1].strftime("%Y-%m-%d"))

    assert "vsa_confidence_delta" in result
    assert isinstance(result["vsa_confidence_delta"], float)


@pytest.mark.unit
def test_neutral_result_has_no_vsa_confidence_delta_key():
    length = 120
    closes = [50.0 + 100.0 * i / (length - 1) for i in range(length)]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    volumes = [1_000_000.0] * length
    df = _to_df(closes, highs, lows, volumes)

    result = analyze_wyckoff_structure_from_data(df, df["Date"].iloc[-1].strftime("%Y-%m-%d"))

    assert "vsa_confidence_delta" not in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_wyckoff_bias.py -k vsa_confidence_delta -v`
Expected: FAIL — `KeyError` / `assert "vsa_confidence_delta" in result` fails because the key doesn't exist yet.

- [ ] **Step 3: Implement the field**

In `tradingagents/dataflows/wyckoff_bias.py`, find `analyze_wyckoff_structure_from_data`'s tail:

```python
    vsa_signals, delta = analyze_vsa(df, atr_value, rng, result["phase_bias"], curr_date)
    result["vsa_signals"] = vsa_signals
    result["confidence"] = round(max(0.0, min(1.0, result["confidence"] + delta)), 2)
    return result
```

Replace with:

```python
    vsa_signals, delta = analyze_vsa(df, atr_value, rng, result["phase_bias"], curr_date)
    result["vsa_signals"] = vsa_signals
    result["vsa_confidence_delta"] = round(delta, 4)
    result["confidence"] = round(max(0.0, min(1.0, result["confidence"] + delta)), 2)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_wyckoff_bias.py -v`
Expected: PASS — all tests in the file, including the two new ones and the pre-existing ones (no regressions).

- [ ] **Step 5: Ruff check**

Run: `ruff check tradingagents/dataflows/wyckoff_bias.py tests/test_wyckoff_bias.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/dataflows/wyckoff_bias.py tests/test_wyckoff_bias.py
git commit -m "feat(wyckoff): expose signed VSA confidence delta on the bias payload"
```

---

### Task 2: Add `scripts/backtest_wyckoff.py`

**Files:**
- Create: `scripts/backtest_wyckoff.py`

**Interfaces:**
- Consumes: `analyze_wyckoff_structure_from_data(data: pd.DataFrame, curr_date: str, look_back_days: int = 504) -> dict[str, Any]` from `tradingagents.dataflows.wyckoff_bias` (Task 1's `vsa_confidence_delta` field included); `load_ohlcv(symbol: str, curr_date: str) -> pd.DataFrame` from `tradingagents.dataflows.stockstats_utils` (same signature `backtest_chart_patterns.py` already uses).
- Produces: a standalone CLI script, no importable symbols other tasks depend on.

- [ ] **Step 1: Write the script**

Create `scripts/backtest_wyckoff.py`:

```python
"""Walk-forward hit-rate check for the Wyckoff structure module.

Not a trading backtest — no position sizing, execution, or P&L. It answers a
narrower question: when analyze_wyckoff_structure_from_data reports a
confirmed (Phase D/E) directional read as of some historical date, how often
does price actually move in that direction over the next N trading days?
Use this to sanity check (and eventually manually calibrate) DOMINANT_WEIGHT,
the confidence formula, and the VSA constants in
tradingagents/dataflows/wyckoff_bias.py and wyckoff_vsa*.py — this script
does not tune anything itself.

Usage:
    python scripts/backtest_wyckoff.py AAPL MSFT NVDA \
        --start 2023-01-01 --end 2026-01-01 --step 5 --holding-days 20
"""

from __future__ import annotations

import argparse
from collections import defaultdict

import pandas as pd

from tradingagents.dataflows.stockstats_utils import load_ohlcv
from tradingagents.dataflows.wyckoff_bias import analyze_wyckoff_structure_from_data


def _walk_dates(df: pd.DataFrame, step: int) -> list[pd.Timestamp]:
    """Sample one date every `step` bars, skipping the initial warm-up window."""
    return list(df["Date"].iloc[60::step])


def _forward_return(df: pd.DataFrame, as_of: pd.Timestamp, holding_days: int) -> float | None:
    matches = df.index[df["Date"] == as_of]
    if not len(matches):
        return None
    start = matches[0]
    target = start + holding_days
    if target >= len(df):
        return None
    entry = float(df["Close"].iloc[start])
    exit_price = float(df["Close"].iloc[target])
    return (exit_price - entry) / entry


def _direction_hit(phase_bias: str, forward_return: float) -> bool | None:
    if phase_bias == "bullish":
        return forward_return > 0
    if phase_bias == "bearish":
        return forward_return < 0
    return None


def _vsa_effect(result: dict) -> str:
    delta = result.get("vsa_confidence_delta")
    if not delta:
        return "none"
    return "positive" if delta > 0 else "negative"


def backtest_symbol(
    symbol: str, start: str, end: str, step: int, holding_days: int, stats: dict
) -> None:
    full = load_ohlcv(symbol, end)
    full = full[full["Date"] >= pd.Timestamp(start)].reset_index(drop=True)
    if len(full) < 80:
        print(f"{symbol}: not enough history in range, skipping")
        return

    seen: set[tuple] = set()
    for as_of in _walk_dates(full, step):
        as_of_str = as_of.strftime("%Y-%m-%d")
        window = full[full["Date"] <= as_of]
        try:
            result = analyze_wyckoff_structure_from_data(window, as_of_str)
        except ValueError:
            continue

        if result["trading_range"]["status"] != "confirmed":
            continue
        if result["phase_bias"] == "neutral":
            continue

        key = (result["phase_bias"], result["current_phase"], result["trading_range"]["start_date"])
        if key in seen:
            continue
        seen.add(key)

        forward = _forward_return(full, as_of, holding_days)
        if forward is None:
            continue
        hit = _direction_hit(result["phase_bias"], forward)
        if hit is None:
            continue

        bucket = stats[(result["current_phase"], _vsa_effect(result))]
        bucket["count"] += 1
        bucket["hits"] += int(hit)
        bucket["confidence_sum"] += result["confidence"]
        bucket["return_sum"] += forward


def print_report(stats: dict) -> None:
    print(f"\n{'phase':<8}{'vsa_effect':<12}{'n':>5}{'hit_rate':>10}{'avg_conf':>10}{'avg_fwd_ret':>13}")
    for (phase, vsa_effect), bucket in sorted(stats.items()):
        n = bucket["count"]
        if n == 0:
            continue
        print(
            f"{phase:<8}{vsa_effect:<12}{n:>5}"
            f"{bucket['hits'] / n:>10.1%}{bucket['confidence_sum'] / n:>10.2f}"
            f"{bucket['return_sum'] / n:>13.2%}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbols", nargs="+")
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end", default=pd.Timestamp.today().strftime("%Y-%m-%d"))
    parser.add_argument("--step", type=int, default=5, help="business days between walk-forward checks")
    parser.add_argument("--holding-days", type=int, default=20)
    args = parser.parse_args()

    stats: dict = defaultdict(lambda: {"count": 0, "hits": 0, "confidence_sum": 0.0, "return_sum": 0.0})
    for symbol in args.symbols:
        print(f"Backtesting {symbol}...")
        backtest_symbol(symbol, args.start, args.end, args.step, args.holding_days, stats)

    print_report(stats)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Count lines and confirm the 150-line cap**

Run: `wc -l scripts/backtest_wyckoff.py`
Expected: `<= 150`. If over, move `print_report` and the `_vsa_effect`/`_direction_hit`/`_forward_return` helpers into a new `scripts/backtest_wyckoff_report.py` and import them, keeping `backtest_symbol`/`main` in the primary file.

- [ ] **Step 3: Ruff check**

Run: `ruff check scripts/backtest_wyckoff.py`
Expected: no errors.

- [ ] **Step 4: Smoke-run against real tickers**

Run: `python scripts/backtest_wyckoff.py AAPL MSFT --start 2023-01-01 --end 2026-01-01`
Expected: completes without a traceback; prints `Backtesting AAPL...` / `Backtesting MSFT...` followed by either a report table with at least one row, or no rows if neither symbol produced a confirmed Phase D/E read in range (both are acceptable outcomes — the goal is "runs cleanly against live data," not "guaranteed to find a hit").

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest_wyckoff.py
git commit -m "feat(wyckoff): add walk-forward calibration hit-rate report script"
```

---

## Acceptance Criteria (from spec)

- `scripts/backtest_wyckoff.py` runs end-to-end against real tickers and produces a hit-rate table bucketed by `(current_phase, vsa_effect)`.
- No detection/scoring logic in `wyckoff_range.py`/`wyckoff_accumulation.py`/`wyckoff_distribution.py`/`wyckoff_vsa*.py` changes.
- `wyckoff_bias.py`'s new field is additive; existing Wyckoff/market-analyst tests still pass unmodified.
- No future-data leakage: each walk-forward window only includes bars up to `as_of`.

> This module is for research and analysis support only; it does not constitute investment advice and does not place trades.
