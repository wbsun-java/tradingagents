# Wyckoff Stage 2: Volume Spread Analysis (VSA)

Date: 2026-07-09

## Purpose

Stage 1 of the Wyckoff module (`wyckoff_range.py`, `wyckoff_events.py`,
`wyckoff_accumulation.py`, `wyckoff_distribution.py`, `wyckoff_bias.py`) is
complete and live in Market Analyst. Per
`WYCKOFF_ANALYSIS_PLAN.md`'s "后续迭代" section, Stage 2 adds Volume Spread
Analysis: per-bar effort-vs-result scoring that adjusts Stage 1's
`confidence` value, without replacing or overriding the structural
(range/event/phase) read Stage 1 already produces.

## Scope

- Applies to: two new files (`tradingagents/dataflows/wyckoff_vsa_signals.py`,
  `tradingagents/dataflows/wyckoff_vsa.py`), a small edit to the existing
  `tradingagents/dataflows/wyckoff_bias.py` (wiring only), and a new test file
  (`tests/test_wyckoff_vsa.py`) plus additions to the existing
  `tests/test_wyckoff_bias.py`.
- Does not apply to: `market_analyst.py`, `trading_graph.py`,
  `wyckoff_tools.py` — the tool signature and prompt wiring are unchanged;
  `vsa_signals` rides inside the same JSON string `get_wyckoff_structure`
  already returns. All touched/added files are project-custom (created
  2026-07-01 through 2026-07-07 for Stage 1), not upstream, so no
  upstream-file approval gate applies.
- Out of scope (deferred to a later iteration, not part of this design):
  walk-forward calibration of the ±0.05/±0.15 constants and `dominant_weight`
  (item 2 in the plan's "后续迭代"); extending Wyckoff weighting into
  bull/bear researcher or risk-debate prompts (item 4 — explicitly flagged in
  the plan as requiring separate user approval since it touches upstream
  files); complex/multi-range structure handling (item 3).

## Approaches considered

1. **Two-file split: detectors + orchestrator** (chosen). `wyckoff_events.py`
   (Stage 1's equivalent shared engine) is already exactly 150 lines. The
   full classic VSA set (8 signals, each with evidence text) would likely
   exceed the 150-line-per-new-file cap in a single file. Splitting pure
   per-bar detection (`wyckoff_vsa_signals.py`) from range-window filtering /
   confirming-contradicting tagging / confidence-delta computation
   (`wyckoff_vsa.py`) mirrors the existing Stage 1 split
   (range/events engine/accumulation+distribution thin wrappers/bias
   aggregator) and keeps each file single-purpose.
2. Single `wyckoff_vsa.py` holding detection + orchestration + scoring.
   Rejected: would likely blow past 150 lines with 8 signals, forcing either
   terser/less-readable code or dropping signals from the chosen "full
   classic VSA set" scope.
3. Fold VSA detection and scoring directly into `wyckoff_bias.py`. Rejected:
   turns a thin ~96-line aggregator into a large mixed-responsibility file,
   breaking the pattern the rest of the module follows.

## Design

### Architecture & data flow

- **`wyckoff_vsa_signals.py`**: pure per-bar detector functions. Each takes a
  bar (OHLCV) plus its ATR and 20-day-average-volume context and returns a
  signal dict (`{"signal": ..., "evidence": [...]}`) or `None`. No knowledge
  of trading ranges, phase_bias, or confidence — purely "does this bar match
  this pattern."
- **`wyckoff_vsa.py`**: thin orchestrator. Signature:
  `analyze_vsa(df, atr_value, rng, phase_bias, curr_date) -> tuple[list[dict], float]`.
  Slices bars to `[rng.start_date, curr_date]`, runs each detector per bar,
  tags each hit `confirming`/`contradicting` against `phase_bias`, computes
  the bounded confidence delta. Returns `(vsa_signals, confidence_delta)`.
- **`wyckoff_bias.py`** wiring: after `analyze_accumulation`/
  `analyze_distribution` resolves a non-neutral read (i.e. inside the
  existing `if accumulation is not None: ... elif distribution is not None: ...`
  branches in `analyze_wyckoff_structure_from_data`), call `analyze_vsa` with
  the already-prepared `df`/`atr_value`/`rng`, merge `vsa_signals` into the
  payload, and apply `confidence_delta` to the payload's `confidence`
  (clamped to `[0.0, 1.0]`). When Stage 1 is neutral (`_neutral()` branch),
  VSA is skipped entirely and no `vsa_signals` key appears — VSA is an aid to
  an existing structural read, never a standalone signal (plan principles
  1 and 6).
- No new vendor/network calls: VSA reuses the OHLCV frame and ATR value
  Stage 1 already computed via `load_ohlcv`/`prepare_ohlcv`/`atr` — no extra
  fetch, no new caching concern.

### Signal set

Eight classic VSA signals, each checked only in the variant matching
`phase_bias` (bullish variant when `phase_bias == "bullish"`, bearish variant
when `"bearish"`) so evidence text is always unambiguous about which reading
it supports — avoiding the earlier Stage 1 NKE bug where evidence text
assumed a volume characteristic that didn't hold for the actual bar.

All thresholds are adaptive (ATR for spread, 20-day average for volume),
consistent with plan principle 3:

| Signal | Criteria |
|---|---|
| No-demand | Up bar, spread < 0.5×ATR, volume < 20-day avg |
| No-supply | Down bar, spread < 0.5×ATR, volume < 20-day avg |
| Stopping volume | Down bar, spread > 1.5×ATR, volume > 2×avg, closes upper half of bar range |
| Climax bar | Volume > 3×avg, wide spread, at a local price extreme (reuses Stage 1's volume-ratio math) |
| Effort-no-result (up) | Volume > 1.5×avg, narrow spread, closes near bar low |
| Effort-no-result (down) | Volume > 1.5×avg, narrow spread, closes near bar high |
| Test bar | Narrow spread, volume < 20-day avg, near a prior low (bullish) / prior high (bearish), closes off that extreme |
| Upthrust/shakeout-on-volume | Wide-range bar piercing range boundary intrabar, closes back inside, above-average volume |

### Confirming/contradicting and confidence adjustment

Each signal has a native direction: no-supply, stopping-volume, and
effort-no-result-up are bullish tells; no-demand and effort-no-result-down
are bearish tells; climax bar, test bar, and upthrust/shakeout take the
direction of the bar/context they occur in. A signal is `confirming` if its
native direction matches `phase_bias`, else `contradicting`.

- Each confirming signal: `+0.05` to the running delta.
- Each contradicting signal: `-0.05` to the running delta.
- Running delta (sum across all bars in the range window) is clamped to
  `[-0.15, +0.15]`.
- Final `confidence = clamp(stage1_confidence + delta, 0.0, 1.0)`.

### Output schema

`vsa_signals` is added to the `get_wyckoff_structure` JSON only when a
non-neutral Stage 1 read exists:

```json
"vsa_signals": [
  {
    "signal": "stopping_volume",
    "date": "2026-04-14",
    "direction": "confirming",
    "volume_ratio": 2.3,
    "evidence": ["wide-range down bar on 2.3x avg volume, closed in upper half of range — absorption of selling"]
  }
]
```

`vsa_signals` is present (possibly as an empty list) even when net effect on
confidence was zero, so Market Analyst can cite the absence of confirming
evidence as well as its presence.

## Testing plan

New `tests/test_wyckoff_vsa.py` (synthetic OHLCV, mirrors existing Wyckoff
test style):

- Each of the 8 detectors fires on a hand-built bar matching its criteria and
  stays silent on a bar that doesn't.
- Confirming signals raise confidence within the `+0.15` cap; contradicting
  signals lower it within `-0.15`; a mix of 4 confirming + 4 contradicting
  nets to ~zero movement (not blocked to exactly zero by an all-or-nothing
  gate).
- Bars outside `[range.start_date, curr_date]` are excluded even if they'd
  otherwise match a detector.
- No future-data leakage: bars after `curr_date` never contribute a signal
  (same style as `test_chart_patterns.py` and existing Wyckoff tests).

Additions to existing `tests/test_wyckoff_bias.py`:

- A synthetic accumulation read gets `vsa_signals` in its payload and
  `confidence` reflects the adjustment.
- A neutral read (no trading range) has no `vsa_signals` key and
  `analyze_vsa` is never invoked.

## Acceptance criteria

- New VSA tests pass; existing Wyckoff/market-analyst tests show no
  regression (isolated pytest run per CLAUDE.md's default verification for
  additive changes — no full-suite/ruff-all run required since this only
  touches custom Wyckoff files plus their own tests).
- `ruff check` passes on new/edited files.
- Every emitted VSA signal carries an auditable date, price/volume-ratio
  evidence, and evidence text explaining the effort-vs-result reasoning
  (plan principle 4).
- No VSA signal changes `phase_bias` or `current_phase` — confidence is the
  only value it can move, and only within the ±0.15 bound.
- No signal is computed from data after `curr_date`.

> This module is for research and analysis support only; it does not
> constitute investment advice and does not place trades.
