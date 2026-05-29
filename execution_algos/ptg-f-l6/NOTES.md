# Algorithm Notes: ptg-f-l6

Per-iteration experiment — base_algo `position-tier-gate`, context mode `full-trace`, loop 6.

## Hypothesis

Loops 1-5 show: cap changes = binary cliff, filters (flow, streak) = no-op or hurt.
Loop 6 tries a **minimum hold time** before re-entry: after a position closes, require
at least 2 seconds before allowing the next open. This prevents rapid back-to-back entry
immediately after close, which may occur on oracle noise.

---

## Implementation Decisions

- position_cap=1 (preserved)
- min_reentry_seconds=2.0: no open within 2s of last close
- Track last_close_ts_ns from submitted reduce-only orders

---

## Backtest Observations

**Full 12-date train window:**
ptg-f-l6 (2s min reentry + cap=1): pnl=$3,875.50, -9.08% vs base, trades=74,784.
Best of the 'filter on top of cap' approaches but still worse than base.
**Hypothesis verdict**: FALSIFIED (worse than base). Cooldown cuts trades without P&L benefit.
**Suggested next**: Oracle cluster filter (loop 7).
