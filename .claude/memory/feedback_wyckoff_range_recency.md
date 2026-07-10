---
name: feedback-wyckoff-range-recency
description: "In TradingAgents Wyckoff structure detection, \"is this range still valid\" must be judged by current-price proximity, not by how recently a pivot was touched"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 70e4563b-9865-413f-9e19-0cfb396fb80f
---

When determining whether a detected trading range (accumulation/distribution) is still structurally relevant "as of today," use **price proximity** (is the current close still within roughly one range-height of the boundaries) — not **pivot recency** (was a new swing high/low touched within the last N trading days).

**Why:** The user pushed back on an early implementation of `tradingagents/dataflows/wyckoff_range.py`'s `detect_trading_range`, which required the range's most recent pivot touch to fall within the last ~60 trading days of the lookback window. Real accumulation/distribution campaigns routinely sit quietly for months with no new extreme printed — that's expected Wyckoff behavior (Phase B/C consolidation), not a sign the structure has expired. The recency-based filter was silently dropping valid, still-in-play ranges and reporting `neutral`/`none` for stocks that actually had an active structure, just because it had gone quiet. This was caught via real-ticker spot checks (TSLA, AAPL, etc.) after the feature shipped and tests passed — the synthetic unit tests hadn't covered a "long quiet stretch" scenario.

**How to apply:** When building or reviewing similar deterministic technical-structure detectors (support/resistance, ranges, consolidations) in this codebase, prefer "is price still near this level/structure" over "was this level/structure recently re-confirmed by a new pivot" as the liveness test — the former matches how these structures actually behave in real price action. See `WYCKOFF_ANALYSIS_PLAN.md`'s "交易区间探测" section for the specific fix (price within one range-height of the boundary), and `tests/test_wyckoff_range.py`'s `test_range_stays_valid_through_a_long_quiet_stretch_if_price_is_still_nearby` / `test_range_is_dropped_once_price_has_drifted_far_beyond_it` for the regression tests that pin this behavior.
