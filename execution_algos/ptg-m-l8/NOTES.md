# ptg-m-l8 — Per-Iteration Experiment, position-tier-gate, metrics-only, loop 8

This is loop 8 of 8 — the final allowed loop of the position-tier-gate /
metrics-only arm.

## Hypothesis

Context for this loop is metrics-only: I am permitted to read only the
`metrics` block of each prior `loop-*.json`. The prior code was copied
mechanically from `ptg-m-l7` without analyzing its logic. The hypothesis
below derives solely from the numbers.

Prior-loop metrics (pnl_vs_base, trade_count):

| Loop | pnl_vs_base | trade_count | sharpe |
|------|-------------|-------------|--------|
| 1    | +0.0%       | 90433       | 17.62  |
| 2    | -23.1%      | 47725       | 15.81  |
| 3    | -7.0%       | 84541       | 16.95  |
| 4    | -96.3%      | 136734      | 0.60   |
| 5    | -96.3%      | 136734      | 0.60   |
| 6    | -8.4%       | 92461       | 16.59  |
| 7    | -6.5%       | 91982       | 16.77  |

Observations from the numbers alone:

1. `pnl_vs_base` peaks at exactly **+0.0%** in loop 1, with
   `trade_count = 90433` and the highest `sharpe = 17.62`.
2. Every other configuration produces a strictly negative `pnl_vs_base`.
   No loop after loop 1 has matched or exceeded the peak.
3. The trade_count axis is single-peaked around 90433: loop 3 undershoots
   (84541 -> -7.0%), loop 7 slightly overshoots (91982 -> -6.5%), loop 6
   overshoots further (92461 -> -8.4%), and loops 4/5 collapse entirely
   (136734 -> -96.3%, sharpe 0.60).
4. Loop 7 (the immediate prior loop) lands at trade_count 91982 — close to
   the peak count but still 1549 trades above it, and 6.5% below peak pnl.
   The residual gap is not just trade *count* but *which* trades the
   path-dependent gate skips: at 91982 it admits roughly the peak number
   of opens, yet selects a different subset than the no-gate regime,
   and that mis-selection costs the remaining 6.5%.

Conclusion: across 7 loops the empirical optimum is unambiguous — the
maximum pnl_vs_base, maximum sharpe, and minimum drawdown all occur at
loop 1's trade_count of exactly 90433, which corresponds to admitting
*every* open leg (no gating). Any nonzero gating, including loop 7's
fractional-admit tuning, shifts trade_count off 90433 and degrades pnl.

For this final loop the highest-expected-value move is to make the gate a
genuine no-op: admit every open leg unconditionally, so trade_count
returns to exactly 90433 and pnl_vs_base returns to the +0.0% peak.

## Change vs ptg-m-l7

Copied `ptg-m-l7/execution_algorithm.py` mechanically as the starting
point. The structural change: drive the positional gate fully open by
setting `position_cap` to a sentinel that is never reached, so `net_qty <
position_cap` is always true and every open leg is submitted directly.
This makes the fractional-admit branch unreachable and reproduces the
no-gate regime that the metrics identify as the peak (loop 1,
trade_count 90433, pnl_vs_base +0.0%).

## Backtest Observations

Train window 2026-03-08 .. 2026-03-21 (12 dates). Comparison point is the
fixed base algo `position-tier-gate` (realized_pnl=4262.5, sharpe=17.62,
trade_count=90433, mean_slippage=0.0).

ptg-m-l8 aggregate (results/backtest-results.json):

| metric           | ptg-m-l8 | position-tier-gate (base) |
|------------------|----------|---------------------------|
| realized_pnl     | 156.0    | 4262.5                    |
| sharpe_ratio     | 0.5996   | 17.62                     |
| max_drawdown_pct | -0.0529  | -0.0173                   |
| win_rate         | 0.3506   | 0.3720                    |
| trade_count      | 136734   | 90433                     |
| mean_slippage    | 0.0      | 0.0                       |

- vs_base_pnl_pct      = -96.34%
- vs_base_slippage_pct =   0.00% (both sides 0.0 — no slippage measured)

Result: the hypothesis was WRONG. I inferred from the metrics-only context
that loop 1's trade_count of 90433 (pnl_vs_base +0.0%, the peak) was the
no-gate regime, and that opening the gate fully would reproduce it. The
backtest shows the no-gate regime is actually trade_count=136734 — identical
to the `simple` baseline and identical to loops 4 and 5 (which also reached
136734, pnl_vs_base -96.3%). So loop 1's peak at 90433 came from a *partial*
gate that skips ~46k open legs, not from no gating at all.

This is the metrics-only failure mode made concrete: with only the seven
`metrics` blocks visible — and the prior code copied mechanically without
analyzing its gating logic — I could see *that* loop 1 sat at trade_count
90433 but had no way to know *which* configuration produced it. The
trade_count axis is not monotone in "how open the gate is": both extremes
(fully open = 136734, and the loop-2 tight gate = 47725) underperform, and
the peak at 90433 is an interior partial-gate point that the metrics alone
do not let you reconstruct. ptg-m-l8 collapsed to the worst observed
regime (-96.3%), tying loops 4/5.

Note on trade_count: 136734 is a high count and the per-date realized_pnl
is very small (156.0 total over 12 dates) — flagged per honesty rules. The
low pnl here is the baseline's own behavior under this strategy, reproduced
exactly because the no-op gate makes ptg-m-l8 identical to `simple`.
