# afg-m-l2 — per-iteration experiment loop 2

Base algo: `aggressor-flow-gate` | Context mode: `metrics-only` | Loop: 2
Starting point: `afg-m-l1` (prior loop's algorithm).

## Hypothesis

Prior context (metrics-only — numbers only):

```
Loop 1: pnl_vs_base=-7.3% slippage_vs_base=0.0% sharpe=5.13 trade_count=107623
```

Reading purely from the numbers:

- Loop 1 (afg-m-l1) finished at `pnl_vs_base = -7.3%` — i.e. it *lost* P&L
  relative to the base algo. Slippage was unchanged (0.0%), so the entire
  loss is attributable to which entries the flow gate let through vs.
  skipped.
- Loop 1 ran `trade_count = 107623` fills. A higher fill count paired with
  a lower P&L is the signature of a gate that is too *permissive*: it is
  admitting marginal/adverse entries that drag the aggregate down instead
  of filtering them.

Targeted change for loop 2: make the gate **stricter** so it skips more
adverse-flow entries, with the goal of clawing back the -7.3% gap.

Two coordinated knobs are turned:

1. **Lower `flow_threshold` 1.1 -> 0.6.** A smaller absolute decayed-flow
   threshold trips the skip condition on weaker imbalances, so more
   sell-dominated BUYs and buy-dominated SELLs are filtered out.
2. **Shorten `half_life_seconds` 5.0 -> 2.5.** A tighter half-life makes
   the decayed-flow estimate weight the most recent prints even more
   heavily, so the gate reacts to the freshest aggressor pressure rather
   than to a 5s-smoothed average. Combined with the lower threshold this
   makes the gate both faster and more selective.

Expectation: trade_count drops below loop 1 (more skips), and the skipped
entries are net-adverse so `pnl_vs_base` moves upward toward / past 0%.

## Implementation Decisions

Mechanical copy of `afg-m-l1/execution_algorithm.py` as the starting point.
Only the two config defaults are changed (`flow_threshold`,
`half_life_seconds`) plus the matching `get_execution_algorithm` defaults
and the class/factory identifiers. No structural change to the gate logic,
the deque maintenance, the reduce-only passthrough, or the post-skip
anti-cascade re-entry guarantee.

## Backtest Observations

Train window: 12 dates (2026-03-08 .. 2026-03-20). Backtest run via
`scripts/run_research_backtest.py --algo afg-m-l2 --use-cached-baseline`.

afg-m-l2 aggregate metrics:

| metric            | afg-m-l2   | base (aggressor-flow-gate) |
|-------------------|------------|----------------------------|
| realized_pnl      | 1129.0     | 1255.5                     |
| sharpe_ratio      | 5.1263     | 5.5944                     |
| max_drawdown_pct  | -0.0340    | -0.0332                    |
| win_rate          | 0.3510     | 0.3549                     |
| trade_count       | 106724     | 107198                     |
| mean_slippage     | 0.0        | 0.0                        |

Deltas vs base_algo (`aggressor-flow-gate`):

- `vs_base_pnl_pct      = -10.08%`
- `vs_base_slippage_pct =   0.0%`  (both sides 0.0; no slippage signal here)

The hypothesis was WRONG. The stricter gate (flow_threshold 1.1 -> 0.6,
half_life 5.0s -> 2.5s) did NOT recover the loop-1 P&L gap -- it widened
it: afg-m-l2 lands at -10.08% vs base, worse than afg-m-l1's -7.3%.

Key surprise from the numbers: trade_count BARELY moved (106724 vs
afg-m-l1's 107623, a 0.8% drop) despite a much lower threshold. So the
"make the gate stricter -> filter adverse entries" theory does not hold:
the additional skips this gate produced were net-POSITIVE entries, not
adverse ones. The decayed-flow signal is not a reliable proxy for which
oracle entries are bad -- gating on it (in either direction tried so far)
removes good fills along with bad ones, and the more it gates, the more
P&L it sheds.

Slippage carries zero information for this strategy/symbol (mean_slippage
== 0.0 on every variant and the baseline), so the entire experiment turns
on realized_pnl.

Direction for a future loop: stop tuning the decayed-flow threshold. Both
loop-1 (decay weighting) and loop-2 (stricter decay + lower threshold)
underperform the base flat-window gate. The base algo's flat-sum gate at
its original threshold is still the best point seen. A future loop should
either (a) revert to the flat-window sum and tune ONLY the window length /
threshold around the base configuration, or (b) abandon aggressor-flow
gating of entries entirely and gate something else -- because every
flow-gate variant so far loses P&L relative to base.
