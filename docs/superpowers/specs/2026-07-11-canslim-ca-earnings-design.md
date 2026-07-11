# CANSLIM C+A Earnings-Growth Scorer Design

**Goal:** Add a deterministic scorer for O'Neil's C (current quarterly EPS growth) and A
(annual EPS growth) letters, surfaced as an additive `canslim_earnings` section in the
O'Neil payload the Market Analyst already narrates. Explicitly scoped down from "full
CANSLIM": N/S/L/M are already covered by existing modules (base patterns, pocket pivots,
RS-vs-benchmark proxy), and I (institutional sponsorship) is punted as a data-availability
unknown. This closes the CANSLIM-scope question left open in
`docs/superpowers/specs/2026-07-10-oneil-base-patterns-design.md`.

**Decisions locked during brainstorming:**
- **Surface:** O'Neil payload / Market Analyst (not the Fundamentals Analyst — that is an
  untouched upstream file, and C exists to confirm/deny a technical base setup, so it
  belongs next to the base-pattern read).
- **Vendor:** respect the existing `data_vendors["fundamental_data"]` routing with
  per-vendor adapters; degrade honestly when the configured vendor cannot supply enough
  history; never silently switch vendors.
- **Coupling:** narration-only. No confidence delta into `compute_confidence` in this
  iteration; revisit only if live use shows it is warranted (mirrors how VSA was added to
  Wyckoff as a separate follow-up).
- **Architecture:** module-local fetch + pure scorer (chosen over registering a
  `get_earnings_history` method in `interface.py`'s `VENDOR_METHODS`, which would need
  upstream-file approval and is more general than today's need, and over parsing the
  existing statement tools' output, which inherits leaky dates, shallow yfinance history,
  and fragile string parsing). Precedent: the O'Neil family already sources OHLCV through
  its own `load_ohlcv` helper rather than the central routing table.

## The point-in-time principle for fundamentals

Prices are public the moment they print, but a fiscal quarter's EPS exists "in the past"
weeks before anyone can know it. The existing `_filter_reports_by_date` in
`alpha_vantage_fundamentals.py` gates by `fiscalDateEnding <= curr_date`, which silently
grants ~3–7 weeks of clairvoyance every quarter. This module must gate quarterly data by
**reported/announcement date**, never fiscal period end:

- yfinance's `Ticker.get_earnings_dates` is indexed by announcement date and carries
  `Reported EPS` — inherently point-in-time.
- Alpha Vantage's `EARNINGS` endpoint (free tier, not yet wrapped) carries `reportedDate`
  per quarterly entry.
- Annual EPS for a fiscal year is public only once the Q4/FY report has landed; the AV
  adapter keeps an `annualEarnings` entry only when a quarterly report at or after that
  fiscal year end has `reportedDate <= curr_date`.

## Files

New (each ≤150 lines):

- `tradingagents/dataflows/canslim_earnings_data.py` — vendor dispatch + normalization.
  Public: `load_earnings_history(symbol, curr_date, config=None) -> EarningsHistory`.
  Dispatch on `config["data_vendors"]["fundamental_data"]`:
  - `yfinance`: `Ticker.get_earnings_dates(limit=28)` for quarterly (drop rows after
    `curr_date` or with missing EPS); annual EPS from `income_stmt`'s `Diluted EPS` row
    (4 fiscal years). yfinance's annual statement carries no report dates, so gate each
    fiscal year by `fiscal_end + 90 days <= curr_date` (the typical 10-K filing window)
    — a stated approximation, unlike the AV path's exact `reportedDate` gate.
  - `alpha_vantage`: new `EARNINGS` wrapper (one small function added to the
    project-custom `alpha_vantage_fundamentals.py`, following the existing
    `_make_api_request` pattern): `quarterlyEarnings` filtered by
    `reportedDate <= curr_date`; `annualEarnings` gated per the rule above.
  - Any other configured vendor: raise `ValueError` naming it (never-silently-reroute).
  Types (frozen dataclasses, same file): `EarningsHistory(quarters: list[QuarterEps],
  annual: list[AnnualEps])`; `QuarterEps(fiscal_end: str, reported_date: str, eps: float)`;
  `AnnualEps(fiscal_year: str, eps: float)`. Both lists newest-first.
- `tradingagents/dataflows/canslim_earnings.py` — pure scorer, no network, operates only on
  the already-filtered `EarningsHistory` so it cannot leak future data. Public:
  `score_canslim_ca(history: EarningsHistory) -> dict` returning
  `{"c": {"verdict", "growth_pct", "acceleration", "evidence"},
    "a": {"verdict", "growth_pct", "evidence"}}` with verdicts
  `"pass" | "fail" | "unavailable"`.

Modified (all project-custom or precedented):

- `tradingagents/dataflows/alpha_vantage_fundamentals.py` — +1 function wrapping the
  `EARNINGS` endpoint.
- `tradingagents/dataflows/oneil_bias.py` — `analyze_oneil_setup` (the symbol-aware entry
  point) wraps fetch+score in one try/except; on any exception the payload carries
  `unavailable` verdicts with the exception message as the reason. Result lands as an
  additive top-level `canslim_earnings` key (non-breaking; existing keys untouched).
- `tradingagents/agents/analysts/market_analyst.py` — one prompt paragraph (precedented
  edit, commit 266bfaf): narrate both verdicts with their numbers; say "unavailable"
  honestly rather than inferring growth from other data.

Data flow: `get_oneil_setup(symbol, curr_date)` → `analyze_oneil_setup` → existing
technical pipeline unchanged + `load_earnings_history` → `score_canslim_ca` → merged JSON
→ Market Analyst narration.

## Scoring semantics

Constants at the top of `canslim_earnings.py` — canonical O'Neil numbers as calibration
anchors, consistent with the base-pattern module's treatment of his guideline figures:
`C_MIN_GROWTH_PCT = 25.0`, `A_MIN_CAGR_PCT = 25.0`, `C_MIN_QUARTERS = 5`,
`A_MIN_YEARS = 4`, `YOY_MATCH_TOLERANCE_DAYS = 45`, `EPS_ZERO_EPSILON = 0.01`.

**C (current quarterly EPS growth, canon ≥ +25% YoY):**

- Match the latest reported quarter to its same-quarter-prior-year counterpart by fiscal
  end date (~365 days earlier, ±`YOY_MATCH_TOLERANCE_DAYS` for fiscal-calendar drift) —
  never "4 rows back" blindly. Fewer than `C_MIN_QUARTERS` usable quarters, or no
  counterpart within tolerance → `unavailable`, count/reason stated.
- `growth_pct = (eps_now - eps_yoy) / abs(eps_yoy) * 100`. The `abs()` denominator handles
  a negative year-ago base sanely (a swing from −0.50 to +0.75 is genuinely strong).
- Special cases stated, not scored: |year-ago EPS| < `EPS_ZERO_EPSILON` → `unavailable`
  ("year-ago base too small for a meaningful growth rate"); current EPS negative →
  automatic `fail` regardless of arithmetic (O'Neil requires positive current earnings).
- Verdict: `pass` iff `growth_pct >= C_MIN_GROWTH_PCT`.
- **Acceleration** (reported alongside; never changes the verdict — modifier, not gate,
  same philosophy as the double-bottom undercut): YoY growth for each of the latest 3
  quarters with counterparts; `"accelerating"` if strictly rising, `"decelerating"` if
  strictly falling, `"mixed"` otherwise, `null` if fewer than 3 computable. Evidence
  narrates the sequence with numbers (e.g. "quarterly EPS growth ran +18% → +24% → +31%
  across the last three reports").

**A (annual EPS growth, canon ≥ 25%/yr over 3 years):**

- Requires `A_MIN_YEARS` fiscal years (3 growth intervals); fewer → `unavailable`.
- `pass` iff the 3-year CAGR from oldest to newest is ≥ `A_MIN_CAGR_PCT` **and** at most
  one down year in between (O'Neil tolerates a single off year, not erratic earnings).
- Oldest EPS ≤ 0 → CAGR undefined → fallback: `pass` if every year is positive and newest
  ≥ 2× oldest; otherwise `unavailable`.
- Evidence lists the per-year EPS values and the CAGR.

Three-state verdicts keep "we can't tell" strictly separate from "the answer is no" — thin
EPS history is the common case for recent IPOs, which are disproportionately the stocks
O'Neil setups fire on.

## Error handling

- `load_earnings_history` raises loudly: `ValueError` for an unsupported configured
  vendor; a `NoMarketDataError`-style failure (matching `y_finance.py`'s convention) for
  empty/malformed vendor responses. It never returns a silently-empty history that would
  masquerade as "company has no earnings."
- The `oneil_bias.py` integration is the only place exceptions are swallowed: one
  try/except around fetch+score, degrading to `unavailable` verdicts carrying the reason.
  Network problems, missing API keys, rate limits all become an honest
  "unavailable: <reason>" in the report; the technical read is untouched.
- The scorer raises nothing for data-shaped issues; insufficient/ambiguous data is a
  semantic outcome (`unavailable`), not an error.

## Testing

- `tests/test_canslim_earnings.py` — bulk of coverage, all pure, hand-built
  `EarningsHistory` fixtures, `@pytest.mark.unit`: C pass/fail/exactly-25% boundary,
  acceleration accelerating/decelerating/mixed/null, negative-current-EPS auto-fail,
  near-zero year-ago base, fiscal-quarter matching including a 53-week drift case,
  insufficient quarters; A pass/fail, one-down-year tolerated, two-down-years fail,
  negative-oldest fallback, insufficient years.
- `tests/test_canslim_earnings_data.py` — normalization with vendor calls monkeypatched
  (canned yfinance frames / AV JSON): report-date filtering excludes a quarter reported
  after `curr_date` even though its fiscal period ended before it (the leakage case,
  asserted explicitly); annual-EPS availability gating; unsupported-vendor `ValueError`.
- `tests/test_oneil_bias.py` — extended, not rewritten: `canslim_earnings` key present;
  degradation path (fetcher raising → `unavailable` verdicts + intact technical payload).
- One `@pytest.mark.integration` smoke test hitting yfinance for a real ticker's history
  shape — skipped in normal runs per repo convention. yfinance's actual
  `get_earnings_dates` depth must be verified empirically during implementation (Task-level
  step), since ~8 quarters is expected but not guaranteed; if depth proves < 7, C still
  works (5 needed) but acceleration will often be `null` for yfinance users — acceptable,
  narrated honestly.

## Non-goals

- No S/L/I/M letters (already covered elsewhere or punted).
- No confidence coupling into `compute_confidence` — narration only.
- No caching layer (yfinance is unmetered; the AV `EARNINGS` endpoint is one call per run).
- No `interface.py`/upstream edits; no changes to the Fundamentals Analyst.
- No report-schema changes beyond the additive `canslim_earnings` key.

## Codex model tiers per plan task

Pure scorer (`canslim_earnings.py` + tests): **terra**. Vendor fetch/normalization
(`canslim_earnings_data.py` + AV wrapper + tests): **sol** (date-gating subtleties across
two vendors is the hardest part). `oneil_bias.py` integration + `market_analyst.py`
paragraph + `test_oneil_bias.py` extension: **terra**. Always pass `-m gpt-5.6-<tier>`
explicitly.

## Acceptance criteria

- All new and updated tests pass; scoped `pytest -q` on the three test files plus
  `ruff check` on changed files. `market_analyst.py` is the only cross-agent touchpoint;
  run `tests/test_market_analyst_prefetch.py` as well if it asserts on the prompt.
- A quarter reported after `curr_date` never influences any verdict, even when its fiscal
  period ended before `curr_date` (the leakage test is the contract).
- With `fundamental_data: yfinance` and no network, the O'Neil technical payload is
  byte-identical to today's except for the added `canslim_earnings` key with `unavailable`
  verdicts.
- Report narration states verdicts with numbers and dates; `unavailable` is stated as
  such, never guessed around.

> Research/analysis support only; not investment advice; no trade execution.
