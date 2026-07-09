# O'Neil CANSLIM Technical Analysis Plan

## Goal

Add a deterministic structure-detection tool to the Market Analyst based on the
price/volume technical-analysis portion of William O'Neil's CANSLIM methodology: cup-with-handle
pattern detection, a breakout volume-confirmation rule, and a relative-strength (RS) score
added alongside the existing Minervini trend template. This conclusion ranks below the Wyckoff
structural read in the Market Analyst's overall technical judgment, but above geometric chart
patterns (`chart_patterns`), the trend template (`trend_template`), and ordinary technical
indicators (MACD, Bollinger Bands, etc.).

The fundamentals/institutional-sponsorship letters of CANSLIM (C-A-N-S-L-I — earnings growth,
institutional ownership, etc.) are out of scope for this plan; that belongs to the Fundamentals
Analyst, not a pure technical-analysis addition to the Market Analyst.

## Core Principles

Continuing the principles from `CHART_PATTERN_ANALYSIS_PLAN.md`, `MINERVINI_TREND_TEMPLATE_PLAN.md`,
and `WYCKOFF_ANALYSIS_PLAN.md`:

1. **Structure is identified by code; the LLM only explains it.** The LLM may not claim to
   have identified a cup-with-handle or breakout purely by eyeballing a CSV.
2. **No future data.** All computation only uses data on or before `curr_date`.
3. **Use adaptive thresholds.** Cup depth/duration, handle depth/duration, and the breakout
   volume threshold all use adaptive judgments (ATR, price ratios, volume ratios), never
   fixed percentages.
4. **Provide evidence.** Every detected cup, handle, and breakout event must include a date,
   price, and volume-based justification.
5. **Neutral is allowed.** When no valid cup-with-handle structure is found, `setup_bias` must
   be `neutral` — never forced.
6. **Weight is a policy declaration, not a backtest artifact.** `secondary_weight` is a fixed,
   project-level constant that must be lower than Wyckoff's `dominant_weight` (0.6), to reflect
   its secondary-tier standing; the exact value may later be calibrated by backtesting, but that
   calibration is not an acceptance criterion for this plan.

## Data Flow

Default lookback window `look_back_days=420` (~20 months). O'Neil's cup base typically lasts
7-65 weeks and requires a meaningful prior uptrend leading into it, so the window needs to be
noticeably longer than `chart_patterns.py`'s existing ~252-trading-day default.

```text
Ticker + Analysis Date
          │
          ▼
load_ohlcv (cache, symbol normalization, date cutoff — ~20 months by default)
          │
          ▼
ATR + pivot detection (reuses chart_patterns.py's Pivot / find_pivots)
          │
          ▼
Cup detection (oneil_cup_handle.py) → Handle detection (oneil_cup_handle.py)
          │
          ▼
Breakout + volume confirmation / status / confidence scoring (oneil_breakout.py)
          │
          ▼
              Structured JSON report
                           │
                           ▼
     Market Analyst treats this as the secondary technical anchor: defers to
     Wyckoff's direction when Wyckoff is non-neutral; becomes the anchor itself
     when Wyckoff is neutral. Chart patterns / trend template / indicators may
     only adjust conviction within that direction.
```

Separately, a small independent change adds a continuous `rs_score` next to `trend_template.py`'s
existing single-benchmark relative-strength criterion — weighted by quarter (most recent quarter
weighted more heavily, per O'Neil), used as supporting evidence for cup-with-handle breakout
confidence. It does not change the existing `relative_strength_at_new_high` boolean criterion's
semantics.

## Algorithm Design

### Cup Detection (`oneil_cup_handle.py`)

- **Prior uptrend requirement:** the cup's left-side high must be preceded by a meaningful
  advance. A rounding shape with no prior uptrend is just an ordinary bottom, not an O'Neil cup.
- **Cup depth:** an adaptive range based on ATR / percentage decline from the left-side high
  (O'Neil's own guideline is roughly 12%-33%, wider in extreme markets), never a hardcoded
  fixed percentage.
- **Cup duration:** an adaptive range around O'Neil's 7-65 week guideline, expressed in trading
  days.
- **Shape validation (U-shape, not V-shape):** the decline and recovery must show rounding
  (basing days near the low), not one or a few near-vertical drops — the same "quiet vs.
  violent" evidence discipline the Wyckoff module already applies to distinguishing a quiet
  Spring from a violent Terminal Shakeout; the evidence text must state explicitly which kind
  of behavior was observed, not just report numbers.
- **Right-side confirmation:** the cup's right side must recover to within an ATR buffer of the
  left-side high (the future pivot buy point) before handle detection begins.

### Handle Detection (`oneil_cup_handle.py`)

- Must form in the cup's upper half; a handle whose low drops into the cup's lower half
  invalidates the structure.
- Handle pullback uses an adaptive threshold (smaller than the cup's depth), with a duration
  shorter than the cup (roughly O'Neil's 1-4 week guideline).
- Volume during the handle must be lower than volume during the cup ("volume dry-up") — this
  is a hard validity condition for the handle, not merely a confidence bonus.

### Breakout + Volume Confirmation (`oneil_breakout.py`)

- Breakout condition: close above the pivot buy point (the cup's left-side high), with volume
  meaningfully elevated versus the recent average (an adaptive ratio threshold, not a fixed
  multiple).
- Status machine: `forming` (cup only) → `developing` (handle complete, no breakout yet) →
  `confirmed` (breakout with volume confirmation) → `failed` (handle depth invalidated the
  structure, or the price closed back below the pivot after breaking out).
- A breakout on insufficient volume is not immediately `failed` — it stays `developing`, since
  volume could still confirm in a following session, matching `chart_patterns.py`'s existing
  forming/confirmed distinction.
- Confidence scoring combines cup/handle shape clarity, breakout volume strength, and
  `trend_template.py`'s new `rs_score` (O'Neil requires improving relative strength going into
  a breakout).

### Relative Strength Score Addition (`trend_template.py` change)

- Add `rs_score`: a quarter-weighted return ratio versus the benchmark (most recent quarter
  weighted more heavily), added as a continuous value in the `values` field.
- Does not change the existing `relative_strength_at_new_high` boolean criterion,
  `passed_count`, or `stage_2_uptrend` computation — existing behavior and tests are unaffected.

## Output Interface

Tool name:

```python
get_oneil_setup(
    symbol: str,
    curr_date: str,
    look_back_days: int = 420,
) -> str
```

Example JSON output:

```json
{
  "symbol": "AAPL",
  "analysis_date": "2026-07-08",
  "cup": {
    "start_date": "2025-09-02",
    "left_high": 198.5,
    "low_date": "2025-11-20",
    "low_price": 162.3,
    "right_high_date": "2026-02-10",
    "depth_pct": 18.2,
    "duration_days": 96
  },
  "handle": {
    "start_date": "2026-02-11",
    "end_date": "2026-02-25",
    "low_price": 189.1,
    "volume_ratio_vs_cup": 0.62
  },
  "breakout": {
    "date": "2026-02-26",
    "pivot_price": 198.5,
    "close": 200.4,
    "volume_ratio": 1.55
  },
  "status": "confirmed",
  "setup_bias": "bullish",
  "confidence": 0.68,
  "secondary_weight": 0.4,
  "weight_note": "O'Neil cup-with-handle read ranks below Wyckoff but above chart patterns, trend template, and indicators; if Wyckoff phase_bias is non-neutral, it takes precedence over this result."
}
```

When `status` is `forming`, the `handle`/`breakout` fields are absent; when `developing`, the
`breakout` field is absent. When no valid cup is found, `setup_bias = "neutral"` and
`secondary_weight` is still returned as usual.

## Market Analyst Integration

The Market Analyst must:

1. Call `get_oneil_setup` before the final report (in the same batch as `get_wyckoff_structure`).
2. Apply a three-tier conflict-resolution rule:
   - **Tier 1 (Wyckoff):** when `phase_bias` is non-neutral, direction is ultimately decided by
     Wyckoff — unchanged from the current rule.
   - **Tier 2 (O'Neil):** when Wyckoff is neutral and `setup_bias` is non-neutral, `setup_bias`
     becomes the directional anchor; chart patterns, trend template, and indicators may only
     adjust conviction within that direction, never flip the final technical conclusion. If
     Wyckoff is also non-neutral and conflicts with O'Neil's direction, Wyckoff wins, but the
     report must explicitly state that it "conflicts with the O'Neil cup-with-handle structure."
   - **Tier 3:** when both Wyckoff and O'Neil are neutral, other technical evidence is weighed
     normally, unchanged from today.
3. The report must name the specific cup, handle, and breakout events with their dates, prices,
   and volume — not just state a directional conclusion.
4. Add a row to the Markdown table reflecting `status` / `setup_bias` / `secondary_weight`.
5. Must not invent cup-with-handle structures beyond what the tool reports from the raw CSV.

## File Structure

```text
tradingagents/dataflows/oneil_cup.py
    Cup detection for O'Neil's cup-with-handle pattern: finds a rounded
    consolidation base after a meaningful prior uptrend using centered
    swing-pivot logic shared with chart_patterns.py and wyckoff_range.py.

tradingagents/dataflows/oneil_handle.py
    Handle detection for O'Neil's cup-with-handle pattern: finds the earliest
    confirmed handle trough after a completed cup, requiring the pullback to
    stay in the cup's upper half and show volume dry-up versus the cup.

tradingagents/dataflows/oneil_breakout.py
    Breakout confirmation for O'Neil's cup-with-handle: requires a close above
    the pivot buy point with meaningfully above-average volume, then derives
    forming/developing/confirmed/failed status and confidence scoring.

tradingagents/dataflows/oneil_bias.py
    Synthesizes the O'Neil cup-with-handle read into tool-facing JSON,
    including the project-policy secondary_weight that ranks below Wyckoff's
    dominant_weight.

tradingagents/agents/utils/oneil_tools.py
    LangChain tool wrapper: get_oneil_setup(symbol, curr_date, look_back_days)

tradingagents/dataflows/trend_template.py (existing file, small edit)
    Add rs_score: a quarter-weighted return ratio vs. benchmark, coexisting with the
    existing relative_strength_at_new_high boolean criterion without changing its behavior.

tradingagents/agents/analysts/market_analyst.py (existing file, edit)
    Bind get_oneil_setup; add the three-tier conflict-resolution paragraph.

tradingagents/graph/trading_graph.py (existing file, edit)
    Register get_oneil_setup in the market ToolNode.

tradingagents/agents/utils/agent_utils.py (existing file, edit)
    Export get_oneil_setup.

tests/test_oneil_cup.py
    Synthetic-OHLCV unit tests for cup geometry detection.

tests/test_oneil_handle.py
    Synthetic-OHLCV unit tests for handle geometry detection.

tests/test_oneil_breakout.py
    Synthetic-OHLCV unit tests for breakout/volume confirmation and the status machine.

tests/test_oneil_bias.py
    Synthetic-OHLCV unit tests for tool-facing JSON synthesis and secondary weighting.

tests/test_trend_template.py (existing file, add cases)
    Assertions on rs_score's quarter-weighting behavior; regression assertions that
    relative_strength_at_new_high / passed_count / stage_2_uptrend are unchanged.

tests/test_market_toolnode.py (existing file, add case)
    Add a wiring assertion for get_oneil_setup in the market ToolNode.
```

## Testing Plan

Tests use synthetic OHLCV to avoid real-market flakiness affecting algorithm validation.

- **Cup detection:** a textbook cup (prior uptrend → U-shaped decline and recovery within the
  adaptive depth/duration range) must be detected correctly; a single/consecutive sharp V-shaped
  drop must not qualify as a valid cup; candidates outside the adaptive depth/duration range
  must return no structure.
- **Handle detection:** a valid handle (upper-half pullback, volume dry-up, shorter duration
  than the cup) must be detected correctly; a handle whose low drops into the cup's lower half
  must invalidate the structure.
- **Breakout confirmation:** a volume-confirmed breakout above the pivot → `confirmed`; a
  low-volume breakout → stays `developing` (not `failed`); a confirmed breakout that closes back
  below the pivot → `failed`; confidence should vary sensibly and monotonically with volume
  ratio and `rs_score`.
- **`trend_template.py`:** new test cases confirming `rs_score` scores a stock that outperformed
  mainly in the most recent quarter higher than one with the same total return but earlier
  outperformance; plus a regression check that `relative_strength_at_new_high`, `passed_count`,
  and `stage_2_uptrend` are byte-for-byte unchanged from before this change.
- The market ToolNode must register `get_oneil_setup`.
- No data after the analysis date may participate in any result (future-data leakage check,
  same convention as the other three modules).
- **Not unit-testable, deferred to stage 4 (`antigravity-verify`):** the three-tier
  conflict-resolution rule is prompt text, not code, so it needs a real or constructed market
  scenario — one ticker where Wyckoff is neutral and O'Neil confirms a breakout (report should
  lead with the O'Neil direction), and one where Wyckoff and O'Neil genuinely disagree (report
  should lead with Wyckoff and explicitly flag the conflict).

## Acceptance Criteria

- All new tests pass.
- This change touches shared tool exports (`agent_utils.py`) and graph node registration
  (`trading_graph.py`), so per CLAUDE.md's verification policy, run a full `pytest -q` and
  `ruff check .` pass as well.
- `ruff check` passes.
- The Market Analyst can actually call `get_oneil_setup`, and the report reflects the
  cup-with-handle conclusion and the three-tier priority rule.
- Output contains no data after the analysis date.
- Every detected cup/handle/breakout event has auditable date, price, and volume evidence.

## Current Implementation Status

- [ ] Cup detection (`oneil_cup.py`)
- [ ] Handle detection (`oneil_handle.py`)
- [ ] Breakout + volume confirmation / status machine / confidence scoring (`oneil_breakout.py`)
- [ ] Tool-facing JSON synthesis / secondary weighting (`oneil_bias.py`)
- [ ] `trend_template.py` `rs_score` addition
- [ ] LangChain tool wrapper (`oneil_tools.py`)
- [ ] Market Analyst and market ToolNode integration (three-tier priority rule)
- [ ] Synthetic-market unit tests (cup, handle, breakout, rs_score, ToolNode wiring)
- [ ] Full project regression tests (`pytest -q` + `ruff check .`)
- [ ] Stage 4 scenario verification (Wyckoff-neutral + O'Neil-confirmed / Wyckoff-vs-O'Neil conflict)

## Future Iterations

1. Other O'Neil base patterns (flat base, ascending base, etc.) — only cup-with-handle is
   implemented in this plan.
2. A true market-wide percentile RS Rating (1-99), which needs price data for a broad stock
   universe; this plan's `rs_score` is only a single-benchmark weighted proxy.
3. Use a walk-forward script similar to `scripts/backtest_chart_patterns.py` to historically
   calibrate the cup depth/duration thresholds, the breakout volume threshold, and
   `secondary_weight` (default 0.4).
4. Evaluate whether the volume-on-breakout rule should also apply to `chart_patterns.py`'s
   other existing patterns (explicitly excluded from this plan, cup-with-handle only).

> This feature is for research and analytical assistance only. It is not investment advice and
> does not execute trades automatically.
