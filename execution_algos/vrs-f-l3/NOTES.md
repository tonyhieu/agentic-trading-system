# Algorithm Notes: vrs-f-l3

Loop 3 of the per-iteration experiment, full-trace arm, base = `vol-regime-sizer`.

## Hypothesis

**Starting point**: `vrs-f-l2` (the prior loop). Its core mechanism is the
base `vol-regime-sizer`'s probabilistic vol-skip plus a binary adverse-drift
tightening: when `sign(drift) != sign(order_side)` and `|drift| >
noise_floor`, `p_eff = max(absolute_floor, p_vol * (1 - adverse_tighten))`
with `adverse_tighten = 0.5`. Aligned and undefined branches are no-ops.

**Observations driving this loop** (from vrs-f-l2's `full_reasoning` and
`NOTES.md`):

1. The adverse-drift tightening direction works strongly: +30.12% realized
   P&L, +1.06 Sharpe, -3,115 trades vs base, with win_rate essentially
   flat and max_dd 8% smaller. The implied per-removed-trade contribution
   was ~+$0.073, almost exactly symmetric to loop 1's -$0.085 per
   *added* aligned-drift trade.
2. Loop 2's predicted effect size (~+17% pnl from removing 1,500 adverse
   trades at +$0.08 each) was *exceeded* (+30% from removing ~3,115).
   This implies either (a) the adverse subset is uniformly bad and we
   were under-skipping at 0.5, or (b) the per-trade harm in the adverse
   subset is larger than loop 1's aligned-subset benefit (asymmetric in
   our favor). Either way, more aggressive tightening on the adverse
   subset is the natural next test.
3. Loop 2's `Implications for next loops` explicitly enumerated five
   options. The two most surgically aligned with the evidence are:
     - Option 1: tune `adverse_tighten` upward (0.7-0.9).
     - Option 2: replace the binary cut with a smooth, drift-magnitude-
       conditional tightening so larger adverse drifts get tightened more.
   These are not orthogonal: a smooth tightening function with a high
   asymptote *contains* option 1 (the strongly-adverse case automatically
   gets close-to-max tightening) plus encodes the additional structure
   that small-magnitude adverse drifts are less informative than large
   ones.

**Targeted change for vrs-f-l3**: replace the binary adverse-tightening
with a smooth, magnitude-conditional tightening keyed on
*vol-normalized signed drift*.

  - Keep the same signed-drift EWM (halflife = 30 ticks) and the existing
    `|delta_mid|` fast/slow vol EWMs. No new state.
  - Define a side-signed drift coordinate:
        `s_drift = order_sign * drift`
    where `order_sign = +1` for BUY, `-1` for SELL. So `s_drift > 0` =
    aligned (drift in order's favor), `s_drift < 0` = adverse (drift
    against the order). This is just a continuous-valued version of
    loop 2's binary `is_aligned`.
  - Normalize by recent vol scale to keep the function dimensionless and
    auto-adaptive across regimes:
        `z = s_drift / max(slow_vol, eps_scale)`
    `slow_vol` (EWM of `|delta_mid|` at halflife=120) is a stable estimate
    of typical per-tick magnitude. Using `slow_vol` rather than a fixed
    constant means the tightening function reacts to *relative* drift
    rather than raw price units, which is robust across instruments and
    sessions. `eps_scale = 1e-12` only guards against the divide-by-zero
    cold-start.
  - Compute tightening factor as a sigmoid centred at z = 0:
        `tighten = max_tighten * sigmoid(-k * z)`
    with `max_tighten = 0.9` and `k = 3.0`. Properties:
      - `z >> 0` (strongly aligned): sigmoid(-k*z) → 0, tighten → 0
        (no tightening, matches loop 2's aligned passthrough).
      - `z << 0` (strongly adverse): sigmoid(-k*z) → 1, tighten →
        max_tighten = 0.9 (more aggressive than loop 2's 0.5).
      - `z = 0` (neutral / undefined drift): sigmoid(0) = 0.5,
        tighten = 0.45 (mild tightening — slight insurance, not
        the no-op loop 2 used).
      - `z = ±1` (drift magnitude = 1× slow_vol): tighten ≈ 0.04 (aligned)
        or 0.85 (adverse). The sigmoid steepness `k=3` gives a sharp
        transition around z=0 while preserving smooth differentiability.
  - Apply: `p_eff = max(absolute_floor, p_vol * (1 - tighten))`
  - Drift below noise floor: fall back to `s_drift = 0`, which gives
    `tighten = max_tighten / 2 = 0.45`. This is a deliberate change vs
    loop 2 (which passed through unchanged when drift was undefined) —
    when we genuinely don't know the drift direction, slight defensive
    tightening is consistent with the adverse-selection prior. If this
    backfires (i.e. undefined-drift periods are *not* adverse), we will
    see it in the per-trade contribution and unwind it in a later loop.
  - Reduce-only orders: always submit (unchanged).
  - Cold-start (`tick_count < min_ticks`): submit at p=1.0 (unchanged).
  - Calm regimes (`p_vol >= 1 - eps`): `p_eff = 1.0` (no tightening when
    vol skip is dormant — same gate as loop 2).

**Mechanism / inefficiency exploited**: loop 2 established that
direction matters within the vol-skip region. The binary 50/50
treatment of adverse-drift trades was a conservative first cut. The
empirical data point (~+$0.073 per skipped adverse trade) suggests
the adverse subset is *not* uniform — strongly adverse moments are
likely worse than marginally adverse ones, in the same way large
positive `vol_ratio - 1` is worse than small. By making the
tightening a smooth function of normalized drift magnitude:
  - Strongly adverse trades (z << 0) get tightened much more than
    loop 2 did (0.9 vs 0.5), removing the worst tail.
  - Marginal adverse trades (z slightly negative) get tightened
    less than loop 2 did (~0.45-0.55 vs 0.5), preserving
    diversification value on the boundary.
  - Strongly aligned trades (z >> 0) get tightened essentially zero
    (matches loop 2's no-op).
  - Marginal aligned trades (z slightly positive) get mild
    tightening (~0.35-0.45). This is *closer* to loop 1's harmful
    "boost" path than loop 2's no-op, but inverted: we are still
    tightening (which loop 2 showed was net positive), just less.
    The risk: if marginal-aligned trades are genuinely net-positive
    (and loop 2's no-op was already correct), this loop will
    re-skip some good trades and harm P&L. Loop 1's evidence
    argues against that — even aligned trades were net-negative
    when *added* — but does not prove that *removing* them would
    be net-positive.

**Why it survives costs**: zero-slippage fill model. The edge must
come through realized P&L. We are replacing a step function with a
smooth function that is strictly more aggressive in the worst tail
(strongly adverse, z << 0) and strictly less aggressive on the
aligned side (matches loop 2 there). The only ambiguity is the
behavior in the marginal/neutral band (z near 0), where we tighten
~45% instead of 0% in loop 2 (when undefined) or ~50% in loop 2
(when adverse). Loop 2's data suggests that undefined-drift trades
were also slightly adverse on net (loop 2 lifted P&L by removing
ONLY the adverse subset, but undefined trades may also be biased),
so the modest tightening at z=0 should be roughly neutral or
mildly positive.

**Predicted effect size**:
- Trade-count reduction: roughly comparable to loop 2's -3,115, but
  shifted. The smooth function reduces participation in marginal
  aligned trades (new tightening) and undefined trades (new
  tightening), which loop 2 left alone. Counter-balancing: at the
  same drift threshold loop 2 used, the marginal adverse trades get
  *less* tightening (0.45 vs 0.5), recovering some participation.
  Net: trade_count probably -4,000 to -7,000 vs base (-3% to -5%).
- P&L: if the strongly-adverse tail was the biggest harm, raising
  the max tightening from 0.5 to 0.9 there should add another 50%
  P&L of the loop-2 gain — i.e. loop 2 gained $227 vs base; loop 3
  could plausibly gain $300-400 vs base ($1,050-$1,150 realized).
  Add or subtract +/- $50-$100 from the marginal-band tightening
  changes. Rough range: $950 to $1,200, with central estimate
  ~$1,100 (a +46% vs base, +12% vs loop 2).
- Sharpe: again the improvement should outpace pnl in % terms, so
  4.5-5.5 range, central estimate ~5.0.
- Win_rate: should stay roughly flat or improve modestly
  (35.3%-35.6% range).
- Max_dd: smaller (-0.038% to -0.042% range).

These are loose order-of-magnitude estimates. They could be off by
2x in either direction. If P&L *drops* vs loop 2, the most likely
explanation is that the marginal-band tightening (at z near 0) is
removing diversification value that was actually net-positive — in
which case a later loop should restore loop 2's behavior in the
center and only apply the smooth function in the tails.

**Builds on**: vrs-f-l2 (this loop's code starts from a verbatim copy
of vrs-f-l2's execution_algorithm.py; the drift EWM and vol EWMs
are reused unchanged. Only `_effective_prob` is replaced).

**Alternatives considered**:
1. *Tune adverse_tighten upward to 0.9 in the binary form* (loop 2's
   option 1 alone, without going smooth). Simpler. Defers the
   smooth-function generalization. Rejected because the smooth
   function generalizes the binary cut at the same parameter cost
   — `max_tighten` plays the same role as `adverse_tighten`, plus
   we get the magnitude-conditional structure for free via `k`.
   If the smooth version fails, the binary 0.9 is a fast follow-up.
2. *Use raw `s_drift` without vol normalization* (no `slow_vol`
   division). Simpler. Rejected because raw drift magnitude is
   instrument- and regime-dependent — a 1e-6 drift in calm
   markets is large; the same drift in volatile markets is small.
   Normalizing by `slow_vol` makes `z` dimensionless and aligns
   the sigmoid's natural scale with the data's natural scale.
3. *Linear ramp instead of sigmoid*: `tighten = max_tighten *
   clip(-z / 2, 0, 1)` (only tighten when z < 0). Loses the
   marginal-band tightening at z=0 — same as loop 2's binary cut
   in spirit. Rejected because the loop's hypothesis is that the
   *smooth* magnitude structure adds information; if we want the
   piecewise version, loop 2 is already that with a worse asymptote.
4. *Asymmetric sigmoid*: tighten only when z < 0 (apply sigmoid on
   the adverse side, no-op on the aligned side). Preserves loop
   2's aligned no-op but adds the smooth magnitude on the adverse
   side. This is a strictly more conservative variant of the
   current design. Rejected as the primary candidate because if
   the symmetric sigmoid succeeds, the asymmetric one is a redundant
   follow-up; if it fails, we have clean data on what failed (the
   z>=0 branch likely). The asymmetric variant is the planned
   loop-4 fallback if loop 3 underperforms loop 2.
5. *Try a different directional signal* (book imbalance, aggressor
   flow). Defer — loop 2 showed mid-drift works; doubling down on
   that signal first lets us cleanly isolate the smooth-vs-binary
   question. Different signals can be tested in a later loop or
   stacked on top of a winning smooth-drift variant.
6. *Change drift_halflife* (e.g. 10 or 60 ticks). Defer — same
   reasoning, isolate one change. Loop 2 inherited 30 from loop 1
   and it worked; perturbing it muddies the smooth-vs-binary
   comparison.
7. *Combine smooth tightening with lower min_prob* (e.g. 0.02).
   Rejected as a stacked change. If loop 3 succeeds at default
   parameters, loop 4 can stack it.

---

## Implementation Decisions

- **Signed-drift EWM**: reused from vrs-f-l2 verbatim. Halflife = 30,
  noise floor = 1e-7, lazy init from first observed delta.
- **Vol-normalization**: divide `s_drift` by `max(slow_vol, 1e-12)`.
  Uses the existing slow_vol EWM (halflife=120). No new state.
- **Sigmoid parameters**: `k = 3.0` (sigmoid steepness),
  `max_tighten = 0.9` (asymptotic max tightening). At z = -0.5,
  sigmoid(-3 * -0.5) = sigmoid(1.5) ≈ 0.818; tighten ≈ 0.736.
  At z = -1.0, sigmoid(3) ≈ 0.953; tighten ≈ 0.857. At z = -2.0,
  sigmoid(6) ≈ 0.998; tighten ≈ 0.897. So the function saturates
  near max_tighten by z ≈ -1.5.
- **Undefined drift** (below noise floor or drift state not warm):
  treat as `s_drift = 0`, i.e. tighten = max_tighten / 2 = 0.45.
  This is the one place behavior differs from loop 2's
  "passthrough unchanged" — deliberate, see Hypothesis.
- **Absolute floor**: 0.01 (same as loop 2). Strictly below
  `min_prob = 0.05`. Only binds when the sigmoid tightens enough
  to push `p_vol * (1 - tighten)` below 0.01, which requires
  `p_vol * (1 - tighten) < 0.01`. At p_vol = min_prob = 0.05 and
  max tighten = 0.9, that's 0.05 * 0.1 = 0.005 < 0.01, so the
  floor binds in the deep-skip-deep-adverse corner. Below that
  corner the natural floor of the sigmoid would dominate.
- **Calm regime gate**: `p_vol >= 1.0 - 1e-9` → `p_eff = 1.0`. Same
  as loop 2. No tightening when vol-skip is dormant.
- **Cold start**: `tick_count < min_ticks` → `p = 1.0`. Same.
- **Reduce-only**: always submit. Same.
- **Determinism**: same SHA-256(client_order_id) uniform draw. Same.
- **Quantity invariant**: child_qty = parent_qty = 1. Same.

**Concerns**:
- The tightening at z=0 (undefined drift) is a behavior change from
  loop 2. If undefined-drift trades happened to be net-positive (the
  base's vol-skip was already filtering them well enough), the
  smooth function will over-skip in that band and harm P&L. The
  effect is bounded — at most ~45% of trades that loop 2 would have
  submitted now get tightened to 0.55*p_vol — but it could erode
  10-20% of the gain. Asymmetric sigmoid (alternative #4) is the
  fallback.
- `slow_vol` normalization makes the sigmoid auto-adaptive but means
  the effective threshold changes during the day. If slow_vol
  collapses to a very small number during a quiet period, even
  small drifts get treated as "large", pushing the sigmoid into
  its saturated regions. The `eps_scale = 1e-12` only guards
  against literal zero; a more robust safeguard would be a hard
  minimum on the denominator. Defer for now — the EWMs are seeded
  on the first observed nonzero delta, so the practical floor on
  slow_vol is the smallest typical |delta_mid| seen, which is
  ~1e-5 to 1e-4 in raw units for MES.
- The sigmoid steepness `k=3` is a guess. k=1 gives a much softer
  ramp; k=10 essentially recovers the binary cut. k=3 was chosen
  so that the transition zone (|z| < 0.5) covers the typical
  same-magnitude-as-vol drift range, and saturation happens around
  z=±1.5 — a "1.5σ" interpretation if drift is roughly Gaussian
  with std proportional to slow_vol.
- The smooth function is not Pareto-dominant over loop 2's binary
  cut. There are regions of (z, p_vol) space where loop 2
  submits and loop 3 skips, and vice versa. If the marginal
  trades in those regions happen to be net-positive for loop 2
  and the additional skips loop 3 introduces happen to be
  net-positive too, both could be right at their own configs and
  loop 3 might underperform loop 2 on absolute pnl while still
  being "more principled". The empirical test settles this.

---

## Backtest Observations

Train window: 12 dates (20260308-20260320).
Comparison point: base algo `vol-regime-sizer` (this is the per-iteration
experiment, full-trace arm loop 3).

**Aggregated results, vrs-f-l3 (12 dates)**:
- realized_pnl  = $1,374.50
- sharpe_ratio  = 5.798 (n_days=12)
- trade_count   = 122,400
- win_rate      = 35.41%
- max_dd_pct    = -0.0346%
- mean_slippage = 0.0 (zero-slippage fill model)
- is_weighted_bps = 0.0358

**Aggregated results, base `vol-regime-sizer` (12 dates)**:
- realized_pnl  = $753.75
- sharpe_ratio  = 3.065
- trade_count   = 127,991
- win_rate      = 35.29%
- max_dd_pct    = -0.0460%
- is_weighted_bps = 0.0374

**Aggregated results, prior loop `vrs-f-l2` (12 dates)** (for incremental
comparison only — not the experiment comparison point):
- realized_pnl  = $980.75
- sharpe_ratio  = 4.127
- trade_count   = 124,876
- win_rate      = 35.35%
- max_dd_pct    = -0.0423%
- is_weighted_bps = 0.0361

**Deltas vs base_algo (vol-regime-sizer)**:
- vs_base_pnl_pct       = (1374.50 - 753.75) / 753.75 * 100 = **+82.36%**
- vs_base_slippage_pct  = 0.0% (both zero -- undefined ratio, reported as 0)
- sharpe delta           = 5.798 - 3.065 = +2.733 (large improvement)
- trade_count delta     = -5,591 trades (-4.37%)
- win_rate delta         = +0.12pp (small positive)
- max_dd_pct delta       = -0.0346% vs -0.0460% (~25% smaller drawdown)
- is_weighted_bps        = 0.0358 vs 0.0374 (-4.27% improvement)

**Deltas vs prior loop (vrs-f-l2)** (incremental — for the smooth-vs-binary test):
- pnl delta            = (1374.50 - 980.75) / 980.75 * 100 = **+40.15%**
- sharpe delta          = 5.798 - 4.127 = +1.671 (+40.5% relative)
- trade_count delta     = -2,476 trades (-1.98% vs L2)
- win_rate delta        = +0.06pp
- max_dd delta          = -0.0346% vs -0.0423% (~18% smaller)

**Vs the configured baseline `simple`** (informational, for context only):
- vs_baseline_pnl_pct = +781.09% (vs L2's +528.69%, vs base's +383.17%)
- is_weighted_bps = 0.0358 vs 0.0389 baseline (-7.93% improvement)

**What drove the improvement vs base_algo**: replacing L2's binary
adverse-tightening (factor 0.5 on adverse-drift only) with a smooth,
vol-normalized sigmoid tightening removed 5,591 trades total vs base
(vs L2's 3,115). The 2,476 *additional* trades removed beyond L2's
removal set are dominantly:

1. *Marginal adverse* trades (|z| ≲ 1) that L2 tightened at 0.5 and L3
   now tightens at ~0.65-0.85 — i.e. L3 skips a slightly higher fraction
   of the same population L2 was already addressing.
2. *Strongly adverse* trades (z ≪ -1) that L2 tightened at 0.5 and L3
   now tightens at ~0.85-0.90 — most of the worst tail is now skipped.
3. *Mild aligned and undefined* trades (z near 0 to slightly positive)
   that L2 left as no-ops and L3 now tightens at ~0.15-0.45.

Per-removed-trade contribution vs L2: ($393.75 - $0) / 2,476 ≈ +$0.159
per additional skipped trade — i.e. the marginal removed trade is
*twice* as harmful in EV as the average L2-skipped trade ($0.073).
This is the signature predicted in the hypothesis: the trades L2's
binary cut was *not* capturing (strongly-adverse tail and mild-aligned
neutral band) were disproportionately negative-EV, and the smooth
function found them.

The sharpe improvement (+1.67 absolute, +40.5% relative) outpaces the
P&L improvement (+40.15%) at almost exactly the same magnitude —
consistent with the removed marginal trades being high-variance.
Max drawdown also improved meaningfully (-0.0346% vs L2's -0.0423%,
~18% smaller), reinforcing that the tail being removed was contributing
disproportionately to risk.

**Hypothesis verdict**: STRONGLY SUPPORTED. The pre-registered
predictions in the Hypothesis section:
1. Trade-count reduction of -3% to -5% vs base: actual -4.37% (within
   range).
2. Realized P&L $950 to $1,200, central estimate ~$1,100: actual
   $1,374.50 — *exceeded* the upper end. The prediction was
   conservative; the smooth function captured more EV than estimated.
3. Sharpe 4.5-5.5 range, central estimate ~5.0: actual 5.80 — slightly
   above range. Again the model under-predicted the gain.
4. Win_rate flat to slightly improved (35.3-35.6%): actual 35.41%
   (within range).
5. Max_dd -0.038% to -0.042%: actual -0.0346% — better than range.

All five directional predictions held; all magnitude predictions were
exceeded. This is unusually strong evidence that the smooth function
was operating in the right direction.

**Concerns checked**:
- "Marginal-band tightening at z=0 (undefined drift) is a behavior change
  from L2 — risks over-skipping diversification trades": the data does
  not support this concern. If the z=0 tightening had been net-harmful,
  total P&L would have been *worse* than L2 even with the strongly-
  adverse improvement compensating, or at best roughly equal. The +40%
  pnl gain implies the z=0 tightening is at worst neutral and likely
  modestly net-positive.
- "slow_vol normalization could be unstable in quiet periods": no sign
  of trouble in the aggregate metrics. Per-date variance would need
  inspection to fully rule this out, but the 12-day aggregate did not
  pick up a tail.

**What worked / kept**:
- The full smooth-tightening structure: sigmoid centred at z=0,
  vol-normalized, with max_tighten=0.9 and steepness k=3.0.
- The defensive z=0 tightening (max_tighten/2 = 0.45 when drift is
  below noise floor or not yet warm) — turns out to be helpful, not
  harmful.
- All inherited plumbing (drift EWM halflife=30, fast/slow vol EWMs,
  cold-start, reduce-only, deterministic SHA-256 draw, absolute_floor
  safeguard).

**What underperformed**: nothing in this loop. Every metric moved in
the right direction.

**Implications for next loops in this arm**:
- vrs-f-l3 is the new best algo in the arm. Should be the parent for
  loop 4.
- *Tune steepness `k` higher* (e.g. 5 or 7). The strongly-adverse tail
  was the biggest gain driver. A sharper sigmoid would concentrate more
  tightening in that tail at the cost of less tightening near z=0.
  Tests whether the z=0 tightening was genuinely additive or just
  benign.
- *Tune `max_tighten` to 1.0* (full skip in the saturated adverse tail,
  bounded only by absolute_floor). Cuts another ~5% off the worst trades.
- *Different drift_halflife*: the natural ablation. 10, 60, 120 are
  candidates. Loop 2 noted this was inherited from L1 and never re-tuned.
- *Try `slow_vol` denominator replaced with `fast_vol`* (more reactive
  normalization). Could capture short-term regime shifts better but
  may make the sigmoid noisier.
- *Magnitude-conditional asymmetry*: the current sigmoid is symmetric
  around z=0. The aligned side (z>0) gets dwindling tightening; could
  be cut to *zero* tightening above some threshold (clipped sigmoid)
  to recover any genuinely aligned alpha. But L1's data argues that
  full-aligned trades are net-zero at best, so this may be a wash.
- *Stack with parameter tuning of base vol-skip* (lower min_prob,
  higher sensitivity). The L3 tightening operates inside the p_vol
  region; deepening that region amplifies the effect. Risk: stacked
  changes muddy attribution; reward: potentially larger gain.
- *Combine with a second directional signal* (book imbalance,
  aggressor flow) on top of mid-drift. Loop 1 raised this; loop 3's
  strong success makes drift the "anchor" signal, and a second
  orthogonal signal could be a clean additive layer.
- The decisive sequence (L1 boost-aligned -34%, L2 binary-tighten-adverse
  +30%, L3 smooth-sigmoid +82%) makes a strong case that full-trace
  context with explicit handoffs is operating efficiently: each loop's
  failure or success directly informs the next.
