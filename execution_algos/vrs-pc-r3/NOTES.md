# Algorithm Notes: vrs-pc-r3

## Hypothesis

**Mechanism**: Pivot to the REDUCE-SENSITIVITY base variant. Keep the entire base vol-regime-sizer architecture (fast/slow EWM of |delta_mid|, vol_ratio = fast_vol/slow_vol, exponential skip formula, SHA-256 deterministic draw, reduce-only pass-through). The ONLY structural change is the skip-aggressiveness parameter: `sensitivity = 1.0` (vs base's 2.0). All other parameters unchanged: fast_halflife=20, slow_halflife=120, min_prob=0.05, min_ticks=30, max_vol_ratio=5.0. This changes the skip probability curve as follows: vol_ratio=1.5 -> p=0.61 (vs base 0.37); vol_ratio=2.0 -> p=0.37 (vs base 0.135); vol_ratio=3.0 -> p=0.135 (vs base floors at 0.05); vol_ratio=4.0 -> p=0.05 (floor). Behavior is identical to base in calm regimes (vol_ratio<=1, p=1.0) and in extreme regimes (vol_ratio>>3, both algorithms float near min_prob). The change is concentrated in the moderate-vol band (vol_ratio in [1.3, 2.5]) where base may be over-skipping.

**Inefficiency exploited**: The two prior failed runs in this experiment (vrs-pc-r1: -88% on signed-momentum, vrs-pc-r2: -41% on quote-staleness) both ADDED multiplicative skip layers on top of base, and both failed by reducing trade count too aggressively. This is empirical evidence (n=2, modest but directionally consistent) that base is closer to over-skipping than under-skipping at its current parameter setting. The hypothesis: the moderate-vol band (vol_ratio in [1.3, 2.5]) contains a mix of (a) genuine adverse-selection trades where the oracle is on the wrong side of a real move, and (b) trades during transient vol spikes that mean-revert before the 30s horizon completes. Base's sensitivity=2.0 treats both populations the same and skips ~63%-87% of them. A milder sensitivity=1.0 keeps more of population (b) — recovering favorable-but-vol-spike trades — while continuing to skip most of population (a) which clusters at higher vol_ratios where the curves still match (>3.0 both approach min_prob).

**Why it survives costs**: Zero-slippage and zero-commission fill model (mean_slippage=0, total_commissions=0 in base backtest-results.json). All edge from realized P&L. The mechanism is a minimum-complexity change — no new data subscriptions, no new state, no new code paths. Worst case: if base is correctly tuned and not over-skipping, the variant submits more trades during moderate-vol bursts and incurs strictly worse fills on those marginal trades — but the magnitude is bounded because (i) the bulk of base's skip benefit comes from the extreme tail (vol_ratio>>2) where both algorithms behave identically (floor at min_prob), and (ii) the trade-count uplift in the moderate band is modest. The expected magnitude of effect (either direction) is therefore SMALLER than runs 1 and 2's negative outcomes — making this a low-risk experiment whose outcome (PASS, marginal, or modest FAIL) is informative for parameter-axis calibration of base.

**Builds on**: vol-regime-sizer (single-parameter change: sensitivity 2.0 -> 1.0)

**Alternatives considered**: (1) Trade-tick aggressor intensity (round 1): rejected — volume-not-adverse-selection objection is structurally compelling, and the signal likely correlates >0.7 with |delta_mid| making this a near-duplicate of base. (2) Parkinson-range estimator (criticizer suggestion): a reasonable alternative but does not directly test the polarity of the skip lever — it tests estimator quality, which is a SECONDARY concern when the primary uncertainty is sensitivity calibration. Defer to a future run if reduce-sensitivity converges on PASS. (3) Signed trade-aggressor imbalance: structurally similar to falsified run-1 with a slightly better sensor; high prior of repeated mean-reversion failure mode. (4) Combined reduce-sensitivity AND second structural change: rejected — confounds the experiment; the cleanest test isolates the sensitivity axis. (5) Sensitivity sweep at multiple values (0.5, 1.0, 1.5): only one run available; sensitivity=1.0 is the midpoint between 'base' and 'no skip' and a reasonable single test point. (6) Lower min_prob: rejected — pushes in the OPPOSITE direction (more skipping in extreme vol), inconsistent with the over-skipping hypothesis being tested.

**Debate summary**: 2 round(s), outcome=CONVERGED. Key objections resolved: round 1's trade-tick-intensity hypothesis was abandoned after the Criticizer's MAJOR objection that high trade volume signals liquid depth rather than adverse selection (an inverted-signal risk), plus the redundancy concern that intensity is highly correlated with |delta_mid|. Pivoted in round 2 to the Criticizer's strongest suggested alternative — reducing sensitivity from 2.0 to 1.0 — which directly tests the polarity of base's skip lever in a way runs 1 and 2 did not (both went MORE aggressive and both failed).

---

## Implementation Decisions

- **Single-parameter delta from base**: The implementation copies base's `VolRegimeSizerAlgorithm` exactly, changing only the default `sensitivity` value in the config dataclass and the factory function (2.0 -> 1.0). All other defaults (fast_halflife=20, slow_halflife=120, min_prob=0.05, min_ticks=30, max_vol_ratio=5.0) are unchanged to keep the experimental contrast clean.
- **No new state, no new subscriptions**: Only the quote-tick stream is consumed, exactly as base does it.
- **Reduce-only orders submit unconditionally**: Inherited from base (intraday_flat compliance).
- **Quantity invariant preserved**: child_qty == parent_qty == 1 for all submitted orders.
- **SHA-256 deterministic draw on client_order_id**: Inherited from base; ensures reproducibility across runs.
- **Class and factory naming**: Distinct class names (`VrsPcR3Config`, `VrsPcR3Algorithm`) to avoid any registry collision with base.

**Concerns**:
- No look-ahead bias: vol estimator only uses quote ticks received before the order arrives, identical to base.
- Single-test-point risk: sensitivity=1.0 is a midpoint between base (2.0) and "no vol gate" (0.0). If the optimum lies at 0.5 or below, this test will UNDERSTATE the magnitude of the over-skipping effect. If the optimum lies above 1.0, this test will overshoot in the under-skipping direction. Pragmatic single-shot test, not a sweep.
- Inference weakness: the conclusion "base over-skips" rests on n=2 prior runs that added DIFFERENT signals to base — their failures could also be explained by the added signals being bad, not by base being conservative. The experimental yield is bounded.

---

## Backtest Observations

**Raw metrics** (train window 2026-03-08 → 2026-03-20, 12 trading days):
- realized_pnl = $526.25
- sharpe_ratio = 2.13
- trade_count = 131,060
- mean_slippage = 0.0
- vs base (vol-regime-sizer, realized_pnl=$753.75): vs_base_pnl_pct = **-30.18%**
- vs_base_slippage_pct = 0.0%
- vs simple baseline (per script): delta_pnl_pct = +237.34% (suggested verdict: PASS — but the pc-experiment evaluates against base vol-regime-sizer, not simple, so this is informational only).

**What drove improvement**: Trade_count is higher than runs 1-2 (131k vs 104k/86k) — the lower sensitivity gates fewer orders out. Sharpe (2.13) is between runs 1 and 2, neither cleanly better nor worse.

**What underperformed**: Despite trading more, aggregate P&L ($526.25) still fell short of base ($753.75) by 30%. Halving sensitivity didn't push P&L past base — base's higher-sensitivity skip is apparently filtering some genuinely adverse trades that vrs-pc-r3 is now letting through.

**Hypothesis verdict**: **Contradicted.** The hypothesis predicted that base over-skips and that loosening sensitivity to 1.0 would lift P&L past base. Empirical outcome: loosening hurts. Base's sensitivity=2.0 is closer to optimal than either 1.0 or whatever runs 1-2 implicitly produced. The "base over-skips" inference from n=2 prior runs was wrong — runs 1-2 underperformed because their added signals were bad, not because base was conservative.

**Suggested next attempt**: Try sensitivity SLIGHTLY HIGHER than base (2.5 or 3.0) to test the opposite hypothesis: that base under-skips. This would form a 3-point sensitivity sweep (1.0, 2.0, 3.0) and either confirm 2.0 as a local optimum or shift the bet toward more aggressive skipping.
