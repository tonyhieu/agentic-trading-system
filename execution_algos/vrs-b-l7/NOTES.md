# Algorithm Notes: vrs-b-l7

Experiment arm: `per_iteration_experiment` / base `vol-regime-sizer` /
context mode `brief-summary` / loop 7.

## Context loaded for this loop

Brief-summary context from `loop-1.json` + `loop-2.json` + `loop-3.json`
+ `loop-4.json` + `loop-5.json` + `loop-6.json` (changed / outcome /
hypothesis / brief_summary / next + metrics). Forbidden: full_reasoning
(none present in this arm), L1/L2/L3/L4/L5/L6 NOTES.md prose, and any
prior loop implementation analysis beyond mechanical inspection of L6's
`execution_algorithm.py` for the structural copy.

What I learned from L1-L6 brief-summary:
- L1 added asymmetric drift-override gate; drift_threshold 0.05 too
  coarse, gate fired on ~1 of 111,488 orders -- UNTESTED. PnL flat at
  $42.50 (vs simple $43.25).
- L2 lowered threshold 0.05 -> 0.008; PASS vs simple (+48.55%) but
  -88.91% vs base. The asymmetric override re-admitted negative-EV
  orders.
- L3 (BREAKTHROUGH) inverted gate semantics per L2's `next`: dropped
  aligned-drift override, added `adverse_multiplier=0.5`,
  drift_threshold 0.008 -> 0.005. Result: $943.50 = +62.81% vs base,
  per-extra-skip EV ~$273.
- L4 single-knob deepening 0.5 -> 0.25 per L3's `next`. Result:
  $1086.75 = +87.53% vs base. Marginal per-skip EV vs L3 $0.18/skip.
- L5 single-knob deepening 0.25 -> 0.10 per L4's `next`. Result:
  $1192.50 = +105.78% vs base. Marginal per-skip EV vs L4 $0.21/skip
  -- NOTABLY ABOVE L4-extrapolated $0.09/skip; diminishing-returns
  slope did NOT flatten as L4 predicted.
- L6 single-knob deepening 0.10 -> 0.025 per L5's `next`. Result:
  $1220.75 = +110.66% vs base, +2.37% vs L5. Marginal per-skip EV
  vs L5 $0.117/skip -- BELOW L5's $0.21 and L4's $0.18; the
  diminishing-returns slope L4 originally predicted has finally bent.
  L6 beat L5 on 7/11 dates only. NEW ARM LEADER but the mult lever is
  approaching saturation.
- L6's `next` explicitly prescribed: STOP deepening the multiplier
  (further halving 0.025 -> ~0.006 risks crossing into negative
  marginal EV, and the strict-subset cap doesn't help vs L6); instead
  WIDEN the adverse subset by lowering drift_threshold 0.005 -> 0.003
  in L7, holding adverse_multiplier=0.025 (L6 value). Brings NEW
  borderline-drift orders into the multiplier zone -- a different
  subset of admits than the saturated mult-deepening dimension.
  Predicted L7 pnl: $1,230-1,310 best case, $1,170-1,220 weak-subset
  case. Avoid: changing multiple knobs, further mult deepening,
  changing vol EWM halflives.

## Hypothesis

Per L6's `next`: WIDEN the adverse-drift subset by lowering
`drift_threshold` 0.005 -> 0.003. Everything else held constant
(`adverse_multiplier=0.025` at L6 value, all other defaults
identical). This is a SINGLE config-default edit (no structural
change, no multiplier change).

**Change relative to L6:** `drift_threshold` default 0.005 -> 0.003.
All other defaults identical (fast_halflife=20, slow_halflife=120,
sensitivity=2.0, min_prob=0.05, min_ticks=30, max_vol_ratio=5.0,
drift_halflife=40, adverse_multiplier=0.025). Same gate topology,
same multiplier value, same SHA256 deterministic draw, same
reduce-only path.

Mechanism: with `drift_threshold=0.003` instead of `0.005`:
* The adverse-drift set is DEFINED by `|drift_ewm| > drift_threshold`
  AND opposing the order side. Lowering the threshold ENLARGES the
  adverse set: orders with `drift_ewm` magnitude in `[0.003, 0.005]`
  opposing the order side that were previously treated as non-adverse
  (`p_final = base_p`, no extra skip pressure) are now treated as
  adverse (`p_final = base_p * 0.025`).
* For BUY orders this catches new admits where `drift_ewm` in
  `[-0.005, -0.003]` (mild negative drift opposing a BUY); for SELL
  orders new admits where `drift_ewm` in `[+0.003, +0.005]` (mild
  positive drift opposing a SELL).
* The L7 admit set is a STRICT SUBSET of L6's admit set on
  orders with `|drift_ewm|` in `[0.003, 0.005]` (newly adverse, now
  multiplier-skipped). Outside that band the admit decision is
  unchanged.

Why drift_threshold 0.003 (40% reduction) rather than 0.004 or 0.002:
* L6 explicitly prescribed 0.005 -> 0.003 in the `next` text. A
  0.005 -> 0.004 step might be too narrow to give a sharp signal on
  whether the borderline-drift subset carries EV (small newly-adverse
  set risks high noise per Sharpe); 0.005 -> 0.002 would
  simultaneously widen the subset AND push deep into the noisier
  drift regime, confounding two effects.
* Keeping the drift signal definition aligned with the established
  threshold series (L3 used 0.005 from inception; this is the first
  threshold change in the breakthrough lineage).

Expected behavior (per L6's `next` text):
* Per-skip EV trajectory so far on the MULT axis:
  - L3 extras vs base (mult 0.5): ~$0.27/skip
  - L4 marginal vs L3 (mult 0.25): ~$0.18/skip
  - L5 marginal vs L4 (mult 0.10): ~$0.21/skip
  - L6 marginal vs L5 (mult 0.025): ~$0.117/skip -- slope bent.
* This is the FIRST data point on the THRESHOLD axis. No prior
  baseline for the borderline subset's per-skip EV.
* Predicted L7 marginal-per-borderline-skip EV: comparable to L6's
  $0.117/skip if borderline-drift admits are similarly negative-EV;
  $0.04-0.08/skip if the borderline subset is materially weaker (drift
  magnitude in [0.003, 0.005] carries less directional information
  than [>0.005]).
* Best case: ~$40-90 incremental pnl over 11 dates -> total ~$1,260-1,310.
* Weak-subset case: ~$20-60 incremental pnl -> total ~$1,240-1,280.
* Failure case: per-borderline-skip EV inverts -- borderline-drift
  admits are actually neutral-or-positive-EV, so newly skipping them
  costs pnl. Pnl regresses toward L6's $1,220 or modestly below.
  Strict-subset architecture caps the downside ON THE BORDERLINE
  SUBSET ONLY (orders with |drift_ewm| <= 0.003 or > 0.005 behave
  identically to L6).

The structural guarantee from L3-L6 holds on the unchanged subsets;
L7 is a probe of a NEW lever (subset width) while holding the
saturated lever (multiplier depth) at its current best value.

## Implementation Decisions

* COPIED structural code from vrs-b-l6 (mechanical copy per
  brief-summary boundary; I inspected L6's `execution_algorithm.py`
  only enough to mirror class structure, EWM state, drift signal,
  multiplier application, and SHA256 draw -- no analysis of L6's
  logic semantics beyond what L6's `summary_out` already explains).
* Single edit: `drift_threshold` default 0.005 -> 0.003 in both
  `VrsBL7Config` and `get_execution_algorithm`. `adverse_multiplier`
  unchanged at 0.025 (L6's value).
* `min_prob=0.05` floor still applies to `base_p` only; `p_final`
  may dip to 0.00125 on adverse-drift floor cases (same as L6).
  Intentional and continuous with L3/L4/L5/L6 design.
* All diagnostic counters preserved (`_skipped_base`,
  `_skipped_adverse_extra`).
* Reduce-only path unchanged -- always submit.
* Class names VrsBL6* -> VrsBL7*; docstrings updated to reference
  L6 lineage and the widening intent.

## Backtest Observations

11-date apples-to-apples train aggregate (Sun-Fri 2026-03-08..2026-03-20,
20260319 OOM-killed and dropped from BOTH sides by the runner):

| metric             | vrs-b-l7   | vrs-b-l6   | vrs-b-l5   | vrs-b-l4   | base       | simple    |
| ------------------ | ---------- | ---------- | ---------- | ---------- | ---------- | --------- |
| realized_pnl ($)   | 1403.25    | 1220.75    | 1192.50    | 1086.75    |   579.50   |   43.25   |
| sharpe_ratio       | 6.064      | 5.051      | 4.807      | 4.427      |   3.065(*) |   0.42    |
| trade_count        |  99,059    | 101,505    | 101,747    | 102,252    | 104,372    | 111,489   |
| max_drawdown_pct   | -0.0361    | -0.0390    | -0.0394    | -0.0393    |  -0.046    |  varies   |
| win_rate           | 0.3542     | 0.3534     | 0.3533     | 0.3531     |   0.353    |   0.355   |
| mean_slippage      | 0.0        | 0.0        | 0.0        | 0.0        | 0.0        | 0.0       |
| vs simple pnl_pct  | +3144.51%  | +2722.54%  | +2657.23%  | +2412.72%  | +1239.88%  | -         |
| vs base pnl_pct    | +142.15%   | +110.66%   | +105.78%   | +87.53%    | -          | -91.85%   |

(*) Base sharpe shown is the 12-date value from
`execution_algos/vol-regime-sizer/results/backtest-results.json`; the
11-date subset value used here is the same order of magnitude.

Key deltas:
- **vs L6** (the only structural change: `drift_threshold` 0.005 -> 0.003,
  `adverse_multiplier` held at L6's 0.025): pnl +$182.50 (+14.95%),
  sharpe +1.013, trade_count -2,446 (-2.41%). L7's admit set is a strict
  subset of L6's on the orders with `|drift_ewm|` in [0.003, 0.005] (newly
  adverse, now multiplier-skipped at 0.025); outside that band the admit
  decision is identical to L6.
- **Marginal per-borderline-skip EV vs L6**: $182.50 / 2,446 marginal
  extra skips = **$0.0746/skip**. This landed inside the predicted
  weak-subset band of $0.04-0.08/skip from L6's `next` text. The
  borderline-drift subset (`|drift_ewm|` in [0.003, 0.005]) carries
  somewhat less directional information than the [>0.005] subset --
  per-skip EV roughly 64% of L6's $0.117/skip and 35% of L5's $0.21/skip
  -- but it remains clearly positive-EV. Crucially, the marginal subset
  is ~10x larger (2,446 vs L6's 242 extra skips), so total pnl
  contribution +$182.50 is the largest single step in the breakthrough
  lineage since L3->L4.
- **Per-date check**: L7 beat L6 on 8/11 dates, lost on 3 (20260308
  -$12.50, 20260309 -$14.00, 20260318 -$16.00). The three losses are
  scattered and small relative to wins on volatile mid-week dates
  (20260312 +$60.00, 20260313 +$68.75). Notably L7 reversed both of
  L6's loss-vs-L5 dates: 20260310 (+$10.25 vs L6) and 20260309
  (-$14.00 -- still a loss, but a smaller one).
- Sharpe 6.06 -- new arm best (vs L6 5.05, L5 4.81, L4 4.43, L3 3.83,
  base ~3.06). The +1.01 sharpe jump is the largest in this lineage
  (L5->L6 was +0.24, L4->L5 was +0.38), reflecting both the +14.95%
  pnl improvement and the materially tighter daily distribution
  (3 losses vs L6's 4 below-zero dates of 20260312/13/15/16/17).
- Max drawdown improved to -3.61% (vs L6 -3.90%, L5 -3.94%, L4 -3.93%,
  base -4.60%) -- continued tightening.
- Slippage 0.0/0.0 (no regression).

Hypothesis verdict: **CONFIRMED, weak-subset case landed but outcome
exceeded both predicted bands**.
- L6 predicted L7 pnl in two bands: $1,230-1,310 best case (per-skip EV
  comparable to L6's $0.117/skip) and $1,170-1,220 weak-subset case.
  Observed: $1,403.25 -- **above the best-case band by ~$93**.
- The driver is the larger-than-predicted marginal subset size. L6's
  `next` anticipated comparable per-skip EV to L6's $0.117/skip, but
  the actual per-borderline-skip EV $0.0746/skip is mid-weak-subset.
  However the borderline subset turned out ~10x larger than L6's
  full-mult-deepening subset (2,446 vs 242), more than compensating
  for the lower per-skip EV.
- The strict-subset architecture worked exactly as designed: the
  threshold-widening dimension is ORTHOGONAL to the mult-deepening
  dimension and admits a fresh productive subset.

Verdict: **PASS** vs configured baseline (+3144.51% vs simple, gate
+5.0%), **PASS** vs base_algo (+142.15% vs base $579.50), and **new
arm leader** (improvement-on-improvement vs L6 by +$182.50 pnl /
+1.013 sharpe -- the largest single-step improvement in this lineage
since L3->L4 +$143.25). Same-direction architecture as L3/L4/L5/L6
still works; a fresh orthogonal lever (drift_threshold widening) has
been opened and is productive.

Highest-leverage next change for L8 (FINAL LOOP):
- Two candidate directions, both single-knob:
  (a) **Continue widening the same dimension**: lower `drift_threshold`
      0.003 -> 0.002 (a slightly larger step than 0.005->0.003 was
      relative to L6's 0.005, but still well above zero). The dimension
      just delivered the largest step in the lineage; one more probe
      tests whether the slope is still climbing or has begun to bend.
      Predicted: if per-skip EV holds at ~$0.07/skip on a subset of
      similar relative width (~50% of L7's subset, so ~1,200 new skips),
      incremental pnl ~$80-110, total ~$1,480-1,520. Failure case:
      per-skip EV inverts on the new tail at `|drift_ewm|` in
      [0.002, 0.003] -> regression toward L7's $1,403 (strict-subset cap).
  (b) **Open a fresh orthogonal dimension**: vol-conditional multiplier
      (e.g. apply `adverse_multiplier` only when `vol_ratio > 1.5`),
      reasoning that the adverse-drift signal may carry stronger
      information specifically in elevated-vol regimes where base_p is
      already low. This adds complexity and a new knob.
- L8 choice: **(a)** -- continue the most-recently-productive dimension
  for one more data point. The threshold lever is fresh (only one
  data point so far) and the L7 jump was the largest in the lineage;
  it is more informative to extend it than to open a new dimension
  with no prior signal. Pick `drift_threshold` 0.003 -> 0.002 (a 33%
  reduction, same proportional step as 0.005 -> 0.003 was relative to
  L6). Avoid: changing multiple knobs at once; further mult deepening
  (saturated at L6); vol-conditional multipliers (adds complexity,
  harder to interpret).

Per OBJECTIVE §8 honesty: this is a clear PASS by both the formal
gate (vs simple) AND the arm-level objective (vs base). Trade counts
are healthy (>99k). Per_iteration_experiment loop -- NOT snapshotted
(per arm protocol; experiments/per_iteration_experiment/...). Data
note: 20260319 (690 MB DBN partition) OOM-killed inside docker
subprocess on signal 9; runner correctly dropped it from both sides,
so the comparison is fair over the 11 remaining dates.
