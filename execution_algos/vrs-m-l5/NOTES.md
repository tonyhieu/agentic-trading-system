# vrs-m-l5 — per-iteration experiment, metrics-only mode, loop 5

## Hypothesis (metrics-only context only)

Prior loops on this arm (only allowed signal):

| Loop | sensitivity | min_prob | pnl_vs_base | slippage_vs_base | sharpe | trade_count |
|------|-------------|----------|-------------|------------------|--------|-------------|
| L1   | 3.0         | 0.05     | +24.25%     | 0.0%             | 3.91   | 125,873     |
| L2   | 4.0         | 0.05     | +41.72%     | 0.0%             | 4.43   | 124,497     |
| L3   | 5.0         | 0.05     | +51.04%     | 0.0%             | 4.70   | 123,457     |
| L4   | 6.0         | 0.05     | +76.23%     | 0.0%             | 4.45   | 99,833      |

Per-step marginal change:

| Step      | ΔPnL (pp) | ΔSharpe | Δtrade_count |
|-----------|-----------|---------|--------------|
| L1 → L2   | +17.47    | +0.52   | −1,376       |
| L2 → L3   |  +9.32    | +0.27   | −1,040       |
| L3 → L4   | +25.19    | −0.25   | −23,624      |

Mechanical read of these four numbers: PnL is still rising, but L3→L4 is
the first step where Sharpe DROPPED and trade-count fell ~23× more than
either prior step. Continuing to push `sensitivity` further (e.g. 7.0)
is a 50/50 bet — over-filtering may now be purchasing PnL with
disproportionate per-day variance.

The next single-parameter lever is `min_prob`, the floor on submission
probability. Raising it from 0.05 → 0.10 forces the algorithm to keep
participating at a higher minimum rate even when the vol-regime decay
would otherwise collapse `p` toward zero, re-admitting some of the
high-vol parents that L4 filtered out and reducing per-day variance.

**Hypothesis for L5**: bump `min_prob` 0.05 → 0.10 while holding
`sensitivity = 6.0`. Expected direction: Sharpe should recover toward
L3's level; PnL may give back some of L4's gain because more high-vol
participation is re-admitted; trade_count should rise back up toward
L2/L3 territory. If Sharpe recovers materially without much PnL loss,
L6 has a clear lever direction (push min_prob further, or pair with
sensitivity tweaks). If Sharpe doesn't move, the lever is dead and L6
should pivot.

## Implementation Decisions

- Copied `execution_algos/vrs-m-l4/execution_algorithm.py` verbatim,
  renamed class (`VrsML4*` → `VrsML5*`), and bumped `min_prob` default
  0.05 → 0.10 in `VrsML5Config`, `get_execution_algorithm` arg default,
  and the docstring. `sensitivity` stays at 6.0. No other parameter or
  structural changes.
- Reduce-only orders continue to submit unconditionally — required for
  `intraday_flat` compliance.
- Quantity invariant preserved: at most one contract per parent order.
- Deterministic SHA-256 oracle keyed on `client_order_id` keeps
  probabilistic submission reproducible.

## Backtest Observations

11-date train window (20260308..20260320; 20260319 dropped on both
sides by an OOM in this loop's run — base re-aggregated on the same 11
dates for an apples-to-apples comparison).

| Metric                  | Value         |
|-------------------------|---------------|
| realized_pnl            | 1039.50       |
| sharpe_ratio            | 4.4917        |
| sharpe_n_days           | 11            |
| max_drawdown_pct        | -3.58%        |
| win_rate                | 0.3545        |
| trade_count             | 100,209       |
| mean_slippage           | 0.0           |
| vs_baseline_pnl_pct     | +2303.47%     |  (vs `simple`, both sides on same 11 dates)
| vs_baseline_slippage_pct| 0.0%          |
| vs_base_pnl_pct         | +79.38%       |  (vs `vol-regime-sizer`, both sides on same 11 dates)
| vs_base_slippage_pct    | 0.0%          |

Comparison vs L4 (matched 11-date basis where applicable):

| Metric           | L4 (min_prob=0.05) | L5 (min_prob=0.10) | Δ           |
|------------------|--------------------|--------------------|-------------|
| pnl              | 1021.25            | 1039.50            | +18.25      |
| vs_base_pnl_pct  | +76.23%            | +79.38%            | +3.15 pp    |
| sharpe           | 4.4472             | 4.4917             | +0.045      |
| trade_count      | 99,833             | 100,209            | +376        |
| max_drawdown_pct | −3.62%             | −3.58%             | +0.04 pp    |

**Re-aggregated step curve on matched 11-date basis** (each loop's PnL
summed over the same 11 dates that L5 ran; base 11d = 579.50):

| Loop | sensitivity | min_prob | pnl (11d) | vs_base_pnl_pct | sharpe | trade_count |
|------|-------------|----------|-----------|------------------|--------|-------------|
| base | n/a         | n/a      |   579.50  |   0.00%          | n/a    | n/a         |
| L4   | 6.0         | 0.05     |  1021.25  | +76.23%          | 4.4472 |  99,833     |
| L5   | 6.0         | 0.10     |  1039.50  | +79.38%          | 4.4917 | 100,209     |

**Hypothesis verdict — partial confirmation.** Raising the floor while
holding sensitivity recovered a small slice of Sharpe (+0.045) without
giving back PnL — both moved up. Trade-count rose only +376 (not back
toward L2/L3 territory), implying the `min_prob = 0.10` floor binds
much less often than expected; most of the filtering is still happening
in the decay regime above the floor. The lever helped but its marginal
effect is small at this magnitude. Sharpe is still below L3's 4.70,
i.e. the L3→L4 Sharpe loss is only ~18% recovered.

**Gate decision (vs `simple` per `pass_gate.baseline`)**:
+2303.47% pnl, 0.0% slippage regression → **PASS** (clears +5.0% gate
by 460×; slippage condition vacuous under zero fill-cost model).

**Single highest-leverage next-loop change (L6)**: Because raising
`min_prob` 0.05→0.10 produced only a tiny trade-count rise (+376) and
modest Sharpe gain (+0.045), the floor is binding too rarely at this
sensitivity to matter much. Two candidate levers for L6: (a) push
`min_prob` higher (e.g. 0.20) to make the floor bind more often and
test whether the marginal Sharpe gain compounds, or (b) reduce
`sensitivity` back toward 5.0 paired with the new higher floor to
recover Sharpe without losing the +76% PnL advantage. Option (a) keeps
the single-knob discipline of this arm and isolates the floor lever
cleanly — preferred. If L6 (min_prob=0.20) shows a bigger trade-count
swing and Sharpe recovers further with limited PnL loss, the lever
direction is confirmed. If it inverts (PnL falls, Sharpe doesn't
rise), the floor isn't the right axis and L7 should pivot to
`max_vol_ratio` or `slow_halflife`.
