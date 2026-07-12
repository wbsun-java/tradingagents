# False-Breakout State Machine (SP2) — Design Spec

Date: 2026-07-11
Status: approved design, pre-implementation
Parent: `CHART_PATTERN_ANALYSIS_PLAN.md` (突破失败与更大结构 / 向上假突破后的做空信号 /
向下假跌破后的做多信号, lines ~250–300; asymmetry rules at ~159, 273, 296; acceptance
list at ~438–450)
Sub-project: SP2 of 4. SP1 (post-apex breakout, spec
`2026-07-11-post-apex-breakout-design.md`) landed commits f1dc292/914ee82/a91e468.
SP3 (entry taxonomy) consumes this machine's two signals; SP4 calibrates every
constant introduced here.

## Problem

All four breakout-failure sites in `chart_patterns.py` (triangles via
`find_reversal_index`, rectangles, double top/bottom, standalone S/R level breaks)
detect that a breakout reversed, mark the parent `failed`, and stop. The plan doc
requires the reversal itself to become an actionable opposite-direction signal —
`false_breakout_short` after an upward false break, `false_breakdown_long` after a
downward false break — with deterministic confirmation rules, an asymmetric fast path
for `late_apex_breakout`/`post_apex_breakout` parents, and side effects on the failed
parent (`structure_may_be_expanding`, cancelled target, boundary no longer trusted).

## Scope decisions (user-approved 2026-07-11)

1. **All boundary types in one pass**: triangles, rectangles, double top/bottom, and
   standalone S/R break signals all wire into one generic machine.
2. **Signals are first-class `PricePattern` entries** in the existing `patterns`
   list — no schema changes for reporting or downstream agents.
3. **Pending shorts are emitted** as `status="forming"` entries (watchlist
   semantics, like every other forming pattern).
4. **Architecture A**: generic state machine + thin per-pattern adapters; SP1's
   `find_reversal_index` is reused as the universal stage-1 re-entry detector
   (horizontal boundaries call it with slope 0 and an effectively infinite
   `apex_index`, so its apex freeze is a no-op there).

## The machine

Inputs per confirmed parent breakout: breakout bar index, break direction, boundary
(slope/intercept pair — constant level for horizontal patterns), ATR `buffer`,
parent `risk_flags`, and the OHLCV frame.

### Stage 1 — re-entry

First close back inside the boundary beyond the effective buffer. Parents flagged
`late_apex_breakout`/`post_apex_breakout` keep SP1's landed asymmetry: half buffer
inside SP1's `post_apex_window_bars` window (this is exactly what
`find_reversal_index` already computes). The machine emits a signal only when the
re-entry occurs within `REENTRY_WINDOW_BARS = 10` bars of the breakout — a reversal
that takes longer is not a tradable false break. Parent-failure detection itself
stays exactly as it is today (unbounded search): a late reversal still marks the
parent `failed`, it just produces no signal. The window caps signal emission, never
parent status.

### Stage 2 — confirmation (asymmetric by direction, per the plan doc)

**Upward false break → `false_breakout_short` (direction bearish):**

- At re-entry: emit `forming`.
- Within `CONFIRM_WINDOW_BARS = 8` bars after re-entry, flip to `confirmed` when
  either trigger fires: (a) a close below the pullback low — the lowest Low from the
  breakout bar through the re-entry bar; or (b) a failed retest — a bar whose High
  reaches within `buffer` of the boundary from below but whose Close stays below the
  boundary.
- Parents flagged late/post-apex: `confirmed` immediately at the re-entry bar
  (aggressive tier); reversal is their default expectation.
- Window expires unconfirmed → the forming entry simply remains `forming` in that
  run's output; later runs past the window emit nothing.

**Downward false break → `false_breakdown_long` (direction bullish):**

- `confirmed` at the **aggressive tier at the re-entry bar itself**, guarded by
  no-continued-new-lows: the post-breakdown trough (lowest Low between breakdown and
  re-entry) must occur at least `NO_NEW_LOW_GRACE_BARS = 2` bars before the re-entry
  bar. Guard fails → emit nothing yet; a later qualifying re-entry may still fire.
- Upgrades to the standard tier (higher confidence, flag removed) when a close takes
  out the rebound high (highest High between breakdown and re-entry) or a retest
  holds: a bar whose Low stays ≥ boundary − buffer and whose Close ≥ boundary.
- No forming state on the long side: re-entry itself confirms (aggressive).

### Volume

Compare the re-entry/trigger bar's volume to the trailing 20-bar average (same
mechanism as `_volume_confirmation`). Expansion → `+0.05` confidence AND a narrated
evidence sentence. Contraction → never a penalty; for longs the evidence states it
may reflect exhausted selling pressure. Volume must always be narrated in evidence
text, never left as a silent number. Price structure decides; volume only adjusts.

## Output entries

Each emitted signal is a `PricePattern`:

- `pattern`: `"false_breakout_short"` / `"false_breakdown_long"`; `direction`:
  `"bearish"` / `"bullish"`; `status`: `"forming"` / `"confirmed"`.
- `risk_flags`: `["aggressive_confirmation"]` when confirmed at the aggressive tier
  (a genuine caveat — less structural proof); removed on standard upgrade.
- `levels`: `boundary_price`, `false_break_extreme` (the breakout's highest High /
  lowest Low outside the boundary), `reentry_close`, `trigger_price` (pullback low /
  rebound high when applicable).
- `target_price`: the parent pattern's opposite boundary (no measured extension —
  the structure may be expanding). `invalidation_price`: beyond the false-break
  extreme.
- `confidence`: forming 0.45; confirmed 0.60 standard / 0.55 aggressive; +0.05
  volume expansion; clamped [0.2, 0.9].
- `evidence`: dated/priced sentences for breakout, false-break extreme, re-entry,
  trigger, volume, and the parent linkage (e.g. "reverses the failed
  symmetrical_triangle breakout of 2026-05-03").
- `start_date` = parent breakout bar; `end_date` = the signal's latest state-change
  bar.

## Parent side effects

- Parent stays `failed` with its existing reversal flags; gains
  `structure_may_be_expanding`.
- Parent `target_price` must be `None` once failed (verify existing paths; enforce
  where any failed path still carries a target).
- "Boundary no longer reliable S/R" is narrative only — conveyed by the flags and
  the signal's evidence; no S/R-clustering code changes in SP2.
- Existing tests that assert exact `risk_flags` lists on failed patterns will be
  updated for the new flag — a deliberate, enumerated change in the plan.

## Constants (all SP4 calibration knobs, exact names)

`REENTRY_WINDOW_BARS = 10`, `CONFIRM_WINDOW_BARS = 8`, `NO_NEW_LOW_GRACE_BARS = 2`,
retest tolerance = `1.0 × buffer` (expressed via the existing ATR buffer, no new
constant), confidence table above as named constants.

## Files

| File | Change |
|---|---|
| `tradingagents/dataflows/false_break_types.py` | NEW: signal dataclasses + constants |
| `tradingagents/dataflows/false_break_rules.py` | NEW: pullback-low / rebound-high / retest / no-new-low / volume detectors |
| `tradingagents/dataflows/false_break_machine.py` | NEW: stage-1 + stage-2 orchestration → signal or None |
| `tradingagents/dataflows/false_break_patterns.py` | NEW: signal → `PricePattern` + parent mutation |
| `tradingagents/dataflows/chart_patterns.py` | MOD: wire the four failure sites |
| Tests | NEW file per new module + pipeline tests; every file ≤150 lines, budgets fixed at plan time |

No upstream files are touched. `triangle_post_apex.py` is consumed, not modified.

## Non-goals

- No entry-state taxonomy (`predictive_bottom`/`breakout_entry`/… — SP3).
- No longer-window re-detection of larger structures (each analysis run already
  re-detects; the flag is the hand-off).
- No threshold calibration (SP4 sweeps every constant above).
