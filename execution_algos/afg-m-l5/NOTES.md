# afg-m-l5

Per-iteration experiment, base_algo `aggressor-flow-gate`, context mode
`metrics-only`, loop 5. Starting point: afg-m-l4.

## Hypothesis

Numbers-only read of the four prior loops (metrics block only):

```
Loop 1: pnl_vs_base=-7.3%  sharpe=5.13 trade_count=107623
Loop 2: pnl_vs_base=-10.1% sharpe=5.13 trade_count=106724
Loop 3: pnl_vs_base=-38.0% sharpe=3.30 trade_count=113358
Loop 4: pnl_vs_base=-8.9%  sharpe=5.20 trade_count=106751
```

Two facts dominate the numbers:

1. **Every loop has negative pnl_vs_base.** No gating configuration tried so
   far has beaten the base algo. The gate consistently destroys P&L.
2. **Trade_count and P&L move together at the extreme.** Loop 3 ran the
   highest trade_count (113358) and posted the worst P&L by far (-38.0%) and
   worst Sharpe (3.30). The three loops clustered near ~106.7k-107.6k all
   land in a tight -7.3% to -10.1% P&L band. The least-bad P&L (loop 1,
   -7.3%) sits at the highest count of that cluster (107623).

The base algo `aggressor-flow-gate` itself runs at trade_count 107198. Every
loop's gate removes orders relative to that and loses P&L. The numeric signal
is unambiguous: skipping orders is the cause of the P&L shortfall, and the
loops that skipped least lost least. The highest-leverage move is therefore
to make the gate skip **far fewer** orders -- push trade_count back up toward
(and ideally to) the base's 107198, so that the gate only intervenes on the
most extreme adverse-flow orders.

Loop-5 makes the gate much looser than afg-m-l4:
  - flow_threshold:  0.7  -> 8.0  (far wider gate; trips only on very strong
    decayed imbalances, so almost all orders pass)
  - window_seconds:  9.0  -> 4.0  (shorter look-back => smaller accumulated
    decayed flow, so the now-much-higher threshold is reached very rarely)
  - half_life_seconds: 3.0 -> 2.0 (faster decay further shrinks the decayed
    flow magnitude, reinforcing the loosening)

Expectation: trade_count rises back toward ~107.2k (base level) and P&L /
Sharpe recover toward the base's pnl=1255.5 / sharpe=5.59, i.e. pnl_vs_base
moves from loop-4's -8.9% toward 0%.

## Backtest Observations

Train window 2026-03-08 .. 2026-03-20 (12 dates), `--use-cached-baseline`.

Raw afg-m-l5 aggregate (`results/backtest-results.json`):
  - realized_pnl     = 459.25
  - mean_slippage    = 0.0
  - sharpe_ratio     = 1.7991
  - max_drawdown_pct = -0.05435
  - win_rate         = 0.35049
  - trade_count      = 123480

vs base_algo `aggressor-flow-gate` (pnl=1255.5, slippage=0.0, sharpe=5.5944,
trade_count=107198):
  - vs_base_pnl_pct      = -63.42%
  - vs_base_slippage_pct = 0.0% (both sides have mean_slippage=0)

Outcome: the hypothesis was WRONG. Loosening the gate
(flow_threshold 0.7 -> 8.0, window 9.0 -> 4.0s, half_life 3.0 -> 2.0s) did
NOT recover P&L. afg-m-l5 posts pnl_vs_base = -63.4%, the worst of all five
loops (prior worst was loop 3 at -38.0%). Sharpe collapsed to 1.80 vs base
5.59 and vs loop-4's 5.20.

CAVEAT -- inconsistent comparison footing (honesty flag, OBJECTIVE.md s8):
afg-m-l5's trade_count is 123480. Every prior loop file reports trade_count
in the ~106.7k-113.4k range, and the base_algo aggregate is 107198. This
loop's count is far above all of them. The runner's own summary table shows
the cached `simple` baseline on these 12 dates at trade_count 136734 /
pnl 156.0, whereas the base_algo `aggressor-flow-gate` aggregate is
trade_count 107198 / pnl 1255.5. The cached baseline metrics that the
runner paired against in this run differ materially from whatever the
prior loops' vs_base figures were computed against. The prior loop
`metrics.vs_base_pnl_pct` values (-7.3%, -10.1%, -38.0%, -8.9%) imply a
base pnl of ~1255 (e.g. loop-1 pnl 1163.5 -> -7.33% => base 1255.5), which
is the `aggressor-flow-gate` aggregate -- so this loop's vs_base figure is
computed on the SAME base and IS comparable to prior loops. The raw
trade_count jump (123480 vs prior ~107k), however, is large enough that
the absolute pnl level itself (459.25) is not on a like-for-like footing
with the prior loops' raw realized_pnl values; the cross-loop trade_count
discontinuity should be treated with suspicion. Reported numbers are raw
and uncorrected.

Numbers-only takeaway for a future loop: across loops 1-5 the gate has
never beaten base. Loop 3 (high trade_count 113358) and loop 5 (highest,
123480) are the two worst P&L outcomes; the ~106.7k-107.6k cluster
(loops 1, 2, 4) is the least-bad band. Neither tightening hard (loop 3)
nor loosening hard (loop 5) helped. A future loop should return the gate
parameters to the ~106.7k-107.6k trade_count regime and make only small
perturbations around it.
