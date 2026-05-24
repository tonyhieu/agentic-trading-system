# ptg-m-l2 — Per-Iteration Experiment (position-tier-gate, metrics-only, loop 2)

## Hypothesis

Prior context available this loop (metrics-only mode — numbers only):

```
Loop 1: pnl_vs_base=+0.0% slippage_vs_base=0.0% sharpe=17.62 trade_count=90433
```

The loop-1 metrics are identical to the base algo on every axis:
`vs_base_pnl_pct = 0.0`, `vs_base_slippage_pct = 0.0`, `sharpe = 17.62`,
and crucially `trade_count = 90433` — the same trade count the base algo
produced. A gate that changes nothing in the trade count is inert: whatever
loop 1 added did not bind on a single order. The numbers say "the gate never
fired."

Starting point this loop is the prior loop's algo (ptg-m-l1), copied
mechanically. The single change: make the throttle actually bind. If the
prior throttle threshold was loose enough that zero orders tripped it,
the fix is to tighten it by a wide margin so trade_count moves measurably
away from 90433. I widen the cooldown window from 2.0 s to 10.0 s — ten
times the 1.0 s oracle signal cadence — so that at most one open order can
clear per 10-second window. This must reduce trade_count below the base
90433; the open question the backtest answers is whether removing that
volume of churn helps or hurts realized P&L and Sharpe.

Expected direction: trade_count falls well below 90433. If a meaningful
share of the throttled opens were losers (base/loop-1 win_rate was 0.372,
i.e. most entries lose nominally), realized P&L should hold or improve on a
much smaller trade base, lifting Sharpe. If the throttled opens were
disproportionately winners, P&L falls — that result would itself be
informative for loop 3.

## Implementation Decisions

- Copied `ptg-m-l1/execution_algorithm.py` mechanically as the loop-2
  starting point (metrics-only mode — no analysis of prior code logic).
- One change only: `cooldown_seconds` default 2.0 -> 10.0. This is the
  single lever the loop-1 numbers point at — an inert throttle.
- Reduce-only (closing) orders still execute unconditionally so
  `intraday_flat` is never violated.
- No quantity modification anywhere — orders are submitted intact or
  skipped whole; the quantity invariant is preserved.
- No look-ahead: the cooldown compares `order.ts_init` against the
  `ts_init` of the previously submitted open order; both are past/present.

## Backtest Observations

Train window (12 dates, 2026-03-08 .. 2026-03-20). Comparison point is the
base algo `position-tier-gate` (realized_pnl = 4262.5, mean_slippage = 0.0).

| metric            | ptg-m-l2   | base (ptg) | vs base    |
|-------------------|-----------:|-----------:|-----------:|
| realized_pnl      |    3279.75 |    4262.50 |   -23.06%  |
| mean_slippage     |       0.00 |       0.00 |     0.00%  |
| sharpe_ratio      |     15.813 |     17.619 |    -1.806  |
| max_drawdown_pct  |   -0.00827 |   -0.01727 |  +0.0090pp |
| win_rate          |     0.3752 |     0.3720 |  +0.32 pp  |
| trade_count       |     47 725 |     90 433 |   -47.2%   |

The 10.0 s cooldown bound hard, exactly as the loop-1 numbers predicted it
needed to: trade_count fell 47.2% below the base 90433 — the throttle is no
longer inert. Drawdown improved and win_rate ticked up slightly, confirming
some of the cut volume was low-quality churn.

But realized P&L fell 23.06% vs base and Sharpe dropped ~1.8. Cutting nearly
half the open volume removed more winning P&L than losing P&L, even though
the share of winners (win_rate) barely moved. The conclusion the numbers
force: a flat 10 s throttle is too blunt — it discards good and bad opens
indiscriminately. The base trade_count of 90433 is not pure churn; a large
slice of those entries carry the algo's edge.

Trade count remains very high (47 725 over 12 days), so the result is
statistically solid — not a low-count artifact.

Direction for loop 3: the lever is overshoot. 2.0 s did nothing, 10.0 s cut
too deep and cost P&L. The right cooldown lives between — a value that
trims churn without surrendering edge-bearing opens. A mid setting (≈3-5 s)
is the obvious next probe.
