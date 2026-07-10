# O'Neil Base-Pattern Expansion Design

**Goal:** Expand the O'Neil module from cup-with-handle-only to all six O'Neil base patterns —
cup-with-handle, cup-without-handle, flat base, double-bottom base, ascending base,
high-tight flag (HTF) — behind one shared breakout/status/confidence engine, with
most-advanced-wins arbitration and honest "base-pattern" (not "CANSLIM") report labeling.
CANSLIM fundamental screening (C/A/S/I/M) is a separate workstream, not this spec.

**Approach (chosen over per-pattern silos and chart_patterns.py reuse):** each pattern gets
its own ≤150-line detector file emitting a shared `BasePattern` result; the existing
`oneil_breakout.py` engine is generalized from `CupCandidate` to a pivot price; a thin
orchestrator arbitrates. O'Neil's double bottom is NOT merged into `chart_patterns.py`'s
generic double bottom: they share only the low-level geometry primitives (`Pivot`,
`find_pivots`, ATR — already shared imports), never tuning constants, so later O'Neil
calibration cannot silently change Tier-3 behavior. A prompt-level supersede rule (below)
makes them one pattern in the narration.

## Shared principles (unchanged from ONEIL_CANSLIM_ANALYSIS_PLAN.md)

Structure identified by code, LLM only explains it; no future data past `curr_date`;
adaptive thresholds (ATR/price/volume ratios, never fixed percentages — O'Neil's guideline
numbers below are calibration anchors, not hardcoded gates); every event carries dated,
priced, volume-narrated evidence; neutral allowed; `secondary_weight` stays 0.4 (tier
position in the Wyckoff > O'Neil > others chain is unchanged).

## Files

New (each ≤150 lines):

- `tradingagents/dataflows/oneil_base_types.py` — `BaseCandidate` dataclass for raw detector
  output: `pattern_type`, `pivot_price`, `pivot_date`, per-pattern `geometry` dict, `evidence`,
  and an optional handle reference. The shared engine produces a `PatternDetection` result
  with evaluated `status` and `confidence`.
- `tradingagents/dataflows/oneil_flat_base.py` — tight sideways range ≥ ~5 weeks, shallow
  depth (adaptive, guideline ≈ ≤15%), prior uptrend or prior completed base (base-on-base);
  pivot = base high.
- `tradingagents/dataflows/oneil_double_bottom.py` — W base, ~7-week minimum duration,
  prior uptrend, volume dry-up in the base; pivot = middle peak. Second low must land in an
  adaptive ATR band `[first_low - undercut_allowance, first_low + tolerance]`; behavior is
  classified `undercut` (confidence bonus; evidence narrates the shakeout), `equal`, or
  `higher` (still valid; too far above the band → no detection, other detectors may claim
  the structure). The undercut is a confidence modifier, never a validity gate.
- `tradingagents/dataflows/oneil_ascending_base.py` — three successive pullbacks, each low
  and each high above the last, ~9–16 week guideline, each pullback shallower than a cup;
  pivot = high of the third pullback.
- `tradingagents/dataflows/oneil_htf.py` — huge prior advance (guideline ≈ doubling in
  ≤ ~2 months, adaptive), then a short tight flag with shallow correction; pivot = flag high.
- `tradingagents/dataflows/oneil_base_patterns.py` — thin orchestrator: runs all detectors
  (incl. the existing cup path) and applies arbitration.

Modified (all project-custom, no upstream approval needed): `oneil_breakout.py`,
`oneil_bias.py`, `oneil_tools.py` (labeling), `market_analyst.py` (prompt),
`ONEIL_CANSLIM_ANALYSIS_PLAN.md` (status/labeling). `oneil_cup.py`/`oneil_handle.py` are
reused as-is; cup-without-handle is a status-machine change in `oneil_breakout.py`, not a
new detector.

## Shared engine (`oneil_breakout.py` generalization)

`find_breakout`/`_reversal_after`/`determine_status` take `pivot_price` +
`search_start_index` + optional handle instead of `CupCandidate`. Rules unchanged:
ATR-buffered close above pivot; volume ≥ adaptive ratio within a 3-bar confirmation window;
low-volume breakout stays `developing`, never immediately `failed`; post-breakout reversal
back through the pivot → `failed`. Statuses stay `none/forming/developing/confirmed/failed`;
each detector defines its own "forming" precondition stage (cup without right-side recovery,
flat base under minimum duration, ascending base with two pullbacks, HTF still in flagpole)
and the engine only handles complete-pattern → breakout transitions. A completed cup whose
right side breaks out with volume before any handle forms is `cup_without_handle`, valid at
a lower confidence base than `cup_with_handle`. Confidence keeps today's shape (status base
+ bounded bonuses, cap 0.95) plus a per-pattern base modifier (HTF highest, per O'Neil's own
pattern-power ranking; cup-with-handle above cup-without-handle) and the double-bottom
undercut bonus; volume/RS bonuses unchanged.

## Arbitration (most-advanced-wins)

Rank detections by status (`confirmed` > `developing` > `forming`), tie-break by confidence,
then by pivot-date recency. Winner drives `setup_bias`/`confidence`/`status`; losers go to
`other_detections` (type/status/confidence only) and never affect the bias. A `failed`
pattern never beats a live one; if everything failed, report the most recent failure with
`setup_bias: "neutral"` (a failed structure is stated as failed, not "no structure found").
Nothing detected → `primary_pattern: null`, `setup_bias: "neutral"`.

## JSON schema (breaking change, contained)

Top-level `cup`/`handle`/`breakout` keys are replaced by `primary_pattern` +
`other_detections`. Contract keys always present in `primary_pattern`: `pattern_type`,
`status`, `pivot_price`, `pivot_date`, `breakout` (nullable); `geometry` internals vary per
pattern (double bottom includes `second_low_behavior`; flat base: range high/low/tightness;
ascending base: three pullbacks; HTF: flagpole advance + flag depth). `handle` is populated
only for `cup_with_handle`. Only consumers are `market_analyst.py`'s prefetch-injected
prompt and the O'Neil tests — both updated in the same change; downstream agents read prose
`market_report`, so no compatibility shim.

## Market Analyst prompt (`market_analyst.py`, prompt text only)

- Rewrite the O'Neil paragraph for the new shape: name `pattern_type`, narrate the winning
  detector's dated/priced geometry and evidence, mention `other_detections` in at most one
  sentence, narrate `second_low_behavior` explicitly. Keep verbatim: no inventing patterns,
  no eyeballing structures from the raw CSV.
- Three-tier precedence rule unchanged; wording generalizes "cup-with-handle structure" →
  "base-pattern structure".
- Supersede rule (one sentence): when the O'Neil double-bottom base and the chart-pattern
  tool's generic double bottom cover the same lows, describe them as a single structure
  qualifying under O'Neil's stricter criteria at O'Neil's tier — never as two independent
  patterns confirming each other.
- Labeling sweep: "O'Neil base-pattern analysis" replaces "CANSLIM"/"cup-with-handle" in
  the prompt, Markdown-table row (`pattern_type`, `status`, `setup_bias`,
  `secondary_weight`), and `weight_note`. Internal identifiers (`analyze_oneil_setup`,
  `oneil_*` filenames) keep their names.

## Testing (synthetic OHLCV, `@pytest.mark.unit`)

- Per-detector files: textbook positive; a near-miss negative per hard gate; no-prior-uptrend
  rejection; double bottom covers all three `second_low_behavior` cases, the undercut bonus,
  and the too-far-above rejection; evidence-text assertions require narrated volume behavior.
- Engine regression: existing `test_oneil_breakout.py` behavior unchanged for cup pivots;
  new: cup-without-handle confirms below same-cup-with-handle confidence; low-volume breakout
  stays `developing` for a non-cup pattern.
- Arbitration: confirmed flat base beats forming HTF; ties broken by confidence then recency;
  all-failed → neutral with most recent failure; nothing → `primary_pattern: null`.
- `test_oneil_bias.py` rewritten for the new payload (contract keys, neutral case).
- `test_market_analyst_prefetch.py`: assert the new paragraph via a phrase unique to it
  (e.g. `second_low_behavior`), never a word already in the fixture JSON.
- Future-data leakage check per detector. Detectors reuse `prepare_ohlcv`; any detector
  needing more history than the cup's minimum enforces its own computed minimum row count
  with a `ValueError` (CLAUDE.md convention).
- Stage 4 (user-run, Antigravity opt-in): a non-cup primary pattern scenario, a supersede
  scenario if findable, a Wyckoff-conflict scenario.

## Codex model tiers per plan task

`oneil_base_types.py` + engine generalization: **terra**. Flat base: **terra**. Double
bottom: **terra**. Ascending base: **sol** (hardest geometry). HTF: **terra**. Orchestrator
+ `oneil_bias.py`: **terra**. Prompt/labeling/doc sweep: **luna**. Always pass
`-m gpt-5.6-<tier>` explicitly (config default is still gpt-5.5).

## Acceptance criteria

- All new and updated tests pass; `pytest -q` + `ruff check .` full pass (this change is
  cross-cutting within the O'Neil family and touches `market_analyst.py`).
- Report and JSON never say "CANSLIM"; primary-pattern narration names dated/priced events.
- No data after `curr_date` in any output; every detector rejects insufficient history
  loudly. `secondary_weight` still 0.4; Wyckoff precedence unchanged.

> Research/analysis support only; not investment advice; no trade execution.
