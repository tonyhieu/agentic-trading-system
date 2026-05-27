# Algorithm Notes: ptg-pc-r2

## Hypothesis

**Mechanism**: LOSS-COOLDOWN gate, layered on top of position-tier-gate (cap=1) verbatim. The exec algorithm subscribes to position-close events via on_position_closed(). When a position closes, it reads position.realized_pnl. If realized_pnl < 0 (a losing round trip), it sets cooldown_until_ts = self.clock.timestamp_ns() + cooldown_ns (default cooldown_ns = 1_000_000_000, i.e. 1 second, matching the oracle's 1Hz signal cadence). On each subsequent OPEN order in on_order(), AFTER passing the position-cap=1 gate, check: if self.clock.timestamp_ns() < cooldown_until_ts, SKIP the OPEN. CLOSE orders (is_reduce_only=True) always submit unchanged - we never block exits. Initial cooldown_until_ts = 0 (no cooldown active at session start).

**Inefficiency exploited**: Loss clustering. The base wins only 37.2% of round trips - 63% are losers. Losses are not i.i.d.; they cluster in choppy/noisy regimes (verified in base NOTES: 'high-noise days 20260312, 20260313, 20260316, 20260317 where the oracle flip-flops rapidly'). After a losing close, the immediate next OPEN signal arrives within the same noisy regime and is disproportionately likely to also lose. A short 1-second cooldown - just the oracle's signal cadence - skips the immediate-next-signal in those regimes without significantly impacting trend periods (where losses are rare and consecutive signals are correct). Expected activation: 63% of ~7,500 closes/day = ~4,725 cooldowns/day, each skipping ~1 OPEN. Total OPEN skips ~4,725/day vs base ~7,500/day = ~63% additional trade-count reduction.

**Why it survives costs**: Mean slippage stays 0 (no change to order type or pricing). Commissions are 0 in simulator. The mechanism only reduces trade count via filtering - it cannot worsen execution costs. If the loss-clustering premise is wrong (losses are i.i.d.), worst-case outcome is trade count drops while win rate stays ~37.2%, yielding lower PnL than base. If the premise is right (losses cluster), win rate of the surviving trades rises and PnL improves.

**Builds on**: position-tier-gate (cap=1 retained verbatim as the first gate; loss-cooldown is an additive filter applied AFTER cap=1 passes, only for OPEN orders). Pivots away from r1's signal-consensus (which was empirically inert) and from r2-round-1's passive-maker (which had the skip-on-expiry inversion BLOCKING).

**Alternatives considered**: (1) Round-1 passive-maker with chase fallback: chase pays for the worst-case moved-away fills, likely net negative - declined. (2) Passive-CLOSE with late-session market fallback (criticizer's suggestion): same adverse selection problem on the close side - passive sells fill when market moves up against our exit, and the favorable fills (market moves down) leave us holding into more downside. The asymmetry the criticizer hoped for (let position run if unfilled) cuts both ways; doesn't structurally solve adverse selection. Declined. (3) Marketable-LIMIT price protection: inert in this simulator (slippage already 0). Declined. (4) Spread-conditional anything: MES spread is almost always 1 tick - inert. Declined (r1 lesson). (5) Win-streak conditioning instead of loss-cooldown: symmetric framing, but reinforcing wins is weaker signal than avoiding loss clusters (Bayesian view: a single loss is more informative about regime change than a single win, given asymmetric base rate 37.2%/62.8%). (6) Variable cooldown length (e.g. proportional to loss size): adds parameters without empirical motivation; reserved for follow-up if base mechanism shows promise.

**Debate summary**: 2 rounds, outcome=CONVERGED. Key objections resolved: round 1 BLOCKING (passive-maker skip-on-expiry inversion - filtering OUT correct trades and KEEPING wrong-direction adverse fills) caused abandoning the passive-maker framing entirely in favor of a pure filter on existing MARKET OPENs. Round 1 MAJORs about concurrent-limit cap breach, spawn/cancel API semantics, bid/ask source - all moot under the new framing.

---

## Implementation Decisions

**Hook used**: `on_position_closed(event: PositionClosed)`. Verified in the Nautilus source (nautilus_trader/execution/algorithm.pyx line 471) that this is dispatched to exec algorithms via the position event subscription registered in `register()`. The event carries `realized_pnl` as a `Money` object; we call `.as_double()` to extract the float value.

**Defensive realized_pnl extraction**: try `.as_double()` first; on AttributeError fall back to `float()`; on any other exception treat as zero (no cooldown). Belt-and-braces - prevents a malformed event from raising inside the hook and aborting the run.

**Gate ordering**: position-cap is checked FIRST (cheapest, preserves base behavior), cooldown SECOND (only if cap allows). This way the cooldown only filters OPENs that the base would have submitted.

**Cooldown duration default**: 1_000_000_000 ns = 1.0 second exactly. Matches the oracle's signal cadence per `research/config.yaml -> strategy.kwargs.signal_interval_seconds = 1.0`. Each cooldown blocks exactly the next-second's OPEN signal.

**Initial state**: `_cooldown_until_ts = 0`. The simulator's clock starts at a session timestamp in nanoseconds (large positive integer), so `now_ns < 0` is always false at session start. First OPEN always passes.

**CLOSE pass-through**: reduce-only orders bypass both gates. The mechanism only ever blocks OPEN orders. This preserves intraday_flat compliance - exits always happen.

**Position-cap gate**: identical to the base position-tier-gate code (same `_current_net_qty()` helper using `cache.positions_open()`).

**Session reset**: `on_reset()` clears `_cooldown_until_ts` to 0 defensively. Each backtest date runs in a fresh subprocess so this should rarely matter.

**Concerns**:
- Load-bearing assumption: P(loss | prev was loss) is materially > 63% (the unconditional loss rate). If losses are closer to i.i.d., the mechanism filters trades but doesn't improve win rate of survivors, leading to lower PnL than base. The Criticizer flagged this MAJOR but accepted the bounded-downside framing (no slippage/commission regression).
- Cooldown=1s aligns with the 1.0s oracle cadence. If the strategy's actual emit-times drift slightly (e.g. due to upstream variance), some cooldowns could miss/double-block. Minor robustness concern - the order of magnitude is right.
- Win-rate feedback loop: filtered trades change the population over which win rate is measured. Steady-state analysis is approximate. Acknowledged - not a blocker.

---

## Backtest Observations

**Pre-backtest empirical check (20260312 single-date instrumentation)**: Initial cooldown_ns=1.0s (matching the oracle's nominal 1Hz cadence per config) produced ZERO filter activations - replicating the r1 inert-mechanism trap. Traced the cause: the oracle's actual emit times are not exactly 1.0s apart but typically 1.1-1.5s (signals are scheduled on the next available market tick after the 1.0s schedule). With cooldown=1.0s, the cooldown expired before the next OPEN arrived. Increased cooldown_ns default to 2.0s, which gives the smallest reliable margin to block the immediately-following OPEN signal in the dense regime. Single-date sweep (20260312) at cooldown {1, 2, 3, 5, 10, 30}s showed activations 0/414/521/672/938/1620, and PnL 288.25/279.0/284.5/259.75/259.0/153.5 - the mechanism bites at >=2s but the loss-clustering hypothesis is empirically WEAK (win_rate stays in a tight band 0.418-0.426 across the sweep, while PnL declines roughly with trade count).

**Train window (12 dates, 20260308-20260320) at cooldown_ns=2.0s**:
- ptg-pc-r2: realized_pnl=$4002.00, sharpe=17.19, trade_count=83,924, win_rate=37.26%, max_drawdown=-0.0162%, mean_slippage=0, commissions=0
- base position-tier-gate: realized_pnl=$4262.50, sharpe=17.62, trade_count=90,433, win_rate=37.20%, max_drawdown=-0.0173%, mean_slippage=0
- vs_base_pnl_pct: -6.11% (algo UNDERPERFORMS base; pass gate requires >=+5%)
- vs_base_slippage_pct: 0.00% (both zero - degenerate)
- vs simple baseline (from aggregator backtest-results.json): +2465.38% pnl, sharpe 17.19 vs 0.60

**What drove the result**: The cooldown filter activates and removes ~7% of trades (90,433 -> 83,924). Win rate of survivors changes by only +0.06pp (37.20% -> 37.26%) - essentially zero improvement. Since the filter removes winners and losers nearly proportionally, the trade-count drop translates directly into a roughly proportional PnL drop. Sharpe falls modestly because the same return is generated over fewer trades with similar variance per trade.

**What underperformed**: The loss-clustering hypothesis. The Criticizer flagged this as the dominant empirical risk in round 2 ("the mechanism's success depends critically on P(loss|prev was loss) being materially above 63%"). Empirically, this conditional probability is not materially elevated for this oracle - losses are nearly i.i.d. with respect to the immediate-prior round trip's sign. The cooldown filter therefore acts as a near-uniform random sampler of trades rather than a loss-cluster filter, and PnL/trade is preserved while count drops.

**Hypothesis verdict**: CONTRADICTED. The loss-cooldown mechanism works AS DESIGNED (cooldown arms on losses, blocks the next OPEN within 2s) but the underlying inefficiency it targeted (loss clustering at the 1-2 second horizon for this oracle) does not exist at a magnitude useful for execution-side filtering. Result is a small PnL regression vs base, not a catastrophe (no slippage/commission regression).

**Suggested next attempt**: Two orthogonal directions worth trying. (a) Condition cooldown on the SIZE of the losing close, not just the sign - a 1-tick loss may be noise but a 3+ tick loss may signal regime change. (b) Pivot to a session-level drawdown gate (skip OPENs whenever cumulative realized_pnl drops below a session-PnL trailing peak by more than X) - this targets larger-scale regime breaks rather than per-trade autocorrelation. (c) Abandon the OPEN-filter axis entirely and pursue execution-cost reduction via passive-CLOSE with strict short-timeout-then-market-fallback (the r2-round-1 criticizer's suggestion); the symmetric adverse-selection objection I raised in round 2 is theoretical and worth empirically testing - the worst case is still bounded since fallback guarantees fills.
