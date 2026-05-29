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

### Correction — full 12-date train aggregate

The numbers above were computed from a truncated 2-date aggregate
(2026-03-19, 2026-03-20). Re-aggregating across the full 12-date Sun-Fri
train window from config.yaml -> data_window.train (2026-03-08..2026-03-21,
all 12 per-date metrics.json files already present on disk):

```
vrs-m-l3 (this algo):  pnl=1138.50  sharpe=4.70  trades=123,457  mean_slip=0
simple   (baseline):   pnl=  156.00  sharpe=0.60  trades=136,734  mean_slip=0
vol-regime-sizer (base): pnl=753.75  trades=~124k  mean_slip=0
```

Vs gate baseline (simple): delta_pnl=+629.81%, delta_slippage=0.0% -> PASS.
Vs base_algo (vol-regime-sizer): delta_pnl=+51.04%, trade_count -0.84%.

The "over-filtered / pnl collapsed" diagnosis was an artifact of the 2-date
slice. Across the full window vrs-m-l3 is actually the strongest of the
three loops (l1=+24.2%, l2=+41.7%, l3=+51.0% vs base). Per user
instruction this run is NOT snapshotted — the per_iteration_experiment
arm does not push to S3 from refinement loops.
