# ptg-m-l3 — per-iteration experiment, loop 3 (context mode: metrics-only)

Base algo: `position-tier-gate`. Starting point for this loop: `ptg-m-l2`.

## Hypothesis

Context mode is metrics-only — this hypothesis is derived solely from the
prior-loop metric numbers, not from prior reasoning or NOTES.

Prior metrics:

  Loop 1: pnl_vs_base=+0.0% slippage_vs_base=0.0% sharpe=17.62 trade_count=90433
  Loop 2: pnl_vs_base=-23.1% slippage_vs_base=0.0% sharpe=15.81 trade_count=47725

Reading the numbers:

  - Loop 1 produced metrics identical to the base algo on every field,
    including trade_count = 90433. Whatever throttle loop 1 introduced
    never bound on a single order — it was inert.
  - Loop 2 cut trade_count from 90433 to 47725 (a 47.2% reduction) but
    P&L fell 23.1% vs base and Sharpe dropped from 17.62 to 15.81.

The relationship between the two data points: loop 1's throttle = no
effect, loop 2's throttle = far too aggressive. Halving the trade count
destroyed roughly a quarter of the P&L, and per-trade P&L efficiency
fell (Sharpe down). The throttle strength that maximizes P&L lies
between "none" (loop 1) and "cuts ~half the trades" (loop 2).

Highest-leverage change: dial the throttle back to a mild setting that
trims only a small fraction of trades. The expectation is that most of
the 23% loss is recovered while retaining a modest throttle effect, so
P&L lands much closer to base (loop 1) than to loop 2.

Concretely: the throttle in the copied code is a post-open cooldown
window. Loop 2 used 10.0 s; loop 1's setting (2.0 s) was inert. This
loop sets the cooldown to 3.0 s — just above the inert level, so it
fires occasionally but cuts only a thin slice of opens rather than half
of them.

## Implementation Decisions

Copied `ptg-m-l2/execution_algorithm.py` mechanically. Single change:
`cooldown_seconds` default 10.0 -> 3.0 (constructor default, config
default, and factory default). No structural/logic change.

## Backtest Observations

Train window: 2026-03-08 .. 2026-03-20 (12 dates). Backtest run via
`scripts/run_research_backtest.py --algo ptg-m-l3 --use-cached-baseline`.

ptg-m-l3 aggregate metrics:
  realized_pnl     = 3962.50
  mean_slippage    = 0.0
  sharpe_ratio     = 16.95
  max_drawdown_pct = -0.0182
  win_rate         = 0.3704
  trade_count      = 84541

Vs base algo `position-tier-gate` (pnl=4262.5, slippage=0.0):
  vs_base_pnl_pct      = -7.04%
  vs_base_slippage_pct = 0.0%

Reading the result against the hypothesis:

  - The 3.0 s cooldown cut trade_count from base 90433 to 84541 — a 6.5%
    reduction, a thin slice, exactly the mild-throttle regime aimed for
    (loop 2's 10.0 s cooldown had cut 47%).
  - P&L landed at -7.04% vs base. That recovered most of loop 2's -23.1%
    loss, as predicted, but did not fully return to loop 1's 0.0%.
  - The throttle still has a measurable per-trade cost: trimming 6.5% of
    opens cost 7.0% of P&L, so the trades removed by the cooldown were on
    average slightly above-average in contribution. Sharpe (16.95) sits
    between loop 1 (17.62) and loop 2 (15.81), consistent with a mild
    throttle.

Conclusion: the post-open cooldown does not appear to be P&L-accretive at
any tested strength on this train window — even a 6.5% trim costs more
P&L than the trades were worth. A future loop should consider abandoning
the cooldown entirely and instead targeting a genuinely selective gate
(one that skips a *predictably bad* subset of opens) rather than a
time-uniform throttle.
