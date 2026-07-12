# Entry-State Taxonomy (SP3) — Design Spec

Date: 2026-07-12
Status: approved design, pre-implementation
Parent: `CHART_PATTERN_ANALYSIS_PLAN.md` (交易状态与入场规则, lines ~163–317; output
schema at ~298–315; acceptance list ~441–485)
Sub-project: SP3 of 4. SP1 (post-apex) and SP2 (false-break machine) landed;
SP3 consumes SP2's two signals. SP4 calibrates every constant introduced here.

## Problem

The pattern layer answers *what the structure is* (`forming`/`confirmed`/`failed`), but
recognizing a pattern is not a trade signal — price in the middle of a structure has no
positional edge. The plan doc requires a deterministic **trading layer** that classifies
each detected pattern into an actionable entry state based on where current price sits,
so the LLM explains a state rather than inventing a buy from a shape.

## Scope decisions (user-approved 2026-07-12)

1. **Layer A only; defer the emerging stage.** SP3 is a read-only trading layer over
   patterns as already detected (using only confirmed pivots/levels). The `emerging`
   second-bottom candidate stage (which changes pivot/double-bottom detection geometry)
   is deferred to a later **SP3b**. `predictive_bottom` still fires, but only on forming
   structures whose bottom boundary is already a confirmed pivot/level.
2. **Long-biased taxonomy, matching the plan doc.** Normal bearish/downside setups map to
   `avoid` (no long opportunity); the only contrarian states are SP2's two signals. No new
   trend-short states.
3. **New nested field on every PricePattern.** `entry_assessment` is added to the
   `PricePattern` dataclass; every pattern carries one, including SP2's signals (whose
   state echoes their pattern name). One place to look; uniform for the LLM.
4. **Prompt wiring included** (upstream edit approved for SP3 only): extend the existing
   chart-pattern paragraph in `market_analyst.py` so the LLM treats `entry_assessment.state`
   as authoritative and never rewrites `observe`/`avoid` into a buy.

## Architecture — Approach A (centralized post-pass)

The pattern layer is unchanged. A new trading layer runs as a single post-pass in
`analyze_chart_patterns_from_data`: after all patterns (including SP2 signals) are
collected, one loop calls `assess_entry(df, pattern, atr, current_close)` and attaches the
result. Entry logic lives in one testable place; `chart_patterns.py` gains only the field
and the loop.

### Level extractor (per pattern type → four generic levels)

| Pattern | bottom_boundary | breakout_level (=top) | failure_level |
|---|---|---|---|
| `double_bottom` | min(first, second) low | `neckline` | `invalidation_price` |
| `ascending`/`symmetrical_triangle` (bullish/neutral) | `lower_trendline` | `upper_trendline` | `lower_trendline` − buffer |
| `rectangle` | `support` | `resistance` | `support` − buffer |
| `resistance_breakout` | `broken_level` (now support) | `broken_level` | `invalidation_price` |

`buffer = 0.2·ATR` (existing chart-pattern buffer; no new constant).

### State decision tree (`PROX = ENTRY_PROXIMITY_ATR · ATR`, current close `C`)

**Eligibility** keys off `direction`, not just name: a pattern is **long-eligible** when it
is one of the four types above **and** `direction ∈ {bullish, neutral}`; a pattern is
**bearish-eligible** (→ `avoid`) when `direction == bearish` **or** it is an inherently
bearish type (`double_top`, `descending_triangle`, `support_breakdown`). This routes a
`rectangle` or `symmetrical_triangle` that resolves downward to `avoid` without a special
case.

**Long-eligible patterns:**

1. `status == failed` → **avoid** (a reversed break is already covered by SP2's signal).
2. `status == confirmed` (valid upward break):
   - A post-breakout bar's Low returned within `PROX` of `breakout_level`, `C ≥
     breakout_level` (holding), and that pullback bar was low-volume, inside a
     `RETEST_WINDOW_BARS` window → **breakout_retest_entry**.
   - else `C ≤ breakout_level + PROX` (fresh, still near the level) → **breakout_entry**.
   - else (extended above with no retest) → **observe**.
3. `status == forming` (no breakout yet):
   - `C` within `PROX` of `bottom_boundary` **and** `C > failure_level` →
     **predictive_bottom**.
   - else → **observe**.

**Bearish-eligible patterns** (per the eligibility rule above) → **avoid** at any status.

**SP2 signal patterns** (`false_breakout_short`, `false_breakdown_long`) → `state` = the
pattern's own name; zones/trigger/invalidation passed through from the signal's levels.

Fallback: anything unmatched → **observe** (never a default buy).

## Output — the `entry_assessment` field

Each PricePattern gains `entry_assessment: EntryAssessment` with:

- `state`: one of `predictive_bottom` / `breakout_entry` / `breakout_retest_entry` /
  `observe` / `avoid` / `false_breakout_short` / `false_breakdown_long`.
- `direction`: `long` (three long entries + `false_breakdown_long`), `short`
  (`false_breakout_short`), or `none` (`observe`/`avoid`).
- `entry_zone_low`, `entry_zone_high`: the actionable zone (`None` for observe/avoid).
  - predictive_bottom: `[bottom_boundary − PREDICTIVE_UNDERSHOOT_ATR·ATR, bottom_boundary + PROX]`.
  - breakout_entry / breakout_retest_entry: `[breakout_level, breakout_level + PROX]`.
  - SP2 signals: from `boundary_price`/`false_break_extreme`.
- `trigger_price`: the level that arms the entry (`bottom_boundary`, `breakout_level`, or
  the SP2 `trigger_price`); `None` for observe/avoid.
- `invalidation_price`: the structure's `failure_level` for longs; SP2 invalidation for
  signals; `None` for observe/avoid.
- `confirmation`: one dated/priced sentence describing what confirms the state.
- `volume_role`: `expansion_preferred` (breakout_entry), `low_volume_preferred`
  (breakout_retest_entry), `supporting_not_required`
  (predictive_bottom / false_breakdown_long), or `not_applicable` (observe/avoid).

The field is always present; `observe`/`avoid` carry null zones and a one-line reason.

## Constants (all SP4 calibration knobs, exact names)

`ENTRY_PROXIMITY_ATR = 0.5`, `RETEST_WINDOW_BARS = 15` (min lookback 2),
`PREDICTIVE_UNDERSHOOT_ATR = 0.25`, low-volume test reuses the existing 20-bar volume
baseline (no new constant).

## Prompt wiring (upstream, approved)

Extend `market_analyst.py`'s existing chart-pattern paragraph: name the seven states,
state that `entry_assessment.state` is a deterministic verdict the LLM may only explain,
that `observe`/`avoid` must never be described as an immediate buy, and that the two
false-break states are contrarian reversal signals, not continuation entries.

## Files

| File | Change |
|---|---|
| `tradingagents/dataflows/entry_types.py` | NEW: `EntryAssessment` dataclass + state/tuning constants |
| `tradingagents/dataflows/entry_rules.py` | NEW: level extractor + predicates (near_boundary, retest_hold, low_volume_pullback, is_extended) |
| `tradingagents/dataflows/entry_assessment.py` | NEW: `assess_entry(df, pattern, atr, current) -> EntryAssessment` orchestrator |
| `tradingagents/dataflows/chart_patterns.py` | MOD (custom): add `entry_assessment` field + the post-pass loop |
| `tradingagents/agents/analysts/market_analyst.py` | MOD (upstream, approved): extend the chart-pattern paragraph |
| Tests | NEW file per new module + a pipeline test; every file ≤150 lines, budgets fixed at plan time |

No other upstream files are touched. SP2's modules are consumed unchanged.

## Non-goals

- No `emerging` second-bottom stage / pivot-detection changes (SP3b).
- No symmetric trend-short states (`breakdown_entry`/…) — bearish trend setups are `avoid`.
- No threshold calibration (SP4 sweeps every constant above).
