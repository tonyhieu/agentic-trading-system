# Algorithm Notes: ptg-f-l2

Per-iteration experiment — base_algo `position-tier-gate`, context mode
`full-trace`, loop 2. Starting point: `position-tier-gate` base algo.

## Hypothesis

**Context available (full-trace, loop 2)**: loop 1 full_reasoning + NOTES.md (cap=2
failed: identical to simple; the position_cap lever is binary for this oracle+MES combination;
cap=1 = serialized entry = best; cap>=2 = no-op = simple baseline).

**Mechanism**: Loop 1 established that cap changes don't work — the only useful
direction is to keep cap=1 (base) and add an additional filter on top. Loop 2 tries
a **consecutive-loss streak gate**: after N consecutive losing closed positions,
temporarily block the next open-leg order (forcing one missed entry to let the
market "reset"). Losing streaks may correlate with adverse oracle phases (periods
when the oracle's signal is noisy or mean-reverting against the position direction).
Blocking one re-entry during such a phase reduces exposure during low-oracle-quality
periods.

**Inefficiency exploited**: The base algo (cap=1) still re-enters immediately after
each close, including after consecutive losers. If losing streaks indicate temporarily
lower oracle signal quality, a one-skip cooldown after N consecutive losses may improve
the net P&L by sacrificing some trade count to avoid the most adverse re-entry moments.

**Why it survives costs**: Zero-slippage model means skipping a trade has no frictional
cost. The question is purely whether the streak filter correctly identifies bad re-entry
moments. Streaks of N=2 (skip after 2 consecutive losers) are conservative enough to
preserve most of the base's trade volume while filtering the highest-adverse-selection
re-entries.

**Builds on**: `position-tier-gate` base algo (cap=1 preserved). Adds: loss-streak gate.
Single structural addition.

**Alternatives considered**:
- cap=2 (loop 1): proved to be identical to simple baseline. Ruled out.
- Flow-aware gate (combine with aggressor flow): more complex; deferred to loop 3.
- Time-since-last-close cooldown: different mechanism; deferred to loop 4.

---

## Implementation Decisions

- **`position_cap` = 1**: preserved from base algo (the binary cliff finding from loop 1).
- **`streak_threshold` = 2**: skip re-entry after 2 consecutive losing closes.
  Tracked via a counter of consecutive closed-position P&L < 0. Conservative: a streak
  of 2 is not uncommon in a 37% win-rate regime, but also avoids filtering too many
  entries.
- **Position P&L tracking**: on each `on_order()`, before deciding, check if this is
  a reduce-only order (close). Track closed position P&L from `self.cache.positions_closed()`.
  After a close with negative realized P&L, increment streak counter. After a profitable
  close, reset to 0.
- **Quantity invariant preserved**: never modify order.quantity.
- **No look-ahead**: `self.cache` reflects pre-fill state at decision time.

**Concerns**: Position P&L may be hard to track reliably from `self.cache` at
`on_order()` time before the order is submitted. The approach: query
`self.cache.positions_closed()` and compare the count/most recent P&L at each
reduce-only order. This is a proxy that reads the last closed position's P&L
after each close completes, not before.

---

## Backtest Observations

**Full 12-date train window:**

| Metric | ptg-f-l2 | base (cap=1) |
|---|---|---|
| realized_pnl | $4,262.50 | $4,262.50 |
| vs_base_pnl_pct | **0.00%** | — |
| sharpe_ratio | 17.619 | 17.619 |
| trade_count | 90,433 | 90,433 |

**What happened**: The loss-streak gate is a complete no-op vs the base algo.
Post-mortem: the oracle fires CLOSE+OPEN simultaneously. Between oracle signals,
the position is always flat (net_qty=0 < cap=1). The streak gate only fires for
"between-oracle" opens, but those sees net_qty=0, so the cap gate allows them regardless.
The streak gate would also fire for "concurrent-oracle" opens (same-tick CLOSE+OPEN),
but those are ALREADY blocked by cap=1 (cache shows 1 position at decision time).
In both cases, the streak gate outcome = cap gate outcome = no incremental filtering.

**Hypothesis verdict**: No-op. The streak gate is redundant with the cap=1 mechanism.

**Suggested next attempt**: Any filter at oracle-signal time is redundant with cap=1.
A flow-based gate from trade ticks (subscribed independently) could act BEFORE the oracle
fires, potentially filtering based on current microstructure. This is the afg mechanism
layered on top of ptg.
