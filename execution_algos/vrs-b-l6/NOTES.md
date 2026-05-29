# Algorithm Notes: vrs-b-l6

Experiment arm: `per_iteration_experiment` / base `vol-regime-sizer` /
context mode `brief-summary` / loop 6.

## Context loaded for this loop

Brief-summary context from `loop-1.json` + `loop-2.json` + `loop-3.json`
+ `loop-4.json` + `loop-5.json` (changed / outcome / hypothesis /
brief_summary / next + metrics). Forbidden: full_reasoning (none present
in this arm), L1/L2/L3/L4/L5 NOTES.md prose, and any prior loop
implementation analysis beyond mechanical inspection of L5's
`execution_algorithm.py` for the structural copy.

What I learned from L1-L5 brief-summary:
- L1 added asymmetric drift-override gate; drift_threshold 0.05 too
  coarse, gate fired on ~1 of 111,488 orders -- UNTESTED. PnL flat at
  $42.50 (vs simple $43.25).
- L2 lowered threshold 0.05 -> 0.008; PASS vs simple (+48.55%) but
  -88.91% vs base ($64.25 vs $579.50). The asymmetric override
  re-admitted negative-EV orders.
- L3 (BREAKTHROUGH) inverted gate semantics per L2's `next`: dropped
  aligned-drift override, added `adverse_multiplier=0.5`,
  drift_threshold 0.008 -> 0.005. Result: $943.50 = +62.81% vs base,
  per-extra-skip EV ~$273.
- L4 single-knob deepening 0.5 -> 0.25 per L3's `next`. Result:
  $1086.75 = +87.53% vs base. Marginal per-skip EV $0.18/skip.
- L5 single-knob deepening 0.25 -> 0.10 per L4's `next`. Result:
  $1192.50 = +105.78% vs base. Marginal per-skip EV vs L4 = $0.21/skip
  -- NOTABLY ABOVE L4-extrapolated $0.09/skip; diminishing-returns
  slope did NOT flatten as L4 predicted. New arm leader.
- L5's `next` was explicit: continue deepening 0.10 -> 0.025
  (~2 geometric halvings). Predicted marginal EV $0.08-0.18/skip,
  incremental pnl ~$40-100, total ~$1,230-1,290. AVOID mult=0.0 still
  -- one more data point on the slope is more informative. Alternative
  if L6 confirms saturation: widen adverse subset by lowering
  drift_threshold 0.005 -> 0.003 in L7.

## Hypothesis

Per L5's `next`: deepen the breakthrough lever further from
`adverse_multiplier=0.10` to `0.025`. Everything else held constant.
This is a SINGLE config-default edit (no structural change, no
threshold change).

**Change relative to L5:** `adverse_multiplier` default 0.10 -> 0.025.
All other defaults identical (fast_halflife=20, slow_halflife=120,
sensitivity=2.0, min_prob=0.05, min_ticks=30, max_vol_ratio=5.0,
drift_halflife=40, drift_threshold=0.005). Same gate topology, same
adverse-drift definition, same SHA256 deterministic draw, same
reduce-only path.

Mechanism: with mult=0.025 instead of 0.10, the admit probability on
adverse-drift orders becomes `base_p * 0.025`. E.g.:
* base_p=0.20 (mid-elevated vol): p_final 0.020 -> 0.005
* base_p=0.05 (floor in extreme vol): p_final 0.005 -> 0.00125
The admit set remains a STRICT SUBSET of L5's (and L4's, L3's, base's,
transitively), because mult only decreases. Trade_count predicted
strictly <= L5's 101,747.

Why mult=0.025 (~2 halvings from 0.10) rather than 0.05 (1 halving):
* L5's marginal per-skip EV was $0.21/skip on 505 new skips -- highly
  productive, nowhere near the slope-flattening L4 expected.
* L5 explicitly suggested 0.025 to "better test whether the slope
  finally flattens" -- a more aggressive probe gives sharper signal
  about where the lever's productive region ends.
* The strict-subset architecture caps downside: worst case is L6
  regresses toward L5's $1192.50 by re-skipping admits that turned
  out to be marginal-positive-EV; cannot go below where L4 sits
  ($1086.75) on the relevant admit subset because the L6 skip set
  contains L5's skip set which contains L4's.

Expected behavior (per L5's `next` text):
* Per-skip EV trajectory so far:
  - L3 extras vs base: ~$0.27/skip ($364 / 1,332)
  - L4 marginal vs L3: ~$0.18/skip ($143 / 788)
  - L5 marginal vs L4: ~$0.21/skip ($106 / 505) -- non-monotonic;
    slope did not flatten as L4 expected.
* Mult tightening so far moved p_final to (geometric):
  - L3: base_p * 0.5
  - L4: base_p * 0.25
  - L5: base_p * 0.10
  - L6: base_p * 0.025
  -- L6 collapses the admit zone on adverse orders ~4x tighter than L5.
* New skip-zone for L6: u in `(0.025*base_p, 0.10*base_p)` -- this is
  7.5% of base_p wide (vs L5's 15% wide region between 0.10*base_p and
  0.25*base_p, which yielded 505 marginal skips).
* Rough estimate: if marginal skip population is uniform across u,
  L6 might catch ~(7.5/15)*505 ~= 250 marginal skips. Per-skip EV
  could be anywhere from $0.05/skip (slope finally bends to half) to
  $0.21/skip (slope holds as L4->L5).
* Best case (slope holds): ~250 new skips * $0.20/skip = ~$50
  incremental pnl -> total ~$1,240; matches L5-extrapolated upper
  bound $1,230-1,290.
* Failure case: per-skip EV inverts -- adverse admits at
  u in `(0.025*base_p, 0.10*base_p)` are actually neutral or
  positive-EV, so newly skipping them costs pnl. Pnl regresses
  toward L5's $1192.50 or below; strict-subset architecture caps
  the downside.

The structural guarantee from L3/L4/L5 holds: even in the failure
case, L6 stays a strict subset of L5's admit set; worst case is "some
loss of L5's edge", not catastrophic regression. This is another
calibration probe of the lever L3 confirmed works and L4/L5 confirmed
compounds.

## Implementation Decisions

* COPIED structural code from vrs-b-l5 (mechanical copy per
  brief-summary boundary; I inspected L5's `execution_algorithm.py`
  only enough to mirror class structure, EWM state, drift signal,
  multiplier application, and SHA256 draw -- no analysis of L5's
  logic semantics beyond what L5's `summary_out` already explains).
* Single edit: `adverse_multiplier` default 0.10 -> 0.025 in both
  `VrsBL6Config` and `get_execution_algorithm`.
* `min_prob=0.05` floor still applies to `base_p` only; `p_final`
  may dip to 0.00125 on adverse-drift floor cases (vs 0.005 in L5).
  Intentional and continuous with L3/L4/L5's design choice.
* All diagnostic counters preserved (`_skipped_base`,
  `_skipped_adverse_extra`).
* Reduce-only path unchanged -- always submit.
* Class names VrsBL5* -> VrsBL6*; docstrings updated to reference
  L5 lineage and the deepening intent.

## Backtest Observations

11-date apples-to-apples train aggregate (Sun-Fri 2026-03-08..2026-03-20,
20260319 OOM-killed and dropped from BOTH sides by the runner):

| metric             | vrs-b-l6   | vrs-b-l5   | vrs-b-l4   | base       | simple    |
| ------------------ | ---------- | ---------- | ---------- | ---------- | --------- |
| realized_pnl ($)   | 1220.75    | 1192.50    | 1086.75    |   579.50   |   43.25   |
| sharpe_ratio       | 5.051      | 4.807      | 4.427      |   3.065(*) |   0.42    |
| trade_count        | 101,505    | 101,747    | 102,252    | 104,372    | 111,489   |
| max_drawdown_pct   | -0.0390    | -0.0394    | -0.0393    |  -0.046    |  varies   |
| win_rate           | 0.3534     | 0.3533     | 0.3531     |   0.353    |   0.355   |
| mean_slippage      | 0.0        | 0.0        | 0.0        | 0.0        | 0.0       |
| vs simple pnl_pct  | +2722.54%  | +2657.23%  | +2412.72%  | +1239.88%  | -         |
| vs base pnl_pct    | +110.66%   | +105.78%   | +87.53%    | -          | -91.85%   |

(*) Base sharpe shown is the 12-date value from
`execution_algos/vol-regime-sizer/results/backtest-results.json`; the
11-date subset value used here is the same order of magnitude.

Key deltas:
- **vs L5**: pnl +$28.25 (+2.37%), sharpe +0.244, trade_count -242
  (-0.24%). L6's admit set is a strict subset of L5's (mult only ever
  tightens; cannot loosen).
- **Marginal per-skip EV vs L5**: $28.25 / 242 marginal extra skips =
  **$0.117/skip**. This is BELOW L5's marginal $0.21/skip and BELOW L4's
  marginal $0.18/skip — **the diminishing-returns slope finally bent**
  on this halving (`0.10 → 0.025`, two geometric halvings tested in
  one step). Still positive but the per-skip EV roughly halved.
- **Per-date check**: L6 beat L5 on 7 / 11 dates, tied on 2, lost on 2.
  The two losses are 20260309 (-$8.50) and 20260310 (-$25.25) —
  mid-week dates with strong base pnl ($653 and $413 respectively); the
  newly skipped adverse-drift admits on those dates were apparently
  net-positive-EV, exactly the failure mode L5's `next` flagged for
  the new tail at u ∈ (0.025·base_p, 0.10·base_p). Net of 11 dates
  the lever still paid (+$28.25 total).
- Sharpe 5.05 — new arm best (vs L5 4.81, L4 4.43, L3 3.83, base ~3.06).
  Max drawdown a hair tighter (-3.90% vs L5 -3.94%).
- Slippage 0.0/0.0 (no regression).

Hypothesis verdict: **PARTIALLY CONFIRMED** at the upper-band lower
edge of L5's prediction.
- L5 predicted L6 pnl in the band $1,230–1,290 with marginal EV
  $0.08–0.18/skip. Observed: pnl $1,220.75 (just below L5's lower
  bound by ~$10), marginal EV $0.117/skip (mid-band).
- L5 predicted "slope holds" (best case, ~$0.20/skip) OR "slope
  finally bends" (lower case, ~$0.05–0.10/skip). Observed at $0.117/skip
  is closer to the "slope finally bends" case — L4's predicted
  diminishing returns finally showed up after holding flat through
  L4→L5.
- Strict-subset architecture worked exactly as designed: even though
  per-skip EV halved, total pnl still rose — newly-skipped marginal
  admits at u ∈ (0.025·base_p, 0.10·base_p) were on average
  slightly worse than admits at u ∈ (0.10·base_p, 0.25·base_p),
  giving the small positive marginal.

Verdict: **PASS** vs configured baseline (+2722.54% vs simple, gate
+5.0%), **PASS** vs base_algo (+110.66% vs base $579.50), and **new
arm leader** (improvement-on-improvement vs L5 by +$28.25 pnl /
+0.244 sharpe). Same-direction architecture as L3/L4/L5 still works;
the lever is approaching saturation but has not yet inverted.

Highest-leverage next change for L7:
- The L5 `next` alternative path is now activated: **widen the adverse
  subset** by lowering `drift_threshold` 0.005 → 0.003 in L7, holding
  `adverse_multiplier=0.025` (the L6 value). Reasoning: per-mult-halving
  marginal EV has now bent (0.21 → 0.117 $/skip) — pushing the same
  knob again (0.025 → ~0.006) risks crossing into negative marginal
  EV. A drift_threshold widening brings *new* borderline-drift orders
  into the multiplier zone, testing a different subset of admits than
  the saturated mult-deepening dimension. Predicted L7 pnl: $1,230–
  1,310 if borderline-drift admits have per-skip EV comparable to
  current adverse-drift admits; $1,170–1,220 if the borderline
  subset is materially weaker.

Per OBJECTIVE §8 honesty: this is a clear PASS by both the formal
gate (vs simple) AND the arm-level objective (vs base). Trade counts
are healthy (>100k). Per_iteration_experiment loop — NOT snapshotted
(per arm protocol; experiments/per_iteration_experiment/...). Data
note: 20260319 (690 MB DBN partition) OOM-killed inside docker
subprocess on signal 9; runner correctly dropped it from both sides,
so the comparison is fair over the 11 remaining dates.
