# Algorithm Notes: vrs-b-l2

Experiment arm: `per_iteration_experiment` / base `vol-regime-sizer` /
context mode `brief-summary` / loop 2.

## Context loaded for this loop

Brief-summary context from `loop-1.json` only (changed / outcome /
hypothesis / next + metrics). Forbidden: full_reasoning, L1's NOTES.md,
L1 implementation analysis beyond mechanical inspection.

L1 told me:
- L1 added a signed-mid-increment drift EWM (halflife=40 ticks,
  threshold=0.05) to gate the base vol-regime probabilistic skip:
  skip fires only if vol elevated AND drift adverse to order side.
- Outcome: drift gate fired on essentially 1 of 111,488 orders.
  Threshold + halflife combination is too coarse for an EWM of signed
  mid-increments (most ticks are 0 or ±0.25 — EWM rarely accumulates
  past 0.05). The directional-adverse-selection hypothesis was
  effectively UNTESTED.
- L1's `next` recommended three options: (a) drop threshold ~10x to
  0.005-0.01, (b) switch to signed trade flow / quote imbalance,
  (c) invert gate semantics.

## Hypothesis

The structural form L1 introduced (signed-drift gate on top of the
base vol-skip) cannot be evaluated until the gate fires on a
meaningful fraction of orders. The cleanest, smallest-surface-area
test of the original directional-adverse-selection hypothesis is to
recalibrate the threshold without changing anything else.

**Change relative to L1:** lower `drift_threshold` from 0.05 to
**0.008** (~6x smaller, mid-range of L1's recommended 0.005-0.01
band). Everything else — drift_halflife=40, fast/slow vol halflives,
sensitivity, min_prob, gate semantics (skip iff vol elevated AND
drift adverse; otherwise force p=1.0) — is held identical to L1.

Expected fraction firing: on MES with 0.25-tick increments and an
EWM halflife of 40 ticks, a sustained one-directional sequence of
~3-4 ticks net move builds drift_ewm magnitude past 0.008 quickly.
Crudely, if signed increments are roughly random walk with ~50% zero
and ~50% one-tick ±0.25, the long-run EWM std-dev on signed
increments is on the order of 0.04-0.08 / sqrt(halflife) ~ 0.01-0.02.
So |drift_ewm| > 0.008 should be reached a meaningful fraction of
the time — order of 30-60% of ticks — making the gate decision
non-trivial on most orders.

Predictions:
* Drift gate fires on materially more than 1 order — target order of
  ~30-60% of OPEN orders gated.
* Of those, ~half should be adverse (BUY with drift<0, SELL with
  drift>0); the other half aligned and forced through.
* PnL vs base_algo (`vol-regime-sizer`): three outcomes plausible.
  (i) Beats base — adverse-selection skips concentrate on the
     directionally-bad subset, and base's symmetric skip was throwing
     away aligned-drift orders that fill well. This is the
     hypothesis's success case.
  (ii) Matches base — directional signal is uncorrelated with the
     vol-magnitude signal at the per-order level; sample of skipped
     orders is statistically the same as base's.
  (iii) Worse than base — directional drift in signed mid-increments
     does not predict adverse fills on this oracle; base's symmetric
     skip is doing useful work that the directional override
     defeats.
* Trade count: should be > base (some "adverse-vol" orders the base
  would skip now slip through because drift happens to align).

Risk: even at 0.008 the EWM may saturate at ~|0.02-0.05| on busy
sessions (e.g. 20260316-20260320 which dominate the per-date
trade-count distribution from L1 backtest) — those sessions would
still see most orders gated as adverse, washing out the directional
signal. Acceptable for one loop: we get an empirical answer either
way.

## Implementation Decisions

* Single config change vs vrs-b-l1: `drift_threshold` default
  changed from 0.05 to 0.008. All other defaults preserved.
* Structural code is COPIED from vrs-b-l1 (mechanical copy per
  brief-summary boundary). I did not analyze L1's code beyond
  reading the config field, factory signature, and gate logic
  shape needed to make a config-level edit.
* Class names renamed (VrsBL1* -> VrsBL2*) and docstrings updated
  to reflect the new threshold and the hypothesis under test.
* Reduce-only path unchanged.
* Deterministic SHA-256 draw unchanged — reproducibility preserved.

## Backtest Observations

11-date apples-to-apples train aggregate (Sun-Fri 2026-03-08..2026-03-20,
with 20260319 OOM-killed and dropped from both sides by the runner).

Raw numbers (vrs-b-l2):
* realized_pnl: $64.25
* mean_slippage: 0.0
* sharpe_ratio: 0.2564
* max_drawdown_pct: -0.0529
* win_rate: 0.3501
* trade_count: 111,416

Comparators on the same 11 dates:
* simple_execution_strategy: pnl=$43.25, trades=111,489
* vol-regime-sizer (base_algo): pnl=$579.50, trades=104,372
* vrs-b-l1: pnl=$42.50, trades=111,488

Deltas:
* vs simple: pnl +48.55% (gate +5.0% PASS, +3.0-+5.0 CLOSE) -> PASS
* vs base_algo (vol-regime-sizer): pnl -88.91%, trade_count +6.75%
* vs vrs-b-l1: pnl +51.18%, trade_count -72 (effectively identical)

Status: PASS against the configured baseline (simple); FAIL vs base_algo
(vol-regime-sizer). Per OBJECTIVE §8 honesty: the pass_gate.baseline is
"simple", so the formal status is PASS, but the arm-level objective for
the per_iteration_experiment is whether modifications improve on the
base_algo, and on that axis the L2 result is materially worse than the
base ($64.25 vs $579.50 = -89%). Flagging the "PASS vs simple, FAIL vs
base" pattern explicitly to avoid optimistic-baseline interpretation.

What L2 changed mechanically vs L1: a single config-default edit,
drift_threshold 0.05 -> 0.008 (~6x smaller). All other mechanics
(fast/slow halflives, sensitivity, min_prob, drift_halflife=40, gate
semantics, reduce-only path, SHA256 deterministic draw) were preserved
verbatim — a structural copy from L1.

Did the gate fire meaningfully more? Trade_count gives only an indirect
read: L1 was 111,488 trades, L2 is 111,416 (delta -72 trades out of
~111k). The vol-skip path (which is the only way the algorithm produces
fewer trades than simple — the always-submit override at p=1.0 doesn't
reduce trades) fired on exactly 72 more orders in L2 than in L1.
Compared to the base vol-regime-sizer (104,372 trades, ~7,117 skips
vs simple's 111,489), L2 still applies the vol-skip on only ~1% of the
orders the base would skip. So even at threshold 0.008, the
adverse-drift conjunction is still too restrictive to recover the
base's loss-cutting behavior — most of the "vol elevated" orders the
base skips have aligned drift in L2 and get pushed through at p=1.0.

Crude estimate of drift_ewm magnitude (predicted in Hypothesis 0.01-0.02
typical, threshold 0.008): the realized fraction of orders where drift
was adverse was clearly far below 50%. Most orders in this oracle's
hostile windows (negative-pnl dates 20260312, 20260313, 20260315,
20260316, 20260317) are not in a strongly adverse-drift moment by this
signal; they fire through the override.

Hypothesis verdict: the directional-adverse-selection hypothesis is
STILL effectively untested at the per-order level — but now for a
different reason than L1. L1 didn't test it because the gate fired
~0 times. L2 fires the gate marginally more (72 extra skips), but the
override-on-aligned-drift path lets virtually all the base's "skip"
orders through. The asymmetric design (override + restrictive
adverse-only skip) structurally cannot recover the base's PnL: the
base skips ~7k orders / 11 days that on net contributed positive PnL
(base $579 vs simple $43 over 11 dates implies the base's symmetric
vol-skips are correctly removing ~$536 of bad fills). L2's override
of the vol-skip on the ~50% of high-vol orders with aligned drift
re-admits roughly half of that $536 of bad fills — consistent with
observed L2 ~$64 vs base $579.

PASS vs simple confirms the residual skip path does some useful work,
but the architecture (override + selective skip) is dominated by the
base (symmetric skip) on this oracle/strategy combination. The
directional override is a strict liability against the base, not an
improvement.

Highest-leverage next change: invert the gate semantics. Instead of
"override the base vol-skip when drift is aligned, otherwise apply
vol-skip", make the gate "ALWAYS apply the base vol-skip, but
ADDITIONALLY skip even more aggressively when drift is adverse".
Concretely: p_final = p_vol * (drift_adverse ? 0.5 : 1.0). This is a
strict subset of the base's admitted-orders set (we always skip what
the base skips, plus a little more on adverse-drift) — analogous to
the afg-b-l3 DISJUNCTIVE structure that broke the asymmetric-gate
trap in the aggressor-flow-gate arm. Alternative: drop the override
entirely and revert to base's symmetric skip + a small additional
adverse-drift multiplier; that's the conservative version of the
above. Either way, the directional information should ADD to the
base's skip, not subtract from it.
