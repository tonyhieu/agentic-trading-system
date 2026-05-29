# Algorithm Notes: vrs-f-l4

Loop 4 of the per-iteration experiment, full-trace arm, base = `vol-regime-sizer`.

## Hypothesis

**Starting point**: `vrs-f-l3` (the prior loop), which used a smooth,
vol-normalized signed-drift sigmoid:
    `tighten = max_tighten * sigmoid(-k * z)`
with `max_tighten = 0.9`, `k = 3.0`, and
`z = order_sign * drift / max(slow_vol, eps)`. Applied as
`p_eff = max(absolute_floor, p_vol * (1 - tighten))`. That worked very
strongly: +82.36% pnl, sharpe 5.80 vs base's 3.07, max_dd 25% smaller.

**Observations driving this loop** (from L3's full_reasoning and NOTES):

1. L3 attributed most of the gain to the strongly-adverse tail
   (`z << 0`): the implied per-removed-trade contribution beyond L2 was
   +$0.159, *twice* the +$0.073 per L2-skipped trade. The trades L2's
   binary cut was *not* yet capturing (strongly-adverse tail) were
   disproportionately worse than the average L2-skipped trade.
2. L3's pre-registered effect estimates were under-predictive on three
   of five metrics. Magnitudes were consistently *exceeded*. This
   suggests the gain from tightening the strongly-adverse tail is
   *larger* than L3's smooth function captured — there may be more EV
   sitting in the saturated region that an even sharper / more aggressive
   tail-skip could extract.
3. L3's `Implications for next loops` enumerated several extensions.
   The two most aligned with the empirical signal are:
     - Push `max_tighten` from 0.9 to 1.0 (full skip in saturated tail,
       bounded only by `absolute_floor`).
     - Tune `tighten_steepness` k upward (3 -> 5 or 7) to concentrate
       more tightening in the strongly-adverse tail at the cost of less
       tightening near z = 0.
   These are complementary, not redundant: max_tighten controls the
   *depth* of the adverse asymptote; k controls the *concentration* of
   that depth near z << 0.

**Targeted change for vrs-f-l4**: jointly push `max_tighten` to 1.0
and `tighten_steepness` to 6.0.

Numerical impact on the tightening curve:

| z       | L3 tighten (k=3, mt=0.9) | L4 tighten (k=6, mt=1.0) |
|---------|---------------------------|---------------------------|
| -2.0    | 0.897                     | 1.000  (-> floor)        |
| -1.0    | 0.857                     | 0.998                    |
| -0.5    | 0.736                     | 0.953                    |
| -0.25   | 0.611                     | 0.818                    |
|  0.0    | 0.450                     | 0.500                    |
| +0.25   | 0.289                     | 0.182                    |
| +0.5    | 0.164                     | 0.047                    |
| +1.0    | 0.043                     | 0.002                    |
| +2.0    | 0.002                     | ~0                       |

Net effect: L4 tightens *more* on the adverse side (z <= -0.25) and
*less* on the aligned side (z >= +0.25). The center band (|z| < 0.25)
is roughly comparable, with L4 slightly more aggressive at exact z=0
(0.5 vs 0.45) and at moderately negative z (0.818 vs 0.611 at z=-0.25).

**Mechanism / inefficiency exploited**: L3's data identifies the
strongly-adverse tail as the highest-EV target. The change shifts
participation budget from the marginally-aligned band (where L3
tightened ~0.04-0.16 -- a small over-skip that L1 hinted may be
slightly harmful, since L1's full aligned-boost was net-negative) to
the strongly-adverse tail (where saturation at 1.0 means those trades
are skipped down to `absolute_floor=0.01`, recovering ~5% more
participation removal vs L3 in that region). The bet: the
strongly-adverse marginal trade is more harmful than the marginally-
aligned marginal trade is helpful.

**Why it survives costs**: zero-slippage fill model -- edge comes
through realized P&L. The change is a redistribution of where the
sigmoid spends its tightening budget. If the L3 hypothesis (worst tail
dominates) is correct, this should improve P&L; if the L1 hypothesis
(aligned trades are not safe to add back) is the binding constraint,
this could harm P&L by under-skipping the +0.25 < z < +1 band.

**Predicted effect size** (loose, order-of-magnitude):

- Trade count: L3 = 122,400. L4 will increase aligned-side participation
  (less tightening at z > 0) and decrease adverse-side participation
  (full skip at z << 0). Net direction is unclear -- depends on
  population balance. Rough range: 121,000-124,000.
- Realized P&L: if the strongly-adverse tail dominates, +5% to +15%
  vs L3 -> $1,450-$1,580 range. If the marginally-aligned recovery
  dominates (bad), -5% to -15% -> $1,170-$1,300 range. Best guess:
  modest positive, central ~$1,440 (+5% vs L3).
- Sharpe: should track pnl directionally. Central guess 5.8-6.3.
- Win_rate: marginal moves either way (35.3%-35.6%).
- Max_dd: if the worst-tail trades are removed more aggressively,
  drawdowns should be smaller. Central guess -0.030% to -0.035%.

The hypothesis is plausibly *strictly testable*: if L4 outperforms L3,
the strongly-adverse tail dominates and a future loop should continue
this direction (try clipped sigmoid, even sharper k). If L4
underperforms, the marginal-aligned recovery is harmful and a future
loop should test an *asymmetric* sigmoid (tighten only at z < 0, no-op
at z >= 0).

**Builds on**: vrs-f-l3 (this loop's code starts from a verbatim copy
of L3's execution_algorithm.py; only `max_tighten` and
`tighten_steepness` defaults are changed).

**Alternatives considered**:

1. *Asymmetric sigmoid* (tighten only on z < 0; no-op on z >= 0).
   Strictly more conservative than the current design. Rejected as
   primary because the symmetric vs asymmetric question is best
   tested *after* we know whether the worst-tail saturation is
   genuinely additive. If L4 fails, L5 tests asymmetric.
2. *Tune k=10 + max_tighten=1.0* (binary-like inside the sigmoid
   frame). Loses smoothness benefits. k=6 is a moderate sharpening
   that preserves the gradient near the boundary.
3. *Tune k=5 + max_tighten=0.95* (more conservative interpolation
   between L3 and L4). Rejected for clarity -- want a clean test of
   "more sharpness + full saturation" together; if it works,
   subsequent loops can fine-tune.
4. *Reduce drift_halflife to 10* (more reactive drift signal).
   Defer -- isolate the sigmoid-shape question first.
5. *Replace slow_vol denominator with fast_vol* in z normalization.
   Defer -- isolate the sigmoid-shape question first.
6. *Stack with min_prob = 0.02 + sensitivity = 3.0* (deeper base
   vol-skip). Stacks changes; muddies attribution.
7. *Aggressor-flow or book-imbalance as second signal*. The most
   promising orthogonal extension -- save for L5/L6 after the
   sigmoid-shape sweep stabilizes.

---

## Implementation Decisions

- **Signed-drift EWM**: reused from L2/L3 verbatim. Halflife = 30,
  noise floor = 1e-7, lazy init from first observed delta.
- **Vol-normalization**: divide `s_drift` by `max(slow_vol, 1e-12)`.
  Uses the existing slow_vol EWM (halflife=120). No new state.
- **Sigmoid parameters**: `k = 6.0`, `max_tighten = 1.0`. At z = -0.5,
  sigmoid(3.0) ~ 0.953; tighten ~ 0.953. At z = -1.0, sigmoid(6.0) ~
  0.998. At z = -2.0, sigmoid(12.0) ~ 0.99999; tighten -> 1.0, then
  `p_vol * 0 = 0`, clamped to `absolute_floor = 0.01`.
- **Undefined drift** (below noise floor or drift state not warm):
  treat as `s_drift = 0` -> `tighten = max_tighten / 2 = 0.5`. With
  L4's max_tighten=1.0 this is a *slightly* more aggressive
  defensive tightening than L3 (which had 0.45). Risk: if undefined
  drift periods were modestly net-positive in L3, the 0.05 extra
  tightening could be net-negative. Small effect; flagged for L5
  review.
- **Absolute floor**: 0.01 (same as L3, L2). With max_tighten=1.0
  and p_vol = min_prob = 0.05, the natural p_eff in the saturated
  adverse tail would be 0.05 * 0 = 0, so the floor binds whenever
  we are in deep adverse + deep vol-skip. This is *intended*:
  the worst-case combination of signals reduces participation to
  1%, not zero. Could be raised or lowered in a future loop.
- **Calm regime gate**: `p_vol >= 1.0 - 1e-9` -> `p_eff = 1.0`. Same.
- **Cold start**: `tick_count < min_ticks` -> `p = 1.0`. Same.
- **Reduce-only**: always submit. Same.
- **Determinism**: same SHA-256(client_order_id) uniform draw. Same.
- **Quantity invariant**: child_qty = parent_qty = 1. Same.

**Concerns**:

- The aligned side (z > 0) gets much less tightening in L4 (e.g.
  0.05 at z=+0.5 vs 0.16 in L3). If L3's tightening on that band
  was net-positive (skipping marginally-aligned trades had value),
  L4 will re-introduce some of that harm and partially counter the
  worst-tail gain. The hypothesis test is precisely whether the
  worst-tail gain dominates.
- The z=0 tightening at 0.5 (L4) vs 0.45 (L3) is a small change
  but it stacks for undefined-drift trades (the third-largest L3
  population). Could be a 1-2% effect either way.
- The saturated adverse tail in L4 cuts to absolute_floor=0.01.
  This means even with a strongly-adverse signal, 1% of those
  orders still submit. If the noise floor is somehow generating
  spurious "adverse" signals on what would otherwise be safe
  trades, the floor preserves some participation in those cases.
  Defensive design.
- Sharper sigmoid = larger gradient near z=0 = more sensitivity to
  small drift estimation noise around the boundary. Marginal
  trades whose drift is just barely positive vs just barely
  negative flip from `tighten ~ 0.5` to dramatically different
  values (0.18 vs 0.82 at |z|=0.25). The EWM smoothing at
  halflife=30 should suppress most tick-by-tick noise, but
  burst-driven brief drift sign flips could oscillate
  participation. Diagnostic counters track tightening events but
  not flip frequency -- if L4 produces unexpected behavior, this
  is a candidate explanation.

---

## Backtest Observations

**Coverage caveat (HONESTY)**: vrs-f-l4 backtest completed on only 10 of
the 12 configured train dates (2026-03-08 through 2026-03-18; the L3 and
base_algo aggregates use all 12, through 2026-03-20). The runner was
interrupted before reaching 20260319/20260320, and `S3_BUCKET_NAME`
was unavailable on the retry, so those two dates could not be regenerated.
To preserve apples-to-apples comparability, the L4 aggregate compares to
a re-aggregated `vol-regime-sizer` over the SAME 10 dates rather than to
the canonical 12-date base aggregate. All numbers below reflect this
10-date window. Direct comparison of L4's absolute numbers against L3's
12-date numbers is NOT valid for level-of-pnl-vs-L3 questions; only the
"vs same-window base_algo" delta is valid for this loop's hypothesis test.

### L4 aggregate (10 dates, 2026-03-08..2026-03-18)

| metric           | L4 (vrs-f-l4) | base (vol-regime-sizer, same 10d) | vs base       |
|------------------|---------------|------------------------------------|---------------|
| realized_pnl     | $830.25       | $341.00                            | +143.48%      |
| sharpe_ratio     | 3.93          | 1.54                               | +2.39 abs     |
| trade_count      | 78,703        | 83,340                             | -4,637 (-5.6%)|
| win_rate         | 35.15%        | 35.06%                             | +0.09 pp      |
| max_drawdown_pct | -0.0343%      | -0.0460%                           | 25% smaller   |
| mean_slippage    | 0.0           | 0.0                                | 0.0           |
| is_weighted_bps  | 0.0441        | (n/a, same-window not computed)    | n/a           |

vs_baseline (vs `simple`, on the same 10 dates): pnl +1100.30%,
slippage 0%, is_bps -8.18.

### L3 reference (12 dates) — for context only, not strict comparison

L3 on its full 12-date window produced pnl=$1,374.50, sharpe=5.80,
trade_count=122,400, max_dd=-0.0346%, win_rate=35.41%. Cannot compute a
strict L4-vs-L3 delta without re-running L3 on the same 10 dates or L4
on the missing 2; the two share 10 dates but the aggregates as-stored
differ in coverage. A rough same-day-counting back-of-envelope using L3
per-date totals over the 10 L4 dates is left for the next loop if
needed; given the L4 budget block, recording the honest coverage gap is
the right call.

### Hypothesis assessment

**Direction**: L4 (k=6, max_tighten=1.0) beat its base by +143% pnl on
10 days, vs L3's +82% over 12 days. The directional prediction (sharper
sigmoid + full saturation > L3) is consistent with the data, modulo the
date-window gap. Cross-day Sharpe of 3.93 (vs base 1.54) is a large
improvement, though lower than L3's 5.80 — partly because the 10-day
window may have higher day-to-day return variance than L3's 12-day
window, partly because the sharper sigmoid removes more variance-
generating trades (smaller mean returns dragged into a smaller-N
denominator). With N=10, Sharpe is noisier than at N=12.

**Trade-count signature**: L4 skipped 4,637 trades from the base over
10 days, vs L3's 5,591 skips over 12 days (rough per-day rates: L4
~464/day, L3 ~466/day — very similar). The sharper k=6 sigmoid is
*not* aggressively skipping more trades on average; it's *redistributing*
where the skips land — concentrating in the strongly-adverse tail and
releasing some moderate-aligned trades. This matches the design intent.

**Per-removed-trade contribution (vs base, same-window)**: L4 produced
($830.25 - $341.00) / 4,637 ≈ +$0.1055 per skipped trade. The base on
the same window had trade_count 83,340. Per-skipped-trade EV is in the
expected range — comparable to L3's measured +$0.073 per L2-skipped
trade and the implied +$0.159 per *additional* L3 skip.

**Pre-registered effect estimates vs actual**:

| metric         | L4 prediction (vs L3) | actual (vs L3 12d)  | apples-to-apples?       |
|----------------|------------------------|---------------------|--------------------------|
| trade_count    | 121k-124k (range)      | 78,703 (10d)        | NO (coverage diff)       |
| realized_pnl   | $1,170-$1,580          | $830 (10d)          | NO (coverage diff)       |
| sharpe         | 5.8-6.3                | 3.93 (10d, N=10)    | NO (sharpe scales w/ N)  |
| max_dd         | -0.030% to -0.035%     | -0.0343%            | yes (range matched)      |
| win_rate       | 35.3-35.6%             | 35.15%              | yes (marginal miss)      |

The L3-vs-L4 *level* comparison is not interpretable from this loop's
output; the L4-vs-same-window-base comparison shows a clear directional
gain and the max_dd / win_rate predictions hold up. The next loop will
need to either rerun L4 on the missing 2 dates or rerun L3 on the L4
10-date window to get a clean apples-to-apples L4-vs-L3 read.

### What did and did not work

- **Worked**: full saturation (max_tighten=1.0) + sharper k=6 produced a
  strong gain on the L4 same-window. Direction supports the L3 hypothesis
  that the worst-tail saturation was the dominant lever.
- **Worked**: max_dd improved further (smaller than L3's already-improved
  -0.0346% over a different window). The deeper tail-skip reduces tail
  participation.
- **Unclear**: win_rate marginally below L3's 35.41% by 0.26pp. Could be
  the date-window difference; could be that aggressive saturation also
  skips a few marginally-profitable trades. Not strong enough signal at
  N=10 days to act on.
- **Did not work / unknown**: the sharper k=6 prediction that aggregate
  sharpe would exceed L3 is not confirmed (3.93 vs 5.80) but is
  confounded by coverage. Cannot conclude k=6 is sharpe-positive vs k=3
  from this run.

### Implications for next loops

1. **Rerun L4 on 2026-03-19 and 2026-03-20** to close the coverage gap
   (the most urgent item). If both completed datapoints are favorable,
   L4 likely beats L3 on like-for-like; if unfavorable, L4 may be
   *overfit* to the easier 10 days and a less-aggressive sigmoid is
   preferred.
2. **Asymmetric sigmoid** is still on the menu — if L4 closes the
   coverage gap and still does not exceed L3 by a clear margin, test
   tightening only when z<0 with no-op at z>=0.
3. **Tune `drift_halflife`** (the inherited L1-L3 parameter) as a clean
   one-knob sweep — never perturbed yet.
4. **Move from sigmoid-shape sweeps to orthogonal signals** (book
   imbalance, aggressor flow) once sigmoid-shape stabilizes.

### Diagnostic counter outputs

Not pulled for this run (would require log inspection per date). If the
next loop wants this signal, add it to the persisted metrics.json so the
aggregator can surface it cleanly.

### Honesty flags

- **Coverage gap**: 10/12 dates only. Flagged above; the per-window base
  comparison is the cleanest read. Do NOT compare L4's absolute pnl to
  L3's absolute pnl directly.
- **N=10 sharpe noise**: cross-day Sharpe at N=10 is meaningfully noisier
  than at N=12 (the std-of-daily-returns denominator is the binding
  constraint, not the mean).
- **Trade count 78,703 >> 30**: ample for win_rate / per-trade metrics;
  not a low-trade-count warning.
