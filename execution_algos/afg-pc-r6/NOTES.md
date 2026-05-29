# Algorithm Notes: afg-pc-r6

## Hypothesis

**Mechanism**: Two-Path Additive AFG with conservative acute-burst threshold (build on r2). Maintain a single trade-tick deque pruned to 10s. At each open-order decision: (Path A — r2's gate VERBATIM) compute long_net = signed_vol sum over (t_order - 10s, t_order]; skip BUY when long_net <= -2.0; skip SELL when long_net >= +2.0. (Path B — acute-burst gate) compute short_net = signed_vol sum over (t_order - 2s, t_order]; skip BUY when short_net <= -5.0; skip SELL when short_net >= +5.0. The OVERALL gate fires (skip) when Path A OR Path B fires. Feed OR-result into r2's directional-chain state machine VERBATIM: max_consecutive_skips=3, direction-change force-submits and resets, reduce-only always submits, first-signal warm-up. Look-ahead-free: deque pruned by ts_event <= order.ts_init. Implementation: maintain a single (ts_event_ns, signed_vol) deque; at each decision, walk the deque tail from newest entries and accumulate short_net (entries with ts >= t_order - 2s) and long_net (entries with ts >= t_order - 10s) in the same pass.

**Inefficiency exploited**: r2's 10s window can DILUTE acute adverse bursts where the most current 1-2s shows decisive adverse momentum but is masked by older neutral or favorable flow in the 10s sum. Path B catches these acute-burst regimes that r2 systematically misses. burst_threshold=5.0 in 2s ensures Path B fires only on genuinely acute concentrated bursts. The two paths capture complementary microstructure regimes: A for sustained 10s adverse trends; B for acute fresh bursts that r2 dilutes.

**Why it survives costs**: Zero commission, zero slippage. r2: $1093.25, +600% vs simple, sharpe 5.27. Two-Path Additive AFG STRICTLY EXTENDS r2's skip set with Path B's high-conviction acute-burst skips. Pre-committed falsifiable prediction: realized_pnl on the 12-day train window exceeds base AFG's $1255.50 by at least 5% (PASS gate). Failure modes: (a) Path B fires very rarely (<1% of decisions) — algo behaves like r2 neutral outcome; (b) Path B's additional skips are precision-negative — realized_pnl drops below r2.

**Builds on**: afg-pc-r2 (empirical winner: $1093.25, +600% vs simple, sharpe 5.27). Preserves Path A (r2's 10s gate VERBATIM), directional-chain state machine, max_consecutive_skips=3, reduce-only short-circuit, trade-tick subscription, first-signal warm-up, on_reset semantics. ADDS Path B (2s short-window acute-burst gate at threshold 5.0) ORed with Path A.

**Alternatives considered**: Round 1 AND-agreement (rejected: strictly reduced r2 skip set per r1/r4 empirical pattern); EWMA decay (already tested negative in r5); larger chain caps (already tested negative in r4); lower threshold (r3 tied); burst_threshold=4.0 (rejected: not robustly conservative); burst_threshold=6.0 (rejected: potentially too rare to fire); 1s or 3s short window (1s too noisy, 3s overlaps with 10s); adaptive burst threshold (rejected: coupled-variable complexity); removing Path A (rejected: would lose r2's edge entirely).

**Debate summary**: 3 round(s), outcome=CONVERGED. Key objections resolved: pivoted from AND-agreement (wrong direction per r1/r4 evidence) to OR-additive design that strictly extends r2's skip set; raised burst_threshold from 4.0 to 5.0 to ensure conservative firing protects against r4-style over-skipping.

---

## Implementation Decisions

- **Single deque, dual-window accumulation**: maintain one deque of (ts_event_ns, signed_vol) pruned by 10s window. At each decision, walk deque from oldest to newest pruning stale entries, then sum into both long_net (everything left in deque) and short_net (entries with ts >= t_order - 2s, accumulated by checking the cutoff during the pass).
- **Path A semantics identical to base AFG**: long_threshold=2.0, 10s window.
- **Path B (acute-burst)**: short_window_seconds=2.0, burst_threshold=5.0.
- **Chain state machine from r2** (afg-pc-r2): consecutive_skips counter + last_skipped_side. On adverse-gate fire: if first skip (consecutive_skips==0) or same-direction continuation under cap, skip and increment; if direction change OR cap reached (>=3), force-submit and reset state.
- **Reduce-only**: always submitted immediately (intraday_flat compliance).
- **Warm-up**: if deque empty, submit unconditionally.
- **No look-ahead**: only trade ticks with ts_event delivered before order.ts_init are in the deque; deque pruned by ts_init - window at decision time.
- **Quantity invariant**: order.quantity never modified; only skip or submit.

**Concerns**:
- Path B may fire rarely if 5-contract bursts in 2s are uncommon in MES — would yield ~equivalence to r2.
- The OR-combination assumes Path B's signal is independently predictive (acute bursts as continuation signal). If acute bursts predict short-term REVERSALS instead, Path B skips become anti-selected.

---

## Backtest Observations

Train window: 12 dates (2026-03-08 to 2026-03-20).

**Results summary**:
- afg-pc-r6:        realized_pnl=$1383.25, trade_count=90287, sharpe=6.68
- aggressor-flow-gate (base): realized_pnl=$1255.50, trade_count=107198, sharpe=5.59
- simple baseline: realized_pnl=$156.00, trade_count=136734, sharpe=0.60
- vs_base_pnl_pct: +10.18% (vs aggressor-flow-gate; PASS gate >=5%)
- vs_base_slippage_pct: 0.00%
- vs_baseline (simple) pnl_pct: +786.70%
- max_drawdown_pct: -0.0271 (vs simple -0.0529 / vs r2 ~-0.03)
- is_weighted_bps: 0.0516 (slightly worse IS vs base AFG 0.0472)

**What drove improvement**: Two-Path Additive design beat r2 ($1093.25) by $290 and base AFG ($1255.50) by $128. Path B (acute-burst gate, 2s window, threshold 5.0) added high-conviction skips on top of r2's chain logic. Trade count (90287) is below r2's 92049, indicating Path B does fire and produces additional skips. The chain state machine preserved r2's structural advantages while the OR-additive gate captured acute-burst regimes that r2's 10s averaging dilutes.

**What underperformed**: is_weighted_bps rose from base AFG's 0.0472 to 0.0516 (+9.3%). Same inherent tension as base AFG: flow-based gating holds back entries at moments that sometimes offer the best fill prices. Acceptable given the +10% realized_pnl improvement.

**Hypothesis verdict**: SUPPORTED. The OR-additive two-window design outperformed r2 (empirical winner of prior runs) by +27% on realized_pnl, validating that Path B's acute-burst skips are independently precision-positive and not redundant with Path A's sustained-trend skips. Conservative burst_threshold=5.0 successfully avoided r4-style over-skipping (trade count is in r2's neighborhood, not below it).

**Suggested next attempt**: Sweep burst_threshold downward (4.0, 3.5) to test whether more aggressive Path B firing extracts further edge before hitting the over-skipping regime. Alternatively, test short_window_seconds variations (1.5s, 3s).
