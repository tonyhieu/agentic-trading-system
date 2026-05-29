# Algorithm Notes: sip-afg-l2

## Context Summary (Step 1)

Base algo `aggressor-flow-gate` (10s rolling signed aggressor-volume gate,
symmetric `flow_threshold=2.0` contracts). Single inefficiency claim:
realized aggressor flow over the past 10s predicts adverse selection — an
oracle BUY arriving when sellers have been aggressively hitting the bid is
likely to face an immediate adverse move.

Prior loops (program database):
- **sip-afg-l1 (kept, but regressed -15.19% vs base)** — replaced uniform 10s
  sum with an EWMA (tau=3s) and rescaled the threshold from 2.0 to 0.6
  using an unverified uniform-arrival assumption. Trade count barely moved
  (-0.22%), so the gate moved WHICH orders it skipped, not HOW MANY, with
  net-negative effect. Failure mode the loop-2 method targets: armchair
  quantitative parameters and absence of EDA confrontation.

Open mechanism families for sip-afg-l2 (recency-weighting is now closed):
changing the gate INPUT (signal source), changing the DECISION RULE shape
(magnitude-conditional, tail-conditional, hysteresis), or layering a
side-asymmetric guard.

## Candidates Considered (Step 2)

### Candidate A — Trade-count flow instead of volume flow

- **Weakness in base**: net_flow is volume-weighted, so a single anomalous
  large-size print (e.g. a 10-lot sweep) dominates ~5–10 single-lot prints
  worth of opposing aggressor activity. In MES the modal trade size is 1
  contract; the rare large print is what swings net_flow past the
  2-contract threshold and triggers the gate. The signal could be noisier
  than necessary.
- **Modification**: signed *count* imbalance — count_buy_aggressor_trades
  minus count_sell_aggressor_trades over the same 10s window. Gate fires
  when |count_imbalance| >= count_threshold. Threshold derived from EDA.
- **Predicted direction/magnitude**: if the volume signal is being whipped
  by rare large prints, count flow should be slightly *more* selective on
  the noisy days and produce a modest positive P&L delta (+2% to +6% vs
  base). If size distribution is near-uniform, count and volume will be
  near-identical and the candidate degenerates into the base — negligible
  delta.
- **Key data assumption**: the trade-size distribution has a non-trivial
  right tail in this dataset (i.e. volume-weighted and count-weighted flow
  diverge meaningfully). If sizes are near-constant at 1 contract, this
  candidate is dead.

### Candidate B — Tail-magnitude-conditional gate

- **Weakness in base**: the gate treats |net_flow| = 2 (barely above
  threshold) identically to |net_flow| = 20. But predictive power of
  signed flow about future drift is almost certainly concentrated in the
  tails — barely-positive flow is mostly noise. The base algo gates too
  much at modest magnitudes.
- **Modification**: keep signed aggressor-volume flow, but raise the
  threshold so the gate fires only when |net_flow| is in the upper tail of
  the empirical distribution (e.g. |net_flow| >= p90). Set the threshold
  to the EDA-measured p90 of |net_flow| over the train window.
- **Predicted direction/magnitude**: skip rate drops (fewer gates), but
  the gates that fire are higher-confidence. Net effect: trade_count rises
  vs base by ~5–10%, P&L delta modestly positive (+2% to +8%) if the tail
  is genuinely more predictive than the body.
- **Key data assumption**: future 30s realized drift conditional on
  |net_flow| is monotonically increasing in |net_flow|, with the strongest
  contrast between the tail (>= p90) and the body (< p90). If the
  conditional drift is flat as a function of |net_flow|, this candidate is
  dead — there is no tail premium to exploit.

### Candidate C — Side-asymmetric thresholds

- **Weakness in base**: the threshold is symmetric (2 contracts adverse
  whether BUY or SELL). But adverse-selection magnitude is not symmetric
  in practice — the strategy/market may have a structural bias such that
  BUY entries face larger adverse drift than SELL entries (or vice versa)
  for a given level of signed flow. Symmetric thresholds therefore waste
  precision on one side and over-gate on the other.
- **Modification**: keep 10s window and the volume-based signed flow, but
  use `flow_threshold_buy` and `flow_threshold_sell` independently. Set
  each from the EDA-measured conditional 30s drift on the respective side.
- **Predicted direction/magnitude**: if drift asymmetry exists, the side
  with weaker drift should get a higher threshold (skip less, accept more
  marginal entries) and the side with stronger drift should get a lower
  threshold (skip more aggressively). Net effect: trade_count changes
  modestly (±5%); P&L delta modest positive (+3% to +7%).
- **Key data assumption**: the conditional 30s drift after a signed-flow
  bin differs by side. If the conditional drift curves for BUY and SELL
  overlap, the asymmetric thresholds will be roughly equal and the
  candidate degenerates into the base.

The three candidates are mechanistically distinct: A changes the SIGNAL
INPUT, B changes the DECISION RULE SHAPE, C adds a SIDE-ASYMMETRIC guard.
None overlaps with the EWMA-recency family closed by sip-afg-l1.

## EDA Findings (Step 3)

Dates loaded: **20260308, 20260309, 20260315, 20260318** (all from
`data_window.train`). Method: replay TradeTick stream, maintain the same
10s signed-volume deque the base algo uses, and at every trade timestamp
record net_v together with the realized 30s-ahead midprice drift from the
quote stream. A "skip value" is defined as the realized drift in the
direction that would have penalized the *would-be order*: BUY-skip value =
`-drift` when `net_v <= -2` (positive means price actually fell, so
skipping BUY was correct); SELL-skip value = `+drift` when `net_v >= +2`
(positive means price actually rose, so skipping SELL was correct).
Scripts: `scripts/_eda_sip_afg_l2.py`, `scripts/_eda_sip_afg_l2_focus.py`.

### Candidate A — volume-flow vs count-flow

Assumption: trade size has a non-trivial right tail in this dataset and
volume vs count flow diverge in real gating decisions.

Result on 20260308: trade-size p50=1, p90=3, p99=11, max=31 — the right
tail exists. Volume and count gates fire together 85.3% of the time; when
either fires, only-volume contributes 9.3% and only-count 1.4% of the
disagreement events. Correlation of net_v and net_c at gating evaluation
points is 0.86 (20260308) / 0.71 (20260315). **Assumption survives** —
the signals are not identical — **but the EDA does not give a mechanism
why count-based flow should produce better P&L** than volume; it only
shows the two signals are different. Disqualifying: I have no
EDA-grounded number connecting count-flow disagreement events to better
30s-ahead drift than the volume signal already captures. The candidate is
weakly supported.

### Candidate B — tail-magnitude / decile premium

Assumption: drift conditional on |net_v| is monotonically increasing in
|net_v|, with the strongest contrast in the tail (>= p90).

Result (deciles of |net_v| → mean |drift_30s|):
- 20260308: drift in d=0..d=9 is non-monotonic (auction-time noise in
  d=0), then drift rises roughly monotonically from 1.56 at d=3 to 4.45 at
  d=9. Tail premium ratio (>=p90 vs <p90) = **1.69x**.
- 20260315: drift rises monotonically from 1.29 at d=0 to 1.84 at d=9.
  Tail premium ratio = **1.28x**.

**Assumption partially survives.** Tail does carry more |drift| than the
body, but the premium is modest (1.3-1.7x), not dramatic, and the
relationship is gradual rather than sharply tail-concentrated. A higher
threshold would gate less often on smaller |drift|, but Candidate C below
shows the magnitude effect is dominated by a much larger directional
finding.

### Candidate C — side-asymmetric drift

Assumption: conditional 30s-ahead drift differs by side. Pool 4 train
dates (n=296,012 BUY-skip evaluations, n=266,063 SELL-skip evaluations).

Pooled (4 dates):

| Bucket                                | n       | mean skip value | t-stat   |
|---------------------------------------|---------|-----------------|----------|
| BUY-skip  (net_v <= -2)               | 296,012 | **+0.0931**     | **+25.13** |
| SELL-skip (net_v >=  +2)              | 266,063 | **-0.1445**     | **-41.46** |
| BUY-skip moderate (-3 <= net_v <= -2) |   8,796 | +0.0468         | +2.49    |
| BUY-skip extreme  (net_v <= -10)      | 266,027 | +0.0993         | +25.00   |
| SELL-skip moderate (2 <= net_v <= 3)  |   8,696 | -0.0006         | -0.03    |
| SELL-skip extreme  (net_v >= 10)      | 236,169 | **-0.1597**     | **-43.01** |

**This is the assumption that survives most strongly and is the most
load-bearing finding for this loop.** Three concrete results:

1. The **base algo's BUY-skip is correctly signed** (mean drift = +0.093
   ticks per skip, t=+25). The 10s, 2-contract gate genuinely skips BUYs
   that would have lost money on average.
2. The **base algo's SELL-skip is INVERTED** (mean drift = -0.144 ticks
   per skip, t=-41). When net_v >= +2 (buyers dominate), the future drift
   over 30s is on average DOWN, not UP — i.e., a SELL order placed then
   would have been *profitable*, and the base algo is throwing away
   P&L by skipping it.
3. The SELL inversion **strengthens with magnitude**: SELL-skip moderate
   t=-0.03 (noise), SELL-skip extreme t=-43.01. So a tail-magnitude
   higher threshold (Candidate B) would NOT fix the SELL side — it would
   make it strictly worse.

The mechanism is consistent with short-term mean reversion of aggressive
buying pressure in MES: when buyers cross the offer in volume over the
last 10s, the offer has been lifted to a temporary local high and the
30s-ahead mid drifts back down. The base algo's symmetric design treats
both sides identically and silently loses on every SELL skip. (BUY side
does not show the same inversion, possibly because the dataset's
oracle/strategy has a structural asymmetry in BUY signal frequency, or
because seller-aggression in this contract genuinely predicts adverse
continuation. Either way, the empirical evidence is one-sided.)

**Decision: Candidate C survives. Candidate B is dead (its premise of
monotonic |net_v|→|drift| ignores that the sign flips by side). Candidate
A is technically alive but mechanistically weak (no EDA number ties
count-flow divergence to P&L). One survivor → proceed to Step 4.**

Quantitative parameter for Step 5: keep `flow_threshold_buy = 2.0` (same
as base), set `flow_threshold_sell = +inf` (i.e. disable the SELL gate).
Both numbers come directly from the EDA above: the BUY gate is correctly
signed at the base threshold; the SELL gate is anti-predictive at every
magnitude examined. No armchair numbers.

## Critique (Step 4) — Candidate C (asymmetric / SELL-gate disabled)

**Attack 1 — Constraint interaction.** Does removing the SELL gate
violate `top_of_book_only`, `participation_cap`, `intraday_flat`, or the
quantity invariant? No. The change only affects which orders get
`self.submit_order(order)` called vs not — it never modifies quantity,
post-order limit-vs-market routing, or position-closing behavior.
Reduce-only orders still bypass the gate. The anti-cascade
`_position_flat = True` after any skip is preserved. Constraint risk: **low**.

**Attack 2 — Untested sub-assumptions.** The EDA shows the 30s-ahead mid
drift is on average DOWN when net_v >= +2 in the train window. Three
sub-assumptions that the EDA did NOT directly test:
- *The oracle signal's 30s horizon is the right alignment for "adverse
  selection"*. config.yaml sets `horizon_seconds=30`, so this is the
  strategy's own horizon — I'm using it as given; the assumption is the
  oracle's, not mine.
- *The drift conditional on flow at trade-tick times generalizes to drift
  at order-arrival times*. The oracle generates one signal per
  `signal_interval_seconds=1`, so order arrivals are roughly uniform in
  time. Trade ticks cluster around active periods. The EDA points may be
  oversampled in active windows. This is a moderate concern but the
  pooled-across-4-dates sample (562k events across quiet+active days)
  makes the average a reasonable proxy.
- *The SELL inversion holds in the test window too*. I have not (and may
  not) check this. If the SELL inversion is a train-period artifact (e.g.
  a directional trend the dataset had), the test result will regress.
  This is the dominant risk for OOS. For the IS train backtest (which is
  what loop-2's gate compares), the in-sample signal is real.

**Attack 3 — Trade-count consistency.** The mechanism is "SELL skips are
on net unprofitable, so disabling them lets the SELL orders through and
captures profit that base was throwing away". So I predict:
- `trade_count` **increases** vs base. The SELL gate was firing
  (sip-afg-l1 trace shows base skips ~21% of orders). Roughly half of
  those skips were SELL skips. Disabling SELL skips should restore on the
  order of 8–12% of orders. So trade_count goes from base's 107,198 to
  somewhere around 117k–120k.
- `realized_pnl` **increases** — the recovered SELL orders are on average
  profitable (mean skip-value = -0.144 ticks of unrealized P&L per SELL
  skip × MES multiplier × ~10k+ extra trades).
- `mean_slippage` **unchanged at 0** — gate only affects which orders are
  submitted, not fills.
- `is_weighted_bps` direction is harder. The sip-afg-l1 trace observed
  that flow-gating fires when arrival prices are temporarily favorable,
  so removing the SELL gate restores some of those favorable-arrival
  fills → IS could improve marginally.

This is a consistent story: more trades AND higher P&L is the prediction,
not "fewer skips of bad trades while count stays flat" (which is the
sip-afg-l1 anti-pattern the loop-2 method explicitly warns about).

**Attack 4 — Armchair parameters.** The only numbers in the hypothesis
are `flow_threshold_buy = 2.0` (taken unchanged from the base algo to
isolate the asymmetric-gate change) and `flow_threshold_sell = +inf`
(disable). Both numbers are anchored in Step-3 EDA: the BUY skip is
correctly signed at 2.0 (positive skip value, t=+25), the SELL skip is
inverted at every magnitude examined (t=-43 at extremes). No armchair
parameters.

**Attack 5 — Could the change interact with the anti-cascade
`_position_flat = True`?** Yes — and this is subtle. Currently
`_position_flat` is set to True after EITHER a BUY or SELL skip. With
SELL skipping disabled, `_position_flat = True` is set less often. This
means the BUY gate evaluates more frequently (fewer "free passes" from
the post-skip anti-cascade). Net effect on BUY gating: it fires more
often, which is *good* (BUY skip is correctly signed). But it does
slightly change the BUY gate's behavior even though the BUY threshold is
unchanged. **I'll keep `_position_flat = True` set only after BUY skips**
— consistent with the principle that the anti-cascade exists to prevent
runaway gating on the side that gates.

**Attack 6 — Why didn't the original author build this in?** The base
algo's NOTES.md does not contain a side-conditional drift analysis. The
author proposed and tested a symmetric design directly, found it
positive vs `simple` baseline (+54%), and accepted it. The asymmetry was
empirically there but unexamined. This is exactly the kind of
unexamined-assumption failure the loop-2 method targets, and it is on
the base algo, not on a prior loop attempt.

**Survives critique.** Proceeding to Step 5.

## Hypothesis

**Mechanism.** Same 10-second rolling deque of signed aggressor volume as
`aggressor-flow-gate`. For BUY orders, skip when `net_flow <= -2.0`
(unchanged from base). For SELL orders, never skip — submit
unconditionally. Reduce-only orders always submit (intraday_flat).
Anti-cascade `_position_flat = True` is set ONLY after a BUY skip (the
only side that gates), so the next open is unconditional after a skip.
No other changes from `aggressor-flow-gate`.

**Inefficiency exploited.** The base algo's symmetric SELL gate is
empirically inverted: pooled across 4 train dates (n=266,063 SELL-skip
evaluations), the mean 30s-ahead drift when net_v >= +2 is **-0.1445
ticks** (t = -41.46) — i.e. price drifts DOWN, meaning the would-be SELL
order would have been profitable. The base algo systematically throws
away P&L on every SELL skip. Disabling the SELL gate recovers that P&L.

**Why it survives costs.** The change touches only the order-submission
decision, never quantity, routing, or close-out logic.
`participation_cap` (≤5% top-of-book) is preserved because the algorithm
does not change order sizing. `top_of_book_only` is preserved (no fill
mechanics change). `intraday_flat` is preserved (reduce-only orders
always submit). Slippage is expected to be unchanged (mean_slippage = 0
on both sides under the zero fill-cost model).

**Quantitative anchors.**
- `flow_threshold_buy = 2.0` — kept identical to base. The BUY-skip
  value is correctly signed at this threshold (mean = +0.0931 ticks, t =
  +25.13 over n=296,012 pooled BUY-skip evaluations across 4 train
  dates). Changing it would conflate the asymmetric-gate test with a
  parameter retune.
- `flow_threshold_sell = +inf` (SELL gate disabled). The SELL-skip value
  is inverted at every magnitude examined: moderate (2 <= net_v <= 3)
  mean = -0.0006, t = -0.03 (noise); extreme (net_v >= 10) mean = -0.160,
  t = -43.01 (strongly anti-predictive). No threshold value separates a
  "useful SELL skip" from a "noisy SELL skip" — the whole regime is
  unprofitable. The conservative response is to disable, not to invert.
- `window_seconds = 10.0` — kept identical to base. Window length is
  orthogonal to the side-asymmetric question.

**Predicted outcome (train window, 12 dates):**
- `realized_pnl`: **increases** vs base (+1255.50 baseline). Magnitude
  estimate from EDA: ~133k pooled SELL-skip events imply on the order of
  133k * 0.144 ticks * tick_value $1.25 / 4 (since events are
  evaluation-point oversampled vs actual orders) ≈ $5–15k of recoverable
  per-skip value in EDA units, but the strategy's actual skip count over
  12 days is in the hundreds-to-low-thousands of SELL skips, so the
  realistic recovered P&L is on the order of a few hundred dollars —
  roughly +10% to +30% vs base.
- `trade_count`: **increases** vs base (107,198). Roughly half of the
  base's skips were SELL skips → expect trade_count around 113k–119k.
- `mean_slippage`: unchanged at 0.0.
- `is_weighted_bps`: marginally improved or unchanged. SELL gating fired
  near temporarily-favorable arrival prices; removing it restores those
  fills.
- `sharpe_ratio`, `win_rate`: directional uncertainty but should improve
  if the recovered SELL trades are on average profitable.
- `max_drawdown_pct`: unchanged or slightly worse (more positions opened
  during volatile periods means slightly more equity-curve variance, but
  if those trades are profitable on average the drawdown is unaffected).

**What would falsify this hypothesis in the backtest.** ONE specific
result: **`trade_count` increases by less than 3% vs base AND
`realized_pnl` is flat or negative vs base.** That would mean the SELL
gate was firing rarely in the actual backtest path (so disabling it
recovered few orders) AND/OR the recovered SELL orders were not on
average profitable. Either failure mode would invalidate the
mechanism — the EDA-measured pooled negative skip value does not
transfer to the run-time decision stream.

A second falsifier (weaker): `trade_count` rises substantially (>3%)
but `realized_pnl` falls. That would mean the SELL inversion does not
generalize to the strategy's order arrival distribution — a real but
narrower failure than the primary falsifier.

**Alternatives considered and rejected.**
- **Candidate A (count-flow instead of volume-flow)** — rejected
  because, while count and volume gates disagree on ~15% of decisions,
  no EDA number tied count-flow disagreement events to better 30s-ahead
  drift. The candidate was alive but mechanistically unmotivated.
- **Candidate B (tail-magnitude / higher threshold)** — rejected because
  the magnitude story is dominated by the side story: SELL-skip at
  extreme magnitude is the WORST case, not the best. A tail-magnitude
  gate would amplify the SELL-side error.

