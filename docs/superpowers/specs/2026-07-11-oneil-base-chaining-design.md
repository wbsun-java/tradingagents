# O'Neil Flat-Base Continuation-Chaining Design

**Goal:** Implement the deferred "base-chaining" item from the O'Neil correction arc (see
`project_oneil_stage4_status` memory): verify that a detected flat base's preceding advance
actually originates from a prior *confirmed* breakout, per IBD's continuation-base rule
(a legitimate later-stage base forms only after price has advanced ~20%+ from the prior
base's breakout pivot). This is a binary-ish classification and confidence adjustment, not
full multi-stage (1st/2nd/3rd/4th) counting — that fuller staging concept is explicitly out
of scope and was rejected as premature new infrastructure.

**Scope:** `flat_base` candidates only. Cup, double-bottom, ascending, and HTF detectors are
untouched — IBD's continuation-base concept is most specifically cited for flat bases
forming mid-uptrend after an earlier base's breakout, and narrowing scope avoids
over-generalizing an unproven pattern to every detector at once.

## Approach (chosen over a full multi-stage timeline and a non-recursive heuristic)

For a flat-base candidate's peak, recursively rerun the *existing* detection pipeline
(`detect_all` → `evaluate_candidates` → `arbitrate`) on the strict prefix of the
already-loaded `df` before that peak, to find the most recent `confirmed` breakout. Compare
its `pivot_price` to the flat base's peak price for a ≥20% gain.

Rejected alternatives:
- **Full forward multi-base timeline** (a new module staging every base in history as
  1st/2nd/3rd/4th+): more general and reusable for future "avoid late-stage bases" work, but
  it is exactly the "new infrastructure" already deferred by agreement, and over-builds for
  a single binary gate on one pattern type.
- **Non-recursive heuristic** (checking for *any* prior swing high ≥20% below the peak via
  raw pivots, without verifying a real O'Neil base+breakout occurred there): cheaper, but
  doesn't actually satisfy the IBD rule's intent — it would tag continuations off of
  arbitrary swing highs that were never a validated base.

The recursive rescan wins because it reuses 100% of already-tested detection/evaluation code
(the new code is a thin orchestrator function plus one small pure classifier), and because it
correctly captures "prior *confirmed* breakout" rather than approximating it.

## Files

- **`tradingagents/dataflows/oneil_base_patterns.py`** (modified, existing file): add a
  private helper `_find_prior_confirmed_breakout(df, before_index, atr_value, rs_score)`.
  This lives here — not in a new module — because `detect_all`/`evaluate_candidates`/
  `arbitrate` are already defined in this file; calling them recursively needs no new import
  and creates no cycle. (`oneil_flat_base.py` cannot host this call: `oneil_base_patterns.py`
  already imports `detect_flat_base` from it, so the reverse import would be circular.)
  Wires the result into the flat-base candidate returned by `detect_flat_base` before it
  flows into `evaluate_candidates`.
- **`tradingagents/dataflows/oneil_base_chain.py`** (new, ≤150 lines): pure classifier,
  `classify_continuation(prior_pivot_price, prior_date, peak_price) -> tuple[str, str]`,
  returning one of `"confirmed_continuation"` / `"premature_continuation"` /
  `"no_prior_stage"` plus a narrated evidence string — same style as `classify_second_low` in
  `oneil_double_bottom_rules.py`. Takes plain values only; no dependency on the detection
  pipeline, so it carries zero circular-import risk and is trivially unit-testable.
- **`tradingagents/dataflows/oneil_base_types.py`** (modified): add
  `BaseCandidate.continuation_state: str | None = None`.
- **`tradingagents/dataflows/oneil_breakout.py`** (modified): `compute_confidence` gains a
  new parameter `continuation_state: str | None = None` and a new constant
  `PREMATURE_CONTINUATION_PENALTY = -0.05` (symmetric with the existing `UNDERCUT_BONUS =
  0.05`), subtracted only when `continuation_state == "premature_continuation"`.

## Algorithm & data flow

`_find_prior_confirmed_breakout`:

```
def _find_prior_confirmed_breakout(df, before_index, atr_value, rs_score):
    if before_index < PRIOR_UPTREND_MIN_BARS:
        return None
    prefix = df.iloc[:before_index]
    candidates = detect_all(prefix, atr_value)
    detections = evaluate_candidates(prefix, candidates, atr_value, rs_score)
    confirmed = [d for d in detections if d.status == "confirmed"]
    if not confirmed:
        return None
    return max(confirmed, key=lambda d: d.candidate.pivot_date)
```

Reuses the same `atr_value` scalar already computed once per outer call (matches existing
convention — every detector receives one shared ATR figure, never a per-slice recomputation).
Returns `None` both when there is insufficient history *and* when no confirmed breakout
exists in the available prefix — both map to the neutral `"no_prior_stage"` classification,
never a penalty, since a too-short lookback window must not masquerade as evidence of a
premature setup.

`classify_continuation`:
- prior breakout is `None` → `"no_prior_stage"`; evidence: *"No confirmed prior base was
  found in the available history; treating as a first-stage base."*
- `gain = (peak_price - prior_pivot_price) / prior_pivot_price`; `gain >= 0.20` →
  `"confirmed_continuation"`; evidence narrates the prior breakout's date/pivot and the gain
  percentage.
- otherwise → `"premature_continuation"`; evidence: *"Only gained {gain:.1%} off the {date}
  breakout at {pivot_price:.2f} before basing again — below IBD's 20% continuation
  threshold."*

Wiring: after `detect_flat_base(df, atr_value)` returns a candidate in
`oneil_base_patterns.py`, call `_find_prior_confirmed_breakout(df, candidate.start_index,
atr_value, rs_score)` → `classify_continuation(...)`, append the evidence string to
`candidate.evidence`, and stamp `candidate.continuation_state`. `evaluate_candidates` passes
`candidate.continuation_state` through to `compute_confidence`.

**Gate strictness:** soft flag only. A `"premature_continuation"` flat base is still returned
and still eligible to become the primary/arbitrated pattern — it is never dropped outright,
consistent with how the existing double-bottom undercut case is a confidence modifier, not a
validity gate.

## Error handling

No new failure modes. The recursive call operates on a strict, already-validated prefix of
`df`; if `detect_all` raised on that prefix it would indicate a real bug elsewhere, not
something this feature should swallow.

## Testing

- **`test_oneil_base_chain.py`** (new): table-driven cases for the three classification
  states, including a boundary case at exactly 20% gain (inclusive, per `gain >= 0.20`).
- **`test_oneil_base_patterns.py`** (existing file, extended): integration-style cases using
  synthetic OHLCV fixtures (extending the `oneil_double_bottom_fixtures.py`-style pattern) —
  one with a genuine confirmed prior breakout followed by a flat base at +25%
  (`confirmed_continuation`), one with a flat base forming after a shallow +8% bounce
  (`premature_continuation`), one where the flat base sits too close to the start of the
  available window (`no_prior_stage`, unpenalized).
- **`test_oneil_breakout.py`** (existing file, extended): a couple of table cases confirming
  `compute_confidence`'s penalty fires only for `"premature_continuation"`, and that
  `"confirmed_continuation"`/`"no_prior_stage"` never apply it.

## Explicit non-goals

- No multi-stage counting (2nd vs. 3rd vs. 4th base) — a single three-state classification
  with one confidence penalty threshold, nothing richer.
- No new data fetching — the rescan is strictly bounded to the `df` slice the outer call
  already loaded via `look_back_days`; a prior breakout outside that window is
  indistinguishable from "no prior stage found" and is never penalized.
- Applies to `flat_base` only; cup/double-bottom/ascending/HTF detectors are unmodified.

## Performance note

Adds one recursive `detect_all` + `evaluate_candidates` + `arbitrate` pass per flat-base
candidate (at most one per call, since `detect_flat_base` returns a single candidate), over a
strictly smaller slice than the outer call. Bounded and rare enough not to need further
optimization.

## Codex model tier per plan task

`oneil_base_chain.py` (new pure classifier) + `oneil_base_types.py` field addition:
**terra**. `oneil_base_patterns.py` recursive-rescan wiring: **terra** (touches the shared
orchestrator, worth the mid tier). `oneil_breakout.py` `compute_confidence` parameter:
**terra**. Test files: **terra**. Always pass `-m gpt-5.6-<tier>` explicitly.

## Acceptance criteria

- All new and updated tests pass; scoped `pytest -q tests/test_oneil_base_chain.py
  tests/test_oneil_base_patterns.py tests/test_oneil_breakout.py` plus `ruff check` on
  changed files (this change is additive within the O'Neil family, not cross-cutting enough
  to require the full suite per CLAUDE.md's verification guidance — but run the full suite if
  `oneil_breakout.py`'s signature change looks like it could ripple further at
  implementation time).
- A flat base with a traceable, confirmed, ≥20%-gained prior breakout narrates that
  continuation explicitly in evidence.
- A flat base without a traceable prior breakout (either none exists, or history is
  insufficient) is never penalized — only genuinely premature continuations lose confidence.
- No behavior change to any non-flat-base detector.

> Research/analysis support only; not investment advice; no trade execution.
