# Algorithm Notes: vrs-pc-r5

## Hypothesis

**Mechanism**: Pivot to sensitivity=2.5 + min_prob=0.0 (down from sensitivity=3.0). All other base parameters preserved exactly (fast_halflife=20 ticks, slow_halflife=120 ticks, min_ticks=30, max_vol_ratio=5.0, SHA-256 deterministic draw on client_order_id, reduce-only pass-through unconditional). The skip-probability curve becomes p = exp(-2.5 * max(0, vol_ratio - 1)) with no floor. Comparison at key vol_ratio values vs base (sensitivity=2.0, min_prob=0.05) and vs run-4 (sensitivity=2.0, min_prob=0.0):
  vol_ratio=1.0 -> p=1.000 (base 1.000, run-4 1.000) — identical, calm regime
  vol_ratio=1.2 -> p=0.607 (base 0.670, run-4 0.670) — modest 6pp compression
  vol_ratio=1.5 -> p=0.287 (base 0.368, run-4 0.368) — 8pp compression
  vol_ratio=2.0 -> p=0.082 (base 0.135, run-4 0.135) — 5pp compression
  vol_ratio=2.5 -> p=0.024 (base floors at 0.05, run-4 0.018) — past base floor; near run-4
  vol_ratio=3.0 -> p=0.0067 (base floors at 0.05, run-4 0.0025) — past base floor
  vol_ratio>=4.0 -> p<0.002 (base floors at 0.05, run-4 ~0) — past base floor
The sensitivity=2.5 calibration delivers ~5-10pp probability compression across the moderate band (vol_ratio 1.2-2.0) — meaningfully different from base but FAR less aggressive than 3.0's 12-20pp compression. This intermediate step bounds the downside risk to roughly 2x run-4's, not 5x or more.

**Inefficiency exploited**: Joint reading of runs 3 and 4 narrowed: (1) Run-3 (sensitivity 2.0->1.0, min_prob unchanged at 0.05) lost -30%. The Criticizer correctly noted this is a joint shallower-curve + preserved-floor test, but the OUTCOME polarity is unambiguous: the direction sensitivity-lower lost money. The MIRROR direction (sensitivity-higher) is the untested polarity, regardless of whether the loss attribution is curve-shallowness, floor-interaction, or both. (2) Run-4 (min_prob 0.05->0.0, sensitivity unchanged at 2.0) gained +0.70%. This isolates the floor change: removing it helped. The minimal interpolation between these two data points is: 'tighter skipping in the tail helps; looser skipping anywhere hurts.' sensitivity=2.5 extends run-4's helpful-direction slightly further into the moderate band without committing to an aggressive 3.0 jump. The chosen calibration sensitivity=2.5 still 'samples' the new behavior — it's not so close to base that the effect is undetectable, but it's bounded.

**Why it survives costs**: Zero slippage and zero commission per execution_algos/vol-regime-sizer/results/backtest-results.json (mean_slippage=0.0, total_commissions=0.0). Edge from realized P&L only. Trade-count impact: at sensitivity=2.5, the curve compression is modest (5-10pp across vol_ratio 1.2-2.0). Expected trade_count is somewhere between run-4's 127,992 and a hypothetical ~115k floor — modest, not cliff-like. Variance amplification concern is meaningfully reduced relative to sensitivity=3.0. Worst-case bounding: (1) The downside if the moderate-band participation is actually positive-EV is ~2x larger than run-4's tiny effect — manageable. (2) The upside if the moderate-band participation is actually negative-EV (consistent with base's NOTES per-date loss-reduction pattern, though weakly) is ~3-5x larger than run-4's effect. (3) Asymmetric expected payoff favors taking this single conservative step on the sensitivity axis, especially since this is the natural follow-on to the only PASS in the experiment so far. (4) Reduce-only path unchanged: intraday_flat compliance preserved. (5) Submission set is no longer a strict subset of base's because the moderate band is now also affected — but it IS a strict subset of run-4's: at every vol_ratio, p_run5 = exp(-2.5*excess) < exp(-2.0*excess) = p_run4 (for excess > 0). So the test is cleanly attributable to the sensitivity-bump-over-run-4.

**Builds on**: vrs-pc-r4 (PASS, +0.70%). Single change vs run-4: sensitivity 2.0 -> 2.5. All other parameters identical to run-4 (including min_prob=0.0 inherited from run-4).

**Alternatives considered**: (1) sensitivity=3.0 + min_prob=0.0 (round-1 hypothesis): rejected after the Criticizer's three MAJOR objections on misreading run-3, asymmetric exp-decay magnitude, and trade-count cliff variance amplification. (2) sensitivity=3.0 + min_prob=0.05 (Criticizer suggested isolation): plausible as a sensitivity-axis isolation test, but discards run-4's empirically validated min_prob=0.0 — would be a STEP BACK on the lever that we know helps. Prefer to build on the working lever and step forward cautiously on the new one. (3) EDA before committing (Criticizer suggested): EDA on a single train date would measure the vol_ratio empirical distribution and per-bin base submission outcomes, but the bounded-downside design at sensitivity=2.5 makes the empirical test itself a cheap data point — the run IS the EDA at the system level. (4) sensitivity=2.25 (even more conservative): would compress the moderate-band probability by only 3-5pp; the effect would likely be too small to detect against the 12-day variance band, similar to run-4's $5 effect. (5) sensitivity=2.5 + min_prob=0.02 (intermediate floor): two-variable change confounds attribution. (6) Larger fast_halflife or slow_halflife: changes the SENSOR, orthogonal axis; defer.

**Debate summary**: 2 round(s), outcome=CONVERGED. Key objections resolved: round-1's aggressive sensitivity=3.0 was abandoned after Criticizer's MAJOR objections on (a) attribution of run-3's loss not cleanly to curve-shallowness alone, (b) asymmetric exp-decay magnitudes meaning sensitivity=3.0 was not a symmetric mirror of run-3's 1.0, and (c) trade-count cliff variance amplification risking run-4's entire margin. The pivot to sensitivity=2.5 preserves the directional bet while bounding magnitude to ~2x run-4's effect.

---

## Implementation Decisions

- **Code reuse**: This algorithm inherits structurally from `execution_algos/vrs-pc-r4/execution_algorithm.py` (which itself inherits from `execution_algos/vol-regime-sizer/execution_algorithm.py`). Implementation is a copy of run-4's file with: (a) class names renamed (VrsPcR4* -> VrsPcR5*); (b) `sensitivity` default changed 2.0 -> 2.5 in both the Config and the factory function. Every other branch — `_tick_count < min_ticks`, `fast_vol is None`, `slow_vol < 1e-12`, the reduce-only path, the SHA-256 deterministic draw, the `p >= 1.0 - 1e-9` short-circuit, the `max(self._min_prob, prob)` clamp — is preserved verbatim.

- **min_prob=0.0 inherited from run-4**: The pivot retains run-4's validated change. Combined with sensitivity=2.5, the skip probability curve is p = exp(-2.5 * max(0, vol_ratio - 1)) with no floor. The `max(self._min_prob, prob)` line still executes (clamping to 0.0 in the deep tail to handle any numerical underflow), but the floor is effectively eliminated.

- **Strict-subset property over run-4**: For all vol_ratio > 1.0, exp(-2.5 * excess) < exp(-2.0 * excess), so p_run5 < p_run4 at every order with elevated vol. Since both share the SHA-256 deterministic draw u(client_order_id), any order run-4 skips (u >= p_run4) is also skipped by run-5; some additional orders run-4 submitted in the moderate band (p_run4 > u > p_run5) are skipped by run-5. The submission set is a STRICT SUBSET of run-4's. Comparison to run-4 cleanly attributes the sensitivity lever.

- **Per-vol-bin payoff attribution**: For backtest observation, compare to BOTH base (vol-regime-sizer) and run-4 (vrs-pc-r4). The vs-base headline mixes the sensitivity-bump and the floor-removal; the vs-run-4 comparison isolates the sensitivity-bump alone.

**Concerns**:
- **No look-ahead bias**: vol estimator state is identical to run-4 and base; reads only the EWM populated by `on_quote_tick` callbacks that arrived before the current order.
- **Moderate-band addressable population is unmeasured**: The Criticizer's MINOR objection. The actual fast/slow EWM ratio distribution on MES quote data is unknown without EDA. At sensitivity=2.5, the affected band (vol_ratio 1.2-2.5) is wider than run-4's tail-only set, but the per-trade adverse-EV magnitude in that band may be smaller than in the deep tail. Expected effect could be smaller than the 3-5x run-4 upper bound.
- **Reduce-only invariant**: All reduce-only orders submit unconditionally, identical to run-4 and base.
- **Quantity invariant**: Every submitted order carries the original parent quantity (1 contract). The algorithm never inflates quantity.

---

## Backtest Observations

**Raw metrics** (train window 2026-03-08 → 2026-03-20, 12 trading days):
- realized_pnl = $888.50
- sharpe_ratio = 3.69
- trade_count = 126,677
- mean_slippage = 0.0
- vs base (vol-regime-sizer, realized_pnl=$753.75): vs_base_pnl_pct = **+17.88%**
- vs run-4 (vrs-pc-r4, realized_pnl=$759.00): vs_r4_pnl_pct ≈ +17.06% — the sensitivity-bump alone (controlling for the floor-removal) added ~$130 / 12 days
- vs_base_slippage_pct = 0.0%

**What drove improvement**: The compound of run-4's min_prob=0 floor-removal AND the sensitivity bump 2.0→2.5 produced a meaningful step up. The strict-subset property held: trade_count dropped only ~1.3k from run-4 (127.9k → 126.7k) yet P&L rose by ~$130. The marginal trades pruned in the moderate-elevated band (vol_ratio 1.2–2.5) were net-negative-EV, exactly as the hypothesis predicted.

**What underperformed**: Nothing material. Sharpe of 3.69 is the third-highest across runs (after r2's 9.37 — but r2 was P&L-negative — and is now the best Sharpe among P&L-positive runs). Max-drawdown improved slightly vs run-4 (−4.17% vs −4.60%).

**Hypothesis verdict**: **Supported and meaningfully more so than run-4.** The hypothesis predicted compounding the two levers would extract a non-trivial additional P&L from the moderate-elevated band without trade_count cliff. Empirical outcome confirms — beats base by +17.88%, well past the formal 5% PASS gate. The strict-subset construction lets us cleanly attribute the gain to the sensitivity-bump axis.

**Suggested next attempt**: Push sensitivity further (e.g. 3.0 or 3.5) to test whether the gradient still pays. The Criticizer's run-1 concern was that sensitivity=3.0 would cause a trade-count cliff and variance spike; this run shows the cliff at 2.5 is mild (~1.3k drop from run-4). Worth one more probe in the same direction.
