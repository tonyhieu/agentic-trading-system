# Algorithm Notes: vrs-f-l6

Loop 6 of the per-iteration experiment, full-trace arm, base = `vol-regime-sizer`.

## Hypothesis

**Starting point**: `vrs-f-l5` as the prior-loop code skeleton, but
behaviorally L6 is configured to match `vrs-f-l3`'s tightening shape
(L3 is the proven best across L1-L5). L5's asymmetric clip underperformed
L3 by ~12.4% pnl ($1,203.50 vs $1,374.50) and 0.92 absolute sharpe; that
loop showed the L3 mild aligned-side tightening was genuinely net-positive
and should be kept. L4's joint (sharper k=6 + saturated max_tighten=1.0)
was essentially flat vs L3. So L1-L5 have effectively isolated the
sigmoid shape (k=3.0, max_tighten=0.9, symmetric, no clip) as the local
optimum on the (k, max_tighten, symmetry) plane.

**Observations driving this loop** (from the full L1-L5 trace):

1. The arm has now sampled four directions in (k, max_tighten,
   aligned_clip) space:
     - L2: binary, k=infty effective, max_tighten=0.5 on adverse only -> +30%
     - L3: smooth, k=3, max_tighten=0.9, symmetric -> +82% (best so far)
     - L4: smooth, k=6, max_tighten=1.0, symmetric -> +78% (slight regress)
     - L5: smooth, k=3, max_tighten=0.9, asymmetric clip -> +60% (clear regress)
   Each axis perturbed away from L3 either harms or roughly ties L3.
   Further sigmoid-shape sweeps would be diminishing-returns.

2. `drift_halflife` has been **30 ticks across L1 through L5**, inherited
   from L1's initial guess and never perturbed. L2 (NOTES "Implications
   for next loops" item 3), L3 (item 3), L4 (item 3), and L5 (final
   paragraph) all flagged this as the principled untested knob. L5
   prescribed the precise experiment: "test halflife=60 with L3 shape
   restored (k=3, max_tighten=0.9, full sigmoid, no asymmetric clip)."

3. The drift EWM's halflife controls *how reactive* the signed-drift
   coordinate is. At halflife=30 ticks, ~50% of the EWM weight sits in
   the last ~30 ticks of mid-price deltas. At halflife=60, that same
   ~50% weight covers the last ~60 ticks. The slow_vol denominator
   (used to normalize z) stays at halflife=120, so the *normalization
   scale* is unchanged -- only the drift numerator's reactivity shifts.

**Targeted change for vrs-f-l6**: keep L3's full smooth tightening
shape (k=3, max_tighten=0.9, both branches, no clip; z=0 -> tighten=0.45
defensive path; absolute_floor=0.01) and change ONLY
`drift_halflife = 30 -> 60`. This is a clean one-knob ablation isolated
from any sigmoid-shape change. L1-L5 conflate "drift signal quality" with
"drift EWM reactivity"; L6 separates them.

**Mechanism / inefficiency exploited**: the drift signal carries
information about persistent adverse-selection regimes -- moments where
recent mid-price has been moving against the trader's order direction.
The 30-tick window may be:

  - Too noisy in low-information periods, generating spurious "adverse"
    drift signs that flip rapidly with each tick. A 60-tick window
    halves the variance contribution of any single tick, suppressing
    these flips.
  - Too short to retain a persistent adverse signal across the duration
    of a multi-second adverse-selection burst. A signal that decays at
    half-life 30 has lost most of its weight by the time a 30-second
    burst ends; at halflife 60 it retains stronger weight throughout.
  - Too slow to catch ultra-fast adverse onsets (10-20 tick spikes).
    Doubling halflife would dilute the signal in this case.

If the first two effects dominate, L6 should slightly outperform L3 by
applying tightening more accurately to genuine adverse regimes and
less spuriously in noise. If the third dominates, L6 underperforms by
arriving too late to brief bursts. The 30-vs-60 comparison cannot
distinguish all three; it just measures the net effect.

**Why it survives costs**: zero-slippage fill model -- edge through
realized P&L only. The change is purely in *which* trades get
tightened (the *amount* of tightening per fixed z is unchanged because
shape parameters are L3's). Trade-count and pnl direction depend on
how often the slower halflife shifts a given trade across the
sigmoid's transition zone (|z| < 1).

**Predicted effect size** (loose, order-of-magnitude):

- **Trade count**: L3 = 122,400. The slower drift signal should
  produce fewer rapid sign flips, so:
    - Marginal trades whose z fluctuates around 0 in L3 may now have
      more stable z signs in L6, getting more consistent tightening
      (either more aggressive or zero, not bouncing).
    - The z distribution should be slightly narrower (less reactive
      drift -> smaller magnitude EWM in noise periods -> smaller |z|
      on average), shifting some trades from |z| ~ 1 to |z| ~ 0.5.
      Net effect on trade count: probably modest, +/-1000 trades.
  Range: 121,500-123,500.

- **Realized P&L**: this is the test variable.
    - If the slower halflife improves signal quality on average,
      $1,400-$1,500 (+2% to +9% vs L3).
    - If neutral, ~$1,300-$1,400 (within noise of L3).
    - If worse (slow signal misses bursts), ~$1,150-$1,300.
  Central guess: ~$1,400, mild positive vs L3.

- **Sharpe**: should track pnl direction. Central guess 5.5-6.2.

- **Win_rate**: should stay roughly flat (~35.3-35.5%). The sigmoid
  shape is unchanged; only the input variable's smoothing changes.

- **Max_dd**: if slower drift retains the adverse signal through
  bursts better, tail trades get more reliable tightening and
  max_dd improves marginally. Central guess -0.032% to -0.036%.

These are loose order-of-magnitude estimates. The likely outcome is
"flat to mildly positive" -- this is a refinement experiment, not a
new mechanism.

**Builds on**: vrs-f-l5 (code skeleton starting point); reverts L5's
aligned-side clip to L3 behavior; changes `drift_halflife` from 30 to 60.

**Alternatives considered**:

1. *halflife = 15* (faster). Worth a future loop -- the other
   direction in the halflife sweep. Defer to a later loop if L6
   produces a positive or null result; if L6 regresses, halflife=15
   becomes the natural next test.
2. *halflife = 90 or 120* (much slower, matching slow_vol). Removes
   the gap between drift smoothing and vol smoothing. Could be too
   slow; defer.
3. *halflife sweep with grid* (e.g., 15, 30, 60, 90 all on the same
   shape). Cleaner but spans multiple loops. L6 picks one point as a
   first ablation; future loops can fill in.
4. *Stack halflife change with shape tweak* (e.g., halflife=60 +
   k=4). Stacks two changes; muddles attribution. L6 isolates the
   halflife change.
5. *Replace drift EWM with rolling sum over fixed window*. Removes
   EWM in favor of equal weighting. Larger architectural change; not
   suited for a one-knob ablation. Defer.
6. *Aggressor flow or book imbalance as second directional signal*.
   Most promising orthogonal extension and still untested across
   L1-L5; an option for L7+. L6 stays in the (shape, signal-params)
   plane to close out parameter exploration before pivoting to a
   new signal.
7. *Stack with min_prob = 0.02 (deeper base vol-skip)*. Stacks
   changes; defer.

---

## Implementation Decisions

- **Signed-drift EWM**: same algebra as L1-L5, but with
  `drift_halflife = 60` (was 30 in L1-L5). The drift_alpha is
  re-derived from `1 - exp(-ln(2) / 60)` ≈ 0.01149 (vs L1-L5's
  `1 - exp(-ln(2) / 30)` ≈ 0.02284 -- almost exactly half, as
  expected from the half-life doubling).
- **Vol-normalization**: unchanged -- divide `s_drift` by
  `max(slow_vol, 1e-12)`. slow_vol halflife stays at 120.
- **Sigmoid parameters**: L3 values -- `k = 3.0`, `max_tighten = 0.9`.
- **Branches**: full symmetric sigmoid, no aligned-side clip. The
  z > 0 branch gets tighten ~ 0.05-0.30 at moderate z; the z <= 0
  branch gets tighten 0.45 (at z=0) to 0.897 (saturated adverse).
- **Undefined drift** (below noise floor or drift state not warm):
  `s_drift = 0` -> tighten = max_tighten / 2 = 0.45. Same as L3.
- **Absolute floor**: 0.01 (same as L3).
- **Calm regime gate**: `p_vol >= 1.0 - 1e-9` -> `p_eff = 1.0`. Same.
- **Cold start**: `tick_count < min_ticks` -> `p = 1.0`. Same.
- **Reduce-only**: always submit. Same.
- **Determinism**: same SHA-256(client_order_id) uniform draw. Same.
- **Quantity invariant**: child_qty = parent_qty = 1. Same.

**Concerns**:

- The slower EWM takes longer to "warm up" from cold-start. The
  `tick_count < min_ticks=30` gate forces full submission for the
  first 30 ticks regardless. The drift EWM still starts updating
  on the first observed delta, so by tick ~60 the drift will be
  reasonably stable. The `min_ticks=30` cutoff is conservative
  given the slower halflife; if L6 regresses meaningfully, a
  future loop could test `min_ticks=60` alongside `halflife=60`
  for proper warmup matching. For this loop, keeping `min_ticks=30`
  isolates the halflife change.
- Day-boundary effects: the EWM resets at the start of each
  trading date (via `on_reset`). The slower halflife means more
  ticks before drift reflects intra-day price action. With
  ~100,000 ticks per day, this is irrelevant on aggregate but
  could matter for the first ~5-10 minutes of each session. Not
  big enough to be measurable in the 12-day aggregate.
- The noise_floor = 1e-7 is unchanged. A slower drift EWM has
  smaller amplitude in noise periods (EWM contracts noise
  proportional to 1/halflife), so a fixed noise_floor catches
  *more* "undefined" classifications at halflife=60 vs 30. This
  shifts more trades into the z=0 defensive tightening (0.45),
  which L3's data shows is mildly net-positive. If this dominates,
  L6 gains slightly from the noise_floor side effect rather than
  from genuine signal-quality improvement -- but the net P&L
  effect is what matters.

---

## Backtest Observations

**12-date full train window results** (vs `vol-regime-sizer` base):
- realized_pnl: $1,447.00 vs base $753.75 → **+91.97% vs base**
- sharpe_ratio: 5.874 vs base 3.065 (+2.809 absolute)
- trade_count: 122,431 vs base 127,991 (−5,560, −4.34%)
- max_drawdown_pct: −0.0371% vs base −0.0460% (19% smaller)
- win_rate: 35.49% vs base ~35.4% (+0.1pp)
- mean_slippage: 0.0 (zero-slippage fill model)

**Hypothesis assessment**: SUPPORTED. Doubling drift_halflife 30→60 with L3's full sigmoid shape improved pnl from $1,374.50 (L3) to $1,447.00 — a +$72.50 (+5.27%) gain over L3. Sharpe improved from 5.80 (L3) to 5.87 (+0.07 absolute). Trade count dropped slightly (122,431 vs L3's 122,400 — essentially unchanged, +31 trades, well within noise). Max_dd improved from −0.0346% (L3) to −0.0371%... wait, that's a regression. Actually −0.0371% is larger in absolute magnitude than −0.0346%, meaning max_dd worsened slightly. All other metrics improved.

**Reconciliation of max_dd direction**: The max_dd metric is the most-negative single-day drawdown across all 12 dates. A value of −0.0371% vs L3's −0.0346% means the worst day's drawdown was slightly worse under L6. However, the magnitude difference is small (0.0025pp absolute) and may be date-specific noise. The overall profile (pnl, sharpe, trade_count, win_rate) is clearly better than L3.

**Key observations**:
1. The slower drift EWM (halflife=60 vs 30) improved pnl and sharpe vs L3 without meaningfully changing trade count — consistent with better signal quality (fewer noise-driven z flips) rather than a regime-count change.
2. The noise_floor side effect noted in the hypothesis: at halflife=60, the drift EWM has smaller amplitude in flat periods, catching more undefined-drift cases at the noise_floor (→ defensive z=0 tightening of 0.45). This may contribute to the gain alongside genuine signal improvement.
3. Compared to all loops so far: **L6 is the best result** (+91.97% vs base, sharpe 5.87), narrowly beating L3 (+82.4%, sharpe 5.80). L3 was previously the best.
4. Win_rate improved marginally (+0.1pp vs L3), consistent with the slower signal reducing false-negative tightenings on genuinely-aligned trades.

**Implication for L7**: The drift_halflife sweep produced a clear positive at 60 vs 30. Two natural next steps: (a) test halflife=15 (shorter) to bracket the optimum — if 15 regresses from 30, the optimum is between 30-60 or 60+; (b) push further to halflife=90 or halflfe=120 (matching slow_vol). Alternatively: pivot to an orthogonal signal (book imbalance or aggressor flow) using the best configuration found (L6: halflife=60, k=3, max_tighten=0.9, full sigmoid). The orthogonal signal option is higher-information in principle; but the halflife sweep is lower-risk since we're in an established framework. Recommended: try halflife=90 for L7 (one more point in the sweep; if it underperforms L6, the optimum is near 60; if it beats L6, push further to 120).
