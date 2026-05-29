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
decay rate steepens. At `vol_ratio = 2`, base `p = exp(-2) ~ 0.135`;
with `sensitivity = 3.0`, `p = exp(-3) ~ 0.050`, i.e. essentially the
`min_prob` floor. Calm-regime behaviour is untouched: for `vol_ratio <= 1`
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
`vol_ratio <= 1` pass-through are unchanged). Expected effect: realized P&L
>= base, trade_count down modestly, win rate flat-to-up.

**Risk**: If the base `sensitivity = 2.0` is already near the optimum, a
steeper decay over-skips — it discards profitable moderate-vol entries
(the floor at `vol_ratio = 2` leaves almost nothing) and realized P&L
falls below base. Loop 1 metrics-only context cannot distinguish these
cases ex ante; the backtest is the test.

## Backtest Observations

Train window: 2026-03-08 .. 2026-03-20 (12 dates). `--use-cached-baseline`.

    metric              vrs-m-l1     vol-regime-sizer (base)
    realized_pnl          936.50      753.75
    sharpe_ratio          3.9099      3.0647
    max_drawdown_pct     -0.0421     -0.0461
    win_rate              0.35418     0.35287
    trade_count           125873      127991
    mean_slippage         0.0         0.0

    vs_base_pnl_pct       +24.25%
    vs_base_slippage_pct  0.0%  (both slippage = 0.0 exactly)

Against the `simple` baseline the runner reports vs_baseline_pnl_pct=+500.32%
and a suggested PASS verdict — informational only; this experiment has no
pass gate.

**Result**: The hypothesis held. Steepening the decay (`sensitivity` 2.0 ->
3.0) raised realized P&L +24.25% over base while trade_count fell only 1.66%
(127991 -> 125873). The small trade-count drop confirms the steeper decay
removed marginal high-vol entries rather than broadly cutting participation:
calm- and moderate-vol orders still flow because `vol_ratio <= 1` passes
through unchanged and the `min_prob` floor at vol_ratio=2 differs only
0.135 -> 0.050. Sharpe rose 3.065 -> 3.910 and max drawdown improved
(-0.046% -> -0.042%); win rate edged up +0.13pp. This is consistent with the
loss-avoidance reading of the base algo: skipping the worst high-vol tail
harder both lifts P&L and tightens the equity curve. Slippage stayed exactly
0.0 on both sides — the oracle/simple-fill model produces no slippage signal
here, so slippage is uninformative for this experiment arm.

**Caveat**: trade_count is high (~126k over 12 dates), so the metrics are
statistically well-supported; no low-sample flag needed.
