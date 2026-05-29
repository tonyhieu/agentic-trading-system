# Algorithm Notes: ptg-f-l8

Per-iteration experiment — base_algo `position-tier-gate`, context mode `full-trace`, loop 8 (final).

## Hypothesis

Loops 1-7 show: the position-tier-gate base at cap=1 is the near-optimal operating point.
No additional filter has improved over the base:
- cap=2 = simple (binary cliff)
- streak gate = no-op
- flow gates (30s, 5s) = hurt
- directional cap = (prediction: will hurt or match)
- min reentry time = (prediction: will hurt or match)  
- cluster filter = (prediction: will hurt or match)

**Loop 8 final attempt**: Try a COMBINATION of two mechanisms that individually show
the smallest degradation: cap=1 + very short min_reentry (0.5s) to block only the
ultra-rapid re-entries. This is more conservative than loop 6 (2s), targeting only
the fastest churn.

Actually, given all evidence, the final loop should test the **cleanest possible cap=1
variant** with a careful look at whether min_reentry_seconds at a very small value (0.5s)
is equivalent to the base (since oracle signals fire every 1s, a 0.5s block wouldn't
catch any, effectively = base).

---

## Implementation Decisions

- position_cap=1 (preserved)
- min_reentry_seconds=0.5: very short cooldown (likely = base since oracle fires at 1s intervals)

---

## Backtest Observations

**Full 12-date train window:**
ptg-f-l8 (0.5s min reentry + cap=1): pnl=$4,262.50, 0.00% vs base = IDENTICAL.
As predicted: oracle fires every 1s, so 0.5s block never catches any inter-oracle reentry.
**Hypothesis verdict**: No-op. Arm closes. Base cap=1 is the optimal operating point.
All 8 loops fail to improve: cap=2 = simple; filters = no-op or degrade; flow gates = hurt.
The position-tier-gate mechanism at cap=1 is effectively at its optimum for this oracle.
