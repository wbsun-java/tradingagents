---
name: oneil-stage4-status
description: "O'Neil base-pattern expansion - all 8 tasks committed; stage 4 found two start-anchor bugs; awaiting user's pick (cup recommended first)"
metadata: 
  node_type: memory
  type: project
  originSessionId: fc8faf11-79a3-4580-9066-5b4be720e03d
---

State as of 2026-07-10 (plan: `docs/superpowers/plans/2026-07-10-oneil-base-patterns.md`):

- All 8 plan tasks done via codex-delegate and committed on main
  (adee528..f86aa65: types, engine, flat base, double bottom, ascending base, HTF,
  orchestrator/JSON, prompt sweep). Full suite was green (684 passed, ruff clean).
- `scripts/stage4_oneil_verify.py` (market-analyst-only propagate runner) exists,
  ruff-clean, UNCOMMITTED. User ran the stage-4 scenarios themselves; code works.
- Stage-4 audit of every detector against [[pattern-start-at-high]] found:
  1. **Cup bug** (`oneil_cup.py detect_cup`): no containment gate — interior highs may
     exceed the chosen left high; rim slides to an earlier lower pivot to fit the 50%
     depth cap (HOOD live case). Fix: reject lh if any High in (lh, right_high) exceeds
     lh.price + ~0.25 ATR; regression test = HOOD-shaped fixture must yield None.
  2. **Double-bottom bug** (`oneil_double_bottom.py`): prior_uptrend anchored at L1
     (first bottom) instead of the last settled pivot high before L1; deep first
     declines wrongly rejected; prior high absent from geometry/evidence. Full fix spec
     was drafted (re-anchor gate, require decline from prior high, add prior_high to
     geometry + dated/priced evidence, deep-decline regression test).
  3. Flat base minor (start not pinned to arrival high, bounded by 15% depth cap);
     generic chart-tool double bottom cosmetic (start_date at first low).
- Next step when user returns: they pick which pattern to fix first (Claude recommended
  cup); fix goes through codex-delegate (gpt-5.6-terra), never hand-edited; commits
  need explicit approval per [[no-auto-commit-specs]].
- Useful stage-4 candidates from live scans (2026-07-10): CRWD high_tight_flag
  developing, HOOD Wyckoff-conflict, LLY 2026-05-15 weak double-bottom supersede.
