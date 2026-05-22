# position-tier-gate-b-l4

Per-iteration experiment — arm: `base_algo=position-tier-gate`,
`mode=brief-summary`, **loop 4**.

Starting point (copied, then modified): `position-tier-gate-b-l3`.

## Hypothesis

The brief summaries of loops 1-3 deliver one converged directive: **binary
skip/submit entry gating has failed three independent ways** — equity
drawdown breaker (loop 1, one-way latch, +71.6% but pure volume
suppression), re-arming equity breaker (loop 2, restored volume → -50.3%),
and order-time book-imbalance gating (loop 3, -10.5%, win-rate moved only
+1.1pp). Loop 3's `next` field states the remaining real room is the
execution objective itself: slippage is identically 0.0 on every algo so
nothing can be won there, but `is_weighted_bps` differs across algos —
loop-3 0.064, base 0.045, simple 0.039 — and a future loop should target
implementation shortfall (IS) via order *timing*, not skip gating.

Acting on that directive. The IS metric (`backtest_engine/arrival_price.py`)
is defined as:

    is_bps = (fill_px - arrival_mid) * direction / arrival_mid * 10_000

where `arrival_mid` is the top-of-book mid at the order's `ts_init`
(decision time, before the execution algo touches the order). IS therefore
measures the adverse price drift between the moment the strategy *decides*
to trade and the moment the order actually *fills*. Any execution friction
that delays a fill — serialized entry, skip-then-resubmit cycles, holding
an order back — lets the market drift away from the arrival mid and
inflates IS.

That is exactly why the base `position-tier-gate` (IS 0.045) and especially
loop-3's imbalance gate (IS 0.064) are *worse* on IS than `simple` (0.039):
`simple` submits every order the instant it arrives, so its decision-to-fill
gap is minimal; every gating variant either delays or churns orders.

**Loop-4 change**: remove all gating entirely (it has failed three ways and
it inflates IS) and route every order — open and close alike — to the venue
with zero added latency at `on_order()` time, i.e. submit immediately in
the same handler invocation, no quote lookups, no state, no deferral. This
is the timing-optimal execution the loop-3 directive points at: it should
drive `is_weighted_bps` down toward `simple`'s 0.039 (a large improvement
on base's 0.045), and because it stops suppressing/churning the order flow
it should also restore `realized_pnl` and `trade_count` toward the
`simple`/base envelope rather than the degraded loop-1/2/3 values.

Expected outcome: `vs_base_pnl_pct` materially positive (loop-3 was
-10.5%), `vs_base_slippage_pct` 0.0 (slippage is identically 0.0 across the
whole experiment — no lever there), and IS improving vs base. This loop
deliberately tests whether *removing* execution friction — the inverse of
every prior loop — is what actually helps, which the IS numbers predict.

## Backtest Observations

Backtest: `run_research_backtest.py --algo position-tier-gate-b-l4
--use-cached-baseline`. All 12 train dates (2026-03-08 .. 2026-03-20)
completed. Per-date trade counts 449 .. 28377; the smallest day
(20260308, 449) is modest but not a low-sample collapse — no low-sample
flag.

Raw aggregate (loop-4 vs base `position-tier-gate`):

| metric           | loop-4    | base       | delta            |
|------------------|-----------|------------|------------------|
| realized_pnl     | -8857.50  | -5892.25   | vs_base -50.32%  |
| mean_slippage    | 0.0       | 0.0        | vs_base   0.0%   |
| sharpe_ratio     | -28.30    | -27.23     | worse            |
| trade_count      | 152300    | 101304     | +50996           |
| win_rate         | 0.3272    | 0.3285     | -0.13pp          |
| max_drawdown_pct | -0.1386   | -0.0986    | worse            |
| is_weighted_bps  | 0.04497   | 0.04501    | -0.08% (flat)    |

FAILs vs the `simple` baseline (-8857.50 vs +156).

The hypothesis was **wrong**, and the result is informative:

1. **IS did not move.** Loop-4's `is_weighted_bps` (0.04497) is within
   0.08% of base (0.04501) — it did NOT fall toward `simple`'s 0.039. The
   premise that the base algo inflates IS by *delaying* fills is false:
   the base `position-tier-gate` already submits every order it does not
   skip immediately, with no deferral, so removing its skip gate adds no
   timing advantage. `simple`'s lower IS (0.039) is therefore not a
   latency effect this loop can capture by routing faster — it comes from
   *which* orders exist in each algo's fill set, not from when they fill.

2. **Loop-4 is numerically identical to loop-2.** realized_pnl -8857.50,
   sharpe -28.30, trade_count 152300, max_dd -0.1386 match loop-2 to the
   digit. Loop-2's re-arming equity breaker almost never latched, so it
   effectively passed every order through — exactly what loop-4 does
   unconditionally. Two structurally different algorithms collapse to the
   same "submit everything" behaviour and the same fill set. This is the
   ungated upper bound on order flow under this strategy.

3. **The sigma=200 per-trade drag dominates.** Submitting all 152300
   orders loses -8857.50; the base, by skipping ~50000 opens, loses only
   -5892.25. Consistent with loop-2's finding that the per-trade edge is
   structurally negative, so trading more loses more. Removing friction
   does not help when the marginal trade is negative-EV.

4. **Slippage remains identically 0.0** on every algo in this experiment
   — there is genuinely no lever there, confirming loop-3's note.

Conclusion: neither skip gating (loops 1-3) nor friction removal (loop 4)
beats the base on P&L, and IS is essentially fixed across binary
submit/skip policies. The only remaining structural lever is order
*transformation* — modifying quantity (slicing into child orders) or
adding genuine timing offsets — rather than the submit/skip dichotomy,
which is now exhausted in both directions.
