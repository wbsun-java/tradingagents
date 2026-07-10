---
name: oneil-stage4-status
description: "O'Neil base patterns - cup family fully corrected to canonical rules (committed); next queue is double bottom, flat-base start anchor, developing-staleness"
metadata: 
  node_type: memory
  type: project
  originSessionId: fc8faf11-79a3-4580-9066-5b4be720e03d
---

State as of 2026-07-10 evening (plan: `docs/superpowers/plans/2026-07-10-oneil-base-patterns.md`):

- Original 8 plan tasks committed earlier (adee528..f86aa65); stage-4 runner is
  `scripts/stage4_oneil_verify.py` (committed a687977).
- Cup family fully corrected per [[pattern-start-at-high]] and the user's canonical
  cup-and-handle rules, verified by user's own test runs (87 tests + ruff green):
  1. Containment: no interior high may exceed the rim (`contained_below`,
     `starting_peak` helpers in oneil_base_types).
  2. Forming-cup stage (`oneil_cup_forming.py`): highest contained rim, partial
     recovery; HOOD reads cup_without_handle forming from 2025-10-06 @ 153.86.
  3. Dual cup candidates (completed + forming) go to arbitration; failed micro-cups
     can't mask a live forming cup.
  4. Forming means forming NOW: HTF flag / flat-base forming windows must extend to the
     last bar (killed HOOD's stale 2025-07 flag).
  5. Canonical O'Neil numbers: prior advance ≥30% (shared PRIOR_UPTREND_MIN_GAIN_RATIO
     0.3), cup 35-325 days, depth ≤60% (bear-market allowance, user-approved), cup
     bottom volume dry-up hard gate (`oneil_cup_quality.py`, narrated), handle must
     drift downward, cup_with_handle pivot = HANDLE HIGH (not the rim);
     cup_without_handle pivot stays the rim.
- Effect: stale 18-month "developing" cups (MSFT/AMZN/TSLA) correctly culled; NVDA
  pivot now the handle high (2026-04-27 @ 216.83).
- Remaining queue (user picks): (a) double-bottom initial-peak anchor + containment
  (full spec drafted in an earlier session prompt — anchor prior_uptrend at last
  settled pivot high before L1, opening-decline gate, containment through L2,
  prior_high in geometry/evidence); (b) flat-base start pinned to arrival high;
  (c) staleness/price-proximity rule for long-"developing" completed patterns.
- All fixes go through codex-delegate; commits only on the user's explicit approval.
