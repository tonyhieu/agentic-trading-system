# Algorithm Notes: vrs-pc-r6

## Hypothesis

**Mechanism**: Raise sensitivity from 2.5 (run-5) to 3.0 while keeping min_prob=0.0. All other base parameters preserved exactly (fast_halflife=20 ticks, slow_halflife=120 ticks, min_ticks=30, max_vol_ratio=5.0, SHA-256 deterministic draw on client_order_id, reduce-only pass-through unconditional). The skip-probability curve becomes p = exp(-3.0 * max(0, vol_ratio - 1)) with no floor. Strict-subset property over run-5: for all vol_ratio > 1.0, p_r6 < p_r5, so submission set is a STRICT SUBSET of run-5's.

**Inefficiency exploited**: Three empirical data points triangulate the sensitivity axis cleanly: sensitivity=1.0 (run-3) → -30.18%; sensitivity=2.0 (run-4 with min_prob=0.0) → +0.70%; sensitivity=2.5 (run-5 with min_prob=0.0) → +17.88%. Joint with run-3's opposite-direction loss, the gradient is unambiguous: STEEPER curve helps. The 0.5-step from 2.0→2.5 pruned ~1.3k trades (127.9k → 126.7k) and added ~$130 P&L — i.e. high marginal adverse-EV per pruned trade in the moderate-elevated band. Run-6 tests whether the gradient continues at 2.5→3.0.

**Why it survives costs**: Zero slippage and zero commission (verified). Edge from realized P&L only. Strict-subset property over run-5 caps the downside: any trade run-5 skipped is also skipped by run-6, so vs-run-5 P&L delta cleanly attributes the sensitivity-bump axis. Projected trade_count ~123-125k (extrapolating ~1.5-3k more pruning from the 2.5→3.0 step) — still in healthy regime, no cliff.

**Builds on**: vrs-pc-r5 (PASS, +17.88% vs base — best result so far). Single change: sensitivity 2.5 → 3.0.

**Alternatives considered**: (1) sensitivity=3.5 (more aggressive): higher cliff risk; prefer the validated 0.5-step gradient. (2) sensitivity=2.75 (more conservative): smaller step; effect may be lost in variance noise. (3) sensitivity=3.0 + min_prob=0.05: would discard the strict-subset property over runs 4-5. (4) Two-variable changes (e.g., sensitivity + fast_halflife): confounded attribution; defer. (5) Different vol estimator (Parkinson, spread-based): orthogonal axis; defer until sensitivity is exhausted. (6) Asymmetric directional gating: falsified family from run-1.

**Debate summary**: 1 round, outcome=CONVERGED. The Round-1 Proposer pitched sensitivity=3.0 as the natural extension of the run-3 → run-4 → run-5 empirical gradient with bounded downside via the strict-subset over run-5. The Criticizer raised no BLOCKING or MAJOR objections and converged to PASS in a single round.

---

## Implementation Decisions

- **Single-parameter delta from run-5**: only `sensitivity` default changes (2.5 → 3.0). All other code paths, classes, and state are bitwise-identical to run-5's `VrsPcR5Algorithm`.
- **Strict-subset property over run-5**: For all vol_ratio > 1.0, exp(-3.0 * excess) < exp(-2.5 * excess), so p_r6 < p_r5 at every order. With the SHA-256 deterministic draw on client_order_id, any order run-5 skips (u >= p_r5) is also skipped by run-6 (u >= p_r5 > p_r6).
- **Per-vol-bin payoff attribution**: For backtest observation, compare to BOTH base (vol-regime-sizer) and run-5 (vrs-pc-r5). The vs-base headline mixes the sensitivity-bump (run-4 → run-5 → run-6) and the floor-removal (base → run-4); the vs-run-5 comparison isolates the sensitivity-bump alone.

**Concerns**:
- **No look-ahead bias**: vol estimator state identical to runs 4-5 and base.
- **Cliff risk at sensitivity=3.0**: Run-5 cliff was mild (~1.3k trade-count drop from run-4); extrapolating linearly suggests ~1.5-3k more drop here. If the moderate-band marginal trades that run-6 newly skips are actually net-positive-EV (rather than net-negative-EV), the downside is ~2x run-5's effect — meaningful but bounded.
- **Reduce-only invariant**: All reduce-only orders submit unconditionally, identical to base and runs 4-5.
- **Quantity invariant**: Every submitted order carries the original parent quantity (1 contract).

---

## Backtest Observations

**Raw metrics** (train window 2026-03-08 → 2026-03-20, 12 trading days):
- realized_pnl = $900.75
- sharpe_ratio = 3.77
- trade_count = 125,789
- mean_slippage = 0.0
- vs base (vol-regime-sizer, realized_pnl=$753.75): vs_base_pnl_pct = **+19.50%**
- vs run-5 (vrs-pc-r5, realized_pnl=$888.50): vs_r5_pnl_pct ≈ +1.38% — the marginal 0.5-step on sensitivity (2.5→3.0) added ~$12 / 12 days
- vs_base_slippage_pct = 0.0%

**What drove improvement**: The strict-subset property over run-5 held. Run-6 pruned ~900 additional trades vs run-5 (126,677 → 125,789) and added ~$12 P&L. The gradient on the sensitivity axis remains positive but is plateauing.

**What underperformed**: Marginal returns to sensitivity-bumping are shrinking sharply. The 2.0→2.5 step (run-4→run-5) added ~$130 from ~1.3k pruned trades; the 2.5→3.0 step (run-5→run-6) added only ~$12 from ~900 pruned trades. Per-pruned-trade marginal P&L dropped from ~$0.10 to ~$0.01 — an order of magnitude.

**Hypothesis verdict**: **Supported, but with weakening signal.** The hypothesis predicted continuation of the run-3 → run-4 → run-5 gradient. Empirically the gradient continues in sign but is decaying fast in magnitude. The moderate-band trades that runs 5→6 newly skip are still net-adverse-EV on average, but only mildly so. The bulk of the addressable inefficiency has been extracted by sensitivity=2.5.

**Suggested next attempt**: The sensitivity axis appears nearly exhausted at this calibration. Two natural next probes: (a) Cross-axis combo: combine the best sensitivity (3.0 or 2.5) with a faster halflife (e.g. 10 ticks for the fast EWM) to test whether the bursts that should trigger skipping are being detected too slowly. (b) Try sensitivity=3.5 once more for a clean refusal — if no improvement (or worse: regression), declare 2.5-3.0 the local optimum and pivot to a structurally different lever (e.g. a microstructure liquidity signal complementary to the |delta_mid| estimator).
