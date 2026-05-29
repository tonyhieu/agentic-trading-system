# Algorithm Notes: afg-pc-r4

## Hypothesis

**Mechanism**: Extended-Chain AFG (clean): identical to afg-pc-r2 in every respect (signed 10s flow window over a deque pruned by ts_event, 2.0 flow_threshold, directional-chain state machine — start chain on first adverse gate firing; extend chain only on same-side adverse follow-ups; direction-change immediately force-submits and resets state; reduce-only always submits; _position_flat first-signal warm-up; on_reset clears all state) EXCEPT max_consecutive_skips raised from 3 to 5.

**Inefficiency exploited**: r2's directional-chain captures persistent adverse-flow regimes but caps at 3 consecutive same-direction skips. r2's per-date breakdown shows P&L deltas concentrated on heavy-volume persistent-regime days. If the persistent regimes on those days exceed 3 oracle signals (~3s), the cap is binding and r2 is leaving suppression on the table. Raising cap to 5 directly tests whether r2's cap is currently the constraint.

**Why it survives costs**: Zero commission, zero slippage cost model. r2: $1093.25; base AFG: $1255.50. Falsifiable prediction: realized_pnl on the 12-day train window will exceed base AFG's $1255.50 by at least 5% (PASS gate). Failure modes: (a) cap not binding in practice (regimes rarely exceed 3 same-direction signals) — algo behaves identically to r2; (b) cap binding but additional skips are precision-negative (deferred entry is worse than r2's earlier force-submit).

**Builds on**: afg-pc-r2 (Persistent-Flow AFG with directional-chain). One-knob coordinate-descent step — max_consecutive_skips 3 -> 5 — verbatim from r2's suggested-next-attempt #1.

**Alternatives considered**: Magnitude-conditional cap (round 2, rejected: two-knob confound). Per-session reset heuristic (round 2, rejected: unvalidated). Orthogonal-axis gate (rejected: r3 underperformed on that direction). cap=4 (rejected as too-small step). cap=10/unbounded (rejected: unsafe deferred-entry risk).

**Debate summary**: 3 round(s), outcome=CONVERGED. Key objections resolved: round 1's clean single-knob proposal was criticized for ignoring r2's state-leakage concern; round 2 over-corrected with a two-knob magnitude-conditional + session-reset design (rejected as confound); round 3 returned to the clean single-knob test as round-2 criticizer recommended, deferring state-leakage analysis to post-backtest.

---

## Implementation Decisions

- Verbatim re-implementation of afg-pc-r2's directional-chain state machine (no behavioural changes to first-signal warm-up, direction-change reset, gate criterion, reduce-only short-circuit, or on_reset semantics).
- Only difference vs r2: `max_consecutive_skips` default raised from 3 to 5. All other config parameters preserved exactly (window_seconds=10.0, flow_threshold=2.0).
- No look-ahead: deque pruned by `order.ts_init - window_ns` at decision time, identical to base AFG and r2.
- Quantity invariant: never modifies `order.quantity`; only submits or skips.

**Concerns**:
- State-leakage (per r2 NOTES): chain state may accumulate across sessions within a multi-date subprocess. The backtest engine's per-date subprocess isolation should make this moot (each date gets a fresh process and a fresh algo instance) but the per-date skip-rate progression should be inspected post-backtest. If r4's per-date skip rate progresses monotonically the same way r2's did (17%->35%), the state-leakage hypothesis is likely benign or both r2 and r4 are governed by the same path-dependent dynamic.
- cap=5 vs cap=4 is a parameter choice without principled basis beyond a larger step size revealing more curvature.

---

## Backtest Observations

**Raw results (train window, 12 dates, --use-cached-baseline)**:
- afg-pc-r4: realized_pnl=$710.25, sharpe=3.412, trade_count=89,421, mean_slippage=0.0, max_drawdown_pct=-0.0318%, win_rate=35.05%, is_weighted_bps=0.0516
- base AFG:  realized_pnl=$1255.50, sharpe=5.594, trade_count=107,198, mean_slippage=0.0
- afg-pc-r2: realized_pnl=$1093.25, sharpe=5.265, trade_count=92,049
- simple baseline: realized_pnl=$156.00, trade_count=136,734
- vs base AFG pnl: **-43.43%** (FAIL the +5% gate)
- vs base AFG slippage: 0.0%
- vs simple baseline: +355.29%

**What drove improvement**: Nothing vs base AFG. vs simple baseline the algo still wins very large (+355%), but the headline experiment is vs base AFG and there it underperforms.

**What underperformed**: Raising max_consecutive_skips from 3 (r2) to 5 reduced realized_pnl from $1093.25 to $710.25 — a $383 regression. Trade count dropped from r2's 92,049 to 89,421 (~2,600 fewer trades, confirming the cap was binding in some chains). The additional skips beyond the third are precision-NEGATIVE: deferring entries for chain positions 4 and 5 yields a worse fill outcome than r2's force-submit at position 4. This is the inverse of the hypothesized direction — r2's cap=3 was apparently already past the local optimum or close to it, and r4's cap=5 over-suppresses.

**Hypothesis verdict**: **FALSIFIED**. The hypothesis predicted cap=5 would extend regime suppression on heavy-volume days and increase realized_pnl by >=5% vs base AFG. Reality: realized_pnl fell 35% vs r2 and 43% vs base AFG. The implication: r2's chain mechanism captures most of the available regime-suppression edge at cap=3; extending the chain past 3 same-direction signals systematically defers entries into worse prices than the force-submit-and-reset alternative. The "persistent regimes exceed 3s" intuition was wrong — most regimes either clear within 3s or extend long enough that the deferred entry at position 5 is into a worse mean-reverted price than the immediate entry at position 4.

**Suggested next attempt**: (a) Try cap=2 (smaller than r2's 3) — the response surface curvature suggests the optimum may be at cap<3, not cap>3; (b) Alternatively, KEEP r2's cap=3 and investigate the per-date skip-rate progression (16.9%->35.2%) flagged in r2's NOTES to determine whether the apparent edge in r2 is genuine regime detection or a path-dependent artifact of accumulating chain state; (c) Try `max_consecutive_skips=3` (r2 verbatim) but add a `flow_threshold` adjustment for chain positions 2 and 3 (require stronger adverse flow to keep chain alive past first skip) — couples chain-extension to ongoing signal strength.
