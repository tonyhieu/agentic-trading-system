# Algorithm Notes: vrs-f-l2

Loop 2 of the per-iteration experiment, full-trace arm, base = `vol-regime-sizer`.

## Hypothesis

**Starting point**: `vrs-f-l1` (prior loop's code). Its core mechanism is the
base `vol-regime-sizer`'s probabilistic skip on open-leg orders, with an
*added* directional-alignment relaxation: when sign(drift) matches the order
side and |drift| > noise_floor, the skip probability is softened toward 1.0
via `p_eff = p_vol + align_boost * (1 - p_vol)`. The signed-drift EWM
infrastructure (halflife=30 ticks, noise_floor=1e-7) is already plumbed in.

**Observation driving this loop** (from vrs-f-l1's `full_reasoning` and its
NOTES.md "Backtest Observations"): the alignment-as-*relaxation* hypothesis
was decisively refuted (-34.23% pnl vs base, sharpe 1.98 vs 3.07). The
loop-1 reasoning identified the symmetric inversion as the most promising
direction: "Drift-alignment as a *tightening* signal (skip even more
aggressively when drift is adverse, i.e. opposite to the order) is the
symmetric inversion of this loop's idea and may actually work -- the same
data point that refuted the relaxation supports the inversion: aligned
trades are *worse* than the base's blind skip, which means adverse-drift
trades may be even worse and warrant a tighter skip."

This is the explicit "next direction" handoff from loop 1's full-trace
context. The logic is:

  1. Loop 1 showed: relaxing the skip on aligned-drift trades is harmful.
     The ~3,000 marginal aligned-drift trades had similar win_rate but
     worse magnitude profile (P&L dropped $258 with hit-rate roughly flat).
  2. If aligned-drift entries in high-vol regimes are worse than the
     base's average skipped trade, by direct symmetry adverse-drift
     entries (where the recent mid is moving *against* the order) are
     likely *even worse* -- the trader is buying as the market falls
     (or selling as it rallies). These are textbook adverse-selection
     setups.
  3. The base algo currently treats both aligned and adverse high-vol
     moments identically (skip via `p_vol`). If adverse-drift trades are
     the worst subset within the base's skip-region, *tightening* the
     skip there (skipping more) should preserve the base's gains on the
     aligned/neutral subset while removing the worst trades from the
     adverse-drift subset.

**Targeted change for vrs-f-l2**: replace the *relaxation* mechanism from
loop 1 with a *tightening* mechanism on adverse-drift open-leg orders.
Specifically:

  - Keep the signed-drift EWM (halflife = `drift_halflife = 30`) and the
    `_is_aligned` helper from loop 1's plumbing -- the infrastructure is
    free and orthogonal.
  - Replace `_effective_prob` so the aligned branch is a no-op (just use
    `p_vol`, no boost) and the adverse branch tightens by a configurable
    factor:
      - aligned (sign(drift) == sign(order), |drift| > noise_floor):
        `p_eff = p_vol` (no change vs base -- this is the key inversion
        from loop 1, where the aligned case was *boosted*).
      - undefined (|drift| <= noise_floor, or drift state not yet
        warm): `p_eff = p_vol` (fall back to base behavior).
      - adverse (sign(drift) != sign(order), |drift| > noise_floor):
        `p_eff = max(absolute_floor, p_vol * (1 - adverse_tighten))`
        with `adverse_tighten = 0.5` (cuts adverse-drift participation
        in half) and `absolute_floor = 0.01` (don't go below 1% so we
        retain a tiny diversification term).
  - Reduce-only orders: always submit (unchanged from base/loop 1).
  - Cold-start (`tick_count < min_ticks`): submit at p=1.0 (unchanged).
  - Calm regimes (`p_vol >= 1.0`): `p_eff = 1.0` -- no tightening when
    the vol regime itself does not call for skip.

**Mechanism / inefficiency exploited**: the base algo's vol-only skip is
direction-blind. Within its "skip more in high vol" region, the marginal
trades are not equally adverse -- the worst ones (highest expected
adverse selection) are those where the trader's order direction *opposes*
the recent mid-price drift. By compounding `(1 - adverse_tighten)` on top
of `p_vol` only in that adverse subset, we are surgically reducing
participation where the empirical evidence (loop 1's data point) most
strongly suggests it should be reduced.

**Why it survives costs**: zero-slippage fill model, so the edge must
come through realized P&L. Loop 1's data showed that the marginal
direction-conditioned trades have worse magnitude. We are skipping (a
fraction of) the worst subset -- adverse-drift -- so realized P&L should
improve relative to the base. Slippage stays at 0.0.

**Predicted effect size**:
- Loop 1 added 3,038 trades vs the base (relaxation on the aligned
  subset). Roughly the adverse subset is similar in count.
- If we skip ~50% of adverse-drift trades inside the vol-skip region,
  we remove on the order of 1,500 trades from the base's ~127,991.
- If those marginal trades are net-negative (as loop 1's symmetric
  evidence implies), each removed trade contributes ~+$0.08 in
  expectation (loop 1: $258 lost over 3,038 added trades ≈ -$0.085
  per added trade). Removing 1,500 adverse trades ≈ +$130 over the
  base's $753.75 → roughly +17% pnl improvement.
- Sharpe should improve more than P&L because we are removing
  *high-variance, low-edge* trades.
- Trade count should drop by 1-2% relative to base (~125-127k).

These are loose order-of-magnitude estimates, not predictions to commit
to. The actual effect could be 2x larger or smaller, or be inverted if
the symmetry argument fails.

**Builds on**: vrs-f-l1 (the prior loop's code is the starting skeleton;
the signed-drift EWM and is_aligned helper are reused verbatim).

**Alternatives considered**:
1. Combine adverse-tightening with aligned-relaxation (i.e. asymmetric
   in both directions). Rejected: loop 1 showed the relaxation side
   hurts; combining the harmful relaxation with the (untested)
   tightening just contaminates the test of the tightening hypothesis.
   Keep the experiment clean by only varying the adverse side.
2. Use a soft, smooth function of drift magnitude (e.g., `p_eff = p_vol
   * exp(-k * max(0, -drift_aligned))`) instead of a binary
   sign(drift) test. More principled, but harder to interpret and
   harder to compare to loop 1. Defer to a future loop if the binary
   inversion succeeds.
3. Use book imbalance or trade aggressor as the directional signal
   instead of mid-drift. Loop 1's full_reasoning flagged that
   "mid-drift may correlate with oracle direction at sigma=6, so
   aligned drift is near-tautology". For *adverse* tightening, that
   same near-tautology cuts in our favor: adverse drift becomes
   "oracle direction contradicts recent price action", which is a
   legitimate adverse-selection flag. So mid-drift is actually
   well-suited for the *adverse* side even if it was bad for the
   *aligned* side. Reserve aggressor flow / imbalance for a future
   loop.
4. Pure parameter tuning of the base (e.g., lower `min_prob`, higher
   `sensitivity`). This is the conservative direction loop 1 flagged
   but parameter tuning is unlikely to capture the *direction-aware*
   structure that the adverse-tightening hypothesis is built on. If
   adverse-tightening fails, parameter tuning is a fallback for a
   later loop.
5. Tighter `adverse_tighten` (e.g., 0.9 = skip 90% of adverse). More
   aggressive but risks over-skipping if drift sign is noisy. 0.5 is
   a moderate first cut.

---

## Implementation Decisions

- **Signed-drift EWM**: reused from vrs-f-l1 verbatim. Half-life =
  `drift_halflife = 30` ticks. Same noise floor `drift_noise_floor =
  1e-7`. Same lazy initialization (first observed delta_mid seeds the
  EWM).
- **Adverse-tightening factor**: `adverse_tighten = 0.5`. Halves
  participation in the adverse-drift subset within the vol-skip region.
  Conservative first cut.
- **Absolute floor**: 0.01 (1%). Strictly below `min_prob = 0.05` so it
  only binds in the adverse-tightening branch. Prevents `p_eff = 0`
  from creating a deterministic null in the adverse subset.
- **Aligned branch**: no-op. `p_eff = p_vol`. This is the explicit
  inversion of loop 1, which boosted this branch.
- **Undefined branch** (drift below noise floor or not yet warm):
  `p_eff = p_vol`. Identical to base.
- **Calm regime** (`p_vol >= 1 - 1e-9`): `p_eff = 1.0`. Even adverse
  drift in calm vol doesn't trigger tightening -- the skip mechanism
  itself is dormant.
- **Cold start** (`tick_count < min_ticks`): submit at `p=1.0`.
- **Reduce-only**: always submit.
- **Determinism**: same SHA-256(client_order_id) uniform draw as
  base and loop 1. Only the `p` value fed into the comparison changes.
- **Quantity invariant**: child_qty = parent_qty = 1.

**Concerns**:
- If the mid-drift direction is *uncorrelated* with the oracle
  signal's actual error direction, adverse-tightening is wasted
  skipping -- removes similar mix of wins and losses, degrading P&L
  by removing diversification. Loop 1's evidence is suggestive but
  not conclusive of the inverse correlation.
- The "expected effect size" calculation above relies on symmetry
  between aligned and adverse drift trades in their expected
  per-trade contribution. This may not hold -- e.g., the aligned
  subset might be uniformly weakly-negative while the adverse subset
  is bimodal (some strongly-negative, some strongly-positive).
- If adverse-drift trades are *actually* contrarian and net-positive
  (oracle is right but mid is briefly noisy), tightening removes
  alpha rather than adverse selection. Loop 1's data argues against
  this but does not prove it.
- The drift EWM at halflife=30 ticks is roughly a 30-tick (sub-
  second to ~few-second) window. If oracle errors actually cluster
  at a different timescale, the wrong halflife means we're
  measuring the wrong drift. Halflife was chosen to match loop 1
  for direct comparison; future loops can re-tune.

---

## Backtest Observations

Train window: 12 dates (20260308-20260320).
Comparison point: base algo `vol-regime-sizer` (this is the per-iteration
experiment, full-trace arm loop 2).

**Aggregated results, vrs-f-l2 (12 dates)**:
- realized_pnl  = $980.75
- sharpe_ratio  = 4.127 (n_days=12)
- trade_count   = 124,876
- win_rate      = 35.35%
- max_dd_pct    = -0.0423%
- mean_slippage = 0.0 (zero-slippage fill model)
- is_weighted_bps = 0.03612

**Aggregated results, base `vol-regime-sizer` (12 dates, from
execution_algos/vol-regime-sizer/results/backtest-results.json)**:
- realized_pnl  = $753.75
- sharpe_ratio  = 3.065
- trade_count   = 127,991
- win_rate      = 35.29%
- max_dd_pct    = -0.0460%
- mean_slippage = 0.0
- is_weighted_bps = 0.03737

**Deltas vs base_algo (vol-regime-sizer)**:
- vs_base_pnl_pct       = (980.75 - 753.75) / 753.75 * 100 = **+30.12%**
- vs_base_slippage_pct  = 0.0% (both zero -- undefined ratio, reported as 0)
- sharpe delta           = 4.127 - 3.065 = +1.063 (substantial improvement)
- trade_count delta     = -3,115 trades (-2.43%) -- the adverse-tightening
  removed ~3.1k trades from the base's mix, consistent with hypothesis
- win_rate delta         = +0.06pp (barely changed; tightening did not
  selectively kill wins more than losses)
- max_dd_pct delta       = -0.0423% vs -0.0460% (8% less drawdown)
- is_weighted_bps        = 0.0361 vs 0.0374 (-3.4% improvement)

**Vs the configured baseline `simple`** (informational, for context only --
the experiment uses base_algo as the comparison point):
- delta_pnl_pct = +528.69% (algo strongly beats simple, vs base
  vol-regime-sizer's +383.17% -- vrs-f-l2 is meaningfully better than
  its base on the simple-baseline yardstick too)
- is_weighted_bps = 0.0361 vs 0.0389 baseline (-7.11% improvement)

**What drove the improvement vs base_algo**: the adverse-drift tightening
removed ~3,115 trades from the base's mix -- specifically the subset
where sign(drift) opposes sign(order_side) inside the vol-skip region.
P&L rose by $227 while trade_count fell, so the removed trades had
*net-negative* expected value. The implied per-removed-trade
contribution is roughly +$0.073 per skipped trade -- almost exactly
symmetric to loop 1's -$0.085-per-added-trade penalty for the aligned
boost. This is strong consilience: the same direction signal that
*added* harm in loop 1 (when boosting) *removed* harm in loop 2 (when
tightening), with matching effect size.

Sharpe improved substantially (3.07 -> 4.13). The trade-count drop is
only -2.43%, but the P&L improvement is +30.12% -- meaning the removed
trades were disproportionately costly. This is exactly the adverse-
selection signature: a small subset of high-variance, low/negative-EV
trades that drag the overall distribution.

Max drawdown also improved (from -0.0460% to -0.0423%, ~8% smaller),
consistent with removing the worst trades.

**Hypothesis verdict**: STRONGLY SUPPORTED. Both predictions held:
1. Adverse-drift trades inside the base's vol-skip region are net-
   negative-EV (confirmed: removing 50% of them lifted P&L by $227).
2. Sharpe improvement outpaces P&L improvement (+34.7% sharpe vs
   +30.1% P&L), consistent with removing high-variance trades.

The order-of-magnitude prediction in the Hypothesis section (~+17%
P&L, ~125-127k trades, sharpe improvement) was even exceeded on P&L
(+30%) and matched on trade count (-2.4%). The symmetry argument
from loop 1's full-trace context proved out empirically.

**What worked / kept**: the adverse-drift tightening mechanism, the
absolute_floor (0.01) safeguard, the halflife=30 drift EWM. The aligned
branch as a no-op preserves the base's behavior on aligned trades --
this matters: re-introducing a boost there (as loop 1 did) would
re-inject the harm loop 1 measured.

**What underperformed**: nothing in this loop. Both win_rate and
max_drawdown moved in the right direction.

**Implications for next loops in this arm**:
- The adverse-drift tightening direction is *clearly* productive. The
  natural next moves are:
  1. *Tune `adverse_tighten` upward* (e.g., 0.7 or 0.9). 0.5 was a
     conservative first cut; if the adverse subset is uniformly bad,
     more aggressive tightening should help up to some point.
  2. *Add a magnitude term* -- instead of binary aligned/adverse, use
     a continuous function of |drift| / vol_baseline so larger
     adverse drifts get tightened more.
  3. *Tune `drift_halflife`* -- 30 ticks was inherited from loop 1.
     The data point we have does not pin down the optimal timescale;
     loops could try 10, 60, 120.
  4. *Re-investigate the aligned branch* -- now that we know
     direction matters, the aligned-passthrough might be improvable.
     One option: a *small* aligned boost (not 0.7 as loop 1, but
     maybe 0.1 or 0.2) might recover some upside without re-
     introducing too much harm. But this is risky given loop 1's
     decisive refutation.
  5. *Different directional signal* -- book imbalance or trade
     aggressor as the directional signal. Mid-drift worked, but
     other signals may decorrelate from the oracle direction
     differently and add independent information.
- A future loop could also combine adverse-tightening with parameter
  tuning of the base vol-skip itself (lower min_prob, higher
  sensitivity) to amplify the skip-region where the tightening
  operates.
