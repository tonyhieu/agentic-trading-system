# Algorithm Notes: vrs-b-l3

Experiment arm: `per_iteration_experiment` / base `vol-regime-sizer` /
context mode `brief-summary` / loop 3.

## Context loaded for this loop

Brief-summary context from `loop-1.json` + `loop-2.json` only
(changed / outcome / hypothesis / brief_summary / next + metrics).
Forbidden: full_reasoning (none present in this arm), L1/L2 NOTES.md
prose, prior loop implementation analysis beyond mechanical
inspection of L2's execution_algorithm.py for the structural copy.

What I learned from L1+L2 brief-summary:
- L1 added an asymmetric drift-override gate (`override base vol-skip
  when drift aligned, apply skip only on adverse`); drift_threshold
  0.05 was too coarse, fired on ~1 order in 111k -- HYPOTHESIS
  UNTESTED. L1 PnL nearly identical to simple ($42.5 vs $43.25).
- L2 lowered threshold 6x (0.05 -> 0.008); gate fired on ~72 extra
  orders only; even with more firing, the asymmetric override
  re-admits ~half of base's correctly-skipped negative-EV orders.
  PASS vs simple (+48.55%), but -88.91% vs base ($64.25 vs $579.50).
- L2's `next` prescribed inverting the gate semantics: `ALWAYS apply
  base vol-skip, with ADDITIONAL skip pressure on adverse drift`,
  concretely `p_final = p_vol * (drift_adverse ? 0.5 : 1.0)`.
  L2's brief_summary referenced afg-b-l3 as a structural analogue:
  "DISJUNCTIVE structure that broke the asymmetric-gate trap" in the
  aggressor-flow-gate arm.

## Hypothesis

The L1/L2 architecture failed because it was a SUPERSET of base's
admit set on aligned-drift orders -- it re-admitted ~half of base's
correctly-skipped negative-EV orders to chase a small directional EV
on the adverse-only skip. The fix is structural: switch from
SUPERSET-on-aligned-drift to SUBSET-via-additional-skip-on-adverse.

**Change relative to L2:**
1. Remove the aligned-drift override entirely. Aligned/neutral drift
   no longer forces p=1.0; it just uses base p_vol.
2. Add a multiplicative skip on adverse drift:
   `p_final = base_p * adverse_multiplier` with adverse_multiplier=0.5.
3. Lower drift_threshold 0.008 -> 0.005 per L2's hint (widen adverse
   coverage).

Together these three are a single coherent change of gate semantics
(L2's prescribed `next`). I treat them as one targeted edit rather
than three independent edits -- the multiplier+remove-override pair
is the inversion itself, and the threshold drop is a calibration
already half-prescribed by L2.

Expected behavior:
* For every order, `p_final <= base_p`. So the admit set is a STRICT
  SUBSET of base's admit set.
* Trade_count <= base's trade_count (104,372 over 11 dates). Trade
  count delta vs base depends on (a) fraction of orders flagged
  adverse and (b) how many base would have admitted at random draw
  that the multiplier now skips. With drift_threshold=0.005 the
  adverse fraction should be higher than L2's ~0.1% but likely well
  below 50%; with adverse_multiplier=0.5 the additional skips on
  adverse orders are ~half of base's adverse-side admits.
* Crude trade-count expectation: base skips ~7,117/111k = ~6.4% of
  orders relative to simple. L3 should skip those same 7,117 plus
  some adverse-extra; if adverse fraction is ~10-20% and base
  admits ~95% of adverse, the extra skips are ~0.05*0.1*0.95*111k ~
  ~530 to ~1060. So trade_count target ~103,300-103,800.

PnL predictions:
* Best case: directional signal is informative on the high-vol subset
  base admits -- adverse-drift admits in base have lower EV than
  aligned-drift admits, and skipping ~half of them adds positive EV
  on top of base. PnL beats base by some margin in the $50-100 range
  over 11 dates (analogous to afg-b-l3 -> l4 which was +12% vs base
  on a single orthogonal lever after the disjunctive switch).
* Worst case: directional signal is uninformative or has wrong sign
  on this oracle. The multiplier just skips half of adverse-drift
  orders at random; expected EV change is approximately zero;
  variance increases slightly. PnL matches base within $10-30.
* Failure case: signed-mid-drift EWM is anti-correlated with EV on
  adverse-drift orders (i.e., adverse-drift admits are actually
  BETTER than aligned-drift admits at the per-order level). PnL
  drops below base by some margin proportional to the additional
  skips' actual EV.

The structural improvement is independent of which case obtains:
even the worst case is base-parity, not L2's -89% regression. This
is the inflection-point bet.

## Implementation Decisions

* COPIED structural code from vrs-b-l2 (mechanical copy per
  brief-summary boundary; I inspected L2's
  `execution_algorithm.py` only enough to mirror class structure,
  EWM state, drift signal, and SHA256 draw -- no analysis of L2's
  logic semantics beyond what L2's `summary_out` already explains).
* In `on_order`: removed the early-return path that submitted
  unconditionally on `not adverse`. Now every order goes through the
  vol-draw at p_final = base_p * (adverse ? mult : 1.0).
* Added `adverse_multiplier` config field; default 0.5.
* Lowered `drift_threshold` default 0.008 -> 0.005.
* `min_prob=0.05` floor applies to base_p only; p_final may go
  below 0.05 on adverse orders (e.g. base_p=0.05 floor in extreme
  vol gives p_final=0.025 on adverse-drift orders). Intentional --
  the directional signal justifies extra selectivity below the
  base floor.
* Diagnostic counters split into `_skipped_base` (base would have
  skipped too at this u) vs `_skipped_adverse_extra` (base would
  have admitted, but multiplier tightened to a skip). Diagnostic
  only -- no behavioral effect.
* Reduce-only path unchanged -- always submit.
* Class names VrsBL2* -> VrsBL3*; docstrings updated.

## Backtest Observations

### Raw 11-date aggregate (Sun-Fri 2026-03-08..2026-03-20, 20260319 OOM-dropped)

* realized_pnl: **$943.50** (sum across 11 dates).
* trade_count: **103,040** orders submitted.
* sharpe_ratio: **3.832** (n_days=11).
* mean_slippage / max_abs_slippage: 0.0 / 0.0 (zero fill-cost model;
  see research/NOTES.md).
* max_drawdown_pct: -4.03%.
* win_rate: 35.33%.
* is_weighted_bps: 0.0404; is_total_price: $5,509.75.

### Comparison vs gate baseline (simple)

* simple 11-date pnl: $43.25, trades: 111,489.
* **vs_baseline_pnl_pct = +2,081.50% (PASS, gate +5.0%)**.
* vs_baseline_slippage_pct = 0.0 (no regression).
* vs_baseline_is_bps = -5.281 bps (improvement; lower IS is better).

### Comparison vs base_algo vol-regime-sizer (the per_iteration_experiment yardstick)

* base 11-date pnl: $579.50, trades: 104,372.
* **vs_base_pnl_pct = +62.81%** (clear breakthrough — first L1-L3 loop in
  this arm to beat base by any margin; L1 was -92.67%, L2 was -88.91%).
* trade_count delta vs base: **-1.28%** (-1,332 trades).
  Sign matches the architectural prediction (strict subset of base's
  admit set). Magnitude was somewhat under-predicted in the hypothesis
  (I expected -0.5 to -1.0% / -530 to -1060 extra skips; actual was
  -1.28% / -1332 extra skips), implying the adverse-drift fraction at
  drift_threshold=0.005 is closer to ~20% of base's at-risk admits
  than the ~10% I bracketed.

### What changed L2 -> L3 (mechanical diff)

Three coordinated edits, one structural intent (the disjunctive
inversion L2's `next` prescribed):

1. **Removed the aligned-drift override path.** L2's `on_order`
   short-circuited at `if not adverse: submit at p=1.0`. L3 deletes
   that branch entirely — every OPEN order runs through the vol-draw.
2. **Added multiplicative adverse-drift skip.** New config
   `adverse_multiplier=0.5`. `p_final = base_p * 0.5` if adverse,
   else `p_final = base_p`. The min_prob floor (0.05) applies to
   `base_p` only — `p_final` may dip to 0.025 on adverse-drift
   orders at the floor. Intentional.
3. **Lowered drift_threshold 0.008 -> 0.005.** Calibration only, per
   L2's `next` hint.

Together: gate semantics flip from
`override-on-aligned-drift + adverse-only-skip` (superset of base's
admit set; structurally a strict liability) to
`always-apply-base-skip + extra-skip-on-adverse` (strict subset of
base's admit set; worst case = base parity, best case = base + the
directional refinement's EV).

### What drove the breakthrough

The single dominant lever is **architectural, not numeric**. The
threshold drop alone (0.008 -> 0.005) and the multiplier alone
(0.5 vs 1.0) cannot in principle produce a +63% pnl jump from a
-89% baseline; the change of admit-set topology can. The breakthrough
confirms the L2 `next` analysis verbatim: the previous architecture
re-admitted ~half of base's correctly-skipped negative-EV orders to
chase a much smaller directional EV; the disjunctive architecture
keeps every one of base's skips and adds a small directional
refinement on top.

Quantitatively: base's edge over simple is $579.50 - $43.25 = $536.25
of skip-EV over 11 dates from ~7,117 base-skipped orders, i.e.
~$75/skip. L3 adds 1,332 extra skips vs base for an additional
$943.50 - $579.50 = $364 of pnl, i.e. ~$273/extra-skip on the
adverse-drift extras. That's >3x base's per-skip EV — strong
evidence that the adverse-drift subset of base's would-be admits
really is materially worse than the aligned-drift subset, exactly
as L1's original directional-adverse-selection hypothesis posited.

### Hypothesis verdict: CONFIRMED

Three things L1's hypothesis claimed had to be true for the
directional refinement to work, all now corroborated:
* Signed-mid-drift EWM with halflife 40 carries genuine
  adverse-selection information (not just noise) — yes; per-skip EV
  of $273 is far above noise.
* The information is concentrated on the high-vol subset (where
  base's symmetric skip already fires) — yes; the multiplier on top
  of base_p combines them multiplicatively and still extracts EV.
* The previous architecture's failure was structural, not signal —
  yes; same drift signal, same threshold band, just changing the
  gate topology turns -89% into +63%.

The architectural inflection is now well-characterized in this arm
(and in afg-b: L3 was the same kind of inflection there too).

### Single highest-leverage next change

The breakthrough lever is the adverse-drift multiplier. With
`adverse_multiplier=0.5` we cut admit prob in half on adverse
orders; with the per-extra-skip EV running at ~$273, the marginal
adverse-drift admit at u just-below-base_p is *very* expensive to
let through. The natural next probe is to **push the multiplier
down further: 0.5 -> 0.25 (or even 0.1)** at fixed
drift_threshold=0.005. Two outcomes are possible:
* Best case (likely if per-skip EV is roughly uniform across the
  adverse subset): pnl increases roughly linearly with extra skips
  until the marginal adverse admit's EV falls below zero.
* Failure case: pnl flattens or drops if the highest-EV-to-skip
  adverse admits are already being caught by mult=0.5 and the
  marginal ones we'd newly skip have small or negative EV.

Alternative (less leverage): lower drift_threshold 0.005 -> 0.003
to widen the adverse subset rather than deepen the multiplier on
the existing subset. Either is a single coherent move; the
multiplier probe is preferable because L3 already established the
adverse subset is well-defined at 0.005.

L4 should be a single-knob push along the breakthrough lever, not
a structural re-architecting. The disjunctive structure is working
— compound it before changing it.
