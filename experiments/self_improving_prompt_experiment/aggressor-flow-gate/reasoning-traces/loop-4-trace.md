# Loop 4 Reasoning Trace

## Hypothesis generation method used

prompt-l0.md — the seed 4-step single-pass linear method (read base → identify ONE weakness → propose ONE concrete modification → state expected direction). Back in force because loop-2 and loop-3's proposed methods were reverted by the keep/discard gate; the running best is loop-1, whose `prompt_out` chain rolls back to prompt-l0 as the active prompt.

## How the hypothesis emerged from the method

Step 1: I read `execution_algos/aggressor-flow-gate/execution_algorithm.py` and its NOTES.md. The base mechanism is a symmetric absolute-volume gate: maintain a rolling 10s deque of `(ts, signed_size)` and skip the next open order when `net_flow <= -2.0` (BUY-side) or `net_flow >= 2.0` (SELL-side). The base NOTES picks `flow_threshold = 2.0` "by intuition" with no calibration against the empirical net-flow distribution and no conditioning on regime volume.

Step 2: I picked ONE weakness: an absolute contract threshold treats `net_flow=2` identically in a quiet window (4 total contracts → 50% imbalance, a strong signal) and in a busy window (80 total contracts → 2.5% imbalance, sampling noise). The base under-fires in quiet regimes and over-fires in busy regimes.

Step 3: ONE concrete modification — replace the gate INPUT from raw signed-volume sum to a volume-normalized signed-flow fraction `net_flow / total_volume`, keeping a single symmetric threshold `frac_threshold = 0.25`. Everything else (window length, reduce-only bypass, anti-cascade `_position_flat`) is preserved verbatim. This is categorically a "different gate input" per the seed prompt — orthogonal to loop-1's kernel change (EWMA weighting), loop-2's side-asymmetry change, and loop-3's confirmation-rule change.

Step 4: Predicted direction — realized_pnl rises (+3% to +12% range due to uncalibrated threshold), trade_count direction ambiguous, slippage unchanged at 0.0, sharpe and win_rate marginally up if regime-adapted gate picks better entries.

The hypothesis emerged cleanly from the method's prescribed 4 steps. I did NOT improvise additions (no EDA on the empirical flow_fraction distribution, no calibration step) — per the experimental boundary, I am supposed to follow the method as written so the critic sees its gaps.

## Where the method helped

The "ONE weakness, ONE modification" discipline kept me from spreading my changes across multiple axes. Specifically it prevented me from simultaneously (a) normalizing the input AND (b) making the threshold side-asymmetric — which would have confounded loop-2's already-refuted asymmetry hypothesis with the new input-type change. The single-axis constraint guarantees attribution: if loop-4 fails (or succeeds), the result is clean evidence about contracts→fraction reframing, not a four-way crossbreed.

The "categorize against prior loops" framing (also in the seed prompt) was useful when justifying why this is a novel direction: l1 changed kernel, l2 changed side-conditionality, l3 changed decision-rule shape; l4 changes input type itself. This made loop-4 a non-overlapping basis vector in the design space.

## Where the method felt limiting or unnecessary

The seed prompt's Step 3 explicitly says "propose ONE concrete modification … you expect would address that weakness." Nothing in the method asks me to **measure** anything about the empirical distribution before committing to a parameter value. So I picked `frac_threshold = 0.25` from proportional reasoning (`2 / 8 = 0.25` if a "typical" window sees 8 total contracts) and shipped. The method gave me no mechanism to validate that 8 contracts is even close to the median 10s total volume in MES intraday — it could be 4, 20, or 80, and the gate behavior is wildly different in each case.

The seed prompt also has no built-in pre-implementation discrimination step. With a freshly chosen threshold, two scenarios produce indistinguishable forward-looking arguments:
1. `frac_threshold = 0.25` is well-calibrated → gate fires similarly often to base but in regime-adapted ways → P&L rises.
2. `frac_threshold = 0.25` is miscalibrated low (because empirical `|flow_fraction|` clusters near 1.0 due to within-window sign autocorrelation) → gate fires far more often than base → recovers no profitable trades and skips many that base let through → P&L drops.

Both are equally consistent with the NOTES.md weakness analysis. The method asks me to predict direction (Step 4) but provides no test for which scenario applies. I picked scenario 1 and was wrong.

## What a different method might have produced

A "measure-then-commit" method: after Step 2 (identify weakness), insert a mandatory EDA step: load 1–2 train dates, compute `flow_fraction` at every order arrival, and verify that the proposed threshold meaningfully partitions the empirical distribution (e.g. require the threshold lies between the 30th and 70th percentile of |flow_fraction| at order-arrival times, otherwise you're effectively gating "almost always" or "almost never"). Such a method would have either (a) caught that 0.25 is mis-calibrated and forced me to retune to e.g. 0.6 before shipping, or (b) confirmed 0.25 is reasonable and let me ship with stronger justification.

A different alternative: a "mirror hypothesis" method (similar to what loop-3's reverted critique proposed) — pair the primary hypothesis with a steelmanned mirror that uses the same evidence to predict the opposite outcome, then identify a discriminating observable. Here the mirror is concrete: "in MES intraday, 10s windows are dominated by within-window sign autocorrelation, so |flow_fraction| typically ≈ 1.0 and a 0.25 threshold means 'gate fires whenever there is any directional imbalance at all', which destroys good trades." That mirror is testable in ~5 minutes of EDA and predicts the actual outcome.

## What the backtest showed

Raw numbers vs base (`aggressor-flow-gate`):
- realized_pnl: 780.25 vs 1255.50 — **−37.85%** (catastrophic regression).
- trade_count: 120,148 vs 107,198 — **+12.08%** (the gate fires LESS often, letting through ~13k more orders than base).
- sharpe_ratio: 3.548 vs 5.594 — **−36.6%** (the recovered trades have higher variance / worse mean).
- max_drawdown_pct: −4.07% vs −3.32% — **22.5% worse**.
- win_rate: 0.3523 vs 0.3549 — −0.25pp (essentially flat).
- mean_slippage: 0.0 vs 0.0 — unchanged (as predicted; this is a gate-only change).
- is_weighted_bps: 0.0490 vs 0.0472 — marginally worse implementation shortfall.

The trade_count delta is the key diagnostic. The gate fires LESS often than base (the +12,950 trade count means more orders passed through). This means `frac_threshold = 0.25` is empirically HIGHER than the typical |flow_fraction| at order arrival — exactly the OPPOSITE of what I worried about in NOTES.md ("0.25 may be too low"). My armchair guess that 8 contracts is a typical 10s total volume was very wrong; the real total volume must be much smaller (so a `net_flow=2` represents an even higher fraction than 0.25), OR the within-window distribution makes |flow_fraction| at gate-evaluation time much smaller than I imagined.

This is consistent with the **predicted falsifier in NOTES.md**: "if trade_count is within ±2% of base AND realized_pnl is flat or negative, the 0.25 threshold is miscalibrated." Trade_count is +12% (not within ±2%), but realized_pnl IS negative — so the qualitative falsifier triggers: my parameter choice is wrong, and I cannot distinguish whether the underlying contracts→fraction mechanism is right or wrong without re-running at a calibrated threshold. The method gave me no path to that calibration.

What surprised me: the magnitude. I expected the worst case to be flat-to-modestly-negative; I got −37.85%, which is the largest single-loop regression of any sip-afg loop so far (l1: kept positive, l2: small negative, l3: −43%, l4: −37.85%). The fraction-reframing did not even produce a "small" miss — the parameter was so far off that the gate effectively stopped functioning as intended.

What confirmed expectations: mean_slippage stayed at 0.0 (gate-only change preserves fill mechanics).

## Where I felt uncertain

- The threshold choice (0.25). NOTES.md explicitly flags this as armchair. I justified it via proportional reasoning rather than measurement. The method's single-pass linear structure provided no opportunity to measure before committing.
- The interpretation of the `total_volume == 0` warm-up branch. I chose to submit unconditionally (matching base's "no signal, no skip"), but this means in genuinely quiet windows (where the signal would be MOST informative under the fraction framing because even tiny imbalances are meaningful), the gate is disabled. This is a logical inconsistency — the very regime my hypothesis claimed to improve is the regime where the warm-up branch kicks in. I noticed this writing this trace, not at implementation time.
- NO_AGGRESSOR handling: I excluded these from both numerator and denominator, but I'm not sure if NAUTILUS emits them in MES MBP1 replay — could not verify without EDA. If they're never emitted, the choice is moot; if they are emitted in non-trivial numbers, my denominator is biased.
- Whether the `+12%` trade_count means the threshold is too HIGH (gate fires less often → 0.25 > typical |flow_fraction|) or whether it means the threshold is too LOW in a different way (gate STILL fires when total_volume is tiny because |1/1| = 1.0 > 0.25, creating noise-driven skips). Without inspecting per-date metrics or per-skip logs I cannot disentangle these. The aggregate trade_count delta is consistent with multiple parameter-mis-specification stories.
