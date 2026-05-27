# Algorithm Notes: afg-pc-r3

## Hypothesis

**Mechanism**: Threshold-Lowered AFG with thin-market floor: identical to base AFG (single 10s rolling window of signed aggressor flow over a deque pruned by ts_event; reduce-only always submits; _position_flat=True after skip) EXCEPT (a) flow_threshold lowered from 2.0 to 1.0 (skip BUY when net_flow <= -1.0; skip SELL when net_flow >= +1.0); (b) thin-market noise floor: the gate requires at least min_prints=3 trade prints in the 10s window before it can fire (if len(deque) < min_prints, do NOT skip -- submit unconditionally, identical to AFG's warm-up behavior). All other AFG semantics preserved: trade-tick subscription, look-ahead-free pruning, reduce-only short-circuit.

**Inefficiency exploited**: Base AFG's flow_threshold=2.0 implicitly treats every 1- or 2-contract net adverse imbalance as below the signal-to-noise threshold. But base AFG's empirical evidence (broad 10/12 date wins, +704.8% vs simple) shows its existing skip set is high-precision -- the marginal value of adding skips at lower magnitudes should be positive as long as we filter out trivial-trade-count noise. The thin-market floor (min_prints=3) prevents the lower threshold from firing on near-empty windows where a single small print would gate.

**Why it survives costs**: Zero commission, zero slippage cost model (verified). Edge accrues entirely as realized_pnl. Base AFG: realized_pnl=$1255.50, +704.8% vs simple. Lowering threshold to 1.0 expects skip rate to rise from 21.6% to ~25-30%. If the additional skips are structurally homogeneous with AFG's existing skips (same level criterion, just lower magnitude), they should be similarly precision-positive. Falsifiable prediction: realized_pnl on the 12-day train window will exceed base AFG's $1255.50 by at least 5% (PASS margin).

**Builds on**: aggressor-flow-gate (base) -- preserves every mechanic except (a) lowered threshold (2.0 -> 1.0) and (b) added min_prints=3 thin-market floor. Distinct from afg-pc-r1 (burst-ratio acceleration) and afg-pc-r2 (persistent-chain skipping).

**Alternatives considered**: Block-aggression gate (round 1, rejected: not empirically grounded at MES sizes). Dual-window confirmation (round 2, rejected: structural tightener, inherits r1's fewer-skips problem). Lower threshold without min_prints floor (rejected: misfires in thin windows). Threshold=0.5 (rejected: too aggressive for first attempt). min_prints=5 (rejected: too restrictive; 3 is minimal anti-noise guard).

**Debate summary**: 3 round(s), outcome=CONVERGED. Key objections resolved: round 1 block-aggression mechanism abandoned due to lack of MES microstructure grounding; round 2 dual-window intersection abandoned because it inherits r1's fewer-skips failure mode; round 3 converged on a single-knob threshold-lowering test with a principled thin-market noise guard.

---

## Implementation Decisions

- Reused the base AFG architecture verbatim (deque of signed (ts_event_ns, signed_vol) tuples, O(1) net_flow running sum, prune-by-ts_event).
- Only two material changes from base AFG: `flow_threshold` default 1.0 (was 2.0) and a `min_prints=3` floor checked before evaluating the gate.
- min_prints check uses `len(self._flow_deque)` after pruning -- so it counts trade prints inside the current 10s window only.
- Anti-cascade (`_position_flat=True` after skip) unchanged. Reduce-only unchanged.

**Concerns**: Parameter risk on both flow_threshold=1.0 (could be 0.5 or 1.5) and min_prints=3 (could be 2 or 5). No look-ahead risk -- the only data read is the deque of past trade prints pruned to events with ts_event >= order.ts_init - window_ns.

---

## Backtest Observations

**Raw results (train window, 12 dates)**:
- afg-pc-r3: realized_pnl=$1251.75, sharpe=5.573, trade_count=107,083, mean_slippage=0.0, max_drawdown_pct=-0.0327%, win_rate=35.51%
- base AFG: realized_pnl=$1255.50, sharpe=5.594, trade_count=107,198, mean_slippage=0.0, max_drawdown_pct=-0.0332%, win_rate=35.49%
- vs base AFG pnl: -0.299% (FAIL the +5% gate)
- vs base AFG slippage: 0.0% (flat)
- vs simple baseline: +702.4% (basically unchanged from AFG's +704.8%)

**What drove improvement**: Nothing material. Trade count only fell by 115 (107,198 -> 107,083) -- ~0.1% -- which strongly suggests the lowered threshold from 2.0 to 1.0, combined with the min_prints=3 floor, produced almost no additional skips in practice. The algo behaves essentially identically to base AFG on this train window.

**What underperformed**: The hypothesis that "more skips at lower flow magnitudes will be precision-positive" is falsified, but for an unexpected reason: the additional skips barely fired at all. This implies one of two things: (a) the min_prints=3 floor was too restrictive in moments where net_flow was in the 1.0-2.0 range (when net_flow is small, the underlying activity is likely also small), so the floor blocked most candidate-new-skips; or (b) the distribution of |net_flow| in the 10s window is bimodal -- either well below 2.0 (mostly 0) or well above (a couple contracts adverse residual is rare in this market). Either way, the parameter change did not produce the behavioural change the hypothesis predicted.

**Hypothesis verdict**: Falsified -- realized_pnl flat-to-slightly-worse vs base AFG (-0.3%), well below the +5% PASS gate. The net effect of the parameter change in this configuration was essentially null.

**Suggested next attempt**: Either (a) drop min_prints to 2 (or remove it entirely) and re-test threshold=1.0 to see if the floor was the binding constraint; or (b) shift to a fundamentally different axis -- the prior three pc attempts (r1 burst, r2 chain, r3 threshold) all underperformed AFG, suggesting AFG's mechanics on this train window are at a local optimum and the next attempt should consider an orthogonal signal (e.g., spread-state at order arrival, top-of-book queue depletion rate) rather than further refinements of the signed-aggressor-flow primitive.
