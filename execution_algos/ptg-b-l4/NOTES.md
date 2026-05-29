# ptg-b-l4 -- adverse-move override at 5-tick threshold

## Hypothesis

Brief-summary context allowed for this loop: loop-1.json + loop-2.json +
loop-3.json (metrics + summary_out only). I mechanically inspected
`execution_algos/ptg-b-l3/execution_algorithm.py` only -- no prior-loop
NOTES prose.

L3 (adverse_threshold_ticks=3) was -22.29% vs base on the 11
apples-to-apples dates (recovered +19 pp from L2's -41.30%, which had
itself recovered +34 pp from L1's -75.33%). The lineage shows a clean
monotonic convex trajectory:

  L1 (age-only, 5s):   -75.33% vs base, +13.25% trades
  L2 (adverse, 1 tick): -41.30% vs base, +9.80% trades  (+34 pp gain)
  L3 (adverse, 3 ticks): -22.29% vs base, +2.42% trades  (+19 pp gain)

The L3 brief summary `next` text proposed exactly one targeted change:
**raise adverse_threshold_ticks from 3 to 5** ($1.25 in price, five
full-spread displacements). The reasoning given there is L2's branching
rule, which said: "if L3 still has +trade_count vs base, the predicate
is still admitting too many reversals and L4 should test 5 ticks."

L3 has +2.42% trade_count vs base (+1,785 extra trades), so that branch
fires. The expected outcome is fewer admitted reversals (closer to or
below base's trade count of 73,802) with better per-admit pnl, which
should further narrow or close the vs-base gap. The convex monotonic
trajectory predicts diminishing but positive marginal returns to one
more tightening.

This loop implements exactly that single targeted change. The same gate
skeleton is preserved -- only the threshold constant changes.

### One targeted change vs. L3

- L3: `adverse_threshold_ticks = 3.0` (default = $0.75)
- L4: `adverse_threshold_ticks = 5.0` (default = $1.25)

Everything else is identical, including:
  - reversal vs same-direction-add classification
  - reduce-only short-circuit (always submits)
  - quote subscription pattern (idempotent, in `on_order`)
  - fall-back-to-skip behavior on missing quote or missing avg_px_open
  - diagnostic counters

### Why exactly 5 (not 4 or 6)

L3's `next` text proposed 5 as the natural single-step probe under L2's
branching rule. The adaptive rule (also from L3's `next`) is:
  - If L4 pnl improves with trade_count within ~+/-1% of base, the
    predicate is approaching the right calibration. (No more single-step
    tightening; L5 should pivot.)
  - If L4 trade_count drops materially BELOW base (gate too strict,
    collapsing to ~no admitted reversals), L5 should bracket back to 4.
  - If L4 pnl is still below base with +trade_count, the adverse-mid
    proxy is exhausted as a conditioning variable -> L5 should pivot to
    a different axis (signed aggressor imbalance, spread vs rolling
    median, hold-time floor on reduce-only).

The in-flight diagnostic to look at first in step 7 is `trade_count`
relative to base's 73,802 and the sign of the pnl delta -- together
they determine which branch above fires.

### Failure mode I am explicitly betting against

The risk in the opposite direction from L3: 5 ticks may be too strict,
admitting almost no reversals and dropping trade_count materially below
base while losing the small remaining beneficial admits. In that case
L4 pnl would be below base AND trade_count would be below base,
indicating the predicate has collapsed past the useful regime. That is
not a failure of the experiment -- it pins down the other endpoint of
the threshold curve -- but it would mean L4 does not beat base and L5
would test 4 ticks. The prediction I am betting on is that **5 ticks
admits substantially fewer reversals than 3 ticks (perhaps cutting
admits in half), and that the dropped admits are on average money-
losing, so L4 pnl moves up toward or past base** while trade_count
moves toward or slightly below base.

## Implementation Decisions

- Copied `execution_algos/ptg-b-l3/execution_algorithm.py` mechanically
  as the starting point; renamed `PtgBL3Config`/`PtgBL3Algorithm` to
  `PtgBL4Config`/`PtgBL4Algorithm`; changed the
  `adverse_threshold_ticks` default value from 3.0 to 5.0 in three
  places (Config default, Config docstring, factory kwarg default).
- Updated the module-level docstring to describe the single change vs
  L3 and the prediction.
- Did NOT alter the algorithm's structural logic, helper functions,
  counter set, or the `frozen=True` config pattern.
- The submitted-reversal-override log line message was reworded from
  ">= threshold (3 ticks default)" to ">= threshold (5 ticks default)"
  for accuracy; the numeric values logged are still computed from the
  config.
- `__init__.py` updated to re-export from the renamed module docstring.
- Registered in `execution_algos/__init__.py`.

## Backtest Observations

11-date apples-to-apples train aggregate (Sun-Fri 2026-03-08..2026-03-20,
with 20260319 OOM-killed and dropped from both sides by the runner):

  - ptg-b-l4:        $3,140.75 / 74,420 trades
  - base ptg:        $3,564.25 / 73,802 trades
  - simple baseline:    $43.25 / 111,489 trades

Aggregate deltas:

  - vs simple:  +7161.85% pnl  (PASS vs simple gate, +5.0% threshold)
  - vs base:    -11.88% pnl, +0.84% trade_count (+618 trades, -$423.50)

Sharpe 15.32 over 11 days (small-N artifact; treat as directional only).
Slippage 0.0/0.0 (no fill-cost model).
Win rate 37.08% (vs base 37.20%).
Max DD -1.79%.
is_weighted_bps 0.0424 vs simple 0.673 (better arrival-mid capture).

Per-date diff (L4 - base, dollars):
  20260308:   -6.00
  20260309:  -87.50
  20260310: -112.00
  20260311:  -25.50
  20260312:  -54.25
  20260313:  -71.25
  20260315:   -7.50
  20260316:  -21.00
  20260317:   -6.50
  20260318:  -11.75
  20260320:  -20.25
  -----------------
  Total:    -423.50

Worse than base on 11/11 dates in absolute dollars; no date flipped from
positive to negative this loop (L4's 20260313 is -$5.75 vs base's
+$65.50, which is the largest single-day pnl regression at -$71.25, but
20260316 was already negative under base at -$37 and L4 only worsens it
to -$58). The single-day pattern is uniform small-but-consistent
underperformance, not concentrated losses.

### Lineage trajectory vs base

  L1 (age-only, 5s):     -75.33% vs base, +13.25% trades (+9,779)
  L2 (adverse, 1 tick):  -41.30% vs base,  +9.80% trades (+7,232)
  L3 (adverse, 3 ticks): -22.29% vs base,  +2.42% trades (+1,785)
  L4 (adverse, 5 ticks): -11.88% vs base,  +0.84% trades (+618)

Convex monotonic improvement holds: +33 pp (L1->L2), +19 pp (L2->L3),
+10 pp (L3->L4) -- diminishing but positive marginal returns to each
single-step tightening. trade_count is now within ~1% of base, well
inside the "+/-1%" calibration band the L3 next text identified as the
sign the predicate is "approaching the right calibration." But pnl is
still -11.88% below base, meaning the remaining +618 admitted reversals
are on average money-losing.

### Diagnosis (which branch from L3's next text fires)

L3's next text proposed three forward branches conditioned on L4's
outcome:
  - (a) pnl improves AND trade_count within ~+/-1% of base
        -> predicate approaching the right calibration; no more
        single-step tightening; L5 should pivot.
  - (b) trade_count drops materially BELOW base (gate too strict)
        -> L5 bracket back to 4 ticks.
  - (c) pnl still below base AT 5 ticks with +trade_count
        -> adverse-mid axis exhausted; L5 pivot to different axis
        (signed aggressor imbalance, spread vs rolling median,
        hold-time floor on reduce-only).

Empirical result: trade_count = +0.84% vs base (well within +/-1%, NOT
materially below), and pnl = -11.88% (still below base). This is a
mix of (a) and (c): the trade_count is in the calibration band, but
pnl has not closed the gap, AND each marginal step of tightening
returned diminishing absolute gains ($677 from L2->L3 vs $371 from
L3->L4). The implication is that the adverse-mid axis on its own
cannot fully close the gap to base: it has compressed the +trade_count
delta from +9.8% to +0.84% but cannot eliminate the residual
underperformance of the remaining admits.

### Status

Vs simple gate: PASS (+7161.85% pnl, well above the +5.0% threshold;
slippage no-regression at 0.0/0.0).
Vs base (informational, brief-summary arm): -11.88%, all 11 dates
worse. No formal pass/fail vs base.

### Forward direction (input to L5 hypothesis)

The simple "raise the constant by 2 ticks" lever is approaching
exhaustion: each step still gains some pnl but trade_count is now in
the +/-1% band relative to base, so further tightening will tend to
collapse below base before fully closing the residual underperformance.
The L5 candidate set should bracket between two paths:
  (i) one more single-step tightening to 7 ticks ($1.75) to confirm the
      adverse-mid lever has indeed exhausted (predicted endpoint:
      trade_count below base, pnl unchanged or slightly worse); or
  (ii) keep the 5-tick adverse predicate and ALSO require something
       structural on the admitted reversal -- candidates:
         * hold-time floor (the position must be at least N seconds old
           in addition to having moved 5 ticks adversely);
         * spread-not-widened guard (skip the override if current spread
           > 1 tick, because admitting reversals through wide spreads
           pays away the mid-edge to the spread); or
         * signed aggressor imbalance on the most recent tick (only
           admit if recent flow agrees with the proposed new direction).
L5's chosen direction is documented in execution_algos/ptg-b-l5/NOTES.md.
