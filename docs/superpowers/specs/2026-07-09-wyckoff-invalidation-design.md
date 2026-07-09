# Wyckoff Breakout-Failure (Invalidation) Detection

Date: 2026-07-09

## Purpose

Per `WYCKOFF_ANALYSIS_PLAN.md`'s "后续迭代" item 3 ("复杂结构处理"). Investigation
found the literal item description (multi-range/composite detection) is
already mostly handled today: `detect_trading_range` prefers the most
recently touched candidate and excludes a candidate once price has drifted
more than one range-width away, so a genuinely new, already-formed range
naturally out-competes a stale one. The real gap is narrower and more
concrete: once `detect_events` reaches Phase D or E (Sign-of-Strength, Last
Point, Back-Up all imply price broke out of the range in the read's
direction), nothing checks whether that breakout *held*. If price later
reverses all the way back through the original range boundary, the module
still reports `"status": "confirmed"` with the original `phase_bias` and a
same-or-higher `confidence` — presenting a dead call as live. This design
adds that check.

## Scope

- Applies to: a new `tradingagents/dataflows/wyckoff_invalidation.py`
  (detection logic) and its test file; small edits to
  `tradingagents/dataflows/wyckoff_accumulation.py`,
  `tradingagents/dataflows/wyckoff_distribution.py` (thread the check
  through, add an `invalidated` field to each result dataclass), and
  `tradingagents/dataflows/wyckoff_bias.py` (override `phase_bias`/
  `confidence`/`status` and add the `invalidated` key when triggered, skip
  VSA when invalidated).
- Does not apply to: `wyckoff_range.py`, `wyckoff_events.py` (both untouched
  — `wyckoff_events.py` is already at the 150-line cap, so new logic goes in
  a new file rather than growing it, matching the Stage 1/Stage 2 VSA
  precedent), `market_analyst.py`, `trading_graph.py` (tool signature/prompt
  wiring unchanged — this rides inside the same JSON string
  `get_wyckoff_structure` already returns).
- Out of scope (not part of this design): detecting or reporting a *second*,
  newly-forming range after the first fails (per the investigation above,
  `detect_trading_range` already tends to surface a new range once it has
  its own two-touch confirmation; there's no evidence today's algorithm
  actively fails at this, so it isn't touched); invalidation checks for
  Phase A/B/C reads (a Spring reversing back inside the range is expected,
  healthy structure, not a failure — see "Design" below); walk-forward
  calibration of the new invalidation buffer (would ride the existing
  `scripts/backtest_wyckoff.py` naturally once this ships, not a new script).

## Approaches considered

1. **New `wyckoff_invalidation.py` file, wired into the accumulation/
   distribution wrappers** (chosen). Keeps `wyckoff_events.py` at its current
   150 lines instead of pushing it over the cap, and mirrors the Stage 2 VSA
   precedent (`wyckoff_vsa.py` also stayed separate from `wyckoff_events.py`
   rather than growing it).
2. Add the check directly inside `detect_events` in `wyckoff_events.py`.
   Rejected: that file is already exactly at the 150-line cap; this would
   grow it past the limit for logic that's conceptually a separate concern
   (event *sequence* detection vs. post-hoc *outcome* checking).
3. Detect and report a second range/full composite structure (the literal
   plan wording). Rejected per the Scope section above — investigation shows
   the existing candidate-selection logic already handles the common case,
   and building explicit multi-range tracking now would be speculative
   complexity without a demonstrated gap.

## Design

### What counts as invalidation

Only checked when `detect_events` returns Phase `"D"` or `"E"` — those are
the only phases where a breakout claim (`sign_of_strength`) actually exists
to invalidate. Phases `undetermined`/`A`/`B`/`C` are untouched: a Spring/
Upthrust reversing back *inside* the range at Phase B/C is expected,
healthy structure (the code already requires the Spring's close back inside
the range as part of qualifying it as a Spring at all), not a failure.

For a qualifying phase, scan bars strictly after the last event in the
`events` list (whichever of `sign_of_strength`/`last_point_of_support(or
supply)`/`back_up(or upthrust)` was most recently detected) through the end
of the frame. Accumulation is invalidated by the first bar whose `Close`
closes back below `rng.range_low - buffer`; distribution by the first bar
whose `Close` closes back above `rng.range_high + buffer` (`buffer = atr_value
* 0.2`, the same constant `detect_events` already uses). This mirrors the
existing single-bar-close convention `detect_events` uses for `sign_of_strength`
itself (no multi-bar confirmation window) — consistent with the rest of the
module rather than a new convention.

### `wyckoff_invalidation.py`

```
def check_invalidation(
    df: pd.DataFrame,
    atr_value: float,
    rng: TradingRange,
    direction: Literal["accumulation", "distribution"],
    events: list[WyckoffEvent],
    phase: Phase,
) -> WyckoffEvent | None:
```

- Returns `None` immediately if `phase not in ("D", "E")` or `events` is
  empty.
- Otherwise scans from `events[-1]`'s bar index onward for the first
  disqualifying close described above; returns a `WyckoffEvent` (reusing the
  existing dataclass from `wyckoff_events.py`) named `"range_failure"` with
  date/price/volume_ratio/evidence text (e.g. `"Price closed back below the
  original range low of 82.10 on 2026-03-01, giving back the prior
  breakout — this accumulation read no longer holds."`), or `None` if no
  such bar exists.

### Wiring into the wrappers

`AccumulationResult`/`DistributionResult` gain a new field:
`invalidated: bool = False`. In `analyze_accumulation`/`analyze_distribution`,
after `detect_events` returns `(events, phase)`:

```python
failure = check_invalidation(df, atr_value, rng, "accumulation", events, phase)
if failure is not None:
    events = [*events, failure]
return AccumulationResult(events=events, phase=phase, confidence=confidence_for(events, phase), invalidated=failure is not None)
```

(mirrored for distribution). The failure event is appended to the same
`events` list already surfaced in the JSON — no new top-level array.

### Wiring into `wyckoff_bias.py`

In `_payload`, when `result.invalidated` is `True`:

- `trading_range.status` is forced to `"invalidated"` (a new value alongside
  the existing `forming`/`developing`/`confirmed`) instead of whatever
  `_STATUS_BY_PHASE` would otherwise map the phase to.
- `phase_bias` is forced to `"neutral"` — the existing `weight_note` text
  ("...unless `phase_bias` is neutral/undetermined") already tells
  downstream consumers not to weight a neutral read, so no wording change is
  needed there.
- `confidence` is forced to `0.0`.
- `current_phase` is left as the actual reached phase (`"D"` or `"E"`) —
  it's a true historical fact (the event sequence really did happen), only
  the *live* call is being withdrawn.
- A new top-level key `"invalidated": true` is added (always present,
  `true`/`false`) so a consumer can branch on it without scanning `events`
  for a `"range_failure"` entry.
- `analyze_vsa` is **not called** when invalidated — mirrors the existing
  `_neutral()` branch, which also skips VSA. There's no live directional
  call left for VSA to adjust the confidence of.

Non-invalidated reads are completely unaffected: `"invalidated": false` is
still added for schema consistency (every non-neutral read gets the key,
same as `vsa_signals`/`vsa_confidence_delta` today), but nothing else about
`_payload`'s existing behavior changes.

### Output schema example

```json
{
  "trading_range": {"kind": "accumulation", "status": "invalidated", ...},
  "events": [
    {"event": "selling_climax", ...},
    {"event": "sign_of_strength", ...},
    {"event": "last_point_of_support", ...},
    {"event": "back_up", ...},
    {
      "event": "range_failure",
      "date": "2026-03-01",
      "price": 82.10,
      "volume_ratio": 1.4,
      "evidence": ["Price closed back below the original range low of 82.10 on 2026-03-01, giving back the prior breakout — this accumulation read no longer holds."]
    }
  ],
  "current_phase": "E",
  "phase_bias": "neutral",
  "confidence": 0.0,
  "invalidated": true,
  "dominant_weight": 0.6,
  "weight_note": "..."
}
```

## Testing plan

New `tests/test_wyckoff_invalidation.py`:

- A synthetic Phase-E accumulation sequence with a later bar closing below
  `range_low - buffer` → `check_invalidation` returns a `range_failure`
  event with correct date/price.
- The same sequence without that later reversal → returns `None`.
- Distribution mirror of both cases (closing back above `range_high +
  buffer`).
- Phase `"C"` (no Sign-of-Strength reached) with a later close beyond either
  boundary → returns `None` (invalidation only applies to D/E).
- Empty `events` list → returns `None` (guards against an empty-list
  `events[-1]` crash).

Additions to `tests/test_wyckoff_bias.py`:

- A synthetic accumulation read engineered to reach Phase E and then reverse
  → payload has `"invalidated": true`, `"phase_bias": "neutral"`,
  `"confidence": 0.0`, `"trading_range"]["status"] == "invalidated"`, and no
  `vsa_signals`/`vsa_confidence_delta` keys (VSA skipped).
- The existing accumulation/distribution fixtures (which don't reverse)
  still get `"invalidated": false` and unchanged `phase_bias`/`confidence`
  behavior — a regression check that the new field doesn't alter existing
  passing tests' assertions.

## Acceptance criteria

- No detection logic in `wyckoff_range.py`/`wyckoff_events.py` changes.
- `wyckoff_events.py` stays at 150 lines (untouched).
- New `wyckoff_invalidation.py` stays at or under 150 lines (new-file cap).
- A Phase D/E read that reverses through the original boundary is reported
  with `phase_bias: "neutral"`, `confidence: 0.0`, `status: "invalidated"`,
  and `invalidated: true` — never presented as a live confirmed directional
  call.
- All existing Wyckoff/VSA/market-analyst tests still pass unmodified.
- No future-data leakage: the invalidation scan only ever looks at bars
  already inside the `df` passed in (which is itself already truncated to
  `curr_date` by `prepare_ohlcv`).

> This module is for research and analysis support only; it does not
> constitute investment advice and does not place trades.
