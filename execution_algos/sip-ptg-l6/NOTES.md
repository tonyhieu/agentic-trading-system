# sip-ptg-l6 — Zero-PnL-After-Flip Gate

## Hypothesis

**Base mechanism (Step 1)**

`position-tier-gate` conditions on `self.cache.positions_open()` net quantity at `on_order()` time. With `position_cap=1`, it skips non-reduce-only OPEN orders when net_qty ≥ 1. This serializes entries: one position at a time. All reduce-only CLOSE orders always submit (intraday_flat). All standalone OPENs (when flat) always submit.

**Weakness (Step 2)**

When the oracle generates a signal where the entry price and exit price are IDENTICAL (zero realized PnL for a closed position), the subsequent direction-flip OPEN arrives with a stale signal: no new price information has been incorporated. These "post-zero-flip" OPENs have mean realized PnL of -0.0020 (slightly negative) across 12 training dates. In regime X (post-zero-PnL-close), the base submits all direction-flip OPENs; if instead it skipped them, expected outcome is a small gain from avoiding marginally negative trades.

*"In the regime where the last closed position had zero PnL and the new OPEN is a direction flip, the base submits unconditionally; if instead it skipped, expected outcome is elimination of the -0.002/trade drag from this event class."*

**Modification (Step 3)**

Add a secondary gate for standalone OPENs (non-reduce-only, when net_qty=0):
- Query `self.cache.positions_closed(instrument_id=...)` for the most recently closed position.
- If the last closed position had zero realized PnL AND the current OPEN is a direction flip from that position's entry direction: SKIP.
- Otherwise: SUBMIT as normal.

Constraints check:
- **No opposing positions**: we SKIP the OPEN entirely, staying flat. No two simultaneous positions.
- **Quantity invariant**: no modification to order quantity.
- **Top-of-book**: unchanged.
- **Participation_cap**: qty=1, unchanged.
- **Intraday_flat**: reduce-only always submits.

## Empirical Pre-Check

**Step 4a — Prediction**

The new branch will fire **at least 500 times per day** on average across the 12 training dates, where N = 500.

Reasoning: from positions.csv analysis, ~11,406 total "post-zero-flip" events across 12 dates = 950/day average.

**Step 4b — Verification surface**

Cached baseline artifacts: `execution_algos/position-tier-gate/results/<YYYYMMDD>/positions.csv`. Count positions where prev_pnl == 0 AND direction_change == True.

**Step 4c — Count and compare**

| Date | Fires |
|------|-------|
| 20260308 | 6 |
| 20260309 | 68 |
| 20260310 | 48 |
| 20260311 | 77 |
| 20260312 | 263 |
| 20260313 | 425 |
| 20260315 | 147 |
| 20260316 | 1,819 |
| 20260317 | 2,206 |
| 20260318 | 2,241 |
| 20260319 | 2,215 |
| 20260320 | 1,891 |

**Total: 11,406 across 12 dates → Average: 950/day**

Actual = 950/day ≥ N = 500. **PASS.**

Justification: clearly non-vacuous. Fires on every training date.

## Expected Direction and Magnitude (Step 5)

- **realized_pnl**: ↑ (slightly higher). The post-zero-flip positions have mean PnL = -0.0020 across all 12 dates. Removing 11,406 positions with total PnL = -22.50 yields estimated gain of +22.50 = +0.53% vs base. Magnitude: **very small gain ("fraction of a percent")**. Dynamic cascade effects may dominate and change the sign.

- **mean_slippage**: unchanged (0.0). Top-of-book only, qty=1.

- **trade_count**: ↓ slightly. Removing ~950 positions/day from the ~7,536/day total.

- **OMS check**: No opposing positions created. The gate SKIPS the OPEN, leaving the algo flat. ✓

**Warning**: The magnitude is very small (+0.53% static estimate) and may not survive dynamic cascade effects. This hypothesis is at the edge of detectability.
