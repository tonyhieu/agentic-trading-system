# ptg-m-l5 — per-iteration experiment loop 5 (position-tier-gate, metrics-only)

## Hypothesis

Context mode is metrics-only: the only prior-loop information available is the
`metrics` block of loop-1..loop-4. Hypothesis derived solely from those numbers.

Prior loop metrics (vs base = position-tier-gate):

| loop | trade_count | pnl_vs_base | sharpe |
|------|-------------|-------------|--------|
| 1    | 90433       | +0.0%       | 17.62  |
| 2    | 47725       | -23.1%      | 15.81  |
| 3    | 84541       | -7.0%       | 16.95  |
| 4    | 136734      | -96.3%      | 0.60   |

The numbers describe a single-peaked (concave) relationship between
`trade_count` and `pnl_vs_base`. The maximum sits at loop 1's trade count
(~90433). Moving below it (loop 2 at 47725) loses 23% P&L; moving far above it
(loop 4 at 136734) collapses P&L by 96% and crushes Sharpe from ~17 to 0.6.
Loop 3 at 84541 — just below the loop-1 count — sits between, at -7%.

So the open-order flow has an optimum near loop 1's count. Both starvation
(too few opens) and flooding (too many opens) hurt. The highest-leverage move
for loop 5 is to land `trade_count` back at the loop-1 peak (~90k).

The starting point is loop 4's code (`ptg-m-l4`), a pure positional gate with
`position_cap`. Loop 4 set `position_cap=5`, which barely fires and produced
136734 trades (over the peak). Loop 3 set `position_cap=1`, producing 84541
(just under the peak). The peak count (90433) lies between those two regimes.
Loop 5 sets `position_cap=2`: one notch looser than loop 3's gate so slightly
more opens pass than loop 3's 84541, nudging the count up toward loop 1's
~90433 without reaching loop 4's over-trading regime.

Expected outcome: trade_count between loop-3 (84541) and loop-4 (136734),
ideally near the ~90k peak, with pnl_vs_base recovering from loop 4's -96%
back toward loop 1's break-even, and Sharpe recovering toward ~17.

## Backtest Observations

Train window (12 dates, 2026-03-08..2026-03-20). Base = position-tier-gate.

| metric        | ptg-m-l5 | base (ptg) |
|---------------|----------|------------|
| realized_pnl  | 156.0    | 4262.5     |
| mean_slippage | 0.0      | 0.0        |
| sharpe_ratio  | 0.5996   | 17.619     |
| max_dd_pct    | -0.0529  | -0.0173    |
| win_rate      | 0.3506   | 0.3720     |
| trade_count   | 136734   | 90433      |

- vs_base_pnl_pct = (156.0 - 4262.5) / 4262.5 * 100 = -96.34%
- vs_base_slippage_pct = 0.0% (both slippages are 0.0; zero denominator → 0.0)

The result is bit-identical to loop 4 (ptg-m-l4): realized_pnl 156.0,
trade_count 136734, sharpe 0.5996. Lowering position_cap from 5 (loop 4) to 2
changed nothing.

Interpretation: the positional gate fires only when absolute net open
quantity reaches position_cap. In this strategy/algo regime the net open
quantity never reaches 2 contracts — opens and closes interleave so net
exposure stays at 0–1. Therefore any position_cap >= 2 leaves the gate
permanently inert, and the algorithm degenerates to "submit every open"
exactly as loop 4 did. The 136734 trade_count is the unthrottled ceiling.

The metrics-only hypothesis — that an intermediate position_cap would land
trade_count near loop 1's ~90k peak — is falsified for caps >= 2. The
single-peaked trade_count→pnl curve seen across loops 1–4 cannot be traversed
by tuning position_cap above 1: only cap=1 (loop 3, 84541 trades) actually
throttles. A future loop that wants a trade_count between 84541 and 136734
needs a different gate mechanism (e.g. probabilistic open admission, or a
gate keyed on a quantity other than net position) — position_cap is a
two-state lever (cap=1 throttles, cap>=2 does not), not a continuous dial.
