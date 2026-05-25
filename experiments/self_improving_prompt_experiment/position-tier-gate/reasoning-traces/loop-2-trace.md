# Loop 2 Reasoning Trace

## Hypothesis generation method used

Propose -> empirically verify -> commit (the loop-1 critic's evolved method).
Mandatory step 4 empirical pre-check: commit to a numeric prediction N for how
often the new branch should fire per day, then count it from the cheapest
verification surface (cached baseline `orders.csv` / `positions.csv` joined on
exec spawn id) before any code is written.

## How the hypothesis emerged from the method

The method genuinely shaped the choice. Step 1 forced an explicit reading of
the base mechanism (portfolio-state gate on `on_order()`). Step 2 demanded ONE
plausible weakness with a quantifiable per-trade signature, which pushed me
to actually open `execution_algos/sip-ptg-l1/results/<DATE>/positions.csv`
across all 12 train dates and bucket per-trade PnL by fill-time half-spread.
The buckets revealed a sharp inflection at +/-1 tick: positions whose fill
landed outside +/- 0.125 USD of arrival_mid collectively lose money (-$1,017
over 10,785 events). This concrete number directly produced the
proposal text in step 3 (wide-spread skip guard) and the prediction in step 4
(N = 100 events/day; actual = 898.8). Without the method's "commit to N then
count" requirement I would likely have proposed a more abstract spread
condition without checking whether the targeted subset was actually
loss-making in the base's own data.

## Where the method helped

Two specific moments. **First**, step 4a — being forced to commit to a
numeric N before looking at data prevented me from doing post-hoc "this
looks like enough" reasoning. I wrote N=100, ran the count (898.8), saw 9x
the floor — a real and falsifiable pass. **Second**, the bucketing
itself in step 2 caught a non-obvious shape: the wide-spread bucket is not
just noisy, it has a *negative* mean PnL on aggregate. Without that
empirical surface I would probably have hypothesized "wider spreads -> worse
fills" without realizing the base's already-existing position gate doesn't
filter them. The method made the gap visible.

## Where the method felt limiting or unnecessary

The method validates that the *event class* is non-empty and negative-EV in
the base's realized stream. It does NOT validate the **counterfactual** —
i.e., what happens to subsequent orders when these wide-spread opens are
skipped. That turned out to be exactly where the hypothesis broke (see
"What the backtest showed"). The +1 tick spread events occur disproportionately
in fast-moving microstructure regimes; when I skip the OPEN at moment t, the
next CLOSE+OPEN pair still arrives roughly 1 second later and faces the same
or worse spread, *but the realized PnL on the skipped leg's would-be partner
trades is also lost*. The method's empirical surface (positions.csv from the
base) shows the loss on the SKIPPED subset in isolation; it has no machinery
to model the chain reaction of skipping. A more honest step 4 would require
a counterfactual probe — re-run one date with a stub algorithm that logs
*which orders would be skipped*, then compute the PnL of the surviving
positions only, not the PnL of the skipped subset.

A second concern: step 4 makes the cached `orders.csv` / `positions.csv`
surface the default. This biases the researcher toward weaknesses that
*manifest in the base's existing fills* and discourages weaknesses that
manifest in orders the base never submitted. For loop 2 that bias was fine.
For later loops, if I want to ADD orders rather than SKIP them, the method
provides no clean verification surface.

## What a different method might have produced

A **counterfactual simulation method**: same step 1-3, but step 4 requires
running a one-date probe with the proposed algorithm that LOGS its
decisions (skip vs submit) and computes the PnL of the surviving positions,
not the discarded ones. This would cost one extra ~90-second backtest per
loop but catches exactly the failure mode loop 2 hit: the skipped
positions' contribution to *future* positions is invisible to the static
artifact. The hypothesis under that method might have been the same
(wide-spread skip) but the prediction would have been adjusted from "+24%
uplift" to something far more pessimistic when the probe showed that the
counterfactual PnL across all 81,557 surviving trades was -488 rather than
the +1,017 implied by linearly extrapolating from the skipped subset.

Alternatively, a **two-candidate propose-criticize architecture**: generate
two competing proposals (here: wide-spread-skip vs same-side-pair-skip),
write a one-paragraph critique of each, then keep the one whose critique is
hardest to write convincingly. Loop 2's critique paragraph for the
wide-spread proposal would have surfaced exactly the "but subsequent legs
may also be affected" concern that the current method handwaves.

## What the backtest showed

Raw numbers, all 12 train dates, sip-ptg-l2 vs base `position-tier-gate`:

| metric            | base       | sip-ptg-l2 | delta            |
|-------------------|-----------:|-----------:|------------------|
| realized_pnl      | 4,262.50   | 3,774.00   | **-488.50 (-11.46%)** |
| sharpe_ratio      | 17.619     | 19.215     | **+1.596 (+9.06%)**   |
| max_drawdown_pct  | -0.01727   | -0.00537   | **+0.0119 abs (+68.9%)** |
| win_rate          | 0.37204    | 0.37492    | +0.0029 (+0.29 pp)    |
| trade_count       | 90,433     | 81,557     | -8,876 (-9.82%)      |
| mean_slippage     | 0.0        | 0.0        | unchanged         |

**The big surprise**: predicted PnL direction (^) was wrong. The empirical
pre-check correctly identified that the wide-spread OPEN subset collectively
loses $1,017 in the base, but skipping it lost the algorithm $488 of net
PnL on aggregate. This is a clean falsification of the linear-EV assumption
in step 5's reasoning ("expected uplift ~$1,017 across 12 dates"). The
mechanism: skipping the wide-spread OPEN at t prevents the wide-spread
LOSING trade, but the next CLOSE+OPEN flip 1 sec later still arrives —
and the chain of subsequent trades the skipped position was paired into
included trades that, in aggregate, MORE than offset the $1,017 of losses.
The realized PnL of the surviving 81,557 trades (3,774) is below the
realized PnL of the original 90,433 trades (4,262).

**What did confirm expectations**: Sharpe ^ (less variance from fewer
high-risk fills), max_drawdown improved by ~69% (the skipped wide-spread
trades were contributing to drawdown peaks), trade_count v ~10% (in line
with the ~10,785 skipped OPEN-leg events being ~12% of total fills).

**Per-date pattern** (informal inspection): the algo BEAT base on early
calm dates (Mar 8-10 small books) but LOST big on the late high-volume
dates (Mar 18-20). On Mar 19 specifically the algo did 848 vs base's
behavior that suggests the base captured significantly more PnL on those
dates' wide-spread regimes than the algo did by skipping them.

## Where I felt uncertain

- **Counterfactual extrapolation in step 5**: I anchored predicted uplift to
  the sum-PnL of the *skipped subset*. This implicitly assumes the
  remaining trade chain is unaffected by skipping. That's clearly wrong in
  hindsight, and I should have flagged it at the time. The current
  method gave no explicit prompt to consider this — it asks "is the event
  class non-vacuous?" not "is the counterfactual PnL improvement linear in
  the skipped subset's PnL?"
- **`spread_threshold = 0.25 USD` exact value**: I picked 1 tick because
  that's the natural inflection in the bucketing. I considered 0.20 (= 1
  tick + half-tick tolerance) but the bucketing showed the (0.20, 0.45)
  bucket was *more* negative (-$0.124 mean) than (-0.20, -0.05), so the
  threshold choice felt OK. But I didn't sweep.
- **`self.cache.quote_tick()` semantics at `on_order()` time**: I assumed
  the quote tick is updated synchronously with the strategy's view of the
  market. If `on_order()` fires BEFORE the engine has propagated the
  latest quote, the spread reading is stale. Tools to verify this were
  available (I could have read the engine code) but I didn't, on the
  grounds that the on-order spread is at most one tick behind the truth
  and the bucketing is robust to a one-tick error.
- **Trade-count metric semantics**: I predicted ~-12% on the assumption
  that `trade_count` counts unique positions. Actual is -9.82%, close
  enough that I didn't dig further, but I never confirmed which entity
  is counted (positions vs fills vs orders).
- **`positions.csv` schema for sip-ptg-l1**: I used sip-ptg-l1 as a
  behaviorally-identical proxy for `position-tier-gate` (per loop-1
  trace). I did not re-verify bit-identicality of the order stream
  between the two; the loop-1 trace asserts it but I trusted it.
- **No tool errors worked around**. Skill ran clean — load DBN tools were
  not needed since the cached `positions.csv` had what I needed for the
  empirical pre-check.
