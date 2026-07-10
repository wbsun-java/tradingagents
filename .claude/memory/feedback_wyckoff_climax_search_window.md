---
name: feedback-wyckoff-climax-search-window
description: "In TradingAgents Wyckoff event detection, search for climax/capitulation bars across a raw-bar window, not just the pivots that define the range boundary"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 70e4563b-9865-413f-9e19-0cfb396fb80f
---

When detecting a Wyckoff selling/buying climax (or any "extreme event" that's expected to anchor a structure), search **raw bars in a window** around the range's formation — not just the subset of pivots that happened to cluster into the range's boundary.

**Why:** The user manually spot-checked `get_wyckoff_structure` against real tickers (NKE, then a broader scan) after the feature shipped with passing unit tests. NKE showed `neutral` despite a real, textbook accumulation range being present. Root cause: the climax search (`tradingagents/dataflows/wyckoff_events.py`) only considered pivots in `rng.low_touches`/`rng.high_touches` (the exact touches that define the boundary cluster). A real capitulation bar often prints *away* from where the range eventually settles — price keeps drifting a little further before finding support — so the actual highest-volume capitulation day (NKE: 2026-04-01, 6.8x average volume) was priced too far from the final boundary to cluster into the touch list, and was silently invisible to the detector. Fixed by scanning a window of raw bars spanning from `start_index - 20` to `last_touch_index + 20` for the highest-volume bar within one range-width of the boundary, instead of restricting to the clustered touch pivots. This is the same category of lesson as [[feedback_wyckoff_range_recency]] (proximity-based, not structurally-exact-match-based) but on a different sub-component — worth checking for the same pattern in any future Wyckoff work (e.g. Stage 2 VSA): don't assume the pivot/cluster abstraction built for boundary detection is the right search space for finding a *different* kind of event.

**How to apply:** After shipping a detector whose unit tests are synthetic-fixture-only, do a real-ticker spot-check sweep (multiple tickers/dates) before trusting the feature — synthetic fixtures encode the author's assumptions and can miss exactly this kind of "the real event doesn't line up with the abstraction" gap. When adding new Wyckoff sub-events, ask "would this actually be one of the already-detected pivots, or could it plausibly print elsewhere nearby?" before restricting the search space to an existing pivot/cluster list.
