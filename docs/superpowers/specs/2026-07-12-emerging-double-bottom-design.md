# Emerging Double-Bottom Stage (SP3b) — Design Spec

Date: 2026-07-12
Status: approved design, pre-implementation
Parent: `CHART_PATTERN_ANALYSIS_PLAN.md` (predictive_bottom / 底部预判, line ~197: "允许第二个
底部尚未成为确认枢轴点，因此应新增 emerging 候选阶段").
Sub-project: SP3b — the piece split out of SP3 (entry taxonomy) during its brainstorming.
SP1/SP2/SP3/SP4 have landed. This is the last deferred chart-pattern item.

## Problem

`find_pivots` confirms a swing low only after `span` later bars exist, so `_double_patterns`
cannot see a W-bottom whose second low is still forming (the last ~`span` bars) — exactly
the earliest, best-reward/risk entry a trader wants. SP3's `predictive_bottom` therefore
never fires at a fresh second bottom, only once it has confirmed into a `forming` double
bottom. SP3b adds an `emerging` candidate stage that recognizes the second bottom before it
confirms as a pivot, guarded conservatively against a low that is still falling.

## Scope decisions (user-approved 2026-07-12)

1. **Double-bottom second bottom only.** No double-top "emerging" (no long state feeds it);
   no emerging for triangles/rectangles (their support boundaries already confirm, so
   `predictive_bottom` already works there).
2. **Conservative turn-up required** (not fire-at-the-touch): emerging needs a nascent
   bounce off the candidate low before it is recognized — see detection rule 2.
3. **`emerging` is a new `PatternStatus` value** on the double_bottom PricePattern.
4. **One-line prompt note included** (approved upstream edit, same market_analyst.py
   chart-pattern paragraph as SP3).

## Detection — `find_emerging_double_bottom(df, pivots, atr, span) -> PricePattern | None`

A new module `double_bottom_emerging.py`. Long-only; fires only when the normal path cannot
yet see the second bottom. Rules, in order (any failure → `None`):

1. **Candidate low:** the lowest `Low` within the last `EMERGING_WINDOW_BARS` bars; its
   index must be `>= 1` bar back (not the final bar).
2. **Nascent turn-up:** the current close sits `>= EMERGING_TURN_UP_ATR * ATR` above the
   candidate low, AND no `Low` after the candidate is lower than it. Price must visibly
   bounce off the second-bottom level first.
3. **Match to a confirmed first bottom:** a confirmed low pivot with
   `|candidate_low - first.price| <= tolerance` (`tolerance = max(ATR, average * 0.03)`,
   `average = (first.price + candidate_low) / 2`, same as `_double_patterns`), and
   `gap = candidate_index - first.index` in `[max(5, span * 2), 80]`.
4. **Microstructure guard** (per [[double_bottom_microstructure]]): the candidate may equal,
   exceed, or *briefly shallow-undercut* the first bottom, bounded by the same `tolerance`
   (`candidate_low >= first.price - tolerance`) — not a deep breakdown. The neckline (the
   max `High` between `first.index` and `candidate_index`) must clear
   `depth >= max(ATR * 1.25, average * 0.02)`, exactly like the confirmed double.
5. **Emit** a `double_bottom` PricePattern, `status = "emerging"`, `direction = "bullish"`,
   `second_extreme = candidate_low`, `neckline` as computed, `target = neckline + depth`,
   `invalidation_price = candidate_low - ATR * 0.2`, `confidence = EMERGING_CONFIDENCE`
   (the most speculative stage), `volume_confirmed = None`, and dated/priced evidence
   naming the first bottom, the candidate low, the turn-up, and the neckline.

If several confirmed first bottoms match, use the most recent one that satisfies all gates.

## Schema & wiring (in `chart_patterns.py`)

- `PatternStatus` Literal gains `"emerging"`.
- `status_order` becomes `{"confirmed": 0, "forming": 1, "emerging": 2, "failed": 3}` —
  emerging sorts after forming (more speculative), ahead of failed (still a live setup).
- In `analyze_chart_patterns_from_data`, after `_double_patterns(...)`, call
  `find_emerging_double_bottom(df, pivots, atr_value, pivot_span)` and append its result
  **only if no `double_bottom` is already in `patterns`**. `_double_patterns` is left
  untouched; once the second bottom confirms, its normal `forming` double_bottom supersedes,
  so emerging is strictly the pre-forming fallback and never a duplicate. The existing
  entry_assessment post-pass then runs over the emerging pattern like any other.

## Entry layer & prompt

- **`entry_assessment.py` (SP3-owned):** add a branch at the top of the long-eligible logic
  — `if pattern.status == "emerging": -> predictive_bottom` directly, bypassing the
  `forming` proximity (`near`) check. The rule-2 turn-up pushes price just outside the
  `0.5 * ATR` proximity band, so reusing `near` would wrongly yield `observe`; the emerging
  detector has already established the `predictive_bottom` setup. Entry zone spans the
  candidate low (`bottom_boundary - PREDICTIVE_UNDERSHOOT_ATR*ATR` to `bottom_boundary +
  prox`), trigger = `bottom_boundary` (the candidate low via `extract_levels`), invalidation
  = the pattern's `invalidation_price`, `volume_role = supporting_not_required`.
- **`market_analyst.py` (upstream, approved):** append one sentence to the existing
  chart-pattern paragraph — an `emerging` pattern is a still-forming candidate, even more
  tentative than `forming`; act only on its `entry_assessment.state` and never treat it as
  confirmed.

## Constants (interim, future backtest read)

`EMERGING_WINDOW_BARS` (≈ `span` + small margin; start at `span + 2`),
`EMERGING_TURN_UP_ATR = 0.5`, `EMERGING_CONFIDENCE = 0.4`. All live in
`double_bottom_emerging.py`; a later calibration pass folds them into the SP4 report.

## Files

| File | Change |
|---|---|
| `tradingagents/dataflows/double_bottom_emerging.py` | NEW: detector + its three constants |
| `tradingagents/dataflows/chart_patterns.py` | MOD: `PatternStatus` Literal, `status_order`, the gated call |
| `tradingagents/dataflows/entry_assessment.py` | MOD: `emerging -> predictive_bottom` branch |
| `tradingagents/agents/analysts/market_analyst.py` | MOD (upstream, approved): one sentence |
| Tests | NEW `test_double_bottom_emerging.py` + additions to entry/pipeline/prompt tests; every new file ≤150 lines |

No SP1/SP2 modules change. `entry_rules.extract_levels` already handles `double_bottom`
(uses `min(first_extreme, second_extreme)`), so it needs no change.

## Non-goals

- No double-top emerging, no emerging for other structures.
- No change to `find_pivots` or `_double_patterns` geometry (emerging is additive/gated).
- No calibration of `EMERGING_*` constants (interim; future backtest read).
