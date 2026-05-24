# ptg-m-l4 — Notes

Per-iteration experiment loop-4 variant of `position-tier-gate`
(context mode: metrics-only).

## Hypothesis

Derived solely from the prior-loop metrics blocks (metrics-only mode):

| Loop | trade_count | pnl_vs_base | sharpe |
|------|-------------|-------------|--------|
| 1    | 90433       | +0.0%       | 17.62  |
| 2    | 47725       | -23.1%      | 15.81  |
| 3    | 84541       | -7.0%       | 16.95  |

The three loops trace a clean monotone relationship: every reduction in
`trade_count` below the loop-1 level was accompanied by a proportional
loss in `pnl_vs_base`. Loop 2 cut trades 47% and lost 23.1%; loop 3 cut
trades 7% and lost 7.0%; loop 1 (full flow) tied base at +0.0%. Sharpe
falls in lockstep.

The numeric conclusion: on this strategy, throttling open orders is
purely destructive — there is no productive slice to trim. The cooldown
gate inherited from loop 2/3 only removes profitable opens.

Change for loop 4: remove the post-open cooldown gate entirely and
relax the positional cap so the inherited exposure gate also stops
discarding opens. This restores the full open-order flow. Expected
outcome: trade_count returns to ~90k and `pnl_vs_base` returns to ~0%
(matching loop 1, the best prior result). The point of this loop is to
confirm the monotone signal by reverting to maximum flow rather than
searching for a smaller throttle that the data says cannot exist.

## Backtest Observations

Train window (12 dates, 2026-03-08 .. 2026-03-20), `--use-cached-baseline`.

Comparison point: `execution_algos/position-tier-gate/results/backtest-results.json`
  base realized_pnl = 4262.50, base mean_slippage = 0.0, base sharpe = 17.62,
  base trade_count = 90433.

ptg-m-l4 result:
  realized_pnl   = 156.00      (vs_base_pnl_pct  = -96.34%)
  mean_slippage  = 0.0         (vs_base_slippage_pct = 0.00%)
  sharpe_ratio   = 0.60
  max_drawdown_pct = -0.0529
  win_rate       = 0.3506
  trade_count    = 136734

The hypothesis was WRONG. The metrics-only context showed trade_count and
pnl_vs_base moving together across loops 1-3, suggesting that restoring
full flow would restore base P&L. Instead, removing the cooldown gate and
raising `position_cap` from 1 to 5 produced the HIGHEST trade count of any
loop (136734, vs base 90433) and the LOWEST P&L (156.0, a -96.3% collapse
vs the position-tier-gate base of 4262.5). Sharpe fell from 17.62 to 0.60.

What this reveals: the trade_count <-> pnl correlation visible in the
metrics-only context was spurious. Loop 1 (90433 trades, +0.0%) was the
true base-equivalent because it preserved the inherited `position_cap=1`
serialized-entry constraint. Raising the cap to 5 let opens stack up to 5
contracts of exposure, which is what destroyed P&L — not the trade count
itself. The positional gate at cap=1 was load-bearing; relaxing it was the
damaging change, and the cooldown removal merely added more low-quality
opens on top.

Honesty flag: trade_count is very high (136734) and not a low-count
concern. The large negative result is a genuine regression, recorded as-is.
A future loop should restore `position_cap=1` (serialized entry) and, if
it wants to vary anything, vary it without relaxing that cap — the loop-1
configuration is the floor to beat, not loop-3.
