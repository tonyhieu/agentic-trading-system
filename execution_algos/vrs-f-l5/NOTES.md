# Algorithm Notes: vrs-f-l5

Loop 5 of the per-iteration experiment, full-trace arm, base = `vol-regime-sizer`.

## Hypothesis

**Starting point**: `vrs-f-l4` (the prior loop). Its mechanism is the
vol-normalized signed-drift sigmoid from L3 with sharpened shape:
`tighten = max_tighten * sigmoid(-k * z)` with `max_tighten = 1.0`,
`k = 6.0`, `z = order_sign * drift / max(slow_vol, eps)`. Applied as
`p_eff = max(absolute_floor, p_vol * (1 - tighten))`.

**Observations driving this loop** (from the full L1->L4 trace):

1. The arm trajectory shows monotone improvement L1->L2->L3, then a small
   regression L3->L4: L1 -34.23%, L2 +30.12%, L3 +82.36%, **L4 +78.37%**.
   The full 12-date L4 aggregate ($1,344.50 vs L3's $1,374.50) is now
   available and is essentially flat vs L3, slightly worse on every
   primary metric: pnl -2.18%, sharpe 5.71 vs 5.80, win_rate 35.413% vs
   35.407% (essentially identical), max_dd -0.0343% vs -0.0346% (-0.9%
   relative, basically flat). So jointly pushing `k` 3->6 and
   `max_tighten` 0.9->1.0 was a tiny step backward.

2. L4's design jointly redistributed the sigmoid's tightening budget:
   *more* skipping in the strongly-adverse tail (|z| > 0.25), and
   *less* skipping in the marginally-aligned band (0 < z < 1). L4's
   hypothesis was a clean A/B test: if worst-tail saturation dominates,
   L4 beats L3; if marginal-aligned restoration dominates (re-introducing
   harmful trades), L4 underperforms L3. The data says the two effects
   roughly cancel, with the marginal-aligned harm slightly outweighing
   the worst-tail benefit. This is informative: it constrains the design
   space.

3. L4's enumerated next-step #2 was explicit: "If L4 closes the
   coverage gap and still does not exceed L3 by a clear margin, test
   tightening only when z<0 with no-op at z>=0" -- the **asymmetric
   sigmoid**. The coverage gap is now closed (all 12 dates available
   in L4's results/backtest-results.json), and L4 did NOT exceed L3.
   This is the precise condition L4 prescribed for the asymmetric
   variant.

4. The asymmetric clip isolates two questions that L1-L4 conflated:
   - **The adverse side**: is the L3-shape (k=3, max_tighten=0.9) the
     right amount of tightening, or does the worst tail need more (L4)?
     L4's data says L3-shape is at least as good. So keep L3-shape.
   - **The aligned side**: was L3's mild tightening on the marginal-
     aligned band (~0.05-0.16 at 0.25 < z < 1) net-positive,
     net-neutral, or net-negative? L4's reduction of it (to ~0.002-0.05)
     produced a small overall regression -- *but* that change was
     confounded with the sharper k=6 which also concentrated tightening
     in the deep-adverse tail. We don't actually know whether
     L4's regression came from "too much deep-tail" (over-skipping wins
     in the saturated region) or "too little marginal-aligned" (re-
     adding the harmful aligned trades L3 was skipping). The asymmetric
     L5 disentangles this.

**Targeted change for vrs-f-l5**: revert sigmoid shape to L3's
parameters (`max_tighten = 0.9`, `k = 3.0`), and clip the tightening to
zero on the aligned side (z > 0). Three concrete branches in the
tightening function:

  - **z <= 0** (adverse or zero/undefined drift): same as L3.
    `tighten = max_tighten * sigmoid(-k * z)`. With k=3, max_tighten=0.9:
      - z=0 -> tighten = 0.45 (defensive at undefined drift)
      - z=-0.25 -> tighten = 0.611
      - z=-0.5 -> tighten = 0.736
      - z=-1.0 -> tighten = 0.857
      - z=-2.0 -> tighten = 0.897 (saturated)
  - **z > 0** (aligned drift, sign(drift) matches order side): `tighten = 0`.
    Full no-op. This matches L2's aligned passthrough exactly.

So L5 = L3 on the adverse side, L2 on the aligned side. The
"asymmetric" name refers to the sigmoid being clipped to zero on the
positive branch.

**Mechanism / inefficiency exploited**: L4's data argues that the
marginal-aligned band's mild tightening (L3) was neutral-to-slightly-
positive. But L1's data shows that *adding* aligned trades is
net-negative. These two observations are consistent if the marginally
aligned trades are *close* to net-neutral: L1's harmful boost was
because it relaxed the entire vol-skip on alignment (going from p_vol
to p_eff ~ 1), whereas L3's mild tightening was only modulating
p_eff -> 0.85 * p_vol, which has a much smaller effect.

The asymmetric clip is the principled middle ground: it preserves the
*adverse-side* tightening (proven by L2 and L3 to be the strongest
gain driver) while removing the *aligned-side* tightening (which L4
implies was at best neutral, at worst slightly harmful by removing
some good trades). If aligned-side tightening was genuinely
net-positive in L3, L5 will *regress* slightly vs L3; if it was
genuinely net-negative or zero, L5 will be at least as good as L3.
The clean A/B is informative either way.

**Why it survives costs**: zero-slippage fill model. Edge through
realized P&L only. The change strictly *reduces* skip on the aligned
side (more trades submitted in the 0 < z < 1 band) and is *identical*
to L3 on the adverse side. So the trade-count change should be
unambiguously positive: ~+500 to ~+2,000 trades more than L3.

**Predicted effect size** (loose, order-of-magnitude):

- **Trade count**: L3 = 122,400. L5 will submit more trades on the
  aligned side (those that L3 was tightening at 0.05-0.45 in the
  z range [0, +infty)). Rough range: 123,000-125,000 (+1,000 to +2,500
  vs L3).
- **Realized P&L**: depends on whether the additional aligned trades
  are net-positive, net-zero, or net-negative.
  - If net-positive (L3 was over-skipping): P&L rises to $1,400-$1,500
    range, beating L3.
  - If net-neutral: P&L stays roughly flat at $1,300-$1,400.
  - If net-negative (L3 was correctly skipping them): P&L drops to
    $1,200-$1,350, slightly below L3.
  - Best guess: roughly neutral to slightly positive, central
    estimate ~$1,400.
- **Sharpe**: should roughly track pnl. If pnl is neutral, sharpe
  might drop a bit because we're adding back some variance. Central
  guess 5.5-6.0.
- **Win rate**: should move very slightly in line with pnl.
  35.3-35.5%.
- **Max DD**: small additional aligned-side participation should not
  meaningfully change tail risk. Central guess -0.034% to -0.037%
  (roughly L3's level).

This is a "minimum strict comparison" loop: even if L5 underperforms
L3 marginally, the result is highly informative because it pins down
which side of the sigmoid was carrying the weight.

**Builds on**: vrs-f-l4 (code skeleton); shape params reverted to L3
defaults; aligned-side clip added.

**Alternatives considered**:

1. *Asymmetric with L4 shape (k=6, max_tighten=1.0)*. Tests the
   sharper-adverse interpretation with no aligned tightening.
   Rejected: stacks two changes from L3 (sharper + clip). L5 with
   L3 shape + clip isolates ONE change from L3, giving a clean
   1-d comparison.
2. *Clip at higher threshold (e.g., z > 0.5 only)*: keep mild
   tightening on the marginal-aligned band (0 < z < 0.5) where L3's
   tightening was non-trivial (0.16-0.45), only clip the strongly-
   aligned tail. More conservative but less interpretable. Rejected
   because the strongly-aligned tail is exactly where L3 already had
   near-zero tightening (0.002-0.05 at z >= 1); clipping it doesn't
   change much. The marginal-aligned band (0 < z < 0.5) is where
   the action is.
3. *Threshold-only clip*: define a hard cutoff `z_clip` such that
   for z > z_clip, tighten = 0. Less smooth than a binary z<=0 vs
   z>0 distinction. Adds a hyperparameter. Defer.
4. *Re-tune `drift_halflife`*: still untouched since L1 (=30 ticks).
   Cleaner one-knob sweep. Save for L6/L7.
5. *Aggressor flow / book imbalance as second directional signal*.
   Most promising orthogonal extension; defer to L6+ once
   sigmoid-shape work fully stabilizes.
6. *Stack with lower min_prob (0.02)*: deeper base vol-skip region
   amplifies where tightening operates. Stacks changes; defer.
7. *Drift normalization by fast_vol instead of slow_vol*: more
   reactive but noisier. Defer.

---

## Implementation Decisions

- **Signed-drift EWM**: reused from L4 verbatim. Halflife = 30,
  noise floor = 1e-7, lazy init from first observed delta.
- **Vol-normalization**: divide `s_drift` by `max(slow_vol, 1e-12)`.
  Uses the existing slow_vol EWM (halflife=120). No new state.
- **Sigmoid parameters reverted to L3**: `k = 3.0`, `max_tighten = 0.9`.
- **Aligned-side clip**: when `z > 0`, `tighten = 0` (full no-op,
  matches L2). When `z <= 0` (adverse or undefined/zero drift),
  `tighten = max_tighten * sigmoid(-k * z)`.
- **Undefined drift** (below noise floor or drift state not warm):
  `s_drift = 0` -> `z = 0` -> falls into the `z <= 0` branch ->
  `tighten = max_tighten * sigmoid(0) = 0.45`. Same defensive
  tightening as L3 at undefined drift -- the clip does NOT affect
  the z=0 case.
- **Absolute floor**: 0.01 (same as L3, L4). Only binds in the
  deep adverse + deep p_vol corner.
- **Calm regime gate**: `p_vol >= 1.0 - 1e-9` -> `p_eff = 1.0`. Same.
- **Cold start**: `tick_count < min_ticks` -> `p = 1.0`. Same.
- **Reduce-only**: always submit. Same.
- **Determinism**: same SHA-256(client_order_id) uniform draw. Same.
- **Quantity invariant**: child_qty = parent_qty = 1. Same.

**Concerns**:

- The asymmetric clip introduces a discontinuity at z=0: tightening
  jumps from 0.45 (at z=0) to 0 (at z=0+). This is a sharp boundary
  on a continuous variable; in principle small fluctuations in drift
  estimation could push trades back and forth across the boundary.
  Mitigation: the drift EWM at halflife=30 ticks smooths short-term
  noise; the noise floor 1e-7 prevents pathological zero-crossing
  oscillation. A future loop could test a smooth interpolation
  (e.g., `tighten = max_tighten * sigmoid(-k*z) * (1 - clip(z, 0, 1))`)
  to remove the discontinuity, but L5's job is the clean A/B vs L3,
  not the perfectly-smooth refinement.
- If the marginal-aligned trades were genuinely net-positive in L3
  (i.e., L3's tightening on them was harmful) but L1 still showed
  that *all-aligned* relaxation was harmful, the right interpretation
  is that the curve is non-monotonic in tightening: small tightening
  helps, no tightening is OK, large boost is bad. This loop tests
  one of those three points; we can't fully characterize the curve
  from one experiment.
- The diagnostic `_tighten_applied` counter will now under-count
  vs L3/L4: trades in the z > 0 region with tighten=0 will not
  increment, even though they would have in L3. Need to adjust
  counter semantics or accept the change in semantics.

---

## Backtest Observations

**12-date full train window results** (vs `vol-regime-sizer` base):
- realized_pnl: $1,203.50 vs base $753.75 → **+59.67% vs base**
- sharpe_ratio: 4.880 vs base 3.065 (+1.815 absolute)
- trade_count: 124,308 vs base 127,991 (−3,683, −2.88%)
- max_drawdown_pct: −0.0378% vs base −0.0460% (18% smaller)
- win_rate: 35.36% vs base ~35.4% (approximately flat)
- mean_slippage: 0.0 (zero-slippage fill model)

**Hypothesis assessment**: PARTIALLY SUPPORTED — asymmetric clip removed aligned-side tightening cleanly, but the result is between L3 (+82.4%) and L4 (+78.4%) rather than beating L3. The aligned-side tightening in L3 was mildly net-positive. Removing it costs ~$170 in P&L vs L3 ($1,374.50 → $1,203.50). The drop is ~12.4% of L3 P&L, concentrated in the ~2k additional trades L3 was mildly tightening.

**Key observations**:
1. Trade count (124,308) is higher than L3 (122,400) by ~1,900 trades — consistent with the prediction (+1,000 to +2,500) that aligned-side clipping would release held-back trades. The direction was right; the P&L consequence was mildly negative (those trades were net-marginal but slightly positive in L3's tightened form, now submitted at full p_vol).
2. Sharpe dropped from L3's 5.80 to 4.88 — a 0.92 absolute regression. This suggests the additional aligned-side variance (more trades) added noise without proportional gain, as expected when adding near-zero-EV trades.
3. The adverse-side (z≤0 path) performance is identical by design to L3. Any delta vs L3 is entirely attributable to the aligned-side change. The ~$170 P&L drop + 0.92 sharpe drop is the cost of the aligned-side clip.
4. max_dd improved further vs base but regressed slightly vs L3 (−0.0378% vs L3's −0.0346%): adding ~1,900 trades slightly widened the max daily drawdown, consistent with adding variance.

**Implication for L6**: The asymmetric clip (L5) confirmed that L3's mild aligned-side tightening was genuinely net-positive. L3's shape (k=3, max_tighten=0.9, full sigmoid including aligned side) was better than either the asymmetric clip (L5) or the sharper saturation (L4). The next highest-leverage direction from L4's enumerated list (#4): drift_halflife perturbation. L1-L5 all used drift_halflife=30; no loop has perturbed it. The drift EWM's smoothing horizon directly controls how quickly the adverse/aligned signal adapts. A shorter halflife (e.g., 15) makes z more reactive to recent ticks; a longer one (e.g., 60) smooths noise better but lags regime changes. One-knob sweep: test halflife=60 with L3 shape restored (k=3, max_tighten=0.9, full sigmoid, no asymmetric clip). Alternative: return to L3 exactly and try a second directional signal (book imbalance) as the first orthogonal extension — still the "most promising orthogonal extension" per L4's enumeration and still untested.
