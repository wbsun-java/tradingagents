# O'Neil CANSLIM Cup-with-Handle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: This plan is executed via the
> project's `codex-delegate` skill (stage 3 of the Claude-architect workflow,
> see `docs/superpowers/specs/2026-07-06-codex-delegate-workflow-design.md`),
> not `superpowers:subagent-driven-development` or `superpowers:executing-plans`.
> Each task below carries its own verification command per `codex-delegate`'s
> precondition. After all tasks pass, `antigravity-verify` (stage 4) runs once
> for the whole feature, covering the two scenarios in Task 6's "Stage 4
> scenarios" note.

**Goal:** Add deterministic cup-with-handle pattern detection (William O'Neil
/ CANSLIM) to the Market Analyst, ranked as a secondary technical anchor below
Wyckoff and above chart patterns/trend template/indicators, plus an additive
relative-strength score in the existing Minervini trend template.

**Architecture:** Four new small modules under `tradingagents/dataflows/`
(`oneil_cup.py`, `oneil_handle.py`, `oneil_breakout.py`, `oneil_bias.py`) mirror
the existing Wyckoff module split (`wyckoff_range.py` /
`wyckoff_events.py` / `wyckoff_accumulation.py` / `wyckoff_distribution.py` /
`wyckoff_bias.py`) — one file per responsibility, each reusing
`chart_patterns.py`'s `find_pivots`. A new tool wrapper
(`oneil_tools.py`) exposes `get_oneil_setup`, wired into the Market Analyst
next to the existing Wyckoff/chart-pattern/trend-template tools. A small
additive change to `trend_template.py` adds a quarter-weighted `rs_score`.

**Tech Stack:** Python, `pandas` (already a dependency), `pytest` +
`pytest.mark.unit`, synthetic OHLCV fixtures (no network calls).

## Global Constraints

- Every newly created file must be at most 150 lines (repo-wide convention).
  `ONEIL_CANSLIM_ANALYSIS_PLAN.md`'s File Structure section originally grouped
  cup+handle detection into one `oneil_cup_handle.py` and
  breakout+status+confidence+JSON-assembly into one `oneil_breakout.py`.
  Writing out the real implementation showed the first file would run ~200
  lines and the second ~155 — both over the cap. This plan instead splits
  into four files (`oneil_cup.py`, `oneil_handle.py`, `oneil_breakout.py`,
  `oneil_bias.py`), each under 150 lines, mirroring the Wyckoff module's
  five-file split. This is a file-layout refinement only; the detection
  algorithm, JSON shape, and priority rule are unchanged from the approved
  spec. Update the spec's File Structure section to match once this plan
  lands (Task 6 includes this).
- Do not modify any file that came from the original upstream repository
  without explicit approval. `market_analyst.py`, `trading_graph.py`, and
  `agent_utils.py` are already project-customized (they wire in
  `get_chart_patterns`/`get_trend_template`/`get_wyckoff_structure` today), so
  editing them further to add `get_oneil_setup` following the same pattern is
  in scope, not an upstream-file change requiring separate approval.
- Route all market-data access through `tradingagents/dataflows/` — every new
  module loads OHLCV via `load_ohlcv` (`tradingagents/dataflows/stockstats_utils.py`),
  never a vendor call directly.
- Preserve typed `AgentState` keys — this feature does not add or remove any
  `AgentState` key.
- `ruff check` must be clean under the repo's config (`E, W, F, I, B, UP, C4, SIM`
  selected, `E501` ignored).
- No task in this plan commits anything. `codex-delegate` does not commit as
  part of its own procedure; the actual `git commit` waits for the user's
  explicit approval, same as `ONEIL_CANSLIM_ANALYSIS_PLAN.md` itself.
- Tasks 2-5 must run in order: `oneil_handle.py` imports from `oneil_cup.py`,
  `oneil_breakout.py` imports from both, `oneil_bias.py` imports from all
  three plus `trend_template.py`'s new `relative_strength_score`.

---

### Task 1: `trend_template.py` — add `rs_score`

**Files:**
- Modify: `tradingagents/dataflows/trend_template.py`
- Test: `tests/test_trend_template.py` (existing file, add cases)

**Interfaces:**
- Consumes: nothing new (uses `pandas`, already imported in the file).
- Produces: `relative_strength_score(df: pd.DataFrame, benchmark_df: pd.DataFrame) -> float | None`,
  a module-level function. `evaluate_trend_template`'s returned `values` dict
  gains a new key `"rs_score"`. Task 5's `oneil_bias.py` imports
  `relative_strength_score` directly from this module.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_trend_template.py` (after the existing imports, no
change to any existing test):

```python
def _ramp_with_recent_surge(length: int = 260, base_end: float = 130.0, surge_to: float = 169.0) -> pd.Series:
    """A steady ramp to base_end, then a strong surge in the final quarter."""
    closes = pd.Series(_ramp_ohlcv(100.0, base_end, length - 63)["Close"].tolist() + [None] * 63)
    closes.iloc[-63:] = pd.Series(
        [closes.iloc[-64] * (1.0 + (surge_to / base_end - 1.0) * i / 62) for i in range(63)]
    ).to_numpy()
    return closes


def _series_to_df(closes: pd.Series, length: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": pd.bdate_range("2024-01-02", periods=length),
            "Open": closes,
            "High": closes + 0.5,
            "Low": closes - 0.5,
            "Close": closes,
            "Volume": [1_000_000.0] * length,
        }
    )


@pytest.mark.unit
def test_rs_score_weights_the_most_recent_quarter_more_heavily():
    length = 260
    benchmark = _ramp_ohlcv(100.0, 130.0, length)  # steady benchmark uptrend, no surge

    recent_surge_closes = _ramp_with_recent_surge(length, base_end=130.0, surge_to=169.0)
    recent_df = _series_to_df(recent_surge_closes, length)

    # Same total outperformance, but the surge happened a year-plus-a-quarter
    # ago instead of in the most recent quarter -- construct by taking the
    # recent-surge series and reversing which segment holds the big move.
    old_surge_closes = pd.Series(recent_surge_closes.tolist())
    # Swap the first 63 bars' growth rate with the last 63 bars' growth rate
    # by re-deriving from benchmark with the surge applied at the start
    # instead of the end.
    base = 100.0
    first_quarter_target = base * (169.0 / 130.0)
    old_segment = [base + (first_quarter_target - base) * i / 62 for i in range(63)]
    remainder = [old_segment[-1] * (1.0 + 0.30 * i / (length - 63 - 1)) for i in range(length - 63)]
    old_df = _series_to_df(pd.Series(old_segment + remainder), length)

    recent_result = evaluate_trend_template(recent_df, benchmark)
    old_result = evaluate_trend_template(old_df, benchmark)

    assert recent_result.values["rs_score"] is not None
    assert old_result.values["rs_score"] is not None
    assert recent_result.values["rs_score"] > old_result.values["rs_score"]


@pytest.mark.unit
def test_rs_score_is_none_with_less_than_a_year_of_history():
    stock = _ramp_ohlcv(50.0, 150.0, 200)  # under the 253-bar requirement
    benchmark = _ramp_ohlcv(50.0, 80.0, 200)

    result = evaluate_trend_template(stock, benchmark)

    assert result.values["rs_score"] is None


@pytest.mark.unit
def test_existing_relative_strength_criterion_unaffected_by_rs_score():
    stock = _ramp_ohlcv(50.0, 150.0, 260)
    benchmark = _ramp_ohlcv(50.0, 80.0, 260)

    result = evaluate_trend_template(stock, benchmark)

    # Unchanged from before rs_score existed.
    assert result.criteria["relative_strength_at_new_high"] is True
    assert result.passed_count == 8
    assert result.stage_2_uptrend
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest -q tests/test_trend_template.py`
Expected: FAIL on the three new tests with `KeyError: 'rs_score'` (the key
doesn't exist in `values` yet); the five pre-existing tests still pass.

- [ ] **Step 3: Write the implementation**

In `tradingagents/dataflows/trend_template.py`, add after the
`_MONTH_BARS = 21` line:

```python
_QUARTER_BARS = 63  # ~1 trading quarter
_QUARTER_WEIGHTS = (0.4, 0.2, 0.2, 0.2)  # most recent quarter weighted heaviest (O'Neil/IBD style)


def relative_strength_score(df: pd.DataFrame, benchmark_df: pd.DataFrame) -> float | None:
    """Quarter-weighted excess return vs. benchmark; most recent quarter weighted heaviest.

    Additive alongside `_relative_strength_at_new_high`'s boolean criterion --
    does not change that criterion's, `passed_count`'s, or `stage_2_uptrend`'s
    behavior. Returns None when there isn't a full year of aligned history.
    """
    merged = pd.merge(df[["Date", "Close"]], benchmark_df[["Date", "Close"]], on="Date", suffixes=("", "_bm"))
    needed = _QUARTER_BARS * len(_QUARTER_WEIGHTS) + 1
    if len(merged) < needed:
        return None
    closes = merged["Close"].to_numpy()
    bm_closes = merged["Close_bm"].to_numpy()
    score = 0.0
    for i, weight in enumerate(_QUARTER_WEIGHTS):
        end = len(closes) - 1 - i * _QUARTER_BARS
        start = end - _QUARTER_BARS
        stock_ret = closes[end] / closes[start] - 1.0
        bm_ret = bm_closes[end] / bm_closes[start] - 1.0
        score += weight * (stock_ret - bm_ret)
    return round(float(score), 4)
```

Then in `evaluate_trend_template`, change the `values` dict (currently ending
with `"pct_below_52w_high"`) to add one more key:

```python
    values = {
        "price": price,
        "sma_50": sma50_now,
        "sma_150": sma150_now,
        "sma_200": sma200_now,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "pct_above_52w_low": round((price / low_52w - 1) * 100, 2),
        "pct_below_52w_high": round((1 - price / high_52w) * 100, 2),
        "rs_score": relative_strength_score(df, benchmark_df) if benchmark_df is not None else None,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest -q tests/test_trend_template.py`
Expected: PASS (8 passed).

- [ ] **Step 5: Lint**

Run: `ruff check tradingagents/dataflows/trend_template.py tests/test_trend_template.py`
Expected: clean.

Do not commit.

---

### Task 2: `oneil_cup.py` — cup detection

**Files:**
- Create: `tradingagents/dataflows/oneil_cup.py`
- Test: `tests/test_oneil_cup.py`

**Interfaces:**
- Consumes: `find_pivots(df, span) -> list[Pivot]` from
  `tradingagents/dataflows/chart_patterns.py` (existing, unmodified). `Pivot`
  has fields `index: int`, `date: str`, `price: float`, `kind: "high" | "low"`.
- Produces: `prepare_ohlcv(data, curr_date, look_back_days) -> pd.DataFrame`,
  `atr(df, period=14) -> pd.Series`, `volume_ratio(df, index, window=20) -> float | None`,
  `CupCandidate` dataclass with fields `left_high_index: int, left_high_date: str,
  left_high_price: float, low_date: str, low_price: float, right_high_index: int,
  right_high_date: str, depth_pct: float, duration_days: int, evidence: list[str]`,
  and `detect_cup(df, atr_value, pivot_span=3) -> CupCandidate | None`. Tasks 3,
  4, and 5 import `CupCandidate`, `atr`, `prepare_ohlcv`, `volume_ratio`, and
  `detect_cup` from this module by these exact names.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_oneil_cup.py`:

```python
"""Unit tests for O'Neil cup detection, using synthetic OHLCV."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.oneil_cup import atr, detect_cup, prepare_ohlcv


def _cup(
    prior_up_len: int = 50,
    decline_len: int = 45,
    base_len: int = 20,
    recover_len: int = 45,
    up_gain: float = 60.0,
    depth_pct: float = 0.20,
    start_price: float = 50.0,
    extra_flat: int = 30,
) -> pd.DataFrame:
    closes: list[float] = []
    vols: list[float] = []
    for i in range(prior_up_len):
        closes.append(start_price + up_gain * i / (prior_up_len - 1))
        vols.append(1_000_000.0)
    left_high = closes[-1]
    low_price = left_high * (1 - depth_pct)
    # Decline starts at t>0 so the peak bar stays a strict, unique local max
    # (a flat first step would tie with the peak and defeat find_pivots'
    # uniqueness check).
    for i in range(decline_len):
        t = (i + 1) / decline_len
        ease = (1 - np.cos(t * np.pi)) / 2
        closes.append(left_high - (left_high - low_price) * ease)
        vols.append(1_000_000.0)
    rng = np.random.default_rng(42)
    for _ in range(base_len):
        closes.append(low_price + rng.uniform(-0.3, 0.3))
        vols.append(900_000.0)
    for i in range(recover_len):
        t = i / (recover_len - 1)
        ease = (1 - np.cos(t * np.pi)) / 2
        closes.append(low_price + (left_high - low_price) * ease)
        vols.append(1_000_000.0)
    for _ in range(extra_flat):
        closes.append(closes[-1])
        vols.append(1_000_000.0)
    n = len(closes)
    dates = pd.bdate_range("2024-01-02", periods=n)
    closes_arr = np.array(closes)
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": closes_arr,
            "High": closes_arr + 0.5,
            "Low": closes_arr - 0.5,
            "Close": closes_arr,
            "Volume": vols,
        }
    )


def _v_shape() -> pd.DataFrame:
    prior_up_len, drop_len, recover_len, post_len = 50, 3, 3, 100
    start_price, up_gain, depth_pct = 50.0, 60.0, 0.20
    closes, vols = [], []
    for i in range(prior_up_len):
        closes.append(start_price + up_gain * i / (prior_up_len - 1))
        vols.append(1_000_000.0)
    left_high = closes[-1]
    low_price = left_high * (1 - depth_pct)
    for i in range(drop_len):
        t = (i + 1) / drop_len
        closes.append(left_high - (left_high - low_price) * t)
        vols.append(1_000_000.0)
    for i in range(recover_len):
        t = (i + 1) / recover_len
        closes.append(low_price + (left_high - low_price) * t)
        vols.append(1_000_000.0)
    for _ in range(post_len):
        closes.append(left_high)
        vols.append(1_000_000.0)
    n = len(closes)
    dates = pd.bdate_range("2024-01-02", periods=n)
    closes_arr = np.array(closes)
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": closes_arr,
            "High": closes_arr + 0.5,
            "Low": closes_arr - 0.5,
            "Close": closes_arr,
            "Volume": vols,
        }
    )


def _prepared(df: pd.DataFrame):
    prepared = prepare_ohlcv(df, df["Date"].iloc[-1].strftime("%Y-%m-%d"), look_back_days=420)
    return prepared, float(atr(prepared).iloc[-1])


@pytest.mark.unit
def test_detects_textbook_cup_with_correct_bounds():
    prepared, atr_value = _prepared(_cup())

    cup = detect_cup(prepared, atr_value)

    assert cup is not None
    assert cup.left_high_date == "2024-03-11"
    assert cup.left_high_price == pytest.approx(110.5, abs=0.01)
    assert cup.low_date == "2024-06-06"
    assert cup.low_price == pytest.approx(87.24, abs=0.5)
    assert cup.right_high_date == "2024-08-06"
    assert 15.0 <= cup.depth_pct * 100 <= 25.0
    assert 90 <= cup.duration_days <= 120


@pytest.mark.unit
def test_v_shape_does_not_qualify_as_cup():
    prepared, atr_value = _prepared(_v_shape())

    assert detect_cup(prepared, atr_value) is None


@pytest.mark.unit
def test_no_prior_uptrend_does_not_qualify_as_cup():
    prepared, atr_value = _prepared(_cup(up_gain=0.0))

    assert detect_cup(prepared, atr_value) is None


@pytest.mark.unit
def test_depth_too_shallow_does_not_qualify_as_cup():
    prepared, atr_value = _prepared(_cup(depth_pct=0.03))

    assert detect_cup(prepared, atr_value) is None


@pytest.mark.unit
def test_depth_too_deep_does_not_qualify_as_cup():
    prepared, atr_value = _prepared(_cup(depth_pct=0.65))

    assert detect_cup(prepared, atr_value) is None


@pytest.mark.unit
def test_prepare_ohlcv_drops_future_rows_past_curr_date():
    df = _cup()
    cutoff_date = df["Date"].iloc[80].strftime("%Y-%m-%d")

    prepared = prepare_ohlcv(df, cutoff_date, look_back_days=420)

    assert prepared["Date"].max() <= pd.Timestamp(cutoff_date)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest -q tests/test_oneil_cup.py`
Expected: FAIL / collection error — `tradingagents/dataflows/oneil_cup.py`
does not exist yet (`ModuleNotFoundError`).

- [ ] **Step 3: Write the implementation**

Create `tradingagents/dataflows/oneil_cup.py`:

```python
"""Cup detection for O'Neil's cup-with-handle pattern.

Finds a rounded consolidation base that follows a meaningful prior uptrend,
using the same centered swing-pivot logic as chart_patterns.py and
wyckoff_range.py. See ONEIL_CANSLIM_ANALYSIS_PLAN.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from tradingagents.dataflows.chart_patterns import find_pivots

PRIOR_UPTREND_LOOKBACK = 40
PRIOR_UPTREND_MIN_ATR = 2.0
MIN_CUP_DAYS = 25
MAX_CUP_DAYS = 325
MIN_DEPTH_ATR = 3.0
MIN_DEPTH_PCT = 0.08
MAX_DEPTH_PCT = 0.50
RECOVERY_BUFFER_ATR = 1.0
ROUNDING_WINDOW = 5
ROUNDING_TOLERANCE_ATR = 1.5
ROUNDING_MIN_BARS = 3


@dataclass
class CupCandidate:
    left_high_index: int
    left_high_date: str
    left_high_price: float
    low_date: str
    low_price: float
    right_high_index: int
    right_high_date: str
    depth_pct: float
    duration_days: int
    evidence: list[str] = field(default_factory=list)


def prepare_ohlcv(data: pd.DataFrame, curr_date: str, look_back_days: int) -> pd.DataFrame:
    required = {"Date", "Open", "High", "Low", "Close", "Volume"}
    df = data.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    for column in required - {"Date"}:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = (
        df.dropna(subset=["Date", "High", "Low", "Close"])
        .loc[lambda frame: frame["Date"] <= pd.Timestamp(curr_date)]
        .sort_values("Date")
        .drop_duplicates("Date", keep="last")
        .tail(max(80, int(look_back_days)))
        .reset_index(drop=True)
    )
    if len(df) < 80:
        raise ValueError("At least 80 OHLCV rows are required for O'Neil cup-with-handle analysis.")
    return df


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    previous_close = df["Close"].shift(1)
    true_range = pd.concat(
        [df["High"] - df["Low"], (df["High"] - previous_close).abs(), (df["Low"] - previous_close).abs()],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(period, min_periods=1).mean()


def volume_ratio(df: pd.DataFrame, index: int, window: int = 20) -> float | None:
    if index < 1 or pd.isna(df.at[index, "Volume"]):
        return None
    baseline = pd.to_numeric(df["Volume"].iloc[max(0, index - window):index], errors="coerce").mean()
    return float(df.at[index, "Volume"]) / float(baseline) if baseline else None


def _has_prior_uptrend(df: pd.DataFrame, index: int, atr_value: float) -> bool:
    lookback = max(0, index - PRIOR_UPTREND_LOOKBACK)
    if index <= lookback:
        return False
    change = float(df.at[index, "Close"]) - float(df.at[lookback, "Close"])
    return change >= atr_value * PRIOR_UPTREND_MIN_ATR


def _has_rounding_base(df: pd.DataFrame, low_index: int, low_price: float, atr_value: float, lo_bound: int, hi_bound: int) -> bool:
    lo = max(lo_bound + 1, low_index - ROUNDING_WINDOW)
    hi = min(hi_bound - 1, low_index + ROUNDING_WINDOW)
    if hi < lo:
        return False
    window = df.iloc[lo:hi + 1]
    near_low = (window["Close"] - low_price).abs() <= atr_value * ROUNDING_TOLERANCE_ATR
    return int(near_low.sum()) >= ROUNDING_MIN_BARS


def detect_cup(df: pd.DataFrame, atr_value: float, pivot_span: int = 3) -> CupCandidate | None:
    """Find the most recent complete cup: prior uptrend, rounded decline to a
    low, and recovery back near the left-side high, within adaptive bounds."""
    highs = [p for p in find_pivots(df, pivot_span) if p.kind == "high"]
    candidates: list[CupCandidate] = []
    for lh in highs:
        if not _has_prior_uptrend(df, lh.index, atr_value):
            continue
        window_end = min(len(df) - 1, lh.index + MAX_CUP_DAYS)
        if window_end - lh.index < MIN_CUP_DAYS:
            continue
        low_search = df.iloc[lh.index + 1: window_end + 1]
        if low_search.empty:
            continue
        low_index = int(low_search["Low"].idxmin())
        low_price = float(df.at[low_index, "Low"])
        depth_abs = lh.price - low_price
        depth_pct = depth_abs / lh.price if lh.price else 0.0
        if depth_abs < atr_value * MIN_DEPTH_ATR or not (MIN_DEPTH_PCT <= depth_pct <= MAX_DEPTH_PCT):
            continue
        buffer = atr_value * RECOVERY_BUFFER_ATR
        right_high_index = next(
            (i for i in range(low_index + 1, window_end + 1) if float(df.at[i, "Close"]) >= lh.price - buffer), None
        )
        if right_high_index is None:
            continue
        duration_days = right_high_index - lh.index
        if not (MIN_CUP_DAYS <= duration_days <= MAX_CUP_DAYS):
            continue
        if not _has_rounding_base(df, low_index, low_price, atr_value, lh.index, right_high_index):
            continue
        low_date = df.at[low_index, "Date"].strftime("%Y-%m-%d")
        right_high_date = df.at[right_high_index, "Date"].strftime("%Y-%m-%d")
        candidates.append(CupCandidate(
            left_high_index=lh.index, left_high_date=lh.date, left_high_price=lh.price,
            low_date=low_date, low_price=low_price,
            right_high_index=right_high_index, right_high_date=right_high_date,
            depth_pct=depth_pct, duration_days=duration_days,
            evidence=[
                f"Prior uptrend confirmed into {lh.date} at {lh.price:.2f}.",
                f"Cup declined {depth_pct:.1%} to {low_price:.2f} on {low_date}, basing near the low "
                f"before recovering to {lh.price:.2f} by {right_high_date} over {duration_days} trading days.",
            ],
        ))
    if not candidates:
        return None
    return max(candidates, key=lambda c: c.right_high_index)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest -q tests/test_oneil_cup.py`
Expected: PASS (6 passed).

- [ ] **Step 5: Lint and line-count check**

Run: `ruff check tradingagents/dataflows/oneil_cup.py tests/test_oneil_cup.py`
Expected: clean.
Run: `wc -l tradingagents/dataflows/oneil_cup.py`
Expected: output `142` (or under 150 — if your exact formatting differs
slightly, it must stay under 150; do not let this file grow past it).

Do not commit.

---

### Task 3: `oneil_handle.py` — handle detection

**Files:**
- Create: `tradingagents/dataflows/oneil_handle.py`
- Test: `tests/test_oneil_handle.py`

**Interfaces:**
- Consumes: `find_pivots` from `chart_patterns.py`; `CupCandidate`, `atr`,
  `prepare_ohlcv` from `tradingagents/dataflows/oneil_cup.py` (Task 2, exact
  names as produced there).
- Produces: `HandleCandidate` dataclass with fields `start_date: str,
  end_index: int, end_date: str, low_price: float,
  volume_ratio_vs_cup: float | None, duration_days: int, valid: bool,
  evidence: list[str]`, and `detect_handle(df, cup, atr_value, pivot_span=3) -> HandleCandidate | None`.
  Tasks 4 and 5 import `HandleCandidate` and `detect_handle` from this module
  by these exact names.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_oneil_handle.py`:

```python
"""Unit tests for O'Neil handle detection, using synthetic OHLCV."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.oneil_cup import atr, detect_cup, prepare_ohlcv
from tradingagents.dataflows.oneil_handle import detect_handle


def _cup_then_handle(handle_depth_pct: float = 0.06, handle_vol_mult: float = 0.6, break_lower_half: bool = False) -> pd.DataFrame:
    prior_up_len, decline_len, base_len, recover_len, handle_len = 50, 45, 20, 45, 13
    start_price, up_gain, depth_pct = 50.0, 60.0, 0.20
    closes: list[float] = []
    vols: list[float] = []
    for i in range(prior_up_len):
        closes.append(start_price + up_gain * i / (prior_up_len - 1))
        vols.append(1_000_000.0)
    left_high = closes[-1]
    low_price = left_high * (1 - depth_pct)
    for i in range(decline_len):
        t = (i + 1) / decline_len
        ease = (1 - np.cos(t * np.pi)) / 2
        closes.append(left_high - (left_high - low_price) * ease)
        vols.append(1_000_000.0)
    rng = np.random.default_rng(42)
    for _ in range(base_len):
        closes.append(low_price + rng.uniform(-0.3, 0.3))
        vols.append(900_000.0)
    for i in range(recover_len):
        t = i / (recover_len - 1)
        ease = (1 - np.cos(t * np.pi)) / 2
        closes.append(low_price + (left_high - low_price) * ease)
        vols.append(1_000_000.0)
    right_high = closes[-1]
    handle_low = right_high * (1 - handle_depth_pct)
    if break_lower_half:
        midpoint = (left_high + low_price) / 2
        handle_low = midpoint - 5.0
    for i in range(handle_len):
        t = i / (handle_len - 1)
        depth_ease = np.sin(t * np.pi)
        closes.append(right_high - (right_high - handle_low) * depth_ease)
        vols.append(1_000_000.0 * handle_vol_mult)
    for _ in range(15):
        closes.append(closes[-1])
        vols.append(1_000_000.0)
    n = len(closes)
    dates = pd.bdate_range("2024-01-02", periods=n)
    closes_arr = np.array(closes)
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": closes_arr,
            "High": closes_arr + 0.5,
            "Low": closes_arr - 0.5,
            "Close": closes_arr,
            "Volume": vols,
        }
    )


def _prepared_cup(df: pd.DataFrame):
    prepared = prepare_ohlcv(df, df["Date"].iloc[-1].strftime("%Y-%m-%d"), look_back_days=420)
    atr_value = float(atr(prepared).iloc[-1])
    cup = detect_cup(prepared, atr_value)
    assert cup is not None, "fixture must produce a valid cup for these handle tests"
    return prepared, atr_value, cup


@pytest.mark.unit
def test_detects_valid_handle_in_upper_half_with_volume_dry_up():
    prepared, atr_value, cup = _prepared_cup(_cup_then_handle())

    handle = detect_handle(prepared, cup, atr_value)

    assert handle is not None
    assert handle.valid is True
    midpoint = (cup.left_high_price + cup.low_price) / 2.0
    assert handle.low_price >= midpoint
    assert handle.volume_ratio_vs_cup is not None
    assert handle.volume_ratio_vs_cup < 1.0
    assert handle.duration_days < cup.duration_days


@pytest.mark.unit
def test_handle_dropping_into_lower_half_is_invalid():
    prepared, atr_value, cup = _prepared_cup(_cup_then_handle(break_lower_half=True))

    handle = detect_handle(prepared, cup, atr_value)

    assert handle is not None
    assert handle.valid is False
    assert "lower half" in handle.evidence[0]


@pytest.mark.unit
def test_handle_without_volume_dry_up_is_invalid():
    prepared, atr_value, cup = _prepared_cup(_cup_then_handle(handle_vol_mult=1.5))

    handle = detect_handle(prepared, cup, atr_value)

    assert handle is not None
    assert handle.valid is False
    assert any("did not dry up" in e for e in handle.evidence)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest -q tests/test_oneil_handle.py`
Expected: FAIL / collection error — `tradingagents/dataflows/oneil_handle.py`
does not exist yet.

- [ ] **Step 3: Write the implementation**

Create `tradingagents/dataflows/oneil_handle.py`:

```python
"""Handle detection for O'Neil's cup-with-handle pattern.

Finds the handle's earliest confirmed trough after a completed cup, requiring
it to stay in the cup's upper half and show lower volume than the cup itself
("volume dry-up"). See ONEIL_CANSLIM_ANALYSIS_PLAN.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from tradingagents.dataflows.chart_patterns import find_pivots
from tradingagents.dataflows.oneil_cup import CupCandidate

MIN_HANDLE_DAYS = 5
MAX_HANDLE_DAYS = 25


@dataclass
class HandleCandidate:
    start_date: str
    end_index: int
    end_date: str
    low_price: float
    volume_ratio_vs_cup: float | None
    duration_days: int
    valid: bool
    evidence: list[str] = field(default_factory=list)


def detect_handle(df: pd.DataFrame, cup: CupCandidate, atr_value: float, pivot_span: int = 3) -> HandleCandidate | None:
    """Find the handle's earliest confirmed trough after the cup completes.

    Uses the earliest confirmed swing-low pivot after the cup, not the lowest
    close in the whole search window -- a later, deeper dip (e.g. a failed
    breakout reversing hard after the handle already completed) must not be
    mistaken for the handle's own low.
    """
    start = cup.right_high_index + 1
    last = len(df) - 1
    if last < start:
        return None
    window_end = min(last, cup.right_high_index + MAX_HANDLE_DAYS)
    low_pivots = [p for p in find_pivots(df, pivot_span) if p.kind == "low" and start <= p.index <= window_end]
    if not low_pivots:
        return None
    trough = min(low_pivots, key=lambda p: p.index)
    duration_days = trough.index - start + 1
    if duration_days < MIN_HANDLE_DAYS:
        return None

    window = df.iloc[start:trough.index + 1]
    cup_window = df.iloc[cup.left_high_index:cup.right_high_index + 1]
    cup_avg_vol = float(pd.to_numeric(cup_window["Volume"], errors="coerce").mean())
    handle_avg_vol = float(pd.to_numeric(window["Volume"], errors="coerce").mean())
    volume_ratio_vs_cup = handle_avg_vol / cup_avg_vol if cup_avg_vol else None
    midpoint = (cup.left_high_price + cup.low_price) / 2.0

    evidence: list[str] = []
    valid = True
    if trough.price < midpoint:
        valid = False
        evidence.append(f"Handle low of {trough.price:.2f} dropped into the cup's lower half (below midpoint {midpoint:.2f}), invalidating the base.")
    if volume_ratio_vs_cup is not None and volume_ratio_vs_cup >= 1.0:
        valid = False
        evidence.append(f"Handle volume ({volume_ratio_vs_cup:.2f}x the cup's average) did not dry up relative to the cup.")
    if duration_days >= cup.duration_days:
        valid = False
        evidence.append(f"Handle duration of {duration_days} days is not shorter than the {cup.duration_days}-day cup.")
    if valid:
        evidence.append(
            f"Handle formed in the cup's upper half (low {trough.price:.2f} above midpoint {midpoint:.2f}) "
            f"on {volume_ratio_vs_cup:.2f}x the cup's volume over {duration_days} days."
        )
    return HandleCandidate(
        start_date=df.at[start, "Date"].strftime("%Y-%m-%d"),
        end_index=trough.index, end_date=trough.date, low_price=trough.price,
        volume_ratio_vs_cup=volume_ratio_vs_cup, duration_days=duration_days,
        valid=valid, evidence=evidence,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest -q tests/test_oneil_handle.py`
Expected: PASS (3 passed).

- [ ] **Step 5: Lint and line-count check**

Run: `ruff check tradingagents/dataflows/oneil_handle.py tests/test_oneil_handle.py`
Expected: clean.
Run: `wc -l tradingagents/dataflows/oneil_handle.py`
Expected: under 150 (reference implementation is 82 lines).

Do not commit.

---

### Task 4: `oneil_breakout.py` — breakout confirmation, status, confidence

**Files:**
- Create: `tradingagents/dataflows/oneil_breakout.py`
- Test: `tests/test_oneil_breakout.py`

**Interfaces:**
- Consumes: `CupCandidate`, `volume_ratio` from `oneil_cup.py` (Task 2);
  `HandleCandidate` from `oneil_handle.py` (Task 3).
- Produces: `BreakoutEvent` dataclass with fields `index: int, date: str,
  pivot_price: float, close: float, volume_ratio: float, volume_confirmed: bool`;
  `find_breakout(df, cup, handle, atr_value) -> BreakoutEvent | None`;
  `determine_status(cup, handle, breakout, df, atr_value) -> Status` where
  `Status = Literal["none", "forming", "developing", "confirmed", "failed"]`;
  `compute_confidence(status, handle, breakout, rs_score) -> float`. Task 5
  imports all four of these by these exact names.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_oneil_breakout.py`:

```python
"""Unit tests for O'Neil breakout confirmation and status, using synthetic OHLCV."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.oneil_breakout import compute_confidence, determine_status, find_breakout
from tradingagents.dataflows.oneil_cup import atr, detect_cup, prepare_ohlcv
from tradingagents.dataflows.oneil_handle import detect_handle


def _full_sequence(breakout_vol_mult: float = 1.8, reverses: bool = False, no_breakout: bool = False) -> pd.DataFrame:
    prior_up_len, decline_len, base_len, recover_len, handle_len, post_len = 50, 45, 20, 45, 13, 15
    start_price, up_gain, depth_pct, handle_depth_pct = 50.0, 60.0, 0.20, 0.06
    closes: list[float] = []
    vols: list[float] = []
    for i in range(prior_up_len):
        closes.append(start_price + up_gain * i / (prior_up_len - 1))
        vols.append(1_000_000.0)
    left_high = closes[-1]
    low_price = left_high * (1 - depth_pct)
    for i in range(decline_len):
        t = (i + 1) / decline_len
        ease = (1 - np.cos(t * np.pi)) / 2
        closes.append(left_high - (left_high - low_price) * ease)
        vols.append(1_000_000.0)
    rng = np.random.default_rng(42)
    for _ in range(base_len):
        closes.append(low_price + rng.uniform(-0.3, 0.3))
        vols.append(900_000.0)
    for i in range(recover_len):
        t = i / (recover_len - 1)
        ease = (1 - np.cos(t * np.pi)) / 2
        closes.append(low_price + (left_high - low_price) * ease)
        vols.append(1_000_000.0)
    right_high = closes[-1]
    handle_low = right_high * (1 - handle_depth_pct)
    for i in range(handle_len):
        t = i / (handle_len - 1)
        depth_ease = np.sin(t * np.pi)
        closes.append(right_high - (right_high - handle_low) * depth_ease)
        vols.append(600_000.0)
    pivot = left_high
    if no_breakout:
        for _ in range(post_len):
            closes.append(closes[-1])
            vols.append(1_000_000.0)
    else:
        for i in range(post_len):
            if i == 0:
                closes.append(pivot * 1.02)
                vols.append(1_000_000.0 * breakout_vol_mult)
            elif reverses:
                closes.append(pivot * 0.94)
                vols.append(1_000_000.0)
            else:
                closes.append(pivot * (1.02 + 0.01 * i))
                vols.append(1_000_000.0)
    n = len(closes)
    dates = pd.bdate_range("2024-01-02", periods=n)
    closes_arr = np.array(closes)
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": closes_arr,
            "High": closes_arr + 0.5,
            "Low": closes_arr - 0.5,
            "Close": closes_arr,
            "Volume": vols,
        }
    )


def _prepared_cup_handle(df: pd.DataFrame):
    prepared = prepare_ohlcv(df, df["Date"].iloc[-1].strftime("%Y-%m-%d"), look_back_days=420)
    atr_value = float(atr(prepared).iloc[-1])
    cup = detect_cup(prepared, atr_value)
    assert cup is not None
    handle = detect_handle(prepared, cup, atr_value)
    assert handle is not None and handle.valid
    return prepared, atr_value, cup, handle


@pytest.mark.unit
def test_volume_confirmed_breakout_is_confirmed():
    prepared, atr_value, cup, handle = _prepared_cup_handle(_full_sequence())

    breakout = find_breakout(prepared, cup, handle, atr_value)
    status = determine_status(cup, handle, breakout, prepared, atr_value)

    assert breakout is not None
    assert breakout.volume_confirmed is True
    assert status == "confirmed"


@pytest.mark.unit
def test_low_volume_breakout_stays_developing_not_failed():
    prepared, atr_value, cup, handle = _prepared_cup_handle(_full_sequence(breakout_vol_mult=0.9))

    breakout = find_breakout(prepared, cup, handle, atr_value)
    status = determine_status(cup, handle, breakout, prepared, atr_value)

    assert breakout is not None
    assert breakout.volume_confirmed is False
    assert status == "developing"


@pytest.mark.unit
def test_confirmed_breakout_that_reverses_is_failed():
    prepared, atr_value, cup, handle = _prepared_cup_handle(_full_sequence(reverses=True))

    breakout = find_breakout(prepared, cup, handle, atr_value)
    status = determine_status(cup, handle, breakout, prepared, atr_value)

    assert status == "failed"


@pytest.mark.unit
def test_no_breakout_attempt_yet_is_developing():
    prepared, atr_value, cup, handle = _prepared_cup_handle(_full_sequence(no_breakout=True))

    breakout = find_breakout(prepared, cup, handle, atr_value)
    status = determine_status(cup, handle, breakout, prepared, atr_value)

    assert breakout is None
    assert status == "developing"


@pytest.mark.unit
def test_confidence_increases_with_stronger_breakout_volume():
    prepared, atr_value, cup, handle = _prepared_cup_handle(_full_sequence(breakout_vol_mult=1.4))
    weak_breakout = find_breakout(prepared, cup, handle, atr_value)

    prepared2, atr_value2, cup2, handle2 = _prepared_cup_handle(_full_sequence(breakout_vol_mult=3.0))
    strong_breakout = find_breakout(prepared2, cup2, handle2, atr_value2)

    weak_conf = compute_confidence("confirmed", handle, weak_breakout, None)
    strong_conf = compute_confidence("confirmed", handle2, strong_breakout, None)

    assert strong_conf > weak_conf


@pytest.mark.unit
def test_confidence_increases_with_higher_rs_score():
    prepared, atr_value, cup, handle = _prepared_cup_handle(_full_sequence())
    breakout = find_breakout(prepared, cup, handle, atr_value)

    low_rs_conf = compute_confidence("confirmed", handle, breakout, 0.01)
    high_rs_conf = compute_confidence("confirmed", handle, breakout, 0.20)

    assert high_rs_conf > low_rs_conf


@pytest.mark.unit
def test_status_is_none_with_no_cup():
    assert determine_status(None, None, None, pd.DataFrame(), 1.0) == "none"
    assert compute_confidence("none", None, None, None) == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest -q tests/test_oneil_breakout.py`
Expected: FAIL / collection error — `tradingagents/dataflows/oneil_breakout.py`
does not exist yet.

- [ ] **Step 3: Write the implementation**

Create `tradingagents/dataflows/oneil_breakout.py`:

```python
"""Breakout confirmation for O'Neil's cup-with-handle.

Requires a close above the pivot buy point (the cup's left-side high) with
volume meaningfully above average within a short confirmation window, then
derives the forming/developing/confirmed/failed status and confidence score.
See ONEIL_CANSLIM_ANALYSIS_PLAN.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from tradingagents.dataflows.oneil_cup import CupCandidate, volume_ratio
from tradingagents.dataflows.oneil_handle import HandleCandidate

BREAKOUT_BUFFER_ATR = 0.1
BREAKOUT_VOLUME_RATIO = 1.4
BREAKOUT_CONFIRM_WINDOW = 3
Status = Literal["none", "forming", "developing", "confirmed", "failed"]


@dataclass
class BreakoutEvent:
    index: int
    date: str
    pivot_price: float
    close: float
    volume_ratio: float
    volume_confirmed: bool


def find_breakout(df: pd.DataFrame, cup: CupCandidate, handle: HandleCandidate, atr_value: float) -> BreakoutEvent | None:
    buffer = atr_value * BREAKOUT_BUFFER_ATR
    start = handle.end_index + 1
    if start >= len(df):
        return None
    first_break_idx = next((i for i in range(start, len(df)) if float(df.at[i, "Close"]) > cup.left_high_price + buffer), None)
    if first_break_idx is None:
        return None
    confirm_end = min(len(df), first_break_idx + BREAKOUT_CONFIRM_WINDOW)
    confirming_idx = next(
        (i for i in range(first_break_idx, confirm_end)
         if (volume_ratio(df, i) or 0.0) >= BREAKOUT_VOLUME_RATIO and float(df.at[i, "Close"]) > cup.left_high_price + buffer),
        None,
    )
    idx = confirming_idx if confirming_idx is not None else first_break_idx
    return BreakoutEvent(
        index=idx, date=df.at[idx, "Date"].strftime("%Y-%m-%d"),
        pivot_price=round(cup.left_high_price, 4), close=round(float(df.at[idx, "Close"]), 4),
        volume_ratio=round(volume_ratio(df, idx) or 0.0, 2), volume_confirmed=confirming_idx is not None,
    )


def _reversal_after(df: pd.DataFrame, breakout: BreakoutEvent, cup: CupCandidate, atr_value: float) -> bool:
    buffer = atr_value * BREAKOUT_BUFFER_ATR
    return any(float(df.at[i, "Close"]) < cup.left_high_price - buffer for i in range(breakout.index + 1, len(df)))


def determine_status(cup: CupCandidate | None, handle: HandleCandidate | None, breakout: BreakoutEvent | None, df: pd.DataFrame, atr_value: float) -> Status:
    if cup is None:
        return "none"
    if handle is None:
        return "forming"
    if not handle.valid:
        return "failed"
    if breakout is None or not breakout.volume_confirmed:
        return "developing"
    if _reversal_after(df, breakout, cup, atr_value):
        return "failed"
    return "confirmed"


def compute_confidence(status: Status, handle: HandleCandidate | None, breakout: BreakoutEvent | None, rs_score: float | None) -> float:
    if status in ("none", "failed"):
        return 0.0
    base = {"forming": 0.2, "developing": 0.35, "confirmed": 0.5}[status]
    if handle is not None and handle.valid and handle.volume_ratio_vs_cup is not None:
        base += max(0.0, min(0.15, (1.0 - handle.volume_ratio_vs_cup) * 0.3))
    if breakout is not None:
        base += max(0.0, min(0.2, (breakout.volume_ratio - 1.0) * 0.2))
    if rs_score is not None:
        base += max(0.0, min(0.1, rs_score * 0.1))
    return round(min(0.95, base), 2)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest -q tests/test_oneil_breakout.py`
Expected: PASS (7 passed).

- [ ] **Step 5: Lint and line-count check**

Run: `ruff check tradingagents/dataflows/oneil_breakout.py tests/test_oneil_breakout.py`
Expected: clean.
Run: `wc -l tradingagents/dataflows/oneil_breakout.py`
Expected: under 150 (reference implementation is 86 lines).

Do not commit.

---

### Task 5: `oneil_bias.py`, `oneil_tools.py`, and wiring

**Files:**
- Create: `tradingagents/dataflows/oneil_bias.py`
- Create: `tradingagents/agents/utils/oneil_tools.py`
- Modify: `tradingagents/agents/utils/agent_utils.py:24-47`
- Modify: `tradingagents/graph/trading_graph.py:14-32,168-183`
- Modify: `tests/test_market_toolnode.py`
- Test: `tests/test_oneil_bias.py`

**Interfaces:**
- Consumes: `detect_cup`, `atr`, `prepare_ohlcv`, `CupCandidate` from
  `oneil_cup.py`; `detect_handle`, `HandleCandidate` from `oneil_handle.py`;
  `find_breakout`, `determine_status`, `compute_confidence`, `BreakoutEvent`
  from `oneil_breakout.py`; `relative_strength_score` from `trend_template.py`
  (Task 1); `load_ohlcv` from `stockstats_utils.py` (existing).
- Produces: `analyze_oneil_setup_from_data(data, curr_date, look_back_days=420, rs_score=None) -> dict`,
  `analyze_oneil_setup(symbol, curr_date, look_back_days=420, benchmark="SPY") -> str`
  (JSON string). `oneil_tools.py`'s `get_oneil_setup` LangChain tool wraps
  `analyze_oneil_setup`. Task 6 (Market Analyst prompt) consumes the JSON
  shape this task produces: top-level keys `cup, handle, breakout, status,
  setup_bias, confidence, secondary_weight, weight_note, evidence,
  analysis_date, symbol`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_oneil_bias.py`:

```python
"""Unit tests for the O'Neil setup synthesis / top-level JSON shape."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.oneil_bias import SECONDARY_WEIGHT, analyze_oneil_setup_from_data


def _full_sequence(breakout_vol_mult: float = 1.8) -> pd.DataFrame:
    prior_up_len, decline_len, base_len, recover_len, handle_len, post_len = 50, 45, 20, 45, 13, 15
    start_price, up_gain, depth_pct, handle_depth_pct = 50.0, 60.0, 0.20, 0.06
    closes: list[float] = []
    vols: list[float] = []
    for i in range(prior_up_len):
        closes.append(start_price + up_gain * i / (prior_up_len - 1))
        vols.append(1_000_000.0)
    left_high = closes[-1]
    low_price = left_high * (1 - depth_pct)
    for i in range(decline_len):
        t = (i + 1) / decline_len
        ease = (1 - np.cos(t * np.pi)) / 2
        closes.append(left_high - (left_high - low_price) * ease)
        vols.append(1_000_000.0)
    rng = np.random.default_rng(42)
    for _ in range(base_len):
        closes.append(low_price + rng.uniform(-0.3, 0.3))
        vols.append(900_000.0)
    for i in range(recover_len):
        t = i / (recover_len - 1)
        ease = (1 - np.cos(t * np.pi)) / 2
        closes.append(low_price + (left_high - low_price) * ease)
        vols.append(1_000_000.0)
    right_high = closes[-1]
    handle_low = right_high * (1 - handle_depth_pct)
    for i in range(handle_len):
        t = i / (handle_len - 1)
        depth_ease = np.sin(t * np.pi)
        closes.append(right_high - (right_high - handle_low) * depth_ease)
        vols.append(600_000.0)
    pivot = left_high
    for i in range(post_len):
        if i == 0:
            closes.append(pivot * 1.02)
            vols.append(1_000_000.0 * breakout_vol_mult)
        else:
            closes.append(pivot * (1.02 + 0.01 * i))
            vols.append(1_000_000.0)
    n = len(closes)
    dates = pd.bdate_range("2024-01-02", periods=n)
    closes_arr = np.array(closes)
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": closes_arr,
            "High": closes_arr + 0.5,
            "Low": closes_arr - 0.5,
            "Close": closes_arr,
            "Volume": vols,
        }
    )


@pytest.mark.unit
def test_confirmed_setup_has_full_payload_and_bullish_bias():
    df = _full_sequence()
    curr_date = df["Date"].iloc[-1].strftime("%Y-%m-%d")

    result = analyze_oneil_setup_from_data(df, curr_date, rs_score=0.05)

    assert result["status"] == "confirmed"
    assert result["setup_bias"] == "bullish"
    assert result["secondary_weight"] == SECONDARY_WEIGHT
    assert result["cup"] is not None
    assert result["handle"] is not None
    assert result["breakout"] is not None
    assert len(result["evidence"]) >= 3
    assert result["analysis_date"] == curr_date


@pytest.mark.unit
def test_no_cup_returns_neutral_with_secondary_weight_still_present():
    flat = pd.DataFrame(
        {
            "Date": pd.bdate_range("2024-01-02", periods=200),
            "Open": [100.0] * 200, "High": [100.5] * 200, "Low": [99.5] * 200,
            "Close": [100.0] * 200, "Volume": [1_000_000.0] * 200,
        }
    )
    curr_date = flat["Date"].iloc[-1].strftime("%Y-%m-%d")

    result = analyze_oneil_setup_from_data(flat, curr_date)

    assert result["status"] == "none"
    assert result["setup_bias"] == "neutral"
    assert result["cup"] is None
    assert result["secondary_weight"] == SECONDARY_WEIGHT


@pytest.mark.unit
def test_no_future_data_leaks_into_the_result():
    df = _full_sequence()
    cutoff_date = df["Date"].iloc[150].strftime("%Y-%m-%d")

    result = analyze_oneil_setup_from_data(df, cutoff_date)

    # At day 150 the handle/breakout haven't happened yet in this fixture.
    assert result["status"] in ("none", "forming")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest -q tests/test_oneil_bias.py`
Expected: FAIL / collection error — `tradingagents/dataflows/oneil_bias.py`
does not exist yet.

- [ ] **Step 3: Write the implementation**

Create `tradingagents/dataflows/oneil_bias.py`:

```python
"""Synthesizes the O'Neil cup-with-handle read into the tool-facing JSON.

secondary_weight is a fixed project policy constant (deliberately below
Wyckoff's dominant_weight of 0.6), not derived from this call's data.
See ONEIL_CANSLIM_ANALYSIS_PLAN.md.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from tradingagents.dataflows.oneil_breakout import BreakoutEvent, compute_confidence, determine_status, find_breakout
from tradingagents.dataflows.oneil_cup import CupCandidate, atr, detect_cup, prepare_ohlcv
from tradingagents.dataflows.oneil_handle import HandleCandidate, detect_handle
from tradingagents.dataflows.stockstats_utils import load_ohlcv
from tradingagents.dataflows.trend_template import relative_strength_score

SECONDARY_WEIGHT = 0.4
WEIGHT_NOTE = (
    "O'Neil cup-with-handle read ranks below Wyckoff but above chart patterns, trend "
    "template, and indicators; if Wyckoff phase_bias is non-neutral, it takes "
    "precedence over this result."
)


def _payload(cup: CupCandidate | None, handle: HandleCandidate | None, breakout: BreakoutEvent | None, status: str, bias: str, confidence: float) -> dict[str, Any]:
    evidence: list[str] = []
    cup_dict = None
    if cup is not None:
        evidence.extend(cup.evidence)
        cup_dict = {
            "start_date": cup.left_high_date, "left_high": round(cup.left_high_price, 4),
            "low_date": cup.low_date, "low_price": round(cup.low_price, 4),
            "right_high_date": cup.right_high_date,
            "depth_pct": round(cup.depth_pct * 100, 2), "duration_days": cup.duration_days,
        }
    handle_dict = None
    if handle is not None:
        evidence.extend(handle.evidence)
        handle_dict = {
            "start_date": handle.start_date, "end_date": handle.end_date,
            "low_price": round(handle.low_price, 4),
            "volume_ratio_vs_cup": round(handle.volume_ratio_vs_cup, 2) if handle.volume_ratio_vs_cup is not None else None,
        }
    breakout_dict = None
    if breakout is not None:
        confirmed_word = "Volume-confirmed" if breakout.volume_confirmed else "Unconfirmed (low-volume)"
        evidence.append(f"{confirmed_word} breakout on {breakout.date}: close {breakout.close:.2f} vs. pivot {breakout.pivot_price:.2f}, volume {breakout.volume_ratio:.2f}x average.")
        breakout_dict = {"date": breakout.date, "pivot_price": breakout.pivot_price, "close": breakout.close, "volume_ratio": breakout.volume_ratio}
    return {
        "cup": cup_dict, "handle": handle_dict, "breakout": breakout_dict,
        "status": status, "setup_bias": bias, "confidence": confidence,
        "secondary_weight": SECONDARY_WEIGHT, "weight_note": WEIGHT_NOTE, "evidence": evidence,
    }


def analyze_oneil_setup_from_data(data: pd.DataFrame, curr_date: str, look_back_days: int = 420, rs_score: float | None = None) -> dict[str, Any]:
    """Analyze an OHLCV frame and return a JSON-serializable O'Neil setup read."""
    df = prepare_ohlcv(data, curr_date, look_back_days)
    atr_value = float(atr(df).iloc[-1])
    cup = detect_cup(df, atr_value)
    handle = detect_handle(df, cup, atr_value) if cup is not None else None
    breakout = find_breakout(df, cup, handle, atr_value) if handle is not None and handle.valid else None
    status = determine_status(cup, handle, breakout, df, atr_value)
    bias = "bullish" if status in ("forming", "developing", "confirmed") else "neutral"
    confidence = compute_confidence(status, handle, breakout, rs_score)
    result = _payload(cup, handle, breakout, status, bias, confidence)
    result["analysis_date"] = curr_date
    return result


def analyze_oneil_setup(symbol: str, curr_date: str, look_back_days: int = 420, benchmark: str = "SPY") -> str:
    """Load cutoff-safe OHLCV and return a formatted JSON O'Neil setup report."""
    data = load_ohlcv(symbol, curr_date)
    prepared = prepare_ohlcv(data, curr_date, look_back_days)
    try:
        benchmark_data = load_ohlcv(benchmark, curr_date) if benchmark else None
        benchmark_df = prepare_ohlcv(benchmark_data, curr_date, look_back_days) if benchmark_data is not None else None
    except ValueError:
        benchmark_df = None
    rs_score = relative_strength_score(prepared, benchmark_df) if benchmark_df is not None else None
    result = analyze_oneil_setup_from_data(data, curr_date, look_back_days, rs_score)
    result["symbol"] = symbol.upper()
    return json.dumps(result, indent=2, ensure_ascii=False)
```

Create `tradingagents/agents/utils/oneil_tools.py`:

```python
from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.oneil_bias import analyze_oneil_setup


@tool
def get_oneil_setup(
    symbol: Annotated[str, "ticker symbol of the instrument"],
    curr_date: Annotated[str, "current analysis date in YYYY-mm-dd format"],
    look_back_days: Annotated[int, "lookback window in trading days"] = 420,
) -> str:
    """Deterministically read the stock's O'Neil cup-with-handle setup.

    Detects a rounded consolidation base (cup) following a meaningful prior
    uptrend, a shallower pullback in its upper half (handle) with lower
    volume than the cup, and a breakout above the cup's left-side high
    confirmed by above-average volume. Reports status
    (none/forming/developing/confirmed/failed), setup_bias, confidence, and a
    fixed `secondary_weight` policy constant. This read ranks below the
    Wyckoff structural read but above chart patterns, the trend template, and
    ordinary indicators: when Wyckoff's phase_bias is neutral, this result's
    setup_bias becomes the directional anchor for the technical verdict, but
    Wyckoff wins if both are non-neutral and conflict. Returns
    `setup_bias: "neutral"` with no cup when no valid structure is present in
    the lookback window.
    """
    return analyze_oneil_setup(symbol, curr_date, look_back_days)
```

In `tradingagents/agents/utils/agent_utils.py`, add the import after line 28
(`from tradingagents.agents.utils.wyckoff_tools import get_wyckoff_structure`):

```python
from tradingagents.agents.utils.oneil_tools import get_oneil_setup
```

and add `"get_oneil_setup",` to `__all__` right after `"get_wyckoff_structure",`
(line 47).

In `tradingagents/graph/trading_graph.py`, add to the import block from
`agent_utils` (after `get_news,` alphabetically, before `get_prediction_markets,`
— the existing import list is alphabetically sorted):

```python
    get_oneil_setup,
```

and register it in the market `ToolNode` list (after the `get_wyckoff_structure,`
line, currently line 182):

```python
                    # O'Neil cup-with-handle setup read.
                    get_oneil_setup,
```

In `tests/test_market_toolnode.py`, add `"get_oneil_setup"` to the asserted
set (the `assert {...} <= market_tools` block):

```python
    assert {
        "get_stock_data", "get_indicators", "get_chart_patterns", "get_trend_template",
        "get_wyckoff_structure", "get_oneil_setup",
    } <= market_tools
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest -q tests/test_oneil_bias.py tests/test_market_toolnode.py`
Expected: PASS (3 + 1 passed).

- [ ] **Step 5: Lint and line-count check**

Run: `ruff check tradingagents/dataflows/oneil_bias.py tradingagents/agents/utils/oneil_tools.py tradingagents/agents/utils/agent_utils.py tradingagents/graph/trading_graph.py tests/test_oneil_bias.py tests/test_market_toolnode.py`
Expected: clean.
Run: `wc -l tradingagents/dataflows/oneil_bias.py tradingagents/agents/utils/oneil_tools.py`
Expected: both under 150 (reference implementations are 87 and 26 lines).

Do not commit.

---

### Task 6: Market Analyst integration, spec update, and full regression

**Files:**
- Modify: `tradingagents/agents/analysts/market_analyst.py`
- Modify: `ONEIL_CANSLIM_ANALYSIS_PLAN.md` (File Structure section only)

**Interfaces:**
- Consumes: `get_oneil_setup` from `tradingagents.agents.utils.agent_utils`
  (Task 5).
- Produces: nothing new consumed by later tasks — this is the last task.

- [ ] **Step 1: Bind the tool and add the three-tier prompt paragraph**

In `tradingagents/agents/analysts/market_analyst.py`, add `get_oneil_setup`
to the imports (after `get_language_instruction,` alphabetically — the
existing import block from `agent_utils` is alphabetically sorted):

```python
    get_oneil_setup,
```

Add it to the `tools` list (after `get_wyckoff_structure,`):

```python
            get_oneil_setup,
```

In the system message string, insert a new paragraph immediately after the
existing Wyckoff paragraph (the one ending in `"Do not invent Wyckoff events
beyond what the tool reports."`) and before the
`"Write a very detailed and nuanced report..."` closing paragraph:

```python
"""Also call get_oneil_setup for the ticker and current date before the final report. It deterministically reads whether the stock has formed a William O'Neil cup-with-handle setup: a rounded consolidation base (cup) following a meaningful prior uptrend, a shallower pullback in the cup's upper half on lower volume (handle), and a breakout above the cup's left-side high confirmed by above-average volume. Report its `status` (forming/developing/confirmed/failed), the specific cup/handle/breakout dates and prices, and the `secondary_weight` value. Apply this three-tier precedence rule when synthesizing the report's overall technical conclusion: (1) if the Wyckoff `phase_bias` is bullish or bearish, it remains the final direction as already stated above; (2) if Wyckoff is neutral and this tool's `setup_bias` is bullish, `setup_bias` becomes the directional anchor instead -- chart-pattern, trend-template, and indicator evidence may only adjust conviction within that direction, not flip it to the opposite direction; if Wyckoff is instead non-neutral and conflicts with this tool's direction, say so explicitly ("conflicts with the O'Neil cup-with-handle structure") but still lead with the Wyckoff direction; (3) if both Wyckoff and this tool are neutral, weigh the remaining technical evidence normally. Do not invent cup, handle, or breakout events beyond what the tool reports."""
```

(Concatenate this as another `+` string segment alongside the existing ones,
matching the file's existing style of chaining string literals with `+`.)

Update the Markdown-table instruction sentence (currently `"...including a
row for the Wyckoff phase, phase_bias, and dominant_weight."`) to also
mention the O'Neil row:

```python
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read, including a row for the Wyckoff phase, phase_bias, and dominant_weight, and a separate row for the O'Neil cup-with-handle status, setup_bias, and secondary_weight."""
```

- [ ] **Step 2: Update the spec's File Structure section**

In `ONEIL_CANSLIM_ANALYSIS_PLAN.md`, replace the `## File Structure` code
block's `oneil_cup_handle.py` and `oneil_breakout.py` entries with the actual
four-file split used by this plan (`oneil_cup.py`, `oneil_handle.py`,
`oneil_breakout.py`, `oneil_bias.py`), matching what Tasks 2-5 above created,
and add `tests/test_oneil_bias.py` to the test-file list. Also update the
`Current Implementation Status` checklist items to reference the four real
file names instead of the original two.

- [ ] **Step 3: Full regression**

This change touches shared tool exports (`agent_utils.py`) and graph node
registration (`trading_graph.py`), so per `CLAUDE.md`'s verification policy,
run the full suite instead of just the new files' tests.

Run: `pytest -q`
Expected: all tests pass (no regressions in the pre-existing suite; only
skips unrelated to this change, e.g. `langchain_aws` not installed or
`DEEPSEEK_API_KEY` unset, same as noted in `WYCKOFF_ANALYSIS_PLAN.md`).

Run: `ruff check .`
Expected: clean.

- [ ] **Step 4: Manual smoke of the tool's JSON shape**

Run:

```bash
python -c "
from tradingagents.dataflows.oneil_bias import analyze_oneil_setup
print(analyze_oneil_setup('AAPL', '2026-07-01')[:400])
"
```

Expected: valid JSON printed (starting with `{`), with a `status` key whose
value is one of `none/forming/developing/confirmed/failed` — proves the tool
runs end-to-end against real cached/fetched data, not just synthetic
fixtures. (If no network/API access is available in this environment, it is
acceptable for this step to fail on a data-fetch error rather than a code
error; note that explicitly rather than silently skipping it.)

Do not commit. This task's diff (and every earlier task's diff) is reviewed
and re-verified by `codex-delegate`; the actual `git commit` waits for the
user's explicit approval.

### Stage 4 scenarios (for `antigravity-verify`, after all tasks pass)

Per `ONEIL_CANSLIM_ANALYSIS_PLAN.md`'s Testing Plan, the three-tier
precedence rule is prompt text, not code, so it needs `antigravity-verify`
(stage 4) rather than a unit test:

1. A ticker where Wyckoff's `phase_bias` is neutral and `get_oneil_setup`
   reports `status: "confirmed"` — the report should lead its technical
   conclusion with the O'Neil bullish direction.
2. A ticker where Wyckoff's `phase_bias` is non-neutral and disagrees with
   `get_oneil_setup`'s `setup_bias` — the report should lead with the
   Wyckoff direction and explicitly say it conflicts with the O'Neil
   cup-with-handle structure.

---

### Task 7: Pre-fetch Wyckoff + O'Neil reads (stage-4 finding — reliability fix)

**Background.** Stage-4 verification (`antigravity-verify`) ran the GE scenario
from the "Stage 4 scenarios" note above three times via
`TradingAgentsGraph(...).propagate('GE', '2026-07-01')`. `get_wyckoff_structure`
was called every time; `get_oneil_setup` was only called in 2 of 3 runs. When
it was called, the tool output and the report's synthesis were both correct
(matches the GE expectations above exactly). When it wasn't called, the
report's Wyckoff section was still correct but the O'Neil section was simply
absent — a silent gap, not a wrong answer.

**Root cause.** `market_analyst_node` (`tradingagents/agents/analysts/market_analyst.py`)
relies entirely on the LLM voluntarily choosing to call `get_oneil_setup`
among 7 tools listed in one long system-message wall of text, bound via
`llm.bind_tools(tools)`. The market analyst runs on `quick_thinking_llm`
(`gpt-5.4-mini` in this project's default config) — there is no code-level
guarantee any specific tool in that list actually gets called before the
final report is written.

**Precedent fix already in this repo.** `tradingagents/agents/analysts/sentiment_analyst.py`
hit the identical failure mode for a different reason (LLM skipping/fabricating
instead of calling tools reliably — GitHub issues #557/#796) and was
redesigned to stop depending on LLM tool-calling for its core data: it
pre-fetches all three sources in Python before invoking the LLM and injects
them into the system prompt from turn 0 ("The agent does not use tool-calling;
the data is in the prompt from turn 0"). Each fetcher there "degrades
gracefully and returns a string (no exceptions surface from here), so the LLM
always sees something."

**Fix for this task:** apply the same pattern to the two "precedence-tier"
reads only — `get_wyckoff_structure` and `get_oneil_setup` — since the
report's entire directional conclusion depends on both always being present.
The other five tools (`get_stock_data`, `get_indicators`,
`get_verified_market_snapshot`, `get_chart_patterns`, `get_trend_template`)
stay exactly as they are today — agent-chosen tool calls — because the
report's correctness doesn't hinge on any single one of them running.

**Files:**
- Modify: `tradingagents/agents/analysts/market_analyst.py`
- Test: `tests/test_market_analyst_prefetch.py` (new file, ≤150 lines)

**Scope guardrails (keep this task's diff small and low-risk):**
- Do **not** touch `tradingagents/graph/trading_graph.py`'s `ToolNode`
  registration or `tradingagents/agents/utils/agent_utils.py`'s exports.
  `get_wyckoff_structure`/`get_oneil_setup` remain registered there — they
  just become unreachable from this one graph node since the LLM is no
  longer offered them as callable tools. This is harmless (no other analyst
  binds them) and keeps the fix scoped to one file.
- Do **not** touch `tests/test_market_toolnode.py` — it asserts against the
  `ToolNode`'s registered tools (`_create_tool_nodes`), not the market
  analyst's `bind_tools` list, so it is unaffected by this change and must
  keep passing unmodified.
- Pre-fetching removes the LLM's ability to choose a non-default
  `look_back_days` for these two reads. Use each function's own default
  (`analyze_wyckoff_structure`'s default `look_back_days=504`,
  `analyze_oneil_setup`'s default `look_back_days=420`) — this matches what
  the LLM almost always chose anyway per the stage-4 debug traces. This is a
  deliberate reliability-over-flexibility tradeoff; do not add a mechanism
  for the LLM to override it.

**Interfaces:**
- Consumes: `analyze_wyckoff_structure(symbol: str, curr_date: str, look_back_days: int = 504) -> str`
  from `tradingagents.dataflows.wyckoff_bias` (existing, returns a JSON
  string — this is the plain function `get_wyckoff_structure`'s `@tool`
  wrapper already delegates to); `analyze_oneil_setup(symbol: str, curr_date: str, look_back_days: int = 420, benchmark: str = "SPY") -> str`
  from `tradingagents.dataflows.oneil_bias` (same relationship to
  `get_oneil_setup`). Both are already unit-tested at the dataflow level
  (`tests/test_oneil_bias.py`, existing Wyckoff tests) — this task does not
  re-test their internals, only that `market_analyst_node` always includes
  their output in what it sends the LLM.
- Produces: no new public interface; this task only changes
  `market_analyst_node`'s internal behavior.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_market_analyst_prefetch.py`. Use
`langchain_core.language_models.fake_chat_models.GenericFakeChatModel` (a real
`BaseChatModel` subclass, so `.bind_tools(...)` and the existing
`prompt | llm.bind_tools(tools)` composition behave exactly as they do with a
real provider — do not hand-roll a fake `Runnable`). Subclass it to capture
what the node actually does:

```python
class _CapturingFakeLLM(GenericFakeChatModel):
    """Records the tools bound and the final messages sent to the model."""
    captured_tool_names: list = []
    captured_messages: list = []

    def bind_tools(self, tools, **kwargs):
        type(self).captured_tool_names = [t.name for t in tools]
        return super().bind_tools(tools, **kwargs)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        type(self).captured_messages = messages
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
```

(Adjust to however `GenericFakeChatModel` actually stores/consumes its
`messages` iterator in the installed langchain-core version — give it one
canned response with no tool calls so `market_analyst_node` takes the
`len(result.tool_calls) == 0` branch and returns immediately.)

Test cases required (exact assertions, not exact code):

1. **Both reads always land in what the LLM sees, regardless of tool-calling.**
   Monkeypatch `tradingagents.agents.analysts.market_analyst.analyze_wyckoff_structure`
   and `...analyze_oneil_setup` (patch where imported, i.e. inside
   `market_analyst` module) to return two distinguishable fixed JSON strings
   (e.g. containing sentinel substrings `"SENTINEL_WYCKOFF_PAYLOAD"` and
   `"SENTINEL_ONEIL_PAYLOAD"`). Build a minimal `AgentState` (mirror
   `_make_sentiment_state()` in `tests/test_structured_agents.py` for the
   required keys: `trade_date`, `company_of_interest`, `messages`, plus
   whatever `get_instrument_context_from_state` needs). Call
   `create_market_analyst(fake_llm)(state)`. Assert both sentinel strings
   appear somewhere in the system content of `captured_messages` — this must
   be true unconditionally, i.e. the assertion must not depend on the fake
   LLM emitting any particular tool call.

2. **`get_wyckoff_structure` and `get_oneil_setup` are no longer offered as
   callable tools to this analyst's LLM.** After the same call, assert
   `"get_wyckoff_structure" not in captured_tool_names` and
   `"get_oneil_setup" not in captured_tool_names`, while the other five
   (`get_stock_data`, `get_indicators`, `get_verified_market_snapshot`,
   `get_chart_patterns`, `get_trend_template`) are still present.

3. **A data-fetch failure degrades gracefully instead of crashing the node.**
   Monkeypatch `analyze_oneil_setup` to `raise ValueError("boom")`. Call the
   node and assert it does not raise — it still returns a dict with a
   `market_report` key, and the injected O'Neil block visible in
   `captured_messages` is valid enough that a `setup_bias` of `"neutral"` (or
   equivalent neutral/unavailable signal) is present rather than the node
   crashing or omitting the section silently. Repeat for
   `analyze_wyckoff_structure` raising, asserting a neutral `phase_bias`
   fallback instead of a crash.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest -q tests/test_market_analyst_prefetch.py`
Expected: FAIL / collection error — the module still calls `get_oneil_setup`/
`get_wyckoff_structure` as bound tools, not `analyze_oneil_setup`/
`analyze_wyckoff_structure` as pre-fetched data, so tests 1-2 fail their
assertions and there's nothing yet to make test 3's fallback shape true.

- [ ] **Step 3: Write the implementation**

In `tradingagents/agents/analysts/market_analyst.py`:

Replace the `get_oneil_setup`/`get_wyckoff_structure` tool imports with the
underlying plain functions, and add `json`:

```python
import json

from tradingagents.dataflows.oneil_bias import analyze_oneil_setup
from tradingagents.dataflows.wyckoff_bias import analyze_wyckoff_structure
```

(Keep the other `agent_utils` imports — `get_chart_patterns`, `get_indicators`,
`get_instrument_context_from_state`, `get_language_instruction`,
`get_stock_data`, `get_trend_template`, `get_verified_market_snapshot` —
unchanged.)

Add two module-level helpers above `create_market_analyst`, mirroring
`sentiment_analyst.py`'s "fetchers degrade gracefully" contract:

```python
def _fetch_wyckoff_block(ticker: str, current_date: str) -> str:
    try:
        return analyze_wyckoff_structure(ticker, current_date)
    except Exception as exc:
        return json.dumps({
            "phase_bias": "neutral", "current_phase": "undetermined",
            "events": [], "dominant_weight": 0.6,
            "error": f"Wyckoff read unavailable: {exc}",
        })


def _fetch_oneil_block(ticker: str, current_date: str) -> str:
    try:
        return analyze_oneil_setup(ticker, current_date)
    except Exception as exc:
        return json.dumps({
            "status": "none", "setup_bias": "neutral", "secondary_weight": 0.4,
            "cup": None, "handle": None, "breakout": None, "evidence": [],
            "error": f"O'Neil read unavailable: {exc}",
        })
```

In `market_analyst_node(state)`: add `ticker = state["company_of_interest"]`
and pre-fetch both blocks right after `instrument_context` is resolved; drop
`get_oneil_setup` and `get_wyckoff_structure` from the `tools` list; replace
the Wyckoff and O'Neil system-message paragraphs (currently "Also call
get_wyckoff_structure..." / "Also call get_oneil_setup...") with versions
that state the read has *already been provided* (not something to call a
tool for) and embed the fetched JSON verbatim, keeping the existing three-tier
precedence-rule sentences unchanged in meaning. For example, the Wyckoff
paragraph becomes (same rule text, new framing, JSON embedded via an f-string
using `wyckoff_block`):

```python
f"""The stock's Wyckoff accumulation/distribution structure has already been deterministically read for you below -- do not call any tool to re-derive it. It reports the current consolidation range, the classical events found inside it (selling/buying climax, automatic rally/reaction, secondary test, spring/upthrust, sign of strength/weakness, last point of support/supply), the resulting phase (A through E), and a `phase_bias` (bullish/bearish/neutral). Treat this as the primary technical read and write it as its own section before other technical evidence: state the phase, cite the specific events with their dates and prices, and give the `dominant_weight` value. Apply this rule when synthesizing the report's overall technical conclusion: when `phase_bias` is bullish or bearish, the chart-pattern, trend-template, and indicator evidence may only adjust conviction within that same direction -- they must not flip the technical conclusion to the opposite direction. If that other evidence strongly conflicts with the Wyckoff read, say so explicitly, but still lead the technical conclusion with the Wyckoff direction. When `phase_bias` is neutral (including no clear range in the lookback window), treat the other technical evidence normally, without this constraint. Do not invent Wyckoff events beyond what this JSON reports.

<wyckoff_structure>
{wyckoff_block}
</wyckoff_structure>
"""
```

and analogously for the O'Neil paragraph (same three-tier precedence prose as
today, "already been read for you" framing, `oneil_block` embedded in an
`<oneil_setup>` block). Everything else in the file (the indicator-selection
paragraph, verified-snapshot paragraph, chart-patterns paragraph,
trend-template paragraph, the closing "write a detailed report" /
Markdown-table paragraphs, the `ChatPromptTemplate`/`chain.invoke` wiring, the
`len(result.tool_calls) == 0` report-extraction logic) is unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest -q tests/test_market_analyst_prefetch.py`
Expected: PASS (all cases from Step 1).

- [ ] **Step 5: No regressions in the existing market-analyst-adjacent tests**

Run: `pytest -q tests/test_market_toolnode.py tests/test_trend_template.py tests/test_oneil_bias.py tests/test_oneil_cup.py tests/test_oneil_handle.py tests/test_oneil_breakout.py`
Expected: PASS, unchanged (these must not need edits for this task).

- [ ] **Step 6: Lint and line-count check**

Run: `ruff check tradingagents/agents/analysts/market_analyst.py tests/test_market_analyst_prefetch.py`
Expected: clean.
Run: `wc -l tests/test_market_analyst_prefetch.py`
Expected: ≤150.

Do not commit.

- [ ] **Step 7: Re-run stage-4 scenarios (back to `antigravity-verify`)**

Not part of this task's own verification command (per the plan's split
between `codex-delegate` per-task verification and `antigravity-verify`'s
end-to-end scenario check) — once this task passes, re-run the GE and JPM
scenarios from the "Stage 4 scenarios" note above 3+ times each and confirm
the O'Neil section is present in the report every single time now (not just
most times), with the correct precedence behavior in both scenarios.
