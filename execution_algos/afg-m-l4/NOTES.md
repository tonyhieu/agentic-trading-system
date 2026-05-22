# afg-m-l4

Per-iteration experiment — base_algo `aggressor-flow-gate`, context mode
`metrics-only`, loop 4. Starting point: afg-m-l3.

## Hypothesis

Context available to this loop is the prior loops' `metrics` blocks only:

```
Loop 1: pnl_vs_base=-7.3% slippage_vs_base=0.0% sharpe=5.13 trade_count=107623
Loop 2: pnl_vs_base=-10.1% slippage_vs_base=0.0% sharpe=5.13 trade_count=106724
Loop 3: pnl_vs_base=-38.0% slippage_vs_base=0.0% sharpe=3.30 trade_count=113358
```

Reading the numbers alone:

- Every loop so far underperforms the base on P&L. Loop 1 is the least bad
  (-7.3%); loop 3 is the worst by a wide margin (-38.0%).
- Sharpe held near 5.13 for loops 1 and 2, then collapsed to 3.30 at loop 3.
- trade_count: loop 1 = 107623, loop 2 = 106724, loop 3 = 113358. Loop 3 —
  the worst P&L and worst Sharpe — also has the highest trade_count, ~6k
  above loops 1 and 2.

The numbers-only read: pushing trade_count above ~107k (loop 3) coincided
with both P&L and Sharpe falling off a cliff. The best result, loop 1, sits
at trade_count 107623. So loop 4 reverses loop 3's direction: tighten the
gate so trade_count drops back toward loop-1 territory, expecting P&L and
Sharpe to recover.

Change for loop 4 (relative to afg-m-l3's parameters):
- `flow_threshold`: 2.5 -> 0.7  (tighter gate — trips on weaker imbalances,
  so more adverse-flow orders are skipped and trade_count falls)
- `window_seconds`: 4.0 -> 9.0  (longer look-back accumulates more prints,
  raising the decayed-flow magnitude so the now-lower threshold is reached
  more readily)
- `half_life_seconds`: 4.0 -> 3.0  (modestly faster decay so recent prints
  still dominate within the longer window)

Net effect: a markedly tighter gate than afg-m-l3, intended to bring
trade_count back down near loop 1's ~107.6k and recover P&L / Sharpe.

## Backtest Observations

Train window: 2026-03-08 .. 2026-03-20 (12 dates). `simple` baseline cached.

afg-m-l4 aggregate (execution_algos/afg-m-l4/results/backtest-results.json):
- realized_pnl     = 1143.5
- mean_slippage    = 0.0
- sharpe_ratio     = 5.198
- max_drawdown_pct = -0.0339
- win_rate         = 0.3515
- trade_count      = 106751

Versus base_algo `aggressor-flow-gate`
(realized_pnl=1255.5, mean_slippage=0.0):
- vs_base_pnl_pct      = -8.92%
- vs_base_slippage_pct = 0.0%   (base slippage is 0.0 -> defined as 0.0%)

Read against the prior loops:
- trade_count fell from loop 3's 113358 to 106751 — back near loop 2's
  106724, exactly the direction the tighter gate intended.
- Sharpe recovered from loop 3's 3.30 to 5.20 — back in loop 1/2 territory.
- P&L recovered from loop 3's -38.0% to -8.92%, a large rebound, but did
  not beat loop 1's -7.3%.

The numbers-only hypothesis — lower trade_count recovers P&L and Sharpe —
held: Sharpe and trade_count snapped back, and P&L improved sharply. The
gate still costs ~9% of P&L vs the base; loop 1's parameter region (~107.6k
trades, -7.3%) remains the best seen and a future loop could probe a gate
slightly looser than this one to close the remaining gap.
