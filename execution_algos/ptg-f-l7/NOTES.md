# Algorithm Notes: ptg-f-l7

Per-iteration experiment — base_algo `position-tier-gate`, context mode `full-trace`, loop 7.

## Hypothesis

Loops 1-6 show all modifications either fail or are no-ops. Loop 7 tries the opposite
direction: make the position gate STRICTER. Instead of cap=1 (skip concurrent), use a
**volume-weighted position cap**: skip not just when position >= 1, but also skip if the
oracle has fired >= N times in the last T seconds (clustering filter). Rationale: if
the oracle fires rapidly in the same direction, the later signals may be lower quality
(diminishing returns from multiple entries in the same direction).

This is a cluster-filter: skip if >= 3 oracle signals have been submitted in the last 5s.

---

## Implementation Decisions

- position_cap=1 (preserved)
- cluster_window_seconds=5.0: rolling window for counting submitted opens
- cluster_threshold=3: skip if >= 3 opens submitted in window

---

## Backtest Observations

**Full 12-date train window:**
ptg-f-l7 (cluster filter + cap=1): pnl=$4,262.50, 0.00% vs base, trades=90,433 = IDENTICAL.
Post-mortem: Cap=1 already limits entries to ~90k; cluster rate stays below threshold.
**Hypothesis verdict**: No-op. Cluster filter never fires in serialized-entry regime.
**Suggested next**: Very short reentry (loop 8, final).
