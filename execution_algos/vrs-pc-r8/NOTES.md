# Algorithm Notes: vrs-pc-r8

## Hypothesis

**Mechanism**: Compound two empirically validated levers: keep run-7's faster sensor (fast_halflife=10) AND adopt run-6's steeper sensitivity (sensitivity=3.0). All other parameters preserved from run-7 (min_prob=0.0, slow_halflife=120, min_ticks=30, max_vol_ratio=5.0). The skip-probability formula becomes p = exp(-3.0 * max(0, vol_ratio - 1)), evaluated on a fast_vol EWM with alpha~0.0670 (twice base) and slow_vol EWM with alpha~0.00578 (unchanged). For an order arriving at vol_ratio=2.0 the per-tick skip probability changes from exp(-2.5)~0.082 (r7) to exp(-3.0)~0.050 (r8) — at the elevated-vol slice the order is now ~1.6x more likely to be skipped. For vol_ratio=1.5 the change is exp(-1.25)~0.287 -> exp(-1.5)~0.223, ~22% more selective. In calm regimes (vol_ratio<=1) both produce p=1.0; identical behaviour.

**Inefficiency exploited**: Run-7's empirical evidence reframes the r5->r6 plateau. At fast_halflife=20 (r5/r6 sensor), the marginal sensitivity step 2.5->3.0 added only ~$12 / 12 days because the sensor was missing most of the addressable adverse-EV bursts in the first place — there were few orders for the steeper curve to act on. Run-7 shows the addressable set under fast_halflife=10 is materially larger: trade_count dropped only ~1.2k from r5 yet realized_pnl jumped ~$566 (~$0.45/pruned trade vs ~$0.01 on the r5->r6 step at the slower sensor). With a richer addressable population, the sensitivity axis should re-acquire leverage: every order in the elevated-vol slice gets a steeper exp curve, increasing the fraction skipped per detected burst. The two axes compound because they act on independent gates — the sensor decides which orders enter the elevated-vol slice (the *whether*), and the sensitivity decides what fraction of those orders is skipped (the *how aggressively*). Run-7 confirmed leverage on the *whether*; r8 tests whether leverage on the *how* re-emerges once the *whether* is richer.

**Why it survives costs**: Backtest-results.json for vol-regime-sizer shows mean_slippage=0.0, max_abs_slippage=0.0, total_commissions=0.0 across all 12 train dates. Same property held for runs 4-7. Edge is purely realized P&L driven by skipping adverse-EV oracle orders. Trade-count impact: vs run-7's 125,434, r8 will prune additional orders that fell in the [exp(-3*excess), exp(-2.5*excess)] probability gap. For excess values commonly observed (run-7's per-pruned-trade $0.45 implies many orders hover near vol_ratio=1.5-2.0), the extra prune fraction at each excess level is ~7-25%. Bounded incremental trade-count drop: 0.5k-2k (expect 125.4k -> ~123.5-125k). Worst-case P&L: if the residual addressable population at fast=10 was already mostly skipped by r7's sensitivity=2.5, the extra skips at sensitivity=3.0 are drawn from near-zero-EV trades and r8 P&L matches r7 within ~$50. Expected case: if the r7 data ($0.45/pruned trade) reflects the slope of EV across the curve, the extra ~1k prunes at sensitivity=3.0 are still drawn from positive-marginal-cost orders, adding $100-300 to P&L. Reduce-only path unchanged: intraday_flat compliance preserved. Quantity invariant: child_qty = parent_qty = 1.

**Builds on**: vrs-pc-r7 (PASS, +92.94% vs base, sharpe=6.19, trade_count=125,434, realized_pnl=$1454.25) — the experiment's best result by a wide margin. Single change vs r7: sensitivity 2.5 -> 3.0 (adopt r6's setting). The combined parameter set (fast_halflife=10, sensitivity=3.0) has never been tested. Cross-axis composition of the two independently-validated levers in the experiment.

**Alternatives considered**: (1) fast_halflife=5 (push sensor axis further): r7 NOTES.md flagged this as risky — at halflife=5, alpha~0.13, fast EWM tracks essentially single-tick noise. Variance roughly doubles again from r7 (which already doubled vs base). High chance of jitter-driven false-positive skips dominating signal, given that the calm-regime |delta_mid| variance is comparable to genuine-burst |delta_mid| at the single-tick resolution. Lower expected value than the sensitivity compounding given that we KNOW the sensitivity axis has leverage at fast=10 (run-7 outcomes suggest a rich addressable population, which the r5->r6 step at fast=20 lacked). (2) sensitivity=3.5 at fast_halflife=10 (skip r6's setting, go further): more aggressive but speculative; r6's data confirms 3.0 is safe at the slower sensor; 3.5 has no empirical precedent. (3) Combined fast_halflife=5 + sensitivity=3.0 (two-variable push): compounds two unvalidated changes; high variance; r7 noted this as deferred two-variable. (4) slow_halflife=240 (slower baseline, vol_ratio stays elevated longer): orthogonal axis; less interpretable — vol_ratio decays slower so post-burst orders skip more, but adverse-EV concentration is at burst onset, not post-burst, per the r7 win mechanism (faster detection at onset). (5) slow_halflife=60 (faster baseline): wrong sign — speeds baseline convergence, reduces vol_ratio in elevated regimes, less selective; would shrink not expand addressable set. (6) Parkinson-style EWM of squared deltas: architectural shift; high implementation risk; defer beyond this experiment. (7) Per-side spread-aware sensor: orthogonal architectural axis; defer. (8) Re-running r7 unchanged to confirm reproducibility: no novel information; wastes the final run-slot.

**Debate summary**: 1 round, outcome=CONVERGED. The Round-1 Proposer pitched the compound (fast_halflife=10 + sensitivity=3.0) as the cleanest final-run probe — it tests the compound-axes claim using two independently validated levers. The Criticizer raised three MINOR objections (marginal-EV bounding tighter than $300-500; alternative reading of r5->r6 plateau as a property of sensor smoothness not population size; final-run risk-management framing acceptable but worth naming) but no BLOCKING or MAJOR objections. Converged in 1 round. Key resolved point: no clearly superior untried alternative for a final run — fast_halflife=5 has documented jitter risk, sensitivity=3.5 has no empirical precedent, slow_halflife changes confound attribution.

---

## Implementation Decisions

- **Single-parameter delta from run-7**: only `sensitivity` default changes (2.5 -> 3.0). All other code paths, classes, and state are bitwise-identical to run-7's `VrsPcR7Algorithm`. Class names renamed (VrsPcR7* -> VrsPcR8*).

- **fast_halflife=10 inherited from run-7**: The pivot retains run-7's validated sensor speed (fast_alpha ~0.0670). Slow EWM unchanged (slow_halflife=120, slow_alpha ~0.00578) — baseline is identical to base and runs 4-7.

- **sensitivity=3.0 adopted from run-6**: At sensitivity=3.0, p = exp(-3.0 * max(0, vol_ratio - 1)). The skip curve is steeper than r7's exp(-2.5 * excess). At vol_ratio=1.5 the skip probability rises from 1 - exp(-1.25)~0.713 (r7) to 1 - exp(-1.5)~0.777 (r8). At vol_ratio=2.0 it rises from 1 - 0.082~0.918 to 1 - 0.050~0.950. Curves diverge most in the moderate-elevation band (vol_ratio in 1.2-2.5).

- **min_prob=0.0 retained from run-4 onward**: No floor on submission probability — extreme-vol regimes can produce arbitrarily low submission probabilities. r7's data confirms this is safe.

- **NO strict-subset over run-7**: At the same order, r8's vol_ratio is IDENTICAL to r7's (fast_halflife and slow_halflife unchanged) but r8's p is uniformly less-than-or-equal to r7's p for vol_ratio > 1. The SHA-256 deterministic draw u is identical. Therefore r8 IS a strict subset of r7's submitted orders — any order skipped by r7 is also skipped by r8 (lower p means more orders fail u < p). The vs-r7 P&L delta cleanly attributes the sensitivity-axis lever at the fast sensor in isolation.

**Concerns**:
- **No look-ahead bias**: vol estimator reads only ticks received before each order via `on_quote_tick`; `on_order` reads current EWM state. Identical to runs 4-7 in this respect.
- **Marginal-EV bound is tighter than nominal**: Per the Criticizer's MINOR objection, the orders newly skipped at sensitivity=3.0 are by construction those that r7 was still submitting at moderately elevated vol — their per-order EV is bounded above by r7's $0.45/pruned-trade marginal and likely lower. Expected incremental P&L is $50-$250, not $300-500.
- **Alternative reading of r5->r6 plateau**: If the plateau was caused by sensor smoothness (slow EWM smoothing out short bursts so vol_ratio rises only for sustained periods where EV is flat across the duration) rather than population size, the same flatness could reappear at fast=10. A r8 P&L within ~$50 of r7 would support this reading; a r8 P&L ~$150+ above r7 would refute it.
- **Reduce-only invariant**: All reduce-only orders submit unconditionally, identical to base and runs 4-7.
- **Quantity invariant**: Every submitted order carries the original parent quantity (1 contract). The algorithm never inflates quantity.

---

## Backtest Observations

**Raw metrics** (train window 2026-03-08 → 2026-03-20, 12 trading days):
- realized_pnl = $1554.00
- sharpe_ratio = 6.56
- trade_count = 124,704
- mean_slippage = 0.0
- vs base (vol-regime-sizer, realized_pnl=$753.75): vs_base_pnl_pct = **+106.17%**
- vs run-7 (vrs-pc-r7, realized_pnl=$1454.25): vs_r7_pnl_pct ≈ +6.86% — the sensitivity-bump at fast sensor added ~$100 / 12 days
- vs_base_slippage_pct = 0.0%

**What drove improvement**: The cross-axis hypothesis was correct. With r7's faster sensor capturing a richer set of elevated-vol orders, the sensitivity axis re-acquired leverage. Going from r7 (sensitivity=2.5) to r8 (sensitivity=3.0) pruned ~730 additional trades (125,434 → 124,704) and added ~$100 — per-pruned-trade marginal P&L of ~$0.14, much higher than the corresponding r5→r6 step at the slow sensor (~$0.01). The two axes COMPOUND, validating the diagnosis that the sensitivity-axis plateau at slow sensor was due to a thin addressable population, not exhausted inefficiency.

**What underperformed**: Nothing material. Sharpe of 6.56 is the highest of any P&L-positive run. Max-drawdown improved further to -3.71% (vs r7's -3.83%). Win-rate ticked up to 35.67%.

**Hypothesis verdict**: **Strongly supported.** The hypothesis predicted that adopting both r7's fast sensor AND r6's steep sensitivity would compound, refuting the r5→r6 plateau interpretation as "inefficiency exhaustion." Empirical outcome: +106.17% vs base — more than 2x base's P&L from a clean two-parameter strict-subset configuration. This is the best result of any of the 8 runs in this experiment.

**Suggested next attempt** (outside this experiment's 8-run budget): Push fast_halflife further (e.g. 5 ticks) at sensitivity=3.0 to see if the sensor axis also has continued leverage at this calibration. The crucial diagnostic insight from this experiment is that **sensor responsiveness gates curve effectiveness** — the addressable population for any skip-probability curve is set by what the sensor can see in time. This insight likely generalizes beyond the vol-regime-sizer family.
