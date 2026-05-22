# afg-m-l3 — Per-Iteration Experiment Notes

Per-iteration experiment, base_algo `aggressor-flow-gate`, context mode
`metrics-only`, loop 3. Starting point: afg-m-l2.

## Hypothesis

Context available this loop is the prior loops' `metrics` block only
(metrics-only mode). The numbers:

```
Loop 1: pnl_vs_base=-7.3% slippage_vs_base=0.0% sharpe=5.13 trade_count=107623
Loop 2: pnl_vs_base=-10.1% slippage_vs_base=0.0% sharpe=5.13 trade_count=106724
```

Base algo `aggressor-flow-gate`: realized_pnl=1255.5, sharpe=5.59,
trade_count=107198, mean_slippage=0.0.

Numbers-only reading:
- Both loops underperform the base on P&L (-7.3%, -10.1%) and Sharpe
  (5.13 vs 5.59). Slippage is identically 0.0 everywhere, so slippage is
  not a lever in this setup.
- The trend across loops 1 -> 2 is monotone-worse: pnl_vs_base fell ~2.7
  points and trade_count fell ~900 (107623 -> 106724). Loop 2 evidently
  filtered out more entries than loop 1, and the result got worse.
- The covariation is consistent: fewer trades correlate with worse P&L.
  The gate is destroying profitable fills, not just adverse ones.

Hypothesis: the loop-1/loop-2 gating is too aggressive — every skip is on
balance removing more good entries than bad. Reversing direction should
recover P&L. Loop 3 LOOSENS the gate so trade_count rises back toward (or
above) the base's 107198, expecting pnl_vs_base to move from -10.1% toward
0% or better.

Concretely, three changes all in the loosening direction:
- `flow_threshold` 0.6 -> 2.5: the gate now trips only on much stronger
  net imbalances, so far fewer orders are skipped.
- `window_seconds` 10.0 -> 4.0: a shorter look-back accumulates fewer
  prints, lowering decayed-flow magnitude and further reducing skips.
- `half_life_seconds` 2.5 -> 4.0: a longer half-life is held mild; with
  the much shorter window it mostly keeps in-window weights near 1.0.

Expectation: trade_count climbs back above ~107198; pnl_vs_base improves
(less negative) relative to loop 2's -10.1%.

(Prior algo code was copied mechanically per metrics-only mode rules; no
inspection of its logic beyond parameter values informed this hypothesis.)

## Backtest Observations

Train window 2026-03-08 .. 2026-03-20 (12 dates), `--use-cached-baseline`.

afg-m-l3 results:
- realized_pnl     = 778.0
- mean_slippage    = 0.0
- sharpe_ratio     = 3.298
- max_drawdown_pct = -0.04317
- win_rate         = 0.35138
- trade_count      = 113358

vs base_algo `aggressor-flow-gate` (realized_pnl=1255.5, sharpe=5.59,
trade_count=107198):
- vs_base_pnl_pct      = -38.03%
- vs_base_slippage_pct = 0.00%

Reading against the hypothesis:
- The loosening worked mechanically: trade_count rose to 113358, above the
  base's 107198 and well above loop-2's 106724. So the gate did let many
  more orders through, as intended.
- But the hypothesis was WRONG on outcome. P&L did NOT recover — it
  collapsed: pnl_vs_base went from loop-2's -10.1% to -38.0%, and Sharpe
  fell from ~5.13 to 3.30. Drawdown also worsened (-0.034 -> -0.043).
- The numbers-only inference "fewer trades correlate with worse P&L" was a
  spurious read of just two points. Across loops 1->2->3, trade_count went
  107623 -> 106724 -> 113358 while pnl_vs_base went -7.3% -> -10.1% ->
  -38.0%. There is no monotone trade-count/P&L relationship; the loop-3
  trade_count is the highest yet AND the P&L is the worst yet.
- Interpretation within metrics-only limits: the gate is not destroying
  good entries by being too strict. Letting nearly everything through
  (trade_count above base) is strictly the worst configuration observed.
  The base algo itself sits at +0% by definition with trade_count 107198
  and is better than every loop. A useful gate appears to need to be near
  the base's selectivity, not looser than it.

Next loop should reverse course: tighten back toward the loop-1 region
(trade_count ~107k) rather than continuing to loosen. Loop-3's looser
config is a clear dead end.
