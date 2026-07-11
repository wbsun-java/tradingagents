# O'Neil Flat-Base Continuation-Chaining Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Note for this repo specifically:** this project's established workflow runs each task through the `codex-delegate` skill (Codex CLI, non-interactive, self-verifying) rather than a generic Claude subagent. When executing, use `codex-delegate` per task instead of `subagent-driven-development`'s own dispatch mechanism; the review-gate structure below still applies.

**Goal:** Detect whether a flat base's preceding advance traces to a prior confirmed
breakout with a ≥20% gain (IBD's continuation-base rule), narrate the finding, and apply a
confidence penalty only when the continuation looks premature — without adding any new
staging infrastructure or touching non-flat-base detectors.

**Architecture:** A pure classifier (`oneil_base_chain.py::classify_continuation`) decides the
three-way state (`confirmed_continuation` / `premature_continuation` / `no_prior_stage`) from
plain price/date values. `oneil_base_patterns.py` gains a recursive helper,
`_find_prior_confirmed_breakout`, that reruns the existing `detect_all` →
`evaluate_candidates` pipeline on the df prefix before a flat base's peak to find the most
recent confirmed breakout, then feeds its pivot into the classifier. `evaluate_candidates`
stamps the result onto the candidate and threads it into `compute_confidence`, which applies
`PREMATURE_CONTINUATION_PENALTY` only for the premature case.

**Tech Stack:** Python 3.14, pandas/numpy, pytest (`@pytest.mark.unit`), ruff.

## Global Constraints

- Design source of truth: `docs/superpowers/specs/2026-07-11-oneil-base-chaining-design.md`.
- Scope is `flat_base` only — no other detector (cup, double-bottom, ascending, HTF) changes
  behavior.
- No multi-stage (1st/2nd/3rd/4th) counting — a single three-state classification only.
- No new data fetching — the recursive rescan is strictly bounded to the `df` slice already
  loaded by the caller; a prior breakout outside that slice is indistinguishable from
  "no prior stage found" and must never be penalized.
- Reuse the same `atr_value` scalar already computed once per outer call — never recompute
  ATR on the truncated prefix.
- Gain threshold is `>= 0.20` (inclusive).
- Soft flag only: a `premature_continuation` flat base is still returned and still eligible
  to become the arbitrated primary pattern — never dropped.
- `PREMATURE_CONTINUATION_PENALTY = 0.05`, subtracted the same way `UNDERCUT_BONUS = 0.05` is
  added today in `compute_confidence`.
- New file (`oneil_base_chain.py`) must stay ≤150 lines per `CLAUDE.md` convention.
- All new tests use `@pytest.mark.unit` with synthetic OHLCV (no network/paid-LLM calls).
- Run `ruff check <changed files>` after each task; run the scoped test files listed in each
  task, not the full suite (per `CLAUDE.md`'s isolated-change verification guidance).

---

### Task 1: Pure continuation classifier

**Files:**
- Create: `tradingagents/dataflows/oneil_base_chain.py`
- Test: `tests/test_oneil_base_chain.py`

**Interfaces:**
- Produces: `classify_continuation(prior_pivot_price: float | None, prior_date: str | None, peak_price: float) -> tuple[str, str]` — returns `(state, evidence)` where `state` is one of `"confirmed_continuation"`, `"premature_continuation"`, `"no_prior_stage"`. Also exports `CONTINUATION_GAIN_THRESHOLD = 0.20`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_oneil_base_chain.py
"""Unit tests for O'Neil flat-base continuation-chain classification."""

from __future__ import annotations

import pytest

from tradingagents.dataflows.oneil_base_chain import classify_continuation


@pytest.mark.unit
def test_no_prior_stage_when_no_prior_pivot():
    state, evidence = classify_continuation(None, None, 150.0)
    assert state == "no_prior_stage"
    assert "first-stage base" in evidence


@pytest.mark.unit
def test_confirmed_continuation_at_exactly_20_percent():
    state, evidence = classify_continuation(100.0, "2024-01-15", 120.0)
    assert state == "confirmed_continuation"
    assert "2024-01-15" in evidence
    assert "20.0%" in evidence


@pytest.mark.unit
def test_confirmed_continuation_above_threshold():
    state, _ = classify_continuation(100.0, "2024-01-15", 130.0)
    assert state == "confirmed_continuation"


@pytest.mark.unit
def test_premature_continuation_below_threshold():
    state, evidence = classify_continuation(100.0, "2024-01-15", 108.0)
    assert state == "premature_continuation"
    assert "8.0%" in evidence
    assert "20% continuation threshold" in evidence
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_oneil_base_chain.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tradingagents.dataflows.oneil_base_chain'`

- [ ] **Step 3: Write the implementation**

```python
# tradingagents/dataflows/oneil_base_chain.py
"""Continuation-chain classification for O'Neil flat bases."""

from __future__ import annotations

CONTINUATION_GAIN_THRESHOLD = 0.20


def classify_continuation(
    prior_pivot_price: float | None,
    prior_date: str | None,
    peak_price: float,
) -> tuple[str, str]:
    """Classify a flat base's peak against its most recent prior confirmed breakout."""
    if prior_pivot_price is None:
        return (
            "no_prior_stage",
            "No confirmed prior base was found in the available history; "
            "treating as a first-stage base.",
        )
    gain = (peak_price - prior_pivot_price) / prior_pivot_price if prior_pivot_price else 0.0
    if gain >= CONTINUATION_GAIN_THRESHOLD:
        return (
            "confirmed_continuation",
            f"Advanced {gain:.1%} off the {prior_date} breakout at {prior_pivot_price:.2f} "
            "before basing again, qualifying as a genuine continuation base.",
        )
    return (
        "premature_continuation",
        f"Only advanced {gain:.1%} off the {prior_date} breakout at {prior_pivot_price:.2f} "
        "before basing again — below IBD's 20% continuation threshold.",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_oneil_base_chain.py -v`
Expected: 4 passed

- [ ] **Step 5: Ruff check and commit**

```bash
ruff check tradingagents/dataflows/oneil_base_chain.py tests/test_oneil_base_chain.py
git add tradingagents/dataflows/oneil_base_chain.py tests/test_oneil_base_chain.py
git commit -m "feat(oneil): add flat-base continuation-chain classifier"
```

---

### Task 2: Confidence penalty for premature continuations

**Files:**
- Modify: `tradingagents/dataflows/oneil_breakout.py`
- Test: `tests/test_oneil_breakout.py`

**Interfaces:**
- Consumes: nothing new from Task 1 (uses only the state-string literals `"premature_continuation"` / `"confirmed_continuation"` / `"no_prior_stage"`, not the function itself).
- Produces: `compute_confidence(pattern_type, status, handle, breakout, rs_score, undercut: bool = False, continuation_state: str | None = None) -> float`. New constant `PREMATURE_CONTINUATION_PENALTY = 0.05`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_oneil_breakout.py` (extend the existing `from tradingagents.dataflows.oneil_breakout import (...)` block to also import `PREMATURE_CONTINUATION_PENALTY`, then append):

```python
@pytest.mark.unit
def test_premature_continuation_lowers_confidence():
    base = compute_confidence("flat_base", "developing", None, None, None)
    penalized = compute_confidence(
        "flat_base", "developing", None, None, None,
        continuation_state="premature_continuation",
    )
    assert base - penalized == pytest.approx(PREMATURE_CONTINUATION_PENALTY)


@pytest.mark.unit
def test_confirmed_or_missing_continuation_state_does_not_penalize():
    base = compute_confidence("flat_base", "developing", None, None, None)
    for state in ("confirmed_continuation", "no_prior_stage", None):
        assert compute_confidence(
            "flat_base", "developing", None, None, None, continuation_state=state
        ) == base
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_oneil_breakout.py -k continuation -v`
Expected: FAIL with `ImportError: cannot import name 'PREMATURE_CONTINUATION_PENALTY'`

- [ ] **Step 3: Implement the penalty**

In `tradingagents/dataflows/oneil_breakout.py`, add the constant next to `UNDERCUT_BONUS`:

```python
UNDERCUT_BONUS = 0.05
PREMATURE_CONTINUATION_PENALTY = 0.05
```

Update `compute_confidence`'s signature and body:

```python
def compute_confidence(
    pattern_type: PatternType,
    status: Status,
    handle: HandleCandidate | None,
    breakout: BreakoutEvent | None,
    rs_score: float | None,
    undercut: bool = False,
    continuation_state: str | None = None,
) -> float:
    """Score a live base from status, pattern quality, volume, and relative strength."""
    if status in ("none", "failed"):
        return 0.0
    base = {"forming": 0.2, "developing": 0.35, "confirmed": 0.5}[status]
    base += PATTERN_CONFIDENCE_BONUS[pattern_type]
    if undercut:
        base += UNDERCUT_BONUS
    if continuation_state == "premature_continuation":
        base -= PREMATURE_CONTINUATION_PENALTY
    if handle is not None and handle.valid and handle.volume_ratio_vs_cup is not None:
        base += max(0.0, min(0.15, (1.0 - handle.volume_ratio_vs_cup) * 0.3))
    if breakout is not None:
        base += max(0.0, min(0.2, (breakout.volume_ratio - 1.0) * 0.2))
    if rs_score is not None:
        base += max(0.0, min(0.1, rs_score * 0.1))
    return round(max(0.0, min(0.95, base)), 2)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_oneil_breakout.py -v`
Expected: all pass (existing tests plus the 2 new ones)

- [ ] **Step 5: Ruff check and commit**

```bash
ruff check tradingagents/dataflows/oneil_breakout.py tests/test_oneil_breakout.py
git add tradingagents/dataflows/oneil_breakout.py tests/test_oneil_breakout.py
git commit -m "feat(oneil): penalize premature continuation bases in confidence scoring"
```

---

### Task 3: Recursive prior-breakout rescan, wiring, and fixtures

**Files:**
- Modify: `tradingagents/dataflows/oneil_base_types.py`
- Modify: `tradingagents/dataflows/oneil_base_patterns.py`
- Create: `tests/oneil_base_chain_fixtures.py`
- Modify: `tests/test_oneil_base_patterns.py`

**Interfaces:**
- Consumes: `classify_continuation` from Task 1 (`tradingagents.dataflows.oneil_base_chain`); `compute_confidence(..., continuation_state=...)` from Task 2.
- Produces: `BaseCandidate.continuation_state: str | None = None` field. `evaluate_candidates(df, candidates, atr_value, rs_score, *, apply_chaining: bool = True) -> list[PatternDetection]` (new keyword-only parameter, default preserves existing behavior for all current callers). Private `_find_prior_confirmed_breakout(df, before_index, atr_value, rs_score) -> PatternDetection | None`.

- [ ] **Step 1: Add the `continuation_state` field to `BaseCandidate`**

In `tradingagents/dataflows/oneil_base_types.py`, in the `BaseCandidate` dataclass, add the
field after `undercut`:

```python
@dataclass
class BaseCandidate:
    """A detected base before shared breakout evaluation."""

    pattern_type: PatternType
    complete: bool
    pivot_price: float
    pivot_date: str
    complete_index: int
    geometry: dict[str, Any]
    evidence: list[str]
    handle: HandleCandidate | None = None
    undercut: bool = False
    continuation_state: str | None = None
    start_index: int | None = None
    base_low_price: float | None = None
```

- [ ] **Step 2: Write the synthetic-OHLCV fixture builders**

```python
# tests/oneil_base_chain_fixtures.py
"""Synthetic OHLCV builders for O'Neil flat-base continuation-chain tests."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _frame(closes: list[float], volumes: list[float]) -> pd.DataFrame:
    prices = np.asarray(closes, dtype=float)
    return pd.DataFrame({
        "Date": pd.bdate_range("2024-01-02", periods=len(prices)),
        "Open": prices,
        "High": prices + 0.5,
        "Low": prices - 0.5,
        "Close": prices,
        "Volume": volumes,
    })


def _flat_base_segment(
    start_price: float, ramp_gain: float, tight_days: int = 30, depth: float = 0.08
) -> tuple[list[float], list[float], float]:
    ramp = np.linspace(start_price, start_price + ramp_gain, 60).tolist()
    peak = start_price + ramp_gain + 3.0
    angles = np.linspace(0, 6 * np.pi, tight_days - 1)
    range_closes = (peak * (1 - depth * (0.55 + 0.45 * np.sin(angles)))).tolist()
    closes = ramp + [peak] + range_closes
    vols = [1_000_000.0] * 61 + [700_000.0] * (tight_days - 1)
    return closes, vols, peak


def chained_flat_bases(advance_target_ratio: float) -> tuple[pd.DataFrame, int, float, float]:
    """Two flat bases chained by a confirmed breakout and an advance.

    ``advance_target_ratio`` sets the second base's gain over the first base's
    pivot: 1.25 yields a confirmed continuation (+25%); 1.08 yields a
    premature one (+8%). Returns (df, before_index, peak1, peak2) where
    ``before_index`` is the second base's peak index (its start_index).
    """
    closes1, vols1, peak1 = _flat_base_segment(100.0, 40.0)
    breakout_price = peak1 * 1.05
    post = [breakout_price, breakout_price * 1.01, breakout_price * 1.02]
    postv = [1_600_000.0] * 3
    advance = np.linspace(post[-1], peak1 * advance_target_ratio, 20).tolist()
    post += advance
    postv += [1_000_000.0] * 20
    peak2 = post[-1] + 3.0
    angles2 = np.linspace(0, 6 * np.pi, 29)
    range2 = (peak2 * (1 - 0.08 * (0.55 + 0.45 * np.sin(angles2)))).tolist()
    closes2 = [peak2] + range2
    vols2 = [1_000_000.0] + [700_000.0] * 29
    df = _frame(closes1 + post + closes2, vols1 + postv + vols2)
    before_index = len(closes1) + len(post)
    return df, before_index, peak1, peak2


def single_flat_base() -> pd.DataFrame:
    """One flat base with no earlier stage in its available history."""
    closes, vols, _ = _flat_base_segment(100.0, 40.0)
    return _frame(closes, vols)
```

- [ ] **Step 3: Write the failing integration tests**

Append to `tests/test_oneil_base_patterns.py` (add `from tests.oneil_base_chain_fixtures import
chained_flat_bases, single_flat_base` to the imports):

```python
def _flat_base_detection(df: pd.DataFrame) -> PatternDetection:
    atr_value = float(atr(df).iloc[-1])
    candidates = [c for c in detect_all(df, atr_value) if c.pattern_type == "flat_base"]
    assert candidates, "expected a flat_base candidate"
    return evaluate_candidates(df, candidates, atr_value, None)[0]


@pytest.mark.unit
def test_confirmed_continuation_flat_base():
    df, _, _, peak2 = chained_flat_bases(1.25)
    detection = _flat_base_detection(df)
    assert detection.candidate.pivot_price == pytest.approx(peak2, abs=0.6)
    assert detection.candidate.continuation_state == "confirmed_continuation"
    assert any("continuation base" in line for line in detection.candidate.evidence)


@pytest.mark.unit
def test_premature_continuation_flat_base_is_flagged():
    df, _, _, _ = chained_flat_bases(1.08)
    detection = _flat_base_detection(df)
    assert detection.candidate.continuation_state == "premature_continuation"
    assert any("20% continuation threshold" in line for line in detection.candidate.evidence)


@pytest.mark.unit
def test_premature_continuation_scores_lower_than_confirmed():
    confirmed = _flat_base_detection(chained_flat_bases(1.25)[0])
    premature = _flat_base_detection(chained_flat_bases(1.08)[0])
    assert premature.confidence < confirmed.confidence


@pytest.mark.unit
def test_no_prior_stage_is_not_penalized():
    detection = _flat_base_detection(single_flat_base())
    assert detection.candidate.continuation_state == "no_prior_stage"
    assert any("first-stage base" in line for line in detection.candidate.evidence)
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_oneil_base_patterns.py -k continuation -v`
Expected: FAIL — `continuation_state` is always `None` (field exists but nothing sets it), so
`test_confirmed_continuation_flat_base` and `test_premature_continuation_flat_base_is_flagged`
fail their `continuation_state ==` assertions; `test_no_prior_stage_is_not_penalized` may pass
vacuously since `None` is the default — that's expected at this point, not a problem to fix
yet.

- [ ] **Step 5: Implement the recursive rescan and wire it into `evaluate_candidates`**

In `tradingagents/dataflows/oneil_base_patterns.py`:

Update imports:

```python
from tradingagents.dataflows.oneil_base_chain import classify_continuation
from tradingagents.dataflows.oneil_base_types import BaseCandidate, PRIOR_UPTREND_MIN_BARS
```

Replace the existing `evaluate_candidates` function and add `_find_prior_confirmed_breakout`
right after it:

```python
def evaluate_candidates(
    df: pd.DataFrame,
    candidates: list[BaseCandidate],
    atr_value: float,
    rs_score: float | None,
    *,
    apply_chaining: bool = True,
) -> list[PatternDetection]:
    """Apply the common breakout engine once to each candidate."""
    detections: list[PatternDetection] = []
    last_bar = len(df) - 1
    for candidate in candidates:
        if base_is_stale(candidate, last_bar):
            continue
        if (
            apply_chaining
            and candidate.pattern_type == "flat_base"
            and candidate.start_index is not None
        ):
            prior = _find_prior_confirmed_breakout(df, candidate.start_index, atr_value, rs_score)
            state, evidence_text = classify_continuation(
                prior.candidate.pivot_price if prior is not None else None,
                prior.candidate.pivot_date if prior is not None else None,
                candidate.pivot_price,
            )
            candidate.continuation_state = state
            candidate.evidence.append(evidence_text)
        breakout = (
            find_breakout(df, candidate.pivot_price, candidate.complete_index + 1, atr_value)
            if candidate.complete
            else None
        )
        reversed_after = (
            breakout_reversed(df, breakout, candidate.pivot_price, atr_value)
            if breakout is not None
            else False
        )
        structure_broken = base_structure_broken(df, candidate, atr_value)
        status = determine_status(
            complete=candidate.complete,
            handle=candidate.handle,
            handle_required=candidate.pattern_type == "cup_with_handle",
            breakout=breakout,
            reversed_after=reversed_after,
            structure_broken=structure_broken,
        )
        detections.append(
            PatternDetection(
                candidate, status, breakout,
                compute_confidence(candidate.pattern_type, status, candidate.handle, breakout,
                                   rs_score, undercut=candidate.undercut,
                                   continuation_state=candidate.continuation_state),
            )
        )
    return detections


def _find_prior_confirmed_breakout(
    df: pd.DataFrame, before_index: int, atr_value: float, rs_score: float | None
) -> PatternDetection | None:
    """Return the most recent confirmed breakout strictly before ``before_index``."""
    if before_index < PRIOR_UPTREND_MIN_BARS:
        return None
    prefix = df.iloc[:before_index]
    candidates = detect_all(prefix, atr_value)
    detections = evaluate_candidates(prefix, candidates, atr_value, rs_score, apply_chaining=False)
    confirmed = [item for item in detections if item.status == "confirmed"]
    if not confirmed:
        return None
    return max(confirmed, key=lambda item: item.candidate.pivot_date)
```

(`apply_chaining=False` on the recursive call is what bounds recursion depth to exactly one
extra level — the prefix rescan only needs each candidate's `status`, which never depends on
`continuation_state`, so nested chaining would be correct but wasted work.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_oneil_base_patterns.py -v`
Expected: all pass, including the 4 new tests and all pre-existing ones in this file.

- [ ] **Step 7: Run the full O'Neil test slice and ruff**

```bash
pytest -q tests/test_oneil_base_chain.py tests/test_oneil_breakout.py tests/test_oneil_base_patterns.py tests/test_oneil_flat_base.py tests/test_oneil_bias.py
ruff check tradingagents/dataflows/oneil_base_types.py tradingagents/dataflows/oneil_base_patterns.py tests/oneil_base_chain_fixtures.py tests/test_oneil_base_patterns.py
```

Expected: all pass, ruff clean. (Running `test_oneil_bias.py` too since it exercises
`detect_all`/`evaluate_candidates` end-to-end through `analyze_oneil_setup_from_data` — worth
confirming the new keyword-only `apply_chaining` parameter didn't disturb its default-path
callers.)

- [ ] **Step 8: Commit**

```bash
git add tradingagents/dataflows/oneil_base_types.py tradingagents/dataflows/oneil_base_patterns.py tests/oneil_base_chain_fixtures.py tests/test_oneil_base_patterns.py
git commit -m "feat(oneil): chain flat bases to their prior confirmed breakout"
```

---

## Codex model tier per task

Per the design spec: Task 1 (pure classifier), Task 2 (`compute_confidence` parameter), and
Task 3 (recursive rescan wiring) are all **terra**. Always pass `-m gpt-5.6-terra` explicitly
to `codex-delegate` (config default is still gpt-5.5).

## Acceptance Criteria (from spec)

- A flat base with a traceable, confirmed, ≥20%-gained prior breakout narrates that
  continuation explicitly in evidence (`confirmed_continuation`).
- A flat base without a traceable prior breakout (none exists, or history is insufficient) is
  never penalized (`no_prior_stage`).
- A flat base whose prior breakout gained <20% is flagged and scored lower, but still
  returned as a valid candidate (`premature_continuation`).
- No behavior change to any non-flat-base detector, and no change to any existing test's
  expected outcome (`evaluate_candidates`'s new parameter is keyword-only with a
  backward-compatible default).

> Research/analysis support only; not investment advice; no trade execution.
