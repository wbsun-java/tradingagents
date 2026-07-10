---
name: oneil-stage4-status
description: "O'Neil detectors fully corrected and committed through double-bottom v5 (9398006); only base-chaining remains, plus optional stage-4 LLM rerun"
metadata: 
  node_type: memory
  type: project
  originSessionId: fc8faf11-79a3-4580-9066-5b4be720e03d
---

State as of 2026-07-10 end of session (all committed on main, working tree clean):

- Complete O'Neil correction arc, all via codex-delegate, all user-verified:
  1. Peak anchoring + containment for cup/flat/DB per [[pattern-start-at-high]]
     (72d6922, 457be3f, 291f6a2).
  2. Forming-cup stage, highest-rim selection, dual cup candidates, forming-means-now
     (60831ef and the cup commits).
  3. Canonical numbers: prior advance >=30%, cup 35-325d, depth <=60% cup (user
     choice) / 15-50% DB (book), flat <=15%, breakout 1.4x vs 50-DAY volume SMA
     (c168e85), handle-high pivot, handle downward drift, cup-bottom dry-up.
  4. Lifecycle (8ff5913): BASE_MAX_AGE_DAYS=325 from starting peak; structure_broken
     -> failed on buffered close below the defining low (handle low for
     cup_with_handle, range low flat, min(L1,L2) DB, last pullback low ascending,
     flag low HTF). oneil_base_lifecycle.py.
  5. Double bottom v5 (9398006): flexible lows per [[double-bottom-microstructure]];
     undercut guard max(3%,1.5ATR) + 10-bar reclaim; halves geometry (M upper half,
     feet lower half); right-side up/down-day volume narrated (not gated);
     second_low_behavior three-way restored in detector AND Market Analyst prompt.
- Live sweep behavior (2026-07-10): GOOGL false W dead (reads cup_without_handle
  developing, pivot at the 348.55 rim); TSLA W survives as L2=higher; NVDA W as
  valid undercut; META/XOM/PLTR/COIN/NFLX Ws culled; HOOD cup_without_handle forming
  from 2025-10-06 @153.86; CRWD HTF confirmed.
- REMAINING QUEUE (user picks later): (a) base-chaining — verify a flat base follows
  a prior pattern's confirmed breakout (IBD 20%-from-prior-pivot continuation rule);
  new infrastructure, deferred by agreement. (b) optional stage-4 LLM report rerun,
  e.g. `python scripts/stage4_oneil_verify.py TSLA 2026-07-10` (higher-L2 W
  narration).
- Process: every fix goes through codex-delegate (never hand-edit); present
  canon/numbers verification BEFORE launching (user interrupts launches otherwise);
  commits only on explicit approval.
