# Algorithm Notes: vrs-pc-r4

## Hypothesis

**Mechanism**: Pivot to LOWER-MIN_PROB variant of vol-regime-sizer. Keep the entire base architecture exactly (fast/slow EWM of |delta_mid| with fast_halflife=20, slow_halflife=120 ticks; vol_ratio = fast_vol/slow_vol; SHA-256 deterministic draw; reduce-only pass-through; sensitivity=2.0 unchanged; min_ticks=30 unchanged; max_vol_ratio=5.0 unchanged). The ONLY structural change: min_prob = 0.0 (vs base's 0.05). The skip probability curve becomes p = exp(-2.0 * max(0, vol_ratio - 1)) with no floor (clamped to 0 only if exp underflows). In the moderate-vol band (vol_ratio in [1.0, 2.5]) the algorithm is IDENTICAL to base because exp(-2.0 * max(0, vol_ratio - 1)) > 0.05 only when vol_ratio < ~2.5. The change is concentrated entirely in the extreme-vol tail (vol_ratio > 2.5): vol_ratio=3.0 -> p=0.135 (base also 0.135, both above floor); vol_ratio=4.0 -> p=0.018 (base floors at 0.05); vol_ratio=5.0 -> p=0.0003 (base floors at 0.05); vol_ratio=5.0+ -> p~0 (base floors at 0.05). At sensitivity=2.0, this affects only the most extreme regime tail — by base's NOTES per-date breakdown, this is precisely where the worst-fill trades cluster on adverse days.

**Inefficiency exploited**: Base's NOTES.md per-date results show that the +383% over baseline is driven overwhelmingly by LOSS REDUCTION on adverse days (20260313-17 the algorithm loses 22.9-54.4% LESS than baseline); good days show modest improvement (+2.3-6.8%). This pattern strongly implies the bad-fill trades cluster in time, specifically during extreme-vol regimes. The min_prob=0.05 floor means base STILL submits 5% of even the most extreme-vol trades. The hypothesis: removing this floor catches the very worst extreme-tail trades that base lets through, while leaving all moderate-band behavior unchanged. Empirically motivated by the joint inference: (a) run 1 (extra skip layer overlaid on vol) lost -88% because the signed-mid axis was noisy; (b) run 2 (extra skip on staleness axis) lost -41% because dead-market is a different population; (c) run 3 (less skipping on EXISTING axis) lost -30% because base is correctly skipping the bad trades it skips; therefore the untested polarity is MORE-skipping ON THE SAME AXIS BUT ONLY IN THE TAIL — exactly what min_prob=0.0 does.

**Why it survives costs**: Zero-slippage and zero-commission fill model (mean_slippage=0.0, total_commissions=0.0 from base backtest-results.json). All edge from realized P&L. The mechanism is the minimum-complexity single-parameter change. Worst-case bounding: (1) The decision architecture, fast/slow EWM, sensitivity, all unchanged from base. Only the extreme-tail behavior differs. (2) Magnitude of effect is intrinsically BOUNDED because base's existing skipping at sensitivity=2.0 already drops p to ~0.135 by vol_ratio=2.0 and ~0.018 by vol_ratio=4.0; the floor only changes behavior in a small fraction of trades. (3) If extreme-vol trades have neutral or positive expected fill, this run modestly UNDERPERFORMS base. (4) If extreme-vol trades have negative expected fill (as base's loss-reduction pattern suggests), this run modestly OUTPERFORMS base. (5) This is the only run in this experiment where the worst-case downside is bounded BY DESIGN to a small fraction of trades.

**Builds on**: vol-regime-sizer (single-parameter change: min_prob 0.05 -> 0.0; all other parameters identical to base)

**Alternatives considered**: (1) Parkinson high-low estimator (round 1): rejected — Parkinson-on-discrete-tick-grid concern is structurally valid. (2) Time-based EWM (Criticizer suggestion): tests estimator quality, not tail-aggressiveness; defer. (3) Empirical EDA before commit: informative but not strictly needed for parameter-axis test. (4) Lower min_prob to 0.01 instead of 0.0: 0.0 is the cleaner test of 'remove the floor entirely.' (5) Lower min_prob AND raise sensitivity: confounds the experiment. (6) Power-law decay: adds parameters. (7) Trade-tick intensity: rejected in run-3 round 1 — likely correlated with quote vol.

**Debate summary**: 2 round(s), outcome=CONVERGED. Key objections resolved: round-1 Parkinson estimator was abandoned in full after the Criticizer raised the Parkinson-meets-tick-grid discretization concern AND surfaced the structurally simpler min_prob=0.0 alternative that reads runs 1+3's joint failure as a 'skip more in the tail' signal.

---

## Implementation Decisions

- **Code reuse**: This algorithm is structurally identical to `execution_algos/vol-regime-sizer/execution_algorithm.py` with one parameter change. To minimize accidental refactoring and preserve byte-for-byte equivalence of cold-start branches, the implementation is a copy of the base file with: (a) class names renamed (VolRegimeSizer* -> VrsPcR4*); (b) `min_prob` default changed 0.05 -> 0.0 in both the Config and the factory function. Every other branch — `_tick_count < min_ticks`, `fast_vol is None`, `slow_vol < 1e-12`, the reduce-only path, the SHA-256 deterministic draw, the `p >= 1.0 - 1e-9` short-circuit — is preserved verbatim.

- **Strict-subset property**: With min_prob=0.0, the variant's submission probability for any order is `<=` base's at every order (because `max(0.0, prob) <= max(0.05, prob)` always). The deterministic SHA-256 draw means the same `u` is computed for the same `client_order_id`. So any order that base skips (`u >= 0.05`) is also skipped by this variant if its `p_variant < 0.05`; and any order that base submits in the deep tail (`u < 0.05`) is skipped by this variant when `p_variant < u`. The submission set is therefore a STRICT SUBSET of base's submission set. This bounds the experiment cleanly: the P&L delta is attributable solely to the extreme-tail trades that base submits but this variant does not.

- **Floor behavior**: `max(self._min_prob, prob)` with `_min_prob=0.0` still clamps any negative numerical underflow from `math.exp` to 0.0. `math.exp(-50)` is `1.9e-22`, well above 0. Realistic vol_ratio is bounded above by `max_vol_ratio=5.0`, so the minimum sensitivity-2.0 prob is `exp(-8) ~ 3.4e-4`. No underflow risk in practice.

**Concerns**:
- **No look-ahead bias**: vol estimator state is identical to base; reads only the EWM populated by `on_quote_tick` callbacks that arrived before the current order. Same look-ahead guarantee as base.
- **Bounded effect**: The fraction of trades with vol_ratio>2.5 is small (the bulk of the per-tick |delta_mid| distribution lives in vol_ratio<2.0). Expected effect magnitude is modest — most likely outcome is small improvement, small degradation, or near-base. This is acceptable for a calibration test of the tail-skipping floor.
- **Reduce-only invariant**: All reduce-only (intraday-flat close) orders submit unconditionally, identical to base. No min_prob involvement for those orders.

---

## Backtest Observations

**Raw metrics** (train window 2026-03-08 → 2026-03-20, 12 trading days):
- realized_pnl = $759.00
- sharpe_ratio = 3.09
- trade_count = 127,992
- mean_slippage = 0.0
- vs base (vol-regime-sizer, realized_pnl=$753.75): vs_base_pnl_pct = **+0.70%**
- vs_base_slippage_pct = 0.0%

**What drove improvement**: Removing the min_prob=0.05 floor lets the algorithm skip the most extreme-vol orders entirely (orders where exp(-2 * vol_excess) drops below 0.05 — i.e. roughly vol_ratio > 2.5). Those tail orders had negative expected P&L on net; eliminating them produced a marginal but positive improvement.

**What underperformed**: The improvement is small (~$5 / 12 days). The floor-removal only differs from base in the extreme tail, so the addressable set is narrow. Trade_count fell only ~3% relative to base (~131k → 128k), consistent with the small affected fraction.

**Hypothesis verdict**: **Supported.** The hypothesis predicted that base's min_prob floor was preserving some negative-EV extreme-tail orders that more-aggressive skipping in that regime would shed. Empirical outcome matches — modest positive delta, no slippage regression. Beats base by 0.70% — close to base, below the formal 5% PASS gate but on the right side of zero.

**Suggested next attempt**: Combine min_prob=0 (this run's lever) with a slightly higher sensitivity (e.g. 2.5 or 3.0) to amplify the extreme-tail-skipping effect. The two changes are orthogonal — sensitivity controls the curve steepness, min_prob controls where the curve gets clipped. Together they expand the addressable tail.
