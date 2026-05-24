# Algorithm Notes: vrs-m-l1

Per-iteration experiment — base_algo `vol-regime-sizer`, context mode
`metrics-only`, loop 1. Starting point: `vol-regime-sizer` (base).

## Hypothesis

**Context available (metrics-only, loop 1)**: No prior loops exist. The only
numbers in scope are the base algo's fixed comparison metrics:

    realized_pnl=753.75   sharpe=3.065   mean_slippage=0.0
    win_rate=0.35287      trade_count=127991
    max_drawdown_pct=-0.04605%
    vs_baseline_pnl_pct=+383.17%

**Targeted change (single)**: Raise the volatility-decay `sensitivity`
parameter from `2.0` to `3.0`. This is the only change; every other
parameter (`fast_halflife=20`, `slow_halflife=120`, `min_prob=0.05`,
`min_ticks=30`, `max_vol_ratio=5.0`) is held identical to the base algo.

The submission probability mapping is unchanged in form —
`p = max(min_prob, exp(-sensitivity * max(0, vol_ratio - 1)))` — only the
decay rate steepens. At `vol_ratio = 2`, base `p = exp(-2) ≈ 0.135`;
with `sensitivity = 3.0`, `p = exp(-3) ≈ 0.050`, i.e. essentially the
`min_prob` floor. Calm-regime behaviour is untouched: for `vol_ratio ≤ 1`
the excess term is 0 so `p = 1.0` regardless of `sensitivity`.

**Rationale (metrics-derived only)**: The base algo posts a low win rate
(35.29%) alongside a large realized-P&L edge over the `simple` baseline
(+383%). A sub-coin-flip win rate paired with a strong positive P&L edge
means the headline result is driven by loss avoidance — cutting
participation in the regime where entries lose — rather than by winning
more often. If that is the value mechanism, the high-volatility tail is
where the gate earns its keep. A steeper decay concentrates the skip more
tightly on that tail: it removes more of the worst regime while leaving
calm- and moderate-vol participation essentially intact (the floor and the
`vol_ratio ≤ 1` pass-through are unchanged). Expected effect: realized P&L
≥ base, trade_count down modestly, win rate flat-to-up.

**Risk**: If the base `sensitivity = 2.0` is already near the optimum, a
steeper decay over-skips — it discards profitable moderate-vol entries
(the floor at `vol_ratio = 2` leaves almost nothing) and realized P&L
falls below base. Loop 1 metrics-only context cannot distinguish these
cases ex ante; the backtest is the test.
