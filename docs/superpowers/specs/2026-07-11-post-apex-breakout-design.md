# Post-Apex Triangle Breakout (SP1) — Design Spec

Date: 2026-07-11
Status: approved design, pre-implementation
Parent: `CHART_PATTERN_ANALYSIS_PLAN.md` (apex rules, lines ~140–161, 430–437)
Sub-project: SP1 of 4 (SP2 false-breakout state machine, SP3 entry taxonomy,
SP4 backtest calibration follow)

## Problem

`classify_triangle_breakout` (`tradingagents/dataflows/triangle_breakout.py`)
searches for breakouts only strictly before the theoretical apex. Any move
after the apex is immediately classified `triangle_expired_at_apex` / `failed`.
The plan doc requires a third timing class: a breakout occurring *after* the
trendlines have crossed (`breakout_progress > 100%`) must be reported as
`confirmed` with a `post_apex_breakout` risk flag — riskier than
`late_apex_breakout` — inside a finite post-apex window, with all price
references anchored to the apex intersection value (extrapolating crossed
trendlines produces meaningless levels).

## Scope decisions (user-approved 2026-07-11)

1. **Interim simple reversal.** The full lowered-threshold false-breakout
   confirmation belongs to SP2's state machine. SP1 ships a simple interim
   asymmetric reversal (below) that SP2 later replaces.
2. **Window = fraction of triangle length.** Adaptive to pattern scale, per
   project convention; the fraction is an SP4 calibration knob.
3. **Target anchored at apex.** `target = apex_price ± start_gap`, not
   breakout close.
4. **Structure = new module `triangle_post_apex.py`** owning all post-apex
   logic; `triangle_breakout.py` delegates; `chart_patterns.py` gets one
   small target branch.

## Behavior

### Detection

- Pre-apex search unchanged. Post-apex search runs only when the pre-apex
  search found no breakout and bars exist at/after `apex_index`.
- Window: `POST_APEX_WINDOW_FRACTION = 0.15` of the base-to-apex bar
  distance, clamped to `[POST_APEX_WINDOW_MIN_BARS = 3,
  POST_APEX_WINDOW_MAX_BARS = 10]` bars after `ceil(apex_index)`.
  All three are module constants, placeholders pending SP4 calibration.
- `apex_price` = either trendline evaluated at `apex_index` (they are equal
  there). Break test uses the same ATR-based `buffer` as pre-apex:
  - close > `apex_price + buffer` → bullish `confirmed`,
    `risk_flags = ["post_apex_breakout"]`
  - close < `apex_price - buffer` → bearish, same flag
- `breakout_progress` keeps its existing formula and therefore reads > 1.0.
- Inside the window, no break yet → status stays `forming`; evidence states
  the apex has passed and a finite post-apex watch window is active.
- Window exhausted with no valid break → `failed` +
  `triangle_expired_at_apex` (today's behavior, just deferred to window end).
- `timing_adjustment = POST_APEX_TIMING_ADJUSTMENT = -0.4` (strictly below
  the worst late-apex adjustment of -0.3, per the plan doc's ordering).
- Timing evidence must narrate, in words (not only a flag): the triangle is
  past its theoretical apex; this breakout is statistically more likely a
  false break, with elevated odds of being pushed back within a few sessions.

### Levels, target, invalidation

- `upper_level = lower_level = apex_price` for post-apex breakouts. The
  existing `chart_patterns._triangle_pattern` invalidation assignment
  (opposite frozen boundary) therefore yields the apex price with no change.
- Target: when `"post_apex_breakout"` is in `risk_flags`,
  `target = apex_price + start_gap` (bullish) / `apex_price - start_gap`
  (bearish). Otherwise unchanged. Implemented as one small branch in
  `chart_patterns.py`; `apex_price` is recoverable as the (equal) frozen
  levels already returned on the dataclass.

### Interim asymmetric reversal (SP2 placeholder)

Applies to confirmed breakouts flagged `late_apex_breakout` OR
`post_apex_breakout`:

- Within `reversal window` = the same computed post-apex window length,
  counted from the breakout bar: a close back through the frozen boundary at
  `REVERSAL_BUFFER_FRACTION = 0.5` of the normal buffer confirms reversal →
  `failed` + `breakout_reversed_back_through_triangle`.
- After that window: the existing full-buffer, unbounded reversal check
  continues unchanged. Nothing that fails today stops failing; flagged
  breakouts only become *easier* to fail early.
- The frozen boundary for post-apex breakouts is `apex_price` itself;
  for late-apex it remains the `_line_before_apex` frozen value.
- SP2's false-breakout state machine replaces this entire path; the design
  intent (lower threshold, shorter window, reversal-as-default-expectation)
  is per plan doc lines ~159, 273, 296.

## Files

| File | Change |
|---|---|
| `tradingagents/dataflows/triangle_post_apex.py` | NEW (≤150 lines): window computation, post-apex break search, interim asymmetric reversal, and the timing-evidence/adjustment block relocated from `triangle_breakout.py` (it must learn the post-apex case anyway) |
| `tradingagents/dataflows/triangle_breakout.py` | MOD: delegate to the new module; stays ≤150 lines via the timing-block move; `TriangleBreakout` dataclass unchanged |
| `tradingagents/dataflows/chart_patterns.py` | MOD: one branch anchoring target at apex when the flag is present |
| `tests/test_triangle_post_apex.py` | NEW (≤150 lines): new coverage below |
| `tests/test_triangle_breakout.py` | MOD: update the two tests whose asserted behavior SP1 deliberately changes |

No upstream files are touched.

## Testing

Updated (existing file):

- `test_post_apex_move_does_not_confirm_an_expired_triangle` — a post-apex
  buffered break inside the window now confirms with the flag.
- `test_no_breakout_at_apex_expires_the_triangle_immediately` — expiry now
  happens after the window, not at the apex bar.

New (`test_triangle_post_apex.py`):

- Post-apex break inside window → `confirmed`, flag present, both levels =
  apex price, `breakout_progress > 1.0`, `timing_adjustment == -0.4`.
- No break, window exhausted → `failed` + `triangle_expired_at_apex`.
- No break, still inside window → `forming` with post-apex evidence text.
- Post-apex reversal at half buffer (would NOT trip full buffer) → `failed`
  + reversal flag; the same close outside the reversal window does not.
- Late-apex breakout reversal at half buffer inside window → `failed`
  (asymmetry applies to both flags).
- `chart_patterns` integration: post-apex target = apex ± start_gap,
  invalidation = apex price.

## Non-goals

- No false_breakout_short / false_breakdown_long signals (SP2).
- No emerging stage or entry-state taxonomy (SP3).
- No threshold calibration; every new constant is a named placeholder that
  `scripts/backtest_chart_patterns.py` will sweep in SP4.
