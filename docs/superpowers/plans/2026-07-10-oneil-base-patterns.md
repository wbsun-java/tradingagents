# O'Neil Base-Pattern Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: This plan is executed via the project's
> `codex-delegate` skill (stage 3 of the Claude-architect workflow), not
> `superpowers:subagent-driven-development` or `superpowers:executing-plans`. Each task
> carries its own verification command and an explicit Codex model tier — always pass
> `-m <model>` to `codex exec` (the config default is still gpt-5.5). Per the user's
> 2026-07-10 role split, this plan specifies exact interfaces, detection gates, and test
> scenarios; Codex writes both the implementation and the test code for each task.

**Goal:** Expand the O'Neil module from cup-with-handle-only to all six base patterns
(cup-with-handle, cup-without-handle, flat base, double-bottom base, ascending base,
high-tight flag) behind one shared breakout engine with most-advanced-wins arbitration.

**Architecture:** Each new pattern gets its own ≤150-line detector emitting a shared
`BaseCandidate`; the existing `oneil_breakout.py` engine is generalized from `CupCandidate`
to a pivot price; `oneil_base_patterns.py` orchestrates and arbitrates; `oneil_bias.py`
emits the new `primary_pattern`/`other_detections` JSON. Spec:
`docs/superpowers/specs/2026-07-10-oneil-base-patterns-design.md`.

**Tech Stack:** Python, `pandas`, `pytest` (`@pytest.mark.unit`), synthetic OHLCV fixtures
(no network), reusing `chart_patterns.py`'s `Pivot`/`find_pivots` and `oneil_cup.py`'s
`prepare_ohlcv`/`atr`.

## Global Constraints

- Every newly created file (source, test, doc) ≤ 150 lines. If the Task 7 orchestrator
  exceeds the cap, split arbitration into `oneil_arbitration.py` rather than growing it.
- Only project-custom files are touched (`oneil_*`, `market_analyst.py`,
  `ONEIL_CANSLIM_ANALYSIS_PLAN.md`, tests) — no upstream files, no approval gates needed.
- All OHLCV via existing `prepare_ohlcv` (`oneil_cup.py`) / `load_ohlcv`
  (`stockstats_utils.py`); no new preparer is added, so the computed-minimum-rows
  `ValueError` convention is satisfied by reuse. No `AgentState` changes.
- No future data past `curr_date`; every detector test file includes a leakage test
  mirroring the convention already used in `tests/test_oneil_cup.py`.
- Every detected event carries dated, priced, **volume-narrated** evidence strings —
  volume behavior must be stated in the text, not left as a silent number.
- Detection gates are named module-level constants combining O'Neil guideline ratios with
  ATR floors (the `max(fixed_ratio, atr_multiple)` idiom already used in
  `chart_patterns.py`); never a bare hardcoded percentage inside logic.
- `ruff check` clean (repo config: `E, W, F, I, B, UP, C4, SIM`; `E501` ignored).
- No task commits anything. Commits wait for the user's explicit approval, task by task.
- Task order: 1 → 2 → (3, 4, 5, 6 in any order) → 7 → 8.
- Interface refinement vs. the spec: the spec's single `BasePattern` dataclass is split
  into `BaseCandidate` (raw detector output, Task 1) and `PatternDetection`
  (engine-evaluated result, Task 7) so detectors never compute status/confidence
  themselves — the shared engine runs once, in one place. Detection rules, arbitration,
  and the JSON schema are unchanged from the approved spec; Task 8 updates the spec's
  wording to match.

---

### Task 1: `oneil_base_types.py` — shared candidate type and helpers

**Codex tier:** `gpt-5.6-terra`

**Files:**
- Create: `tradingagents/dataflows/oneil_base_types.py`
- Test: `tests/test_oneil_base_types.py` (new)

**Interfaces:**
- Consumes: `HandleCandidate` from `tradingagents.dataflows.oneil_handle` (existing).
- Produces (exact, later tasks import all of these):

```python
PatternType = Literal["cup_with_handle", "cup_without_handle", "flat_base",
                      "double_bottom_base", "ascending_base", "high_tight_flag"]

@dataclass
class BaseCandidate:
    pattern_type: PatternType
    complete: bool            # False = still forming; breakout search only when True
    pivot_price: float
    pivot_date: str           # "YYYY-MM-DD"
    complete_index: int       # last bar of the pattern; breakout search starts at +1
    geometry: dict[str, Any]  # per-pattern keys, JSON-serializable
    evidence: list[str]
    handle: HandleCandidate | None = None   # cup family only
    undercut: bool = False                  # double bottom only

def prior_uptrend(df: pd.DataFrame, start_index: int, atr_value: float) -> tuple[bool, str]
def volume_dry_up(df: pd.DataFrame, base_start: int, base_end: int) -> tuple[float | None, str]
```

**Behavior contracts:**
- `prior_uptrend`: gain from the lowest close in `df[max(0, start_index-120):start_index]`
  to the close at `start_index` must be ≥ `max(PRIOR_UPTREND_MIN_GAIN_RATIO * low_close,
  PRIOR_UPTREND_MIN_GAIN_ATR * atr_value)` with constants `PRIOR_UPTREND_MIN_GAIN_RATIO
  = 0.2`, `PRIOR_UPTREND_MIN_GAIN_ATR = 6.0`. Returns `(bool, narration)`; the narration
  names the low's date/price and the gain percentage. Returns `(False, ...)` when fewer
  than 30 bars precede `start_index`.
- `volume_dry_up`: mean volume over `[base_start, base_end]` divided by mean volume over
  the 20 bars before `base_start`; `(None, narration)` when fewer than 20 prior bars.
  Narration must say whether volume contracted or expanded and by what ratio.

**Steps:**
- [ ] **Step 1 (Codex):** Write `oneil_base_types.py` and `tests/test_oneil_base_types.py`
  together. Required test scenarios (synthetic frames, reuse/adapt ramp helpers from
  `tests/test_oneil_cup.py`):
  - `test_prior_uptrend_accepts_a_meaningful_advance` — 120-bar ramp gaining 30% into
    `start_index` → `(True, ...)`; narration contains the low's date.
  - `test_prior_uptrend_rejects_a_flat_approach` — flat series → `(False, ...)`.
  - `test_prior_uptrend_rejects_insufficient_history` — `start_index=10` → `(False, ...)`.
  - `test_volume_dry_up_reports_contraction` — base volume half the prior 20-bar mean →
    ratio ≈ 0.5 and narration contains "contract" (or equivalent explicit wording).
  - `test_volume_dry_up_without_prior_bars_returns_none` — `base_start=5` → `(None, ...)`.
  - `test_base_candidate_geometry_is_json_serializable` — `json.dumps` of a populated
    `BaseCandidate.geometry` round-trips.
- [ ] **Step 2 (verify):** `pytest -q tests/test_oneil_base_types.py` → all pass;
  `ruff check tradingagents/dataflows/oneil_base_types.py tests/test_oneil_base_types.py`
  → clean; file ≤ 150 lines.

---

### Task 2: Generalize the breakout engine (`oneil_breakout.py`)

**Codex tier:** `gpt-5.6-terra`

**Files:**
- Modify: `tradingagents/dataflows/oneil_breakout.py`
- Modify: `tradingagents/dataflows/oneil_bias.py` (call sites only — JSON output unchanged)
- Test: `tests/test_oneil_breakout.py` (existing, update call sites + add cases)

**Interfaces:**
- Consumes: `PatternType` from Task 1; `HandleCandidate` (existing); `volume_ratio` from
  `oneil_cup` (existing).
- Produces (exact — Tasks 7 uses all of these):

```python
def find_breakout(df, pivot_price: float, search_start_index: int, atr_value: float) -> BreakoutEvent | None
def breakout_reversed(df, breakout: BreakoutEvent, pivot_price: float, atr_value: float) -> bool
def determine_status(*, complete: bool, handle: HandleCandidate | None,
                     handle_required: bool, breakout: BreakoutEvent | None,
                     reversed_after: bool) -> Status
def compute_confidence(pattern_type: PatternType, status: Status,
                       handle: HandleCandidate | None, breakout: BreakoutEvent | None,
                       rs_score: float | None, undercut: bool = False) -> float
PATTERN_CONFIDENCE_BONUS: dict[PatternType, float]
UNDERCUT_BONUS = 0.05
```

**Behavior contracts:**
- `find_breakout`/`breakout_reversed`: identical rules to today (ATR-buffered close above
  pivot, `BREAKOUT_VOLUME_RATIO` within `BREAKOUT_CONFIRM_WINDOW`, reversal = buffered
  close back below pivot) — only the parameters change from `CupCandidate`/`Handle` to
  `pivot_price` + `search_start_index`.
- `determine_status` decision order: `not complete` → `"forming"`; `handle is not None and
  not handle.valid` → `"failed"`; `handle is None and handle_required` → `"forming"`;
  `breakout is None or not breakout.volume_confirmed` → `"developing"`; `reversed_after`
  → `"failed"`; else `"confirmed"`. (`"none"` stays a caller-level result for no pattern.)
  With `handle_required=True` this reproduces today's cup behavior exactly.
- `PATTERN_CONFIDENCE_BONUS = {"high_tight_flag": 0.05, "cup_with_handle": 0.0,
  "double_bottom_base": -0.02, "ascending_base": -0.03, "flat_base": -0.04,
  "cup_without_handle": -0.05}` — cup_with_handle is 0.0 so every existing confidence
  expectation is numerically unchanged; ordering encodes O'Neil's pattern-power ranking.
  Bonus is added to the status base before the existing bounded handle/volume/RS bonuses;
  `undercut=True` adds `UNDERCUT_BONUS`; floor result at 0.0, cap stays 0.95.
- `oneil_bias.py` in this task ONLY adapts to the new signatures with
  `pattern_type="cup_with_handle"`, `handle_required=True`,
  `search_start_index=handle.end_index + 1`, `pivot_price=cup.left_high_price` — its JSON
  output must be byte-identical to before.

**Steps:**
- [ ] **Step 1 (Codex):** Refactor engine + call sites and update
  `tests/test_oneil_breakout.py` mechanically to the new signatures (same fixtures, same
  expected statuses/confidences). Add new cases:
  - `test_cup_without_handle_reaches_developing` — complete pattern, `handle=None`,
    `handle_required=False`, no breakout → `"developing"` (not `"forming"`).
  - `test_cup_without_handle_confirms_below_cup_with_handle` — identical breakout inputs;
    `compute_confidence("cup_without_handle", ...)` <
    `compute_confidence("cup_with_handle", ...)`.
  - `test_low_volume_breakout_stays_developing_for_non_cup_pattern` — `handle=None`,
    `handle_required=False`, unconfirmed breakout → `"developing"`.
  - `test_undercut_bonus_applies_only_when_set` — same inputs ± `undercut` differ by
    exactly `UNDERCUT_BONUS` (within cap).
- [ ] **Step 2 (verify):** `pytest -q tests/test_oneil_breakout.py tests/test_oneil_bias.py
  tests/test_oneil_cup.py tests/test_oneil_handle.py` → all pass (bias tests unmodified);
  `ruff check` on the three touched source files + test file → clean.

---

### Task 3: Flat base detector (`oneil_flat_base.py`)

**Codex tier:** `gpt-5.6-terra`

**Files:**
- Create: `tradingagents/dataflows/oneil_flat_base.py`
- Test: `tests/test_oneil_flat_base.py` (new)

**Interfaces:**
- Consumes: `BaseCandidate`, `prior_uptrend` (Task 1); `atr` from `oneil_cup`.
- Produces: `detect_flat_base(df: pd.DataFrame, atr_value: float) -> BaseCandidate | None`

**Behavior contracts (constants at file top):**
- `FLAT_MIN_DAYS = 25`, `FLAT_FORMING_MIN_DAYS = 15`, `FLAT_MAX_DAYS = 120`,
  `FLAT_DEPTH_RATIO = 0.15`, `FLAT_DEPTH_ATR = 4.0`.
- Find the most recent window `[s, e]` where: depth `(range_high - range_low) /
  range_high` ≤ `max(FLAT_DEPTH_RATIO, FLAT_DEPTH_ATR * atr_value / range_high)`;
  `prior_uptrend(df, s, atr_value)` is True; `e` is the last bar whose close stays at or
  below `range_high + 0.1 * atr_value` (so an already-broken-out base ends the bar before
  the first buffered close above the high). Duration `e - s + 1`: ≥ `FLAT_MIN_DAYS` →
  `complete=True`; in `[FLAT_FORMING_MIN_DAYS, FLAT_MIN_DAYS)` → `complete=False`
  (forming); below → `None`.
- `pivot_price = range_high`, `pivot_date` = date of the range-high bar,
  `complete_index = e`. `geometry`: `{"start_date", "end_date", "range_high", "range_low",
  "depth_pct", "duration_days"}`. Evidence narrates the tight range, its depth percentage,
  and the prior advance (from the `prior_uptrend` narration).

**Steps:**
- [ ] **Step 1 (Codex):** Write detector + tests together. Required scenarios:
  - `test_textbook_flat_base_detected` — 60-bar +30% ramp, then 30 bars oscillating ±2%
    → `complete=True`, `pattern_type="flat_base"`, pivot == the range high.
  - `test_short_tight_range_is_forming` — same but 18 tight bars → `complete=False`.
  - `test_deep_range_rejected` — 30-bar range 25% deep → `None`.
  - `test_no_prior_uptrend_rejected` — flat approach then tight range → `None`.
  - `test_broken_out_base_ends_before_the_breakout_bar` — tight range then 3 closes above
    the high → `complete_index` is the bar before the first buffered close above.
  - `test_evidence_narrates_depth_and_prior_advance` — evidence text contains the depth
    percentage and the prior-advance narration.
  - Leakage test per the `test_oneil_cup.py` convention.
- [ ] **Step 2 (verify):** `pytest -q tests/test_oneil_flat_base.py` → pass; `ruff check`
  both files → clean; each file ≤ 150 lines.

---

### Task 4: Double-bottom base detector (`oneil_double_bottom.py`)

**Codex tier:** `gpt-5.6-terra`

**Files:**
- Create: `tradingagents/dataflows/oneil_double_bottom.py`
- Test: `tests/test_oneil_double_bottom.py` (new)

**Interfaces:**
- Consumes: `BaseCandidate`, `prior_uptrend`, `volume_dry_up` (Task 1); `Pivot`,
  `find_pivots` from `chart_patterns` (same imports `oneil_cup.py` uses).
- Produces: `detect_double_bottom(df: pd.DataFrame, atr_value: float) -> BaseCandidate | None`

**Behavior contracts (constants at file top; never import tuning constants from
`chart_patterns.py` — geometry primitives only, per spec):**
- `DB_MIN_DAYS = 35`, `DB_MAX_DAYS = 120` (L1→L2 gap bounds).
- Pick the most recent pivot-low pair (L1, L2) with a middle peak M = max high strictly
  between them. Gates: `prior_uptrend(df, L1.index, atr_value)`; M meaningfully above the
  lows: `M - max(L1.price, L2.price) ≥ max(1.25 * atr_value, 0.02 * mean(L1, L2))`;
  volume dry-up over `[L1.index, L2.index]` with ratio < 1.0 (hard gate; narration goes
  into evidence).
- Second-low band: valid iff `L2.price ∈ [L1.price - max(1.5 * atr_value, 0.03 * L1.price),
  L1.price + max(1.0 * atr_value, 0.02 * L1.price)]`. Classify `second_low_behavior` with
  a ±`0.25 * atr_value` dead zone: below → `"undercut"` (`undercut=True`), above →
  `"higher"`, inside → `"equal"`. Outside the band entirely → `None` (another detector may
  claim the structure). Each classification gets its own explicit evidence sentence
  (undercut = shakeout wording; equal = matched lows; higher = held above the first low).
- No forming stage: return only complete candidates (both lows settled by `find_pivots`).
  `pivot_price = M`, `pivot_date` = M's date, `complete_index = L2.index`. `geometry`:
  `{"first_low": {"date", "price"}, "second_low": {"date", "price"},
  "middle_peak": {"date", "price"}, "second_low_behavior", "duration_days"}`.

**Steps:**
- [ ] **Step 1 (Codex):** Write detector + tests together. Required scenarios:
  - `test_textbook_w_with_undercut_detected` — uptrend, decline to L1, rally to M, second
    decline undercutting L1 by ~1 ATR, recovery → candidate with
    `second_low_behavior == "undercut"`, `undercut is True`, pivot == M.
  - `test_equal_lows_valid_without_undercut_flag` — L2 within the dead zone →
    `"equal"`, `undercut is False`.
  - `test_higher_second_low_valid` — L2 ~0.5 ATR above L1 → `"higher"`.
  - `test_second_low_far_above_band_rejected` — L2 well above the upper band → `None`.
  - `test_too_short_w_rejected` — L1→L2 gap of 15 bars → `None`.
  - `test_no_volume_dry_up_rejected` — base volume above the prior mean → `None`.
  - `test_no_prior_uptrend_rejected`.
  - `test_evidence_narrates_shakeout_and_volume` — undercut case's evidence includes the
    shakeout sentence and the volume-contraction narration.
  - Leakage test per convention.
- [ ] **Step 2 (verify):** `pytest -q tests/test_oneil_double_bottom.py` → pass;
  `ruff check` both files → clean; each ≤ 150 lines.

---

### Task 5: Ascending base detector (`oneil_ascending_base.py`)

**Codex tier:** `gpt-5.6-sol` (hardest geometry — most room for subtle wrongness)

**Files:**
- Create: `tradingagents/dataflows/oneil_ascending_base.py`
- Test: `tests/test_oneil_ascending_base.py` (new)

**Interfaces:**
- Consumes: `BaseCandidate`, `prior_uptrend` (Task 1); `Pivot`, `find_pivots` from
  `chart_patterns`.
- Produces: `detect_ascending_base(df: pd.DataFrame, atr_value: float) -> BaseCandidate | None`

**Behavior contracts (constants at file top):**
- `ASC_MIN_DAYS = 40`, `ASC_MAX_DAYS = 100` (H1 → L3 span), `ASC_MIN_PULLBACK_RATIO =
  0.05`, `ASC_MIN_PULLBACK_ATR = 1.5`, `ASC_MAX_PULLBACK_RATIO = 0.20`,
  `ASC_MAX_PULLBACK_ATR = 5.0`.
- From settled pivots, find the most recent alternating sequence H1, L1, H2, L2, H3, L3
  (highs and lows strictly ascending on pivot prices: H1 < H2 < H3 and L1 < L2 < L3).
  Each pullback fraction `(Hi - Li) / Hi` must lie in
  `[max(ASC_MIN_PULLBACK_RATIO, ASC_MIN_PULLBACK_ATR * atr_value / Hi),
    max(ASC_MAX_PULLBACK_RATIO, ASC_MAX_PULLBACK_ATR * atr_value / Hi)]`.
  `prior_uptrend(df, H1.index, atr_value)` required. Span within bounds.
- Three qualifying pullbacks → `complete=True`, `pivot_price = H3.price`,
  `complete_index = L3.index`. Exactly two qualifying pullbacks (third not yet settled) →
  `complete=False` (forming), `pivot_price = H2.price`, `complete_index = L2.index`,
  geometry notes `"pullbacks_completed": 2`. Fewer → `None`.
- `geometry`: `{"pullbacks": [{"high": {"date", "price"}, "low": {"date", "price"},
  "depth_pct"}, ...], "pullbacks_completed", "duration_days"}`. Evidence narrates each
  pullback's dates, depth, and the ascending structure; volume behavior across pullbacks
  is narrated (contracting pullback volume strengthens the read but is not a gate).

**Steps:**
- [ ] **Step 1 (Codex):** Write detector + tests together. Required scenarios:
  - `test_textbook_three_pullback_ascending_base` — stair-step series with three 10-15%
    pullbacks, each high/low above the last, ~60-bar span → `complete=True`, pivot == H3.
  - `test_two_pullbacks_is_forming` — same truncated after L2 settles →
    `complete=False`, `geometry["pullbacks_completed"] == 2`, pivot == H2.
  - `test_flat_lows_rejected` — L2 ≈ L1 (not ascending) → `None`.
  - `test_pullback_too_deep_rejected` — one 30% pullback → `None`.
  - `test_pullback_too_shallow_rejected` — one 2% dip (below the ATR-floored minimum) →
    `None`.
  - `test_span_too_long_rejected` — same shape stretched past `ASC_MAX_DAYS` → `None`.
  - `test_no_prior_uptrend_rejected`.
  - `test_evidence_narrates_each_pullback_and_volume`.
  - Leakage test per convention.
- [ ] **Step 2 (verify):** `pytest -q tests/test_oneil_ascending_base.py` → pass;
  `ruff check` both files → clean; each ≤ 150 lines.

---

### Task 6: High-tight-flag detector (`oneil_htf.py`)

**Codex tier:** `gpt-5.6-terra`

**Files:**
- Create: `tradingagents/dataflows/oneil_htf.py`
- Test: `tests/test_oneil_htf.py` (new)

**Interfaces:**
- Consumes: `BaseCandidate` (Task 1); `atr` from `oneil_cup`.
- Produces: `detect_high_tight_flag(df: pd.DataFrame, atr_value: float) -> BaseCandidate | None`

**Behavior contracts (constants at file top):**
- `HTF_POLE_MIN_ADVANCE = 1.9` (close-to-close multiple ≈ doubling), `HTF_POLE_MAX_DAYS =
  45`, `HTF_FLAG_MIN_DAYS = 5`, `HTF_FLAG_MAX_DAYS = 25`, `HTF_FLAG_MAX_CORRECTION = 0.25`.
- Flagpole: most recent pair `s < p` with `Close[p] / Close[s] ≥ HTF_POLE_MIN_ADVANCE`
  and `p - s ≤ HTF_POLE_MAX_DAYS`. The flagpole itself is the prior uptrend — no separate
  `prior_uptrend` gate. Flag: the window after `p`; flag high = max high in it; correction
  `(flag_high - flag_low) / flag_high ≤ HTF_FLAG_MAX_CORRECTION`. Flag duration in
  `[HTF_FLAG_MIN_DAYS, HTF_FLAG_MAX_DAYS]` → `complete=True`; shorter (≥ 1 bar) with the
  correction holding → `complete=False` (forming); correction exceeded or flag overlong →
  `None`.
- `pivot_price` = flag high, `complete_index` = last flag bar (ends the bar before the
  first buffered close above the flag high, same rule as Task 3). `geometry`:
  `{"pole_start": {"date", "price"}, "pole_end": {"date", "price"}, "advance_pct",
  "pole_days", "flag_high", "flag_low", "correction_pct", "flag_days"}`. Evidence
  narrates the advance, the flag's tightness, and flag volume versus pole volume.

**Steps:**
- [ ] **Step 1 (Codex):** Write detector + tests together. Required scenarios:
  - `test_textbook_htf_detected` — +100% in 35 bars, then 10-bar flag correcting 12% →
    `complete=True`, pivot == flag high.
  - `test_flag_too_young_is_forming` — 3-bar flag → `complete=False`.
  - `test_correction_too_deep_rejected` — 35% flag correction → `None`.
  - `test_advance_too_small_rejected` — +40% pole → `None`.
  - `test_advance_too_slow_rejected` — +100% but over 90 bars → `None`.
  - `test_flag_overlong_rejected` — 40-bar flag → `None`.
  - `test_evidence_narrates_advance_and_flag_volume`.
  - Leakage test per convention.
- [ ] **Step 2 (verify):** `pytest -q tests/test_oneil_htf.py` → pass; `ruff check` both
  files → clean; each ≤ 150 lines.

---

### Task 7: Orchestrator, arbitration, and the new JSON (`oneil_base_patterns.py` + `oneil_bias.py`)

**Codex tier:** `gpt-5.6-terra`

**Files:**
- Create: `tradingagents/dataflows/oneil_base_patterns.py` (split out
  `oneil_arbitration.py` if the 150-line cap forces it)
- Modify: `tradingagents/dataflows/oneil_bias.py` (payload rewrite)
- Modify: `tradingagents/agents/utils/oneil_tools.py` (docstring labeling only)
- Test: `tests/test_oneil_base_patterns.py` (new), `tests/test_oneil_bias.py` (rewrite)

**Interfaces:**
- Consumes: all four detectors (Tasks 3–6), the Task 2 engine, `detect_cup`/`detect_handle`
  (existing), `BaseCandidate` (Task 1).
- Produces (exact):

```python
@dataclass
class PatternDetection:
    candidate: BaseCandidate
    status: Status
    breakout: BreakoutEvent | None
    confidence: float

def detect_all(df: pd.DataFrame, atr_value: float) -> list[BaseCandidate]
def evaluate_candidates(df, candidates: list[BaseCandidate], atr_value: float,
                        rs_score: float | None) -> list[PatternDetection]
def arbitrate(detections: list[PatternDetection]) -> tuple[PatternDetection | None,
                                                           list[PatternDetection]]
```

**Behavior contracts:**
- `detect_all` runs the cup adapter plus the four detectors. Cup adapter: `detect_cup` +
  `detect_handle`; a valid handle → `pattern_type="cup_with_handle"`
  (`complete_index = handle.end_index`); no handle → `"cup_without_handle"`
  (`complete_index` = the cup's right-high index); an invalid handle stays
  `"cup_with_handle"` so the engine's `handle.valid` check yields `"failed"`. Pivot is
  always the cup's left high. **Semantic change, stated on purpose:** a completed cup with
  no handle was previously reported as cup-with-handle `"forming"`; it now reports as
  `"cup_without_handle"` `"developing"` (buyable at the pivot per O'Neil, awaiting
  breakout).
- `evaluate_candidates` runs the shared engine once per candidate: breakout search from
  `complete_index + 1` when `complete`; `handle_required=True` only for
  `"cup_with_handle"`; confidence via `compute_confidence(pattern_type, ..., undercut=
  candidate.undercut)`.
- `arbitrate`: rank live detections by `STATUS_RANK = {"confirmed": 3, "developing": 2,
  "forming": 1}`, tie-break by confidence, then by `pivot_date` recency. `"failed"`
  detections never beat a live one; if ALL detections are failed, the most recent failure
  (by breakout date, else pivot_date) is primary. Empty input → `(None, [])`.
- `oneil_bias.py` rewrite: `analyze_oneil_setup_from_data` returns the spec's schema —
  `primary_pattern` (`pattern_type`, `status`, `pivot_price`, `pivot_date`, `geometry`,
  `handle` dict for cup_with_handle else `null`, `breakout` nullable),
  `other_detections` (list of `{"pattern_type", "status", "confidence"}`), `setup_bias`
  (`"bullish"` iff primary exists with live status, else `"neutral"`), `confidence`,
  `secondary_weight` (0.4, unchanged), `weight_note` (reworded: "O'Neil base-pattern read
  ranks below Wyckoff but above chart patterns, trend template, and indicators; ..."),
  `evidence` (primary's evidence + breakout line), `analysis_date`.
  `primary_pattern: null` + `setup_bias: "neutral"` when nothing is detected.
  `analyze_oneil_setup`'s signature and RS handling are unchanged.

**Steps:**
- [ ] **Step 1 (Codex):** Write orchestrator + rewrite `test_oneil_bias.py` +
  `tests/test_oneil_base_patterns.py` together. Required scenarios:
  - `test_confirmed_flat_base_beats_forming_htf` — arbitration on two hand-built
    detections → flat base primary, HTF in `other_detections`.
  - `test_equal_status_tie_broken_by_confidence_then_recency`.
  - `test_failed_pattern_never_beats_live_one`.
  - `test_all_failed_reports_most_recent_failure_neutral` — primary present with
    `status="failed"`, payload `setup_bias == "neutral"`.
  - `test_nothing_detected_yields_null_primary` — `primary_pattern` is `None`/null,
    `setup_bias == "neutral"`, `other_detections == []`.
  - `test_cup_without_handle_reported_as_developing` — the stated semantic change.
  - `test_payload_contract_keys_always_present` — for a detected case: `pattern_type`,
    `status`, `pivot_price`, `pivot_date`, `breakout` keys exist in `primary_pattern`;
    top level has `setup_bias`, `confidence`, `secondary_weight == 0.4`, `weight_note`,
    `evidence`, `analysis_date`.
  - `test_weight_note_says_base_pattern_not_cup` — `weight_note` contains "base-pattern"
    and not "CANSLIM".
  - End-to-end: a synthetic cup-with-handle frame (reuse `test_oneil_bias.py`'s old
    fixture) still yields `pattern_type == "cup_with_handle"` with the same status as the
    old payload's.
- [ ] **Step 2 (verify):** `pytest -q tests/test_oneil_base_patterns.py
  tests/test_oneil_bias.py tests/test_oneil_breakout.py` → pass; `ruff check` touched
  files → clean; new files ≤ 150 lines.

---

### Task 8: Market Analyst prompt, labeling sweep, plan-doc update

**Codex tier:** `gpt-5.6-luna` (mechanical wording changes against specified text)

**Files:**
- Modify: `tradingagents/agents/analysts/market_analyst.py` (prompt text only)
- Modify: `ONEIL_CANSLIM_ANALYSIS_PLAN.md` (status + labeling note)
- Test: `tests/test_market_analyst_prefetch.py` (existing, add case)

**Behavior contracts:**
- Rewrite the O'Neil prompt paragraph for the new JSON: name
  `primary_pattern.pattern_type`; narrate the winning pattern's dated/priced geometry and
  evidence; `other_detections` get at most one sentence; for a double bottom, state
  `second_low_behavior` explicitly (undercut = shakeout, equal, or higher second low).
  Keep verbatim: no inventing patterns beyond the JSON; no eyeballing structures from the
  raw CSV. Three-tier precedence rule unchanged; wording generalizes "cup-with-handle
  structure" → "base-pattern structure".
- Add the supersede sentence: when the O'Neil double-bottom base and the chart-pattern
  tool's generic double bottom cover the same lows, describe them as a single structure
  qualifying under O'Neil's stricter criteria at O'Neil's tier — never as two independent
  patterns confirming each other.
- Markdown-table instruction: the O'Neil row becomes `pattern_type`, `status`,
  `setup_bias`, `secondary_weight`. "CANSLIM" must not appear in prompt-authored report
  wording. Internal identifiers (`analyze_oneil_setup`, `oneil_*` filenames) unchanged.
- `ONEIL_CANSLIM_ANALYSIS_PLAN.md`: mark "Other O'Neil base patterns" done (pointing at
  the spec/plan), note the labeling change and the cup-without-handle semantic change.
- `docs/superpowers/specs/2026-07-10-oneil-base-patterns-design.md`: rename its
  `BasePattern` dataclass mention to `BaseCandidate`/`PatternDetection` per the plan's
  interface-refinement note (wording only, no rule changes).
- New prompt test must anchor on a phrase unique to the new paragraph (e.g.
  `second_low_behavior` or the supersede sentence) — never a word already present in the
  test's own fixture JSON (lesson from commit 26f98a2). Update the existing prefetch
  tests' fake O'Neil JSON to the new schema shape.
- Final regression (cross-cutting per CLAUDE.md): full `pytest -q` and `ruff check .`.

**Steps:**
- [ ] **Step 1 (Codex):** Apply the prompt/doc edits and extend
  `tests/test_market_analyst_prefetch.py`:
  - `test_base_pattern_paragraph_reaches_the_prompt` — fake O'Neil JSON
    `'{"primary_pattern":{"pattern_type":"flat_base"},"setup_bias":"bullish"}'` →
    assert `"second_low_behavior"` in the system prompt (only the new paragraph contains
    it).
  - `test_double_bottom_supersede_rule_present` — assert on a phrase unique to the
    supersede sentence (e.g. `"single structure"`).
  - Existing prefetch tests updated to the new fake-JSON shape, assertions otherwise
    unchanged.
- [ ] **Step 2 (verify):** `pytest -q tests/test_market_analyst_prefetch.py` → pass; then
  full `pytest -q` → pass; `ruff check .` → clean.

---

## Stage 4 (after all tasks; user-run, Antigravity opt-in)

Run `TradingAgentsGraph(config=DEFAULT_CONFIG.copy(), selected_analysts=["market"])
.propagate(<ticker>, <date>)` and inspect `state["market_report"]` (note: `propagate()`
returns `(final_state, signal)`):
1. A ticker/date where a non-cup pattern is primary — report names that pattern with dates.
2. A supersede case if findable — double-bottom base narrated as one structure.
3. A Wyckoff-conflict case — Wyckoff leads, O'Neil conflict explicitly flagged.

> Research/analysis support only; not investment advice; no trade execution.
