# ptg-b-l8 -- FINAL loop of brief-summary arm: relax spread guard 1 -> 2 ticks

## Hypothesis

Brief-summary context allowed for this loop: loop-1.json through
loop-7.json (metrics + summary_out only). I mechanically inspected
`execution_algos/ptg-b-l7/execution_algorithm.py` (the prior loop's
code) so the L8 change is a clean single-knob edit. NO prior-loop
NOTES prose was read.

### Lineage so far (vs base position-tier-gate, 11 apples-to-apples dates)

  L1 (age-only 5s):                                -75.33%  +13.25% trades
  L2 (adverse >= 1 tick):                          -41.30%   +9.80% trades
  L3 (adverse >= 3 ticks):                         -22.29%   +2.42% trades
  L4 (adverse >= 5 ticks):                         -11.88%   +0.84% trades
  L5 (adverse 5 AND age 5s):                        -9.54%   +0.59% trades
  L6 (... AND spread <= 1 tick):                    -1.91%   +0.20% trades
  L7 (... AND flow_agreement >= 60% over 1s):       -0.72%   +0.08% trades
  L8 (...                AND spread <= 2 ticks):    ???

Marginal pnl per loop: +$1213, +$677, +$371, +$83.50, +$272, +$42.50.
Clear exhaustion shape after L6.

### Why this is the right L8 move (per L7 summary_out)

L7 was the smallest gap of the lineage (-0.72%, -$25.50 aggregate),
within single-date noise floor of beating base but materially short
of crossing. L7's next text identified two natural directions:

  (i) Continue adding orthogonal axes (sixth condition). The L1-L7
      marginal-pnl shape ($1213, $677, $371, $83.50, $272, $42.50)
      shows clear exhaustion; a sixth axis is most likely to drift
      pnl +/-$20 with no clear theoretical mechanism for crossover.
      Low expected upside.
  (ii) TUNE an existing knob inside the 4-axis predicate to reduce
       false skips -- specifically the spread guard from 1 tick
       (MES minimum) to 2 ticks. L7 explicitly recommended this on
       the mechanism that L5->L6 was -$272 pnl on -286 trades
       (-$0.95/trade for wide-spread admits at the 1-tick gate),
       and the now-in-place flow filter should screen the worst
       flow-disagree admits among the re-admitted batch.
       Hypothetical gain: ~+$143 if half are re-admitted at zero
       net pnl, > $25.50 residual gap.

L7 recommended (ii). I am following that recommendation -- this is
the FINAL loop and the only theoretically-grounded mechanism for
crossing base. (i) has low expected upside per L7's own analysis.

### The targeted change

**Exactly one knob: `max_spread_ticks` 1.0 -> 2.0** in both
`PtgBL8Config.max_spread_ticks` and the factory default.

Predicate transitions from
  `adverse_mid >= 5 ticks AND age >= 5s AND spread <= 1 tick AND flow_agreement >= 60%`
to
  `adverse_mid >= 5 ticks AND age >= 5s AND spread <= 2 ticks AND flow_agreement >= 60%`.

Everything else is byte-identical to L7:
  - position cap (1)
  - adverse threshold (5 ticks = $1.25)
  - age floor (5s)
  - flow window (1s) and flow agreement minimum (60%)
  - on_trade_tick handler / rolling signed-flow deque
  - reversal classification
  - same-direction-add skip
  - reduce-only short-circuit
  - quote and trade subscription (`_ensure_subscribed`)
  - fall-back-to-skip on missing quote, missing avg_px_open, empty
    flow window, all-NO_AGGRESSOR window, flow disagreement
  - diagnostic counters (same names, same order)
  - gate ordering inside reversal branch (no-quote -> adverse ->
    age -> spread -> flow -> submit)

### Set-theoretic structure (mechanistic clarity)

  - L8 admit set is a STRICT SUPERSET of L7's admit set: every L7
    admit also satisfies spread <= 2 (since 1 <= 2). So
    trade_count(L8) >= trade_count(L7) = 73,861.
  - L8 admit set is a STRICT SUBSET of L4's admit set: L4 has no
    age, spread, or flow gates; L8 has all three. So
    trade_count(L8) <= trade_count(L4) = 74,420.
  - The NEW admits in L8 \ L7 are exactly:
    `{flow agrees AND adverse >= 5 AND age >= 5 AND 1 < spread <= 2}`.
    These are the trades the hypothesis bets on.
  - Whether trade_count crosses base (73,802) depends only on how
    many of these new admits exist; L7 is already 59 trades above
    base, and the new admits add some unknown number on top.

### Predicted outcome ranges (single hypothesis, before backtest)

  - trade_count: 73,900 - 74,200 (re-admits 50-350 new wide-spread
    trades on top of L7's 73,861). Above base (73,802) by an
    increased margin.
  - pnl: $3,520 - $3,680 -- centered slightly above L7's
    $3,538.75. Three sub-bands by L7 next-text's diagnostic:
      * $3,565+ (crosses base, ~30% prior): the relaxed-spread +
        flow combo is the right structure; L6 spread was over-
        tightened relative to flow availability.
      * $3,520-3,565 (between L7 and base, ~40% prior): partial
        compensation -- flow screens some but not all wide-spread
        losers.
      * Flat with L7 +/-$30 (~20% prior): flow does exactly the
        work spread was doing; arm saturated.
      * $3,480 or lower (regresses below L7, ~10% prior): flow
        cannot rescue wide-spread admits; L7 is arm's best.

### Failure modes I am explicitly betting against

  - Wide-spread reversals (spread = 1.25-2 ticks) tend to coincide
    with strong flow agreement (because aggressive directional
    flow widens the spread by removing one side of the book), so
    the flow filter does NOT screen them well -- in which case the
    re-admitted batch carries the same negative EV as before, and
    L8 regresses below L7.
  - The 1-tick spread guard was screening adverse-resolution
    moments (microbursts where the market discovered the position
    was wrong), and re-admitting those captures losers regardless
    of what flow says.
  - In either failure case, L7 stands as the arm's best result and
    the L8 verdict is "spread guard at 1 tick is correct; arm
    saturated at L7."

### Final-loop accountability note

This is the LAST chance to beat base in this 8-loop arm. The
brief-summary discipline has held throughout (only metrics +
summary_out from prior loops were read; no NOTES.md prose; only
mechanical inspection of the prior loop's code at copy time). If
L8 does not cross base, the arm verdict is that the brief-summary
context regimen produced a sequence of progressively-better but
asymptotic-to-base improvements -- closing 99.3% of the L1 gap
but not crossing it.

## Implementation Decisions

  - Copied `execution_algos/ptg-b-l7/execution_algorithm.py` as the
    starting point; renamed `PtgBL7Config`/`PtgBL7Algorithm` to
    `PtgBL8Config`/`PtgBL8Algorithm`.
  - Single value change: `max_spread_ticks: 1.0 -> 2.0` in both the
    config dataclass default and the factory signature default.
  - Updated the module docstring to describe the L8 hypothesis
    (relaxed spread + retained flow) and the L1-L7 lineage.
  - Updated the gate-3 comment from "tight-spread floor (matches L6)"
    to "spread guard (RELAXED in L8 from 1 tick -> 2 ticks)" so the
    diff against L7 is self-explanatory.
  - Updated the config docstring entry for max_spread_ticks to flag
    the L8 default as the single change vs L7.
  - Updated the factory docstring to identify L8 as "L7 with the
    spread guard relaxed from 1 tick to 2 ticks."
  - Registered in `execution_algos/__init__.py` after ptg-b-l7.
  - `__init__.py` re-exports `get_execution_algorithm` via relative
    import (consistent with L5/L6/L7).
  - NO new counters added: existing
    `_skipped_reversal_wide_spread` counts the same gate, just with
    a different threshold. Adding a separate "L8-only re-admit"
    counter would require a second pass through gate 3, which is
    unnecessary for the verdict.

## Backtest Observations

11-date apples-to-apples train aggregate (Sun-Fri 2026-03-08..2026-03-20,
with 2026-03-19 OOM-dropped on both sides):

  ptg-b-l8: pnl=$3,471.00, trades=73,917, sharpe=15.831,
            mean_slip=0.0, max_dd=-1.73%, win_rate=37.16%
  base ptg: pnl=$3,564.25, trades=73,802 (matched 11 dates)
  L7:       pnl=$3,538.75, trades=73,861, sharpe=16.184

Headline deltas:

  vs simple baseline:  +7925.43% pnl (PASS by ~1585x the +5% gate);
                       slippage tied at 0.0/0.0.
  vs base position-tier-gate: -2.62% pnl ($-$93.25), +0.16% trades
                       (+115 vs base).
  vs L7 (in-arm leader): -1.91% pnl (-$67.75), +0.08% trades (+56),
                       sharpe -0.353 (-2.18%).
  vs L6:               -0.72% pnl (-$25.25), -0.05% trades (-36).
  vs L5:               +7.65% pnl (+$246.75).

What L8 changed vs L7 (mechanical diff of execution_algorithm.py;
brief-summary discipline -- no L7 NOTES prose read):

  - Class/config renames PtgBL7* -> PtgBL8*.
  - SINGLE knob change: `max_spread_ticks` default 1.0 -> 2.0
    (in both `PtgBL8Config.max_spread_ticks` and the factory
    signature default).
  - Docstring/comment edits identifying L8 as L7 with the spread
    guard relaxed from 1 tick to 2 ticks.
  - No other code paths changed (gate ordering, counters,
    on_trade_tick handler, flow window, agreement threshold,
    age floor, adverse threshold, reduce-only and same-direction
    short-circuits all identical to L7 byte-for-byte modulo class
    renames).

Predicate transition:
  L7: adverse_mid >= 5 AND age >= 5s AND spread <= 1 AND flow_agree >= 60%
  L8: adverse_mid >= 5 AND age >= 5s AND spread <= 2 AND flow_agree >= 60%

L8's admit set is a STRICT SUPERSET of L7's (every L7 admit also
satisfies spread <= 2). Confirmed by trade_count: 73,917 > 73,861
(+56 new admits in L8 \ L7).

Hypothesis verdict: CONTRADICTED.

The 56 newly-admitted trades (those with spread in (1, 2] ticks
that pass flow_agree >= 60%) were net money-losing at
-$67.75 / 56 = -$1.21/trade -- materially worse than the
~$0.46/removed-trade ratio observed in L7's flow filter
removals, and ~30% worse than the L5->L6 wide-spread removal
ratio of $0.95/trade. This indicates that:

  (a) The 1-tick spread guard was correctly screening
      adverse-resolution moments. The 1.25-2.0 tick spread
      band is dominated by microbursts where the market is
      actively discovering the position is wrong; the flow
      filter (despite its 60% agreement requirement) cannot
      rescue admits in that regime because aggressive
      directional flow is precisely what widens the spread.
  (b) The L7 hypothesis's mechanism for crossing base
      (re-admit half of L6's -$272 batch at zero net pnl)
      was wrong by sign: re-admits lost money rather than
      breaking even.

L7 remains the in-arm pnl AND sharpe leader. The arm did not
cross base.

Set-theoretic checks (sanity):
  - trade_count(L7)=73,861 <= trade_count(L8)=73,917 (superset
    constraint holds).
  - trade_count(L8)=73,917 <= trade_count(L4)=74,420 (L8 is a
    strict subset of L4's age-and-adverse-only admit set,
    confirmed).
  - L8 admits exactly 115 trades more than base (73,917 vs
    73,802); the +59 trades L7 had over base plus the +56
    new admits L8 added.

8-loop trajectory (vs base position-tier-gate on 11 matched dates):

  L1 (age-only 5s):                                $879.25  -75.33%
  L2 (adverse >= 1 tick):                         $2092.25  -41.30%
  L3 (adverse >= 3 ticks):                        $2769.75  -22.29%
  L4 (adverse >= 5 ticks):                        $3140.75  -11.88%
  L5 (adverse 5 AND age 5s):                      $3224.25   -9.54%
  L6 (... AND spread <= 1 tick):                  $3496.25   -1.91%
  L7 (... AND flow_agree >= 60%):                 $3538.75   -0.72%
  L8 (... AND spread relaxed to 2 ticks):         $3471.00   -2.62%

L7 is the FINAL arm pnl AND sharpe leader. The arm closed 99.3%
of L1's gap by L7 (-75.33% -> -0.72%) but never crossed base;
the final L8 probe of the spread axis regressed slightly,
confirming the L6/L7 1-tick spread guard was at or near the
arm's true optimum.

Status: PASS vs simple (gate baseline; +7925.43% > +5% gate;
slippage tied at 0.0/0.0). Vs base_algo: -2.62% (regression).
Per_iteration_experiment loop -- NOT snapshotted per arm
protocol AND L8 is not the arm leader anyway.
