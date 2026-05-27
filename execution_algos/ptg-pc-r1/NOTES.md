# Algorithm Notes: ptg-pc-r1

## Hypothesis

**Mechanism**: Layer a signal-consensus filter on top of position-tier-gate. The exec algorithm maintains a rolling buffer of the last K OPEN-order directions observed at on_order() (whether the cap eventually submits or skips them). When a new OPEN passes the cap=1 gate, compute the fraction of recent OPEN directions in the buffer matching the new OPEN's direction; if below agreement_threshold (default 0.6 with K=5), SKIP. Otherwise SUBMIT. CLOSE (is_reduce_only=True) orders always submit. Buffer starts empty; during the first K observations, default to SUBMIT (warmup).

**Inefficiency exploited**: Oracle noise (sigma=6.0, ~14% R^2). Most individual signals contain more noise than signal. When consecutive directional decisions disagree, the local stream is noise-dominated; when they agree, persistence is evidence of real edge. The base algo wins at only 37.2% - the consensus filter shifts that distribution by selecting signals more likely to be on the persistent side of the noise floor.

**Why it survives costs**: Mean slippage is 0, commissions are 0 in this simulator (verified from base backtest-results.json). The filter only reduces trade count - it cannot worsen execution costs. Strictly a P&L-by-trade-selection mechanism.

**Builds on**: position-tier-gate (cap=1 retained verbatim; consensus filter is an additional gate applied AFTER the position-cap check passes).

**Alternatives considered**: (1) Original blocked-reversal trigger from round 1 - dropped due to logical incoherence (the dominant cap-block case is the same-ts_init CLOSE+OPEN pair, so the 'blocked direction' is by construction the opposite of the just-closed position). (2) Wider K (e.g. 10) - more stable but more lag; reserved for follow-up tuning. (3) Magnitude-based filter - not available; signal magnitude is not exposed to the exec algo, only orders. (4) Signed/directional position cap - subsumed by K=1 consensus, weaker. (5) Cross-tick spread/volume microstructure filters - different conditioning axis; deferred to a different experiment.

**Debate summary**: 2 rounds, outcome=CONVERGED. Key objections resolved: round 1 BLOCKING (logical incoherence of blocked-reversal framing) and two MAJORs (choppy-day destruction risk and superior untried alternative) were addressed by pivoting to a symmetric, evenly-spaced rolling-window consensus filter that the round-1 Criticizer itself suggested.

---

## Implementation Decisions

**Filter ordering**: position-cap check first; consensus check only on OPENs the cap allows. This preserves the base algo's cache-timing exploit (cap=1 blocks the concurrent CLOSE+OPEN at the same ts_init) and adds the consensus filter on top of the surviving OPENs.

**Buffer update site**: buffer updates on every OPEN observed at `on_order()`, regardless of whether the cap blocks or the consensus filter blocks. This preserves an evenly-spaced view of the oracle's directional signal stream (1Hz cadence per config). If we only updated on submitted orders, the buffer would over-represent the spaced-out signals the cap lets through and lose the actual signal cadence.

**Direction read**: `order.side` - the Nautilus `OrderSide` enum (BUY=1, SELL=2). Unambiguous; no need to relate to the existing position direction.

**Defaults**: `position_cap=1` (matches base algo), `consensus_k=5` (5 second window at 1Hz oracle cadence), `agreement_threshold=0.6` (3-of-5 majority).

**CLOSE orders**: pass through unconditionally (intraday_flat compliance, exposure reduction). They never enter the buffer.

**Warmup**: when fewer than K OPENs have been observed, the filter defaults to SUBMIT (do not block during warmup). Affects only first 5 OPENs per session.

**Session reset**: each backtest date runs in a fresh subprocess (per scripts/run_research_backtest.py), so the algo instance is fresh per day - buffer naturally resets without explicit on_reset() logic. on_reset() is still implemented (no-op) for safety.

**Concerns**:
- The threshold 0.6 with K=5 is a reasonable starting point but not empirically tuned for this oracle. If the consensus filter over-blocks (trade count drops too far), the surviving trades may not compound to a net win.
- The premise that "agreeing recent signals" tracks real edge depends on serial structure in the oracle's correct decisions vs i.i.d. noise. If both are i.i.d., the filter is a near-no-op (trade count drops but win rate ~ unchanged), yielding PnL similar to base.
- No look-ahead risk: buffer is populated solely from past on_order() invocations.

---

## Backtest Observations

**Train window (12 dates, 20260308–20260320)**:
- ptg-pc-r1: realized_pnl=$4262.50, sharpe=17.62, trade_count=90,433, win_rate=37.20%, max_drawdown=-0.0173%, mean_slippage=0.0, commissions=0.0
- base position-tier-gate: realized_pnl=$4262.50, sharpe=17.62, trade_count=90,433, win_rate=37.20%, max_drawdown=-0.0173%
- vs_base_pnl_pct: 0.00%
- vs_base_slippage_pct: 0.00% (mean_slippage was 0 in base; degenerate)

**Per-date spot check (base vs r1)**: byte-identical metrics on every train date examined (20260308, 20260309, 20260312, 20260317 all show identical realized_pnl and trade_count). The consensus filter never blocked a single order in practice.

**What drove improvement**: Nothing - the algo is empirically indistinguishable from the base position-tier-gate. The added consensus filter is inert.

**What underperformed**: The consensus gate. With consensus_k=5 and agreement_threshold=0.6 (i.e., need >=3/5 same direction), the filter is too permissive to bite given the oracle's raw directional stream at the exec-algo boundary. Combined with the position-cap gate ordering (cap checked first), and the fact that the buffer is populated regardless of cap outcome, the consensus condition is satisfied on essentially every OPEN that the cap also allowed. Result: zero filter activations across all 12 train dates.

**Hypothesis verdict**: CONTRADICTED operationally. The hypothesis was that "directional consensus among recent OPENs improves selection." We can't even test the hypothesis because at threshold=0.6/K=5 the filter never fires. The threshold was tuned too low (or K too small) for the oracle stream's directional autocorrelation. The structural claim survives, but the chosen parameters render the mechanism a no-op.

**Suggested next attempt**: Raise agreement_threshold materially (e.g., 0.8 with K=5 = need 4/5 same direction) or widen K to 10 with threshold 0.7 - to verify whether the consensus mechanism can actually bite. If it still produces zero filter activations, the hypothesis is structurally wrong (oracle's directional stream is too persistent / agreement is degenerate at the relevant timescale). If it bites but PnL drops, the hypothesis is empirically wrong (filtered trades were net-positive). Either outcome is informative.
