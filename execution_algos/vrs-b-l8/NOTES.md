# Algorithm Notes: vrs-b-l8

Experiment arm: `per_iteration_experiment` / base `vol-regime-sizer` /
context mode `brief-summary` / loop 8. **FINAL LOOP of this 8-loop arm.**

## Context loaded for this loop

Brief-summary context from `loop-1.json` + `loop-2.json` + `loop-3.json`
+ `loop-4.json` + `loop-5.json` + `loop-6.json` + `loop-7.json` (changed /
outcome / hypothesis / brief_summary / next + metrics). Forbidden:
full_reasoning (none present in this arm), L1/L2/L3/L4/L5/L6/L7 NOTES.md
prose, and any prior loop implementation analysis beyond mechanical
inspection of L7's `execution_algorithm.py` for the structural copy.

What I learned from L1-L7 brief-summary:
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
  diminishing-returns slope finally bent. The mult lever was
  approaching saturation.
- L7 (FRESH-DIMENSION BREAKTHROUGH) per L6's `next`: WIDEN the adverse
  subset by lowering drift_threshold 0.005 -> 0.003, holding
  adverse_multiplier=0.025. Result: $1403.25 = +142.15% vs base,
  +14.95% vs L6 -- the LARGEST single-step pnl gain in the lineage
  since L3 -> L4 (+$143.25). Sharpe +1.01 vs L6 -- largest sharpe
  jump in the lineage. Per-borderline-skip EV vs L6 = $0.0746/skip
  (mid-weak-subset band $0.04-0.08 per L6's prediction); borderline
  subset ~10x LARGER than L6's mult-deepening marginal subset
  (2,446 vs 242 skips), so total contribution exceeded L6's best-case
  band ($1,230-1,310) by ~$93.
- L7's `next` explicitly prescribed for L8: extend the SAME fresh
  threshold dimension by lowering drift_threshold 0.003 -> 0.002 (a
  33% reduction, same proportional step as 0.005 -> 0.003 was relative
  to L6's 0.005). The threshold dimension is fresh (only one data
  point), productive (largest single-step in the lineage), and one
  more probe gives a sharper signal on where the dimension's
  productive region ends. Avoid further mult deepening (saturated at
  L6), vol-conditional multipliers (adds complexity, no prior signal),
  changing vol EWM halflives (orthogonal lever, save for a future arm).

## Hypothesis

Per L7's `next`: extend the threshold dimension by lowering
`drift_threshold` 0.003 -> 0.002. Everything else held constant
(`adverse_multiplier=0.025` at L6/L7 value, all other defaults
identical). This is a SINGLE config-default edit (no structural
change, no multiplier change).

**Change relative to L7:** `drift_threshold` default 0.003 -> 0.002.
All other defaults identical (fast_halflife=20, slow_halflife=120,
sensitivity=2.0, min_prob=0.05, min_ticks=30, max_vol_ratio=5.0,
drift_halflife=40, adverse_multiplier=0.025). Same gate topology,
same multiplier value, same SHA256 deterministic draw, same
reduce-only path.

Mechanism: with `drift_threshold=0.002` instead of `0.003`:
* The adverse-drift set is DEFINED by `|drift_ewm| > drift_threshold`
  AND opposing the order side. Lowering the threshold ENLARGES the
  adverse set: orders with `drift_ewm` magnitude in `[0.002, 0.003]`
  opposing the order side that were previously treated as non-adverse
  (`p_final = base_p`, no extra skip pressure) are now treated as
  adverse (`p_final = base_p * 0.025`).
* For BUY orders this catches new admits where `drift_ewm` in
  `[-0.003, -0.002]` (mild negative drift opposing a BUY); for SELL
  orders new admits where `drift_ewm` in `[+0.002, +0.003]` (mild
  positive drift opposing a SELL).
* The L8 admit set is a STRICT SUBSET of L7's admit set on
  orders with `|drift_ewm|` in `[0.002, 0.003]` (newly adverse, now
  multiplier-skipped). Outside that band the admit decision is
  unchanged.

Why drift_threshold 0.002 (33% reduction) rather than 0.0015 or 0.0025:
* L7 explicitly prescribed 0.003 -> 0.002 in the `next` text. A
  0.003 -> 0.0025 step would be too narrow to give a sharp signal on
  whether the further-borderline subset carries EV (small newly-adverse
  set risks high noise per Sharpe); 0.003 -> 0.001 would push deep
  into the noisier drift regime where the drift signal may be dominated
  by tick noise rather than directional information.
* Keeping the same proportional step as L7's prescription (0.005 ->
  0.003 was a 40% reduction; 0.003 -> 0.002 is a 33% reduction --
  comparable in magnitude).

Expected behavior (per L7's `next` text):
* Per-skip EV trajectory:
  - L3 extras vs base (mult 0.5, thresh 0.005): ~$0.27/skip
  - L4 marginal vs L3 (mult 0.25, thresh 0.005): ~$0.18/skip
  - L5 marginal vs L4 (mult 0.10, thresh 0.005): ~$0.21/skip
  - L6 marginal vs L5 (mult 0.025, thresh 0.005): ~$0.117/skip
  - L7 marginal vs L6 (mult 0.025, thresh 0.003): ~$0.0746/skip
* This is the SECOND data point on the THRESHOLD axis. L7 was the
  first. The drift signal at smaller magnitudes is likely weaker
  per unit measurement, suggesting per-skip EV may drop further.
* Predicted L8 marginal subset size: ~1,000-1,400 new skips at
  |drift_ewm| in [0.002, 0.003] (somewhat less than L7's 2,446
  because the [0.002, 0.003] band is narrower than [0.003, 0.005]
  and drift_ewm distribution is approximately log-spaced).
* Best case: per-skip EV holds at ~$0.07/skip -> incremental pnl
  ~$80-100 -> total ~$1,480-1,520.
* Weaker-subset case: per-skip EV drops to ~$0.04-0.05/skip ->
  incremental pnl ~$50-70 -> total ~$1,450-1,490.
* Failure case: per-skip EV inverts -- borderline-drift admits at
  |drift_ewm| in [0.002, 0.003] are actually neutral-or-positive-EV,
  so newly skipping them costs pnl. Pnl regresses toward L7's $1,403
  or modestly below. Strict-subset architecture caps the downside
  ON THE NEW BORDERLINE SUBSET ONLY (orders with |drift_ewm| <= 0.002
  or > 0.003 behave identically to L7).

The structural guarantee from L3-L7 holds on the unchanged subsets;
L8 is a probe of the second data point on the SAME productive lever
(threshold dimension) while holding the saturated lever (multiplier
depth) at L6/L7's best value.

## Implementation Decisions

* COPIED structural code from vrs-b-l7 (mechanical copy per
  brief-summary boundary; I inspected L7's `execution_algorithm.py`
  only enough to mirror class structure, EWM state, drift signal,
  multiplier application, and SHA256 draw -- no analysis of L7's
  logic semantics beyond what L7's `summary_out` already explains).
* Single edit: `drift_threshold` default 0.003 -> 0.002 in both
  `VrsBL8Config` and `get_execution_algorithm`. `adverse_multiplier`
  unchanged at 0.025 (L6/L7 value).
* `min_prob=0.05` floor still applies to `base_p` only; `p_final`
  may dip to 0.00125 on adverse-drift floor cases (same as L7).
  Intentional and continuous with L3/L4/L5/L6/L7 design.
* All diagnostic counters preserved (`_skipped_base`,
  `_skipped_adverse_extra`).
* Reduce-only path unchanged -- always submit.
* Class names VrsBL7* -> VrsBL8*; docstrings updated to reference
  L7 lineage and the further-widening intent.

## Backtest Observations

**Status: PASS, NEW ARM LEADER AND FINAL LEADER ACROSS ALL METRICS.**

### Aggregate metrics (11 dates, matched-date basis)

| Metric              | vrs-b-l8 | vrs-b-l7 (prior) | base_algo (vrs) | simple |
|---|---:|---:|---:|---:|
| realized_pnl ($)    | **1766.50** | 1403.25 | 579.50 | 43.25 |
| sharpe_ratio        | **8.179**   | 6.064   | ~3.06  | ~0.60 |
| trade_count         | **96,095**  | 99,059  | 104,372 | 111,489 |
| max_drawdown_pct    | **-3.15%**  | -3.61%  | -4.60% | n/a |
| win_rate            | 35.54%      | 35.42%  | 35.29% | 35.6% |
| mean_slippage       | 0.0         | 0.0     | 0.0    | 0.0 |

* vs simple baseline pnl: **+3984.39%** (well above formal +5.0% gate).
* vs base_algo (vol-regime-sizer) pnl on matched 11 dates: **+204.83%**
  ($1766.50 vs $579.50; the formal "vs_base" measure for this arm).
* Slippage 0.0/0.0 (no regression; zero fill-cost model -- see
  `research/NOTES.md`).

### What L8 changed vs L7 (mechanical diff)

I mechanically diffed `execution_algos/vrs-b-l7/execution_algorithm.py`
vs `execution_algos/vrs-b-l8/execution_algorithm.py`. The ONLY behavioral
difference is:

* `drift_threshold` default: **0.003 -> 0.002** in both `VrsBL8Config`
  and `get_execution_algorithm()`.

Every other parameter is identical (fast_halflife=20, slow_halflife=120,
sensitivity=2.0, min_prob=0.05, min_ticks=30, max_vol_ratio=5.0,
drift_halflife=40, adverse_multiplier=0.025). Class names renamed
VrsBL7* -> VrsBL8*; docstrings updated. Gate topology, EWM math, SHA256
draw, reduce-only path, and diagnostic counters are byte-identical
behaviorally. This is a true single-knob, single-step probe.

### What drove the +$363.25 (+25.89%) jump from L7 -> L8

L8 admitted 2,964 FEWER orders than L7 (99,059 -> 96,095). Those skips
came from the newly-widened adverse-drift band: orders with
|drift_ewm| in [0.002, 0.003] that oppose the order side. By design
L8's admit set is a STRICT SUBSET of L7's on that band -- outside it
(|drift_ewm| <= 0.002 or > 0.003) the behavior is byte-identical.

**Marginal per-borderline-skip EV vs L7: $363.25 / 2,964 = $0.1225/skip.**

This is ABOVE L7's marginal-vs-L6 EV of $0.0746/skip and ABOVE
L6's marginal-vs-L5 of $0.117/skip -- meaning the [0.002, 0.003] band
carries directional information AT LEAST as good as the deeper-magnitude
bands the gate already exploits. L7's `next` predicted per-skip EV
would likely drop further toward $0.04-0.05/skip as the drift signal
weakens at smaller magnitudes; that prediction was WRONG -- per-skip
EV actually rose. The threshold dimension is NOT yet saturated at 0.002.

Per-date breakdown vs L7 (8 wins / 3 losses):

| date     | L8 pnl  | L7 pnl  | delta    |
|---|---:|---:|---:|
| 20260308 | 130.75  | 122.25  | +8.50    |
| 20260309 | 763.25  | 750.25  | +13.00   |
| 20260310 | 485.75  | 517.00  | -31.25   |
| 20260311 | 335.50  | 339.25  | -3.75    |
| 20260312 | 66.00   | 28.25   | +37.75   |
| 20260313 | -185.00 | -270.75 | +85.75   |
| 20260315 | -4.25   | -17.00  | +12.75   |
| 20260316 | -283.25 | -356.75 | +73.50   |
| 20260317 | -119.50 | -163.25 | +43.75   |
| 20260318 | 228.50  | 189.25  | +39.25   |
| 20260320 | 348.75  | 264.75  | +84.00   |
| TOTAL    | 1766.50 | 1403.25 | **+363.25** |

The +$363.25 total is dominated by mid-week volatile dates (20260313
+$85.75, 20260320 +$84.00, 20260316 +$73.50, 20260317 +$43.75,
20260318 +$39.25, 20260312 +$37.75). The lone material loss was
20260310 -$31.25; other losses small (-$3.75 on 20260311). Sharpe
jumped +2.12 (6.06 -> 8.18) -- the LARGEST sharpe jump in the entire
lineage (vs L6 -> L7 +1.01, L5 -> L6 +0.24, L4 -> L5 +0.38, L3 -> L4
+0.60). Max drawdown improved to -3.15% (vs L7 -3.61%, base -4.60%).

### Hypothesis verdict: CONFIRMED (with a positive surprise)

Hypothesis (per L7's `next`): extend the fresh-and-productive threshold
dimension by lowering drift_threshold 0.003 -> 0.002; expected per-skip
EV ~$0.04-0.07/skip (weaker-subset case), expected incremental pnl
$50-100, expected total $1,450-1,520 (best case).

Actual: incremental pnl **+$363.25** -- well ABOVE the best-case
prediction band ($1,520) by ~$246; per-skip EV $0.1225, ~64% above the
upper end of the predicted weak-subset band ($0.08). The drift signal
at |drift_ewm| in [0.002, 0.003] turned out to carry MORE directional
information per skip than at [0.003, 0.005], not less. The
strict-subset architecture from L3 continued to hold, and the
single-knob discipline kept the cause attribution unambiguous.

**Architecture-level verdict for the arm:** L3's "always apply base
vol-skip + multiplicative skip on adverse-drift" gate, with adverse
defined by signed-drift EWM opposing order side, remained the
dominant lever through L4-L8. The two productive sub-dimensions were
(a) multiplier depth (L3-L6: 0.5 -> 0.25 -> 0.10 -> 0.025; saturated
at L6) and (b) threshold width (L7-L8: 0.005 -> 0.003 -> 0.002; still
not saturated at L8). All five PASS loops (L3-L8) used single-knob
single-step probes off the prior loop.

### 8-loop trajectory

L1: pnl=$42.50  (vs_base -92.67%, sharpe 0.17, 111,488 trades) -- asymmetric drift override w/ wrong-direction gate
L2: pnl=$64.25  (vs_base -88.91%, sharpe 0.26, 111,416 trades) -- lowered threshold; still wrong-direction
L3: pnl=$943.50 (vs_base +62.81%, sharpe 3.83, 103,040 trades) -- BREAKTHROUGH; inverted gate semantics, mult=0.5
L4: pnl=$1086.75 (vs_base +87.53%, sharpe 4.43, 102,252 trades) -- mult 0.5 -> 0.25
L5: pnl=$1192.50 (vs_base +105.78%, sharpe 4.81, 101,747 trades) -- mult 0.25 -> 0.10
L6: pnl=$1220.75 (vs_base +110.66%, sharpe 5.05, 101,505 trades) -- mult 0.10 -> 0.025 (saturation)
L7: pnl=$1403.25 (vs_base +142.15%, sharpe 6.06, 99,059 trades)  -- threshold 0.005 -> 0.003 (fresh dimension)
**L8: pnl=$1766.50 (vs_base +204.83%, sharpe 8.18, 96,095 trades) -- threshold 0.003 -> 0.002 (NEW LEADER)**

PnL leader: L8 ($1766.50). Sharpe leader: L8 (8.18). Lowest trade
count: L8 (96,095, -13.8% vs L1's 111,488 / -7.9% vs base's 104,372).
L8 is the FINAL LEADER on every primary metric -- arm objective fully
achieved.

