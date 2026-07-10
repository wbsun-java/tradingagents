---
name: pattern-start-at-high
description: "A base pattern starts at the first high before the correction; the decline is part of the pattern, and detectors must not pick an arbitrary anchor"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: fc8faf11-79a3-4580-9066-5b4be720e03d
---

User's principle (2026-07-10, O'Neil base-pattern stage-4 review): a pattern starts
when price first reaches its HIGH before the correction. The decline off that high is
the pattern's first leg. A pattern exists because price trends overlap for a stretch of
time — bulls and bears battling. A detector must not "simply pick one price as the
starting point": the start must be the actual peak, and no bar inside the pattern may
exceed it.

**Why:** Anchoring at the wrong point produces both false negatives (double bottom:
prior-uptrend gate measured into the first LOW rejects textbook Ws whose first decline
is deep) and false positives with wrong geometry (cup: a lower earlier pivot high
"rim" slides under the 50% depth cap while the true peak sits inside the cup — proven
live on HOOD 2026-07-10: reported rim 2025-09-10 @ 123.44, true peak 2025-10-06 @
153.86, real depth 58.7% > 50% cap, so no valid cup at all).

**How to apply:** Any detector's uptrend/start gate anchors at the pattern's starting
HIGH (cup left high, double bottom's preceding pivot high, ascending base H1). Add a
containment gate: no high strictly inside the pattern may exceed the start high plus a
small ATR tolerance. Related: [[oneil-stage4-status]], [[wyckoff-range-recency]]
