# vrs-m-l3 — per_iteration_experiment loop 3 (metrics-only)

## Hypothesis

Context received (metrics-only mode — numbers only, no prose from prior loops):

```
Loop 1: pnl_vs_base=+24.2% slippage_vs_base=0.0% sharpe=3.91 trade_count=125873
Loop 2: pnl_vs_base=+41.7% slippage_vs_base=0.0% sharpe=4.43 trade_count=124497
```

Reading only the deltas L1 -> L2:
- trade_count: -1376 (~-1.1%)
- vs_base_pnl_pct: +17.48pp (~+72% relative growth in over-base PnL)
- sharpe: +0.525 (~+13%)
- slippage: unchanged at 0

The trajectory is unambiguous: a small reduction in trade_count is
accompanied by a disproportionate gain in both PnL and Sharpe. The lowest-edge
trades evidently sit at the margin that's being trimmed. The right play
is to nudge selectivity in the same direction one more notch — a single
parameter tightening — and see whether the trade_count/PnL/Sharpe curve
keeps moving the same way or reverses (concavity check).

This is the only change vs the loop-2 starting point. Code body is copied
mechanically.

## Implementation Decisions

- Single parameter change: `sensitivity` default 4.0 -> 5.0 in
  `VrsML3Config` and `get_execution_algorithm`. Higher sensitivity makes
  the exp(-sensitivity * excess) submission probability decay more
  steeply with vol_ratio excess, which mechanically reduces submission
  rate when vol_ratio > 1.
- All other params (fast_halflife=20, slow_halflife=120, min_prob=0.05,
  min_ticks=30, max_vol_ratio=5.0) unchanged.
- Class names bumped to VrsML3Config / VrsML3Algorithm; registered as
  `vrs-m-l3` in `execution_algos/__init__.py`.

## Backtest Observations

sensitivity=5.0 over-filters. pnl collapsed from 1068.25 (l2) to 505.5 (-32.9% vs base). trade_count dropped from 124497 to 43263 (-65%), indicating the gate is now too aggressive — the excluded trades contain genuine edge. The anomalously high sharpe=65.6 reflects very few losing days in a low-activity regime, not a quality signal. Sensitivity lever is over-extended at 5.0; the optimum is between 4.0 (l2 best) and 5.0.
