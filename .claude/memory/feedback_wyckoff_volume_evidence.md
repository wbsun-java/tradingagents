---
name: feedback-wyckoff-volume-evidence
description: "In TradingAgents Wyckoff analysis, volume characteristics must be surfaced explicitly in event evidence text, not just recorded as a silent JSON field"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 70e4563b-9865-413f-9e19-0cfb396fb80f
---

Volume is the single most load-bearing signal in Wyckoff/VSA analysis. Any event a detector reports (spring, upthrust, climax, test, etc.) must state its volume character in the human-readable evidence text — not just carry a `volume_ratio` number in the JSON that a downstream reader could miss or ignore.

**Why:** The user manually inspected a real NKE run and said a July 1st volume spike "doesn't seem to have been captured" — it actually *was* captured (as a `spring` event with `volume_ratio: 3.11` in the JSON), but the evidence sentence never mentioned volume at all, so it read as if volume hadn't been considered. Digging further surfaced a second, more substantive bug in `tradingagents/dataflows/wyckoff_events.py`: Spring and Terminal Shakeout are both legitimate Wyckoff Phase C tests, but the code (and `WYCKOFF_ANALYSIS_PLAN.md`) had assumed Springs are always low-volume ("缩量假跌破"), when in reality a Spring can be quiet *or* a violent high-volume Terminal Shakeout — NKE's case was the latter (3.1x average volume). Fixed by making the evidence text volume-aware (explicitly says "heavy volume ... terminal shakeout" vs "light volume ... quiet spring").

Fixing this also surfaced a third bug via a new synthetic test: once the climax search scans a wide raw-bar window (see [[feedback_wyckoff_climax_search_window]]), picking the *highest-volume* bar in that window can misfire — a later, louder event (e.g. a violent Spring) can get mistaken for the climax that started the range. Fixed by selecting the *earliest* qualifying bar in the window, not the loudest, since a climax is definitionally what kicks off the range.

**How to apply:** When any TradingAgents technical-structure detector reports a volume-driven event, always render the volume characteristic into the evidence/reasoning text the LLM will read — a number sitting in a structured field that isn't narrated is effectively invisible to both the user and the downstream agent. Also: when a detection window is widened for recall (to fix a false negative), immediately re-check the tie-break/selection rule for false positives it might now introduce — broadening a search space and picking "the most extreme match" are two independent decisions that can fight each other.
