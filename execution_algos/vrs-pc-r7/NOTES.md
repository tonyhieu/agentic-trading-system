# Algorithm Notes: vrs-pc-r7

## Hypothesis

**Mechanism**: Halve the fast EWM halflife from 20 ticks to 10 ticks, holding the rest of run-5's calibration (sensitivity=2.5, min_prob=0.0, slow_halflife=120, min_ticks=30, max_vol_ratio=5.0). Builds on run-5 (best PnL-per-effort result), not run-6, since the sensitivity=3.0 step delivered only $12 marginal gain over run-5 ($888.50 -> $900.75). At fast_halflife=20, alpha = 1 - exp(-ln(2)/20) ~= 0.0341 per tick. At fast_halflife=10, alpha ~= 0.0670 — the fast EWM reaches 50% response to a new tick magnitude in ~10 ticks instead of ~20 ticks (~2x faster). The slow EWM is unchanged (slow_halflife=120, alpha ~= 0.00578), so the baseline is identical — only the speed of fast_vol response to new bursts changes. The skip-probability formula is unchanged: p = exp(-2.5 * max(0, vol_ratio - 1)) with min_prob=0.0 floor.

**Inefficiency exploited**: The sensitivity axis is empirically plateauing: 2.0->2.5 gained $130 (run-4 -> run-5), 2.5->3.0 gained only $12 (run-5 -> run-6). Per-pruned-trade marginal P&L dropped 10x from $0.10 to $0.01. The shrinking marginal return has two possible explanations: (1) the residual addressable adverse-EV set is small and the sensitivity axis is the right lever but is exhausted; (2) the sensor itself is missing the right trades because it's too slow — vol bursts that should trigger skipping are detected only AFTER the trade has already been submitted, so even an arbitrarily steep curve cannot reduce participation in those trades. Explanation (2) predicts that a faster fast_halflife re-opens the addressable set: bursts that previously took 20 ticks to register in fast_vol now register in 10, capturing the order that arrives during burst onset rather than after it passes. This is testable in isolation by holding sensitivity, min_prob, slow_halflife, min_ticks, and max_vol_ratio constant.

**Why it survives costs**: Zero slippage and zero commission verified empirically: execution_algos/vol-regime-sizer/results/backtest-results.json shows mean_slippage=0.0, max_abs_slippage=0.0, total_commissions=0.0. Edge from realized P&L only. Trade-count impact: at fast_halflife=10, the fast EWM is ~2x noisier (variance scales roughly with alpha). More false-positive "vol bursts" will trigger skips where the slow EWM has not moved. Likely trade-count drop: 1-3k from run-5 (126.7k -> ~123-126k); could be 3-6k under pessimistic noise assumptions. The strict-subset property over run-5 does NOT hold: at the same order, vol_ratio can be HIGHER under fast_halflife=10 (faster burst capture) or essentially identical (calm regime) — and r7 may skip orders r5 submitted (responding to a burst r5 missed) AND submit orders r5 skipped (when the faster fast EWM catches up to the slow EWM faster, reducing vol_ratio post-burst). Worst-case bounding: (1) If noise dominates signal, r7 produces more false-positive skips than true-positive skips of adverse-EV trades, and P&L degrades modestly — the 12-day variance band is ~$100-200 absolute. (2) If the faster sensor catches genuine bursts the slow sensor missed, addressable set re-opens and P&L gains proportionally to the noise/signal ratio. Reduce-only path unchanged: intraday_flat compliance preserved. Quantity invariant: child_qty = parent_qty = 1.

**Builds on**: vrs-pc-r5 (PASS, +17.88% vs base, sharpe=3.69, trade_count=126,677). Single change vs run-5: fast_halflife 20 -> 10. All other parameters identical to run-5 (sensitivity=2.5, min_prob=0.0, slow_halflife=120, min_ticks=30, max_vol_ratio=5.0). Deliberately built on r5 rather than r6 to isolate the sensor-axis change from the marginal sensitivity bump; r6's $12 gain over r5 is small enough to be within noise, so r5 is the cleaner baseline for attribution.

**Alternatives considered**: (1) fast_halflife=15 (more conservative, 1.5x speedup): smaller step; sensitivity-axis precedent of 0.5-step gradient suggests bigger steps gave cleaner signals — halving is the natural test of the sensor-axis hypothesis. (2) fast_halflife=5 (more aggressive, 4x speedup): at halflife=5 the fast EWM essentially tracks single-tick noise and becomes very noisy; high chance of false-positive bursts dominating. Defer until 10 shows whether direction is right. (3) slow_halflife=60 (faster baseline): makes the baseline more responsive, reducing vol_ratio in elevated regimes (baseline catches up faster) — OPPOSITE direction of the sensitivity gradient, wrong sign. (4) slow_halflife=240 (slower baseline): plausible alternative axis but confounds the test of the fast-sensor hypothesis. (5) sensitivity=3.5, halflife unchanged (run-6 NOTES option b, clean sensitivity refusal): the 10x drop in per-pruned-trade marginal P&L suggests the sensitivity axis is nearly exhausted at the current sensor — sensitivity=3.5 has a high chance of producing a wash result that confirms exhaustion without opening a new axis. (6) Combined sensitivity=3.0 + fast_halflife=10 (compound on r6): two-variable change; defer to keep r7 attribution clean — if r7 passes a future r8 can compound. (7) EWM of squared mid-deltas (Parkinson-style estimator): bigger architectural change; defer until the linear-halflife axis is exhausted. (8) Per-side spread-aware sensor: different sensor type using bid/ask spread; orthogonal axis; defer.

**Debate summary**: 1 round, outcome=CONVERGED. The Round-1 Proposer pitched the sensor-axis pivot (fast_halflife 20 -> 10) as the natural next probe after the sensitivity axis showed 10x diminishing returns at the r5 -> r6 step. The Criticizer raised three MINOR objections (jitter magnitude under-priced, asymmetric burst-capture window unquantified, builds-on choice debatable r5 vs r6) but no BLOCKING or MAJOR objections, and converged to PASS in a single round. Key resolved point: no clearly superior untried alternative exists — sensitivity=3.5 would confirm plateau without opening a new axis, spread-based and Parkinson sensors are bigger architectural changes, slow_halflife variations are orthogonal and confound the fast-sensor test.

---

## Implementation Decisions

- **Single-parameter delta from run-5**: only `fast_halflife` default changes (20 -> 10). All other code paths, classes, and state are bitwise-identical to run-5's `VrsPcR5Algorithm`. The implementation is structurally a copy of run-5 (which itself derived from base vol-regime-sizer + run-4's min_prob=0.0). Class names renamed (VrsPcR5* -> VrsPcR7*). Every branch — `_tick_count < min_ticks`, `fast_vol is None`, `slow_vol < 1e-12`, the reduce-only path, the SHA-256 deterministic draw, the `p >= 1.0 - 1e-9` short-circuit, the `max(self._min_prob, prob)` clamp — preserved verbatim.

- **min_prob=0.0 and sensitivity=2.5 inherited from run-5**: The pivot retains run-5's validated levers. The skip probability formula is unchanged: p = exp(-2.5 * max(0, vol_ratio - 1)) with the floor effectively eliminated (min_prob=0.0).

- **fast_alpha doubles**: At fast_halflife=10, fast_alpha = 1 - exp(-ln(2)/10) ~= 0.0670; at fast_halflife=20 (run-5/r6 default), fast_alpha ~= 0.0341. The fast EWM update per tick weights the latest |delta_mid| ~2x more heavily — burst capture is ~2x faster, jitter variance is ~2x larger.

- **Slow EWM unchanged**: slow_halflife=120 ticks, slow_alpha ~= 0.00578. The baseline is identical to runs 4-6 and base. Only the speed of fast_vol response to bursts changes; the vol_ratio's denominator is unaffected.

- **NO strict-subset over run-5**: This is a sensor-axis change, not a curve change. At the same order, r7 may compute a higher vol_ratio than r5 (faster burst capture, more skips) or a lower vol_ratio than r5 (faster recovery from a passing burst, more submissions). The SHA-256 deterministic draw u is identical, but p differs by direction and magnitude. The vs-r5 P&L delta cleanly attributes the sensor-axis change in isolation since sensitivity, min_prob, slow_halflife, min_ticks, and max_vol_ratio are constant.

- **Per-vol-bin payoff attribution**: For backtest observation, compare to BOTH base (vol-regime-sizer) and run-5 (vrs-pc-r5). The vs-base headline mixes the sensor-axis change with the floor-removal (base -> r4) and the sensitivity bump (r4 -> r5); the vs-run-5 comparison isolates the sensor-axis change alone.

**Concerns**:
- **No look-ahead bias**: vol estimator reads only ticks received before each order via `on_quote_tick`; `on_order` reads current EWM state. State is identical to base and runs 4-6 in this respect.
- **Jitter magnitude could outweigh signal**: With ~2x variance in fast_vol, false-positive bursts in calm regimes could cause spurious skips. The 1-3k pessimistic-band trade-count drop estimate may be 3-6k if jitter dominates.
- **Asymmetric burst-capture window**: The expected gain depends on bursts lasting 10-20 ticks being empirically populous. Unmeasured. If most bursts are short-tail (<10 ticks) the faster sensor adds noise without expanding the addressable set; if most bursts are long-tail (>20 ticks) the old sensor already caught them.
- **Reduce-only invariant**: All reduce-only orders submit unconditionally, identical to base and runs 4-6.
- **Quantity invariant**: Every submitted order carries the original parent quantity (1 contract). The algorithm never inflates quantity.

---

## Backtest Observations

**Raw metrics** (train window 2026-03-08 → 2026-03-20, 12 trading days):
- realized_pnl = $1454.25
- sharpe_ratio = 6.19
- trade_count = 125,434
- mean_slippage = 0.0
- vs base (vol-regime-sizer, realized_pnl=$753.75): vs_base_pnl_pct = **+92.94%**
- vs run-5 (vrs-pc-r5, realized_pnl=$888.50): vs_r5_pnl_pct ≈ +63.68% — halving fast_halflife added ~$566 / 12 days
- vs run-6 (vrs-pc-r6, realized_pnl=$900.75): vs_r6_pnl_pct ≈ +61.45%
- vs_base_slippage_pct = 0.0%

**What drove improvement**: The sensor-axis hypothesis was strongly correct. Doubling fast_alpha (0.034 → 0.067) made the EWM respond ~2x faster to new bursts, catching adverse-vol orders earlier in the burst window. Trade_count dropped only modestly from run-5 (126,677 → 125,434, ~1k orders pruned) yet P&L jumped ~$566 — per-pruned-trade marginal P&L jumped to ~$0.45, far higher than any prior step.

**What underperformed**: Nothing material. Sharpe of 6.19 is the highest of any P&L-positive run in this experiment by a wide margin (next-best was run-6 at 3.77). Max-drawdown improved to -3.83% (vs run-6's -4.21%). The "asymmetric burst-capture window" MINOR concern raised in debate did not materialize — the additional skips were apparently in the early-burst window where adverse fills concentrate, not in the post-burst recovery window where positive-EV trades sit.

**Hypothesis verdict**: **Strongly supported.** The hypothesis predicted that the sensitivity-axis plateau (run-5 → run-6) was caused by sensor lag, not by inefficiency exhaustion. Empirical outcome confirms with high signal: ~$566 vs run-5 from a single fast_halflife halving. The sensor axis has substantially more leverage than the sensitivity axis at this calibration.

**Suggested next attempt**: Push the sensor axis further: try fast_halflife=5 ticks (alpha ~0.13, ~4x base) to test whether the gradient continues. Alternative: combine fast_halflife=10 (this run's lever) with sensitivity=3.0 (run-6's setting) for a 2-variable best-of-both probe — the per-pruned-trade marginal still has room since run-7 sensitivity is only 2.5. The two axes likely compound.
