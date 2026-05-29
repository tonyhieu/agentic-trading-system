# Algorithm Notes: vrs-f-l7

Loop 7 of the per-iteration experiment, full-trace arm, base = `vol-regime-sizer`.

## Hypothesis

**Starting point**: `vrs-f-l6` (current best across L1-L6). L6's mechanism is
the L3-shape smooth sigmoid (`k=3`, `max_tighten=0.9`, full symmetric, z=0
defensive tightening at 0.45) with `drift_halflife=60` (the single change vs
L3, which had `drift_halflife=30`). All other plumbing identical to L3:
slow_vol denominator (halflife=120), absolute_floor=0.01, lazy drift init,
SHA-256(client_order_id) deterministic draw, calm-regime passthrough, cold
start at min_ticks=30, reduce-only always-submit.

**Observations driving this loop** (from the full L1-L6 trace):

1. The arm trajectory now spans seven points: L1 -34.23%, L2 +30.12%, L3
   +82.36%, L4 +78.37%, L5 +59.67%, **L6 +91.97%** (new best). The (k,
   max_tighten, aligned_clip) plane is well-explored and L3-shape was the
   local optimum on every axis tested. L6 then changed only the
   *signal-input timescale* (drift_halflife 30 -> 60) and beat L3 by
   +$72.50 / +5.27% pnl, sharpe +0.07 absolute, trade_count unchanged
   (122,431 vs 122,400). The +5% gain was meaningful but modest -- meaning
   30->60 was an improvement but not necessarily the optimum.

2. L6's explicit prescription for L7 (final paragraph of NOTES.md and
   full_reasoning): "Recommended: try halflife=90 for L7 (one more point
   in the sweep; if it underperforms L6, the optimum is near 60; if it
   beats L6, push further to 120)." This is the cleanest single-knob
   experimental design available and the directly-handed-off next step.

3. The L3 -> L6 transition was a doubling (30 -> 60). Conventional EWM
   tuning practice says the optimal smoothing horizon should be probed
   geometrically rather than linearly, but pushing to halflife=120 (a
   second doubling) would be too aggressive a single jump given the +5%
   gain at the first doubling -- if pnl-vs-halflife is roughly concave
   with peak near 60-90, a doubling could overshoot. L7 at halflife=90
   is the middle ground: 50% slower than L6, lets the curve be probed at
   higher resolution, and brackets the optimum between L6 and a possible
   L8 at halflife=120 or back to L6's 60.

4. Mechanically, halflife=90 vs 60 shifts the effective drift smoothing
   window from "last ~60 ticks" to "last ~90 ticks". On MES at ~100,000
   ticks per session, that's still <0.1% of the day, but it's a longer
   averaging window than slow_vol's halflife=120 / 2 = 60 effective
   centered window. So halflife=90 starts to approach the same timescale
   as slow_vol -- the *normalization scale* gets less reactive than the
   *signal numerator*. (Actually the opposite: numerator gets less
   reactive than denominator, since EWM half-life governs how fast new
   info is incorporated, so larger halflife = slower numerator.)

5. The expected mechanism if halflife=90 helps: the drift signal at
   halflife=60 may still be capturing some short-burst noise that
   would smooth out at halflife=90, particularly at the start of the
   trading session where drift hasn't had many ticks to settle. The
   defensive z=0 tightening (0.45 at undefined drift) gets triggered
   more often at longer halflives because the EWM amplitude is smaller,
   pushing more |drift| values below the noise_floor. L3 and L6 both
   showed the z=0 tightening is mildly net-positive, so shifting more
   trades into that branch should be modestly beneficial -- *unless*
   we cross some threshold where the drift signal becomes too sluggish
   to differentiate adverse from aligned, at which point the
   sign-conditioned tightening loses its alpha.

6. The expected mechanism if halflife=90 hurts: at halflife=90, the
   drift EWM lags genuine intraday regime shifts. A multi-tick adverse
   burst that started 20 ticks ago is at ~13% EWM weight at halflife=90
   (vs ~21% at halflife=60). If the adverse-selection signal is
   genuinely fast (say, 10-50 tick bursts), halflife=90 dilutes it
   relative to halflife=60. Could regress.

**Targeted change for vrs-f-l7**: change `drift_halflife` from 60 to 90
ticks. All other parameters identical to L6.

**Mechanism / inefficiency exploited**: same fundamental mechanism as
L6 (vol-normalized signed-drift tightening) but with a slower, less
noisy signal input. If the L3->L6 +5% gain came primarily from noise
suppression rather than from extending the signal across longer
adverse bursts, then continuing to slow down the EWM should continue
to help up to some point. If it came primarily from holding adverse
signals longer (filling the gap between EWM lifetime and burst
duration), then halflife=90 might still help (longer bursts still
captured) but with diminishing returns approaching halflife=120
(matched to slow_vol). The empirical test discriminates.

**Why it survives costs**: zero-slippage fill model -- edge through
realized P&L only. The change is purely in the drift signal's smoothing
horizon; the sigmoid shape, vol denominator, base vol-skip, and all
other plumbing are unchanged. Bounded downside: if halflife=90
underperforms L6, L8 can revert to L6's halflife=60 or test halflife=45
as a refinement bracketing the optimum near 60.

**Predicted effect size** (loose, order-of-magnitude):

- **Trade count**: L6 = 122,431. Slowing the drift EWM further:
    - Slightly more "undefined drift" classifications (smaller EWM
      amplitude -> more cases below noise_floor) -> more trades go
      through the z=0 defensive tightening (0.45). This shifts
      participation slightly down on average.
    - Slightly less sharp adverse-side tightening on rapidly-onset
      adverse bursts.
    - Net direction: probably modest, +/- 500 trades. Range:
      121,500-123,500.

- **Realized P&L**: this is the test variable.
    - If noise suppression dominates and the L3->L6 trend continues
      (each 30-tick step adds ~$70 in pnl): $1,500-$1,550 (+4% to
      +7% vs L6).
    - If the halflife=60->90 step is past the optimum and the marginal
      smoothing hurts: $1,350-$1,400 (-3% to -7% vs L6).
    - Central guess: $1,460-$1,500 (mildly positive vs L6, between
      noise and modest gain).

- **Sharpe**: should track pnl direction. Central guess 5.8-6.1.
  If pnl drops slightly, sharpe could drop more (typical when removing
  high-variance trades while reducing total skip count slightly).

- **Win_rate**: roughly flat (~35.4-35.5%). The sigmoid shape is
  unchanged; only the input smoothing changes, which shouldn't
  systematically bias the win/loss ratio.

- **Max_dd**: if slower drift catches more persistent adverse regimes,
  drawdowns could improve marginally. If it misses fast bursts, could
  worsen. Central guess -0.034% to -0.038% (similar to L6's -0.0371%).

These are loose order-of-magnitude estimates. The likely outcome based
on the L3->L6 step direction is "flat to mildly positive". Either
result is informative for the timescale optimization.

**Builds on**: vrs-f-l6 (code skeleton starting point; only
`drift_halflife` default changes 60 -> 90).

**Alternatives considered**:

1. *halflife = 120* (matching slow_vol). More aggressive doubling.
   Rejected as primary because if L7 at halflife=90 beats L6, L8
   becomes the natural place for halflife=120 with a clean bracketing
   read; if L7 regresses, halflife=120 is too aggressive and would
   regress further.
2. *halflife = 45* (mid-step between 30 and 60). Rejected because
   the question of interest is whether the optimum is at 60 (L6),
   above 60 (push further), or above 30 below 60 (cluster). The
   primary test is "above 60" -- if confirmed, the cluster question
   is moot.
3. *Stack halflife change with shape tweak* (e.g., halflife=90 +
   k=4). Stacks two changes; muddies attribution. L7 isolates the
   halflife change.
4. *Aggressor flow / book imbalance as second directional signal*.
   The "most promising orthogonal extension" flagged across L4-L6.
   Defer to L8: closing out the halflife sweep first gives a clean
   parameter baseline before pivoting to a new mechanism. L8 can
   test orthogonal-signal-addition on top of whichever halflife
   value won (L6 or L7).
5. *Replace drift EWM with rolling sum*. Architectural change; defer.
6. *Stack with min_prob = 0.02 (deeper base vol-skip)*. Stacks
   changes; defer.
7. *Per-side drift EWMs* (separate drift estimates for BUY/SELL
   orders). Adds state; muddier attribution; defer.

---

## Implementation Decisions

- **Signed-drift EWM**: same algebra as L1-L6, but with
  `drift_halflife = 90` (was 60 in L6, 30 in L1-L5). The drift_alpha
  is re-derived from `1 - exp(-ln(2) / 90)` ~ 0.00767 (vs L6's
  `1 - exp(-ln(2) / 60)` ~ 0.01149 and L5/earlier's
  `1 - exp(-ln(2) / 30)` ~ 0.02284). So halflife=90 has ~2/3 the
  alpha of halflife=60 and ~1/3 of halflife=30.
- **Vol-normalization**: unchanged -- divide `s_drift` by
  `max(slow_vol, 1e-12)`. slow_vol halflife stays at 120.
- **Sigmoid parameters**: L3/L6 values -- `k = 3.0`, `max_tighten = 0.9`.
- **Branches**: full symmetric sigmoid, no aligned-side clip.
- **Undefined drift** (below noise floor or drift state not warm):
  `s_drift = 0` -> tighten = max_tighten / 2 = 0.45. Same as L3/L6.
- **Absolute floor**: 0.01 (same as L3/L6).
- **Calm regime gate**: `p_vol >= 1.0 - 1e-9` -> `p_eff = 1.0`. Same.
- **Cold start**: `tick_count < min_ticks = 30` -> `p = 1.0`. Same.
  Note: with halflife=90, the EWM takes longer to warm up, but the
  cold-start gate at 30 ticks is independent. By the time the gate
  releases, the drift EWM has had 30 ticks of input, which at
  halflife=90 means ~21% of effective weight; not fully settled but
  starting to discriminate. If L7 regresses, a future loop could
  test stacking `min_ticks=60` to allow more drift warmup.
- **Reduce-only**: always submit. Same.
- **Determinism**: same SHA-256(client_order_id) uniform draw. Same.
- **Quantity invariant**: child_qty = parent_qty = 1. Same.

**Concerns**:

- The slower EWM takes longer to warm up. The first ~60-90 ticks of
  each session have drift EWM amplitude smaller than steady-state,
  which pushes more orders into the "undefined drift" branch (0.45
  defensive tightening). At ~100k ticks/day, 60-90 ticks is the first
  ~0.06-0.09% of the session. Not a big aggregate effect, but in the
  first minute of trading the algorithm is slightly more conservative
  than at halflife=60.
- noise_floor=1e-7 is unchanged. A slower drift EWM has even smaller
  amplitude in flat periods, so even more cases get classified as
  "undefined". Combined with the cold-start observation above, this
  makes the defensive z=0 path more frequently used. L3/L6 evidence
  shows this is mildly net-positive, so the side effect is likely
  beneficial. If L7 beats L6, the gain may come more from this side
  effect than from genuine signal-quality improvement -- but the net
  P&L matters more than the precise mechanism attribution.
- The L3-shape sigmoid (k=3, max_tighten=0.9) was tuned on
  halflife=30 drift estimates. The drift z distribution at
  halflife=90 will have a different shape (narrower, more clustered
  near z=0) than at halflife=30. The sigmoid is dimensionless via
  the slow_vol normalization, so this should mostly compensate, but
  there's no guarantee the k=3 steepness is still optimal at the
  longer halflife. Joint re-tuning is deferred; L7 isolates one
  knob.
- The optimum might be slightly off halflife=60 in either direction.
  If L7 regresses, L8 should test halflife=45 to bracket between
  the L6 win and the L7 loss.

---

## Backtest Observations

**12-date full train window results** (vs `vol-regime-sizer` base):
- realized_pnl: $1,384.50 vs base $753.75 → **+83.68% vs base**
- sharpe_ratio: 5.732 vs base 3.065 (+2.667 absolute)
- trade_count: 122,462 vs base 127,991 (−5,529, −4.32%)
- max_drawdown_pct: −0.0359% vs base −0.0460% (22% smaller)
- win_rate: 35.45% vs base ~35.4% (flat)
- mean_slippage: 0.0 (zero-slippage fill model)

**Hypothesis assessment**: REFUTED. halflife=90 regressed vs L6 (halflife=60): pnl $1,447.00 → $1,384.50 (−$62.50, −4.32%), sharpe 5.874 → 5.732 (−0.142 absolute). The halflife=60 optimum was not improved upon by slowing the drift EWM further. The central guess ($1,460-$1,500) was too optimistic; the actual result fell in the "halflife=60->90 past the optimum" range ($1,350-$1,400).

**Key observations**:
1. Trade count is essentially identical: 122,462 vs L6's 122,431 (+31). The additional signal smoothing (halflife 60→90) did not change the number of trades materially — consistent with the defensive z=0 branch and the sigmoid shape being the dominant drivers of trade-count, not the marginal noise in drift sign.
2. Max_dd improved vs L6 (−0.0359% vs −0.0371%), meaning L7's slower signal produced fewer tail-trade outliers. But this came at the cost of overall P&L and sharpe, not an improvement in the quality/risk tradeoff.
3. The halflife sweep result is now 3 data points: 30 (L3, +82%), 60 (L6, +92%), 90 (L7, +84%). The optimum is near halflife=60, with L7 slipping back below L3's level. The improvement from 30→60 was genuine and repeatable; the step from 60→90 gives it back.
4. L6 (halflife=60) remains the best-known configuration.

**Implication for L8**: L7's prescription from alternatives #1 was "if L7 regresses, halflife=120 is too aggressive and would regress further — pivot to orthogonal signal." The halflife=90 regression confirms this. L8 should pivot to the orthogonal signal direction: book imbalance or aggressor flow as a second directional signal on top of L6's best configuration (halflife=60, k=3, max_tighten=0.9, full sigmoid). This has been deferred across L4-L7 as "most promising orthogonal extension" and the halflife sweep is now sufficiently explored. The clean baseline for adding a second signal is L6.
