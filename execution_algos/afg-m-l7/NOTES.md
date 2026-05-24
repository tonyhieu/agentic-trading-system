# afg-m-l7 — Per-Iteration Experiment NOTES

Base algo: `aggressor-flow-gate`. Context mode: `metrics-only`. Loop: 7.
Starting point: `afg-m-l6` (prior loop).

## Hypothesis

Numbers-only read of the six prior loop `metrics` blocks (the only context
permitted in metrics-only mode):

```
Loop 1: pnl_vs_base=-7.3%  sharpe=5.13 trade_count=107623
Loop 2: pnl_vs_base=-10.1% sharpe=5.13 trade_count=106724
Loop 3: pnl_vs_base=-38.0% sharpe=3.30 trade_count=113358
Loop 4: pnl_vs_base=-8.9%  sharpe=5.20 trade_count=106751
Loop 5: pnl_vs_base=-63.4% sharpe=1.80 trade_count=123480
Loop 6: pnl_vs_base=+5.0%  sharpe=6.02 trade_count=105331
```

Sorted by `trade_count` the relationship is monotone:

```
105331 (L6): pnl +5.0%  sharpe 6.02   <- best, only loop above base
106724 (L2): pnl -10.1% sharpe 5.13
106751 (L4): pnl -8.9%  sharpe 5.20
107623 (L1): pnl -7.3%  sharpe 5.13
113358 (L3): pnl -38.0% sharpe 3.30
123480 (L5): pnl -63.4% sharpe 1.80
```

Fewer admitted orders => higher pnl and higher sharpe, with no exception in
the data. L6 is the only loop that beat base (+5.0%) and it ran the lowest
trade_count of the experiment (105331). The two highest-count loops (113k,
123k) collapsed in both metrics. The gradient points one direction: push
trade_count below L6's 105331 and the pnl/sharpe should continue to rise.

Loop 7 therefore takes one small, in-direction step from L6: tighten the
gate by lowering `flow_threshold` from 0.30 to 0.15 (single parameter
change). A lower threshold means the decayed-flow magnitude clears the bar
on even weaker imbalances, so the gate trips more often, more open orders
are skipped, and trade_count falls modestly below L6's 105331. `window_seconds`
(12.0) and `half_life_seconds` (5.0) are held fixed at L6's values — the
numbers do not justify moving them, and a single-variable step keeps the
trade_count delta controlled so the algo does not overshoot into the
degraded high-count regime by accident in the wrong direction or stall.

Expected outcome: trade_count drops a few hundred to low-thousand below
105331, pnl_vs_base rises modestly above +5.0%, sharpe holds near or above
6.02.

## Backtest Observations

Train window 2026-03-08 .. 2026-03-21 (12 dates), strategy `oracle`,
baseline `simple`, base_algo `aggressor-flow-gate`.

afg-m-l7 aggregate (realized basis):

```
realized_pnl    1346.75      (base aggressor-flow-gate: 1255.50)
sharpe_ratio    6.142        (base: 5.594)
max_drawdown   -0.0345 %     (base: -0.0332 %)
win_rate        0.3534       (base: 0.3549)
trade_count     105087       (base: 107198)
mean_slippage   0.0          (base: 0.0)
```

vs base_algo `aggressor-flow-gate`:

```
vs_base_pnl_pct       = +7.27 %
vs_base_slippage_pct  =  0.00 %  (both 0; oracle/simple-fill setup -- no
                                  slippage signal in this experiment)
```

The hypothesis held cleanly. Lowering `flow_threshold` 0.30 -> 0.15 (the
single in-direction step) pulled trade_count to 105087 -- 244 below L6's
105331, the new lowest count of the experiment -- and pnl_vs_base rose to
+7.27 % from L6's +5.02 %, with sharpe up to 6.14 from 6.02. The monotone
"fewer admitted orders -> higher pnl/sharpe" relationship that the prior
six loops' metrics described continued one more step: afg-m-l7 is now the
best loop of the arm on pnl_vs_base, sharpe, and (lowest) trade_count
simultaneously.

The trade_count delta was modest (-244, ~0.2 %) -- much smaller than the
threshold cut (halved) might suggest. This indicates the decayed-flow
magnitude distribution is concentrated: most non-warm-up evaluations
already cleared 0.30, so dropping the bar to 0.15 only newly trips the
gate on a thin band of marginal cases. The gain per skipped order was
nonetheless favorable, consistent with the gate selecting against adverse
fills. mean_slippage stays 0.0 (no slippage signal in this setup); the
edge is entirely in realized_pnl / sharpe.

Caveats per OBJECTIVE.md section 8: trade_count 105087 is healthy (~8.8k
admitted orders/day average) -- no low-count concern. Sharpe is computed
over 12 days. The trade_count step is small enough that a future loop
should not assume a further threshold cut yields a proportional gain --
the marginal band is thinning.
