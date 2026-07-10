---
name: project-market-analyst-ta-modules
description: "Status of the three deterministic technical-analysis tool modules built for Market Analyst: chart patterns, Minervini trend template, Wyckoff structure"
metadata: 
  node_type: memory
  type: project
  originSessionId: 75c57e5d-6cdf-4687-bc54-99e8f52df6bd
---

Market Analyst has three deterministic (code-computed, not LLM-eyeballed) technical-analysis
tool modules, each with its own root-level `*_PLAN.md` and following shared design principles:
structure identified by code (LLM only explains it), no future-data leakage, adaptive
thresholds (ATR / volume ratios, not fixed percentages), every conclusion backed by
dated/priced evidence, and neutral output allowed when no clear structure exists.

1. **Chart patterns** (`CHART_PATTERN_ANALYSIS_PLAN.md` -> `chart_patterns.py` +
   `trendline_fit.py` + `triangle_breakout.py`). Core detection done and tested: pivots/ATR,
   support/resistance clustering, double top/bottom, boxes, triangles (rising/falling/
   symmetric) with apex-based breakout timing, breakout/breakdown confirmation and failure,
   target/invalidation prices. Deferred: `emerging` pre-confirmation state, entry-state
   taxonomy (`predictive_bottom` / `breakout_entry` / `breakout_retest_entry` / `observe`),
   false-breakout/false-breakdown signals, apex-timing threshold differentiation, and full
   historical calibration via `scripts/backtest_chart_patterns.py`.
2. **Minervini trend template** (`MINERVINI_TREND_TEMPLATE_PLAN.md` -> `trend_template.py`).
   All 8 criteria + relative-strength approximation done and tested; validated on real data
   (AAPL 7/8 pass, TSLA 3/8 — below 50/150/200-day MAs, as expected). Deferred: more rigorous
   relative-strength calibration and a dedicated backtest script analogous to the chart-pattern
   one.
3. **Wyckoff structure** (`WYCKOFF_ANALYSIS_PLAN.md` -> `wyckoff_range.py`, `wyckoff_events.py`,
   `wyckoff_accumulation.py`, `wyckoff_distribution.py`, `wyckoff_bias.py`, `wyckoff_tools.py`,
   plus Stage 2's `wyckoff_vsa_signals.py`, `wyckoff_vsa_range_signals.py`, `wyckoff_vsa.py`).
   Stage 1 (structural/event identification, Phase A-E, `get_wyckoff_structure` tool) done
   2026-07-07: 20 tests, full suite green, ruff clean, validated against real tickers. Stage 2
   (VSA — per-bar effort/result detectors feeding a bounded ±0.15 confidence adjustment) done
   2026-07-09 via brainstorm -> spec -> plan -> codex-delegate per task, commits 6cae314..4c0b6af
   on `main`: 8 detectors split across two files (150-line cap forced a mid-implementation
   split into `wyckoff_vsa_signals.py`/`wyckoff_vsa_range_signals.py`), 26 tests, ruff clean.
   Walk-forward calibration report done 2026-07-09 (`scripts/backtest_wyckoff.py` + additive
   `vsa_confidence_delta` field on `wyckoff_bias.py`, commits 6f47d80/0275dfa/37e8dd7): a
   read-only hit-rate report bucketed by `(current_phase, vsa_effect)` — mirrors
   `backtest_chart_patterns.py`, does not auto-tune anything; a human still reads the report
   and hand-edits `DOMINANT_WEIGHT`/confidence formula/VSA constants. Breakout-failure
   (invalidation) detection done 2026-07-09 (`wyckoff_invalidation.py`, commits
   963a907/91ca768/0665479, spec at `docs/superpowers/specs/2026-07-09-wyckoff-invalidation-design.md`):
   investigation found the plan's literal "composite/multi-range structure" item was already
   mostly handled by `detect_trading_range`'s own candidate-selection logic (prefers newest
   range, excludes stale ones once price drifts too far); the real gap was Phase D/E reads
   never checking whether the breakout held. Now a reversal back through the original boundary
   after the last event forces `phase_bias: "neutral"`, `confidence: 0.0`,
   `status: "invalidated"`, skips the VSA step, on a new `range_failure` event. Final review:
   0 Critical/Important, ready-to-merge. Downstream weight-rule extension done 2026-07-09
   (commits 75261ad/3577d31/827b038 + fix 26f98a2, spec at
   `docs/superpowers/specs/2026-07-09-wyckoff-downstream-weight-design.md`): the first upstream
   files this project has ever edited (see [[project_wyckoff_downstream_approval]] for the
   scoped approval) — `market_analyst.py` now explains `invalidated`/`range_failure` in its own
   prompt, and bull/bear researcher + aggressive/neutral/conservative risk debators each gained
   one tailored paragraph telling them how to weight the Wyckoff `phase_bias`/`dominant_weight`
   already present in `market_report` (prompt-guidance only, no new AgentState plumbing —
   investigation found the data was already reliably reaching these agents). Final review: 0
   Critical/Important, 4 Minor (redundant test assertions, fixed same session). **All four
   Wyckoff "后续迭代" items are now complete — the Wyckoff module is done.**

All three exist so Market Analyst gets a code-verified, evidence-anchored technical verdict
instead of letting the LLM guess a pattern from a raw CSV.

Release state: package version is still `0.3.0` (CHANGELOG.md, released 2026-06-22). Wyckoff
Stage 1+2, the Claude-architect workflow skills (gemini-intake, codex-delegate,
antigravity-verify), and the memory-log-stats-cli pilot ([[project_claude_architect_workflow]])
have all landed on `main` since but are unreleased/not yet in the changelog.

**Deferred-work sequencing (set 2026-07-09, user's explicit order):** work through each
module's deferred/follow-up items one at a time, in this order: (1) Wyckoff — **all four
后续迭代 items complete** (walk-forward calibration, breakout-failure invalidation, downstream
weight-rule extension into bull/bear/risk-debate agents; Stage 1+2 were already done). (2)
O'Neil CANSLIM — next up; not the stage-4 MA-precedence item (already done), but a newly
discovered scope gap: see [[project_oneil_canslim_feature_status]]'s 2026-07-09 update — the
module only detects cup-with-handle + an RS proxy, undersells O'Neil's actual methodology
(other base patterns, CANSLIM's fundamental letters). Open decision, not yet chosen by the
user; ask which direction (expand base patterns / build CANSLIM fundamentals / just fix
labeling) when resuming. (3) Pocket Pivot — no deferred items currently on record; likely just a
calibration-script pass for consistency. (4) Minervini trend template — RS calibration +
backtest script. (5) Chart patterns last (user called it "the most difficult one") — emerging
state / entry-state taxonomy / false-breakout signals / backtest script. Follow this order
unless the user redirects.

**Why:** the user builds this TA-module family one at a time, each behind its own plan doc,
and expects "what's the status" answered from the plan's checklist + tests rather than
re-derived from git archaeology every session.

**How to apply:** when asked for project status, check this memory's three-module list and
the release-state note first. When starting a new TA module, follow the same shared-principles
pattern these three use (code-does-structure, no future data, ATR/volume-adaptive thresholds,
evidence required, neutral allowed) rather than inventing a new convention.
