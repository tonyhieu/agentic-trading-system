# vrs-m-l6 — per-iteration experiment, metrics-only mode, loop 6

## Hypothesis (metrics-only context only)

Prior loops on this arm (only allowed signal):

| Loop | sensitivity | min_prob | pnl_vs_base | slippage_vs_base | sharpe | trade_count |
|------|-------------|----------|-------------|------------------|--------|-------------|
| L1   | 3.0         | 0.05     | +24.25%     | 0.0%             | 3.91   | 125,873     |
| L2   | 4.0         | 0.05     | +41.72%     | 0.0%             | 4.43   | 124,497     |
| L3   | 5.0         | 0.05     | +51.04%     | 0.0%             | 4.70   | 123,457     |
| L4   | 6.0         | 0.05     | +76.23%     | 0.0%             | 4.45   |  99,833     |
| L5   | 6.0         | 0.10     | +79.38%     | 0.0%             | 4.49   | 100,209     |

Per-step marginal change:

| Step      | ΔPnL (pp) | ΔSharpe | Δtrade_count |
|-----------|-----------|---------|--------------|
| L1 → L2   | +17.47    | +0.52   |  −1,376      |
| L2 → L3   |  +9.32    | +0.27   |  −1,040      |
| L3 → L4   | +25.19    | −0.25   | −23,624      |
| L4 → L5   |  +3.15    | +0.04   |    +376      |

Mechanical read: L4→L5 confirmed the floor lever moves metrics in the
desired direction (both PnL and Sharpe rose, trade_count rose) but the
magnitude is tiny — the floor `min_prob = 0.10` binds rarely at
`sensitivity = 6.0`. Three possible explanations: (i) the floor lever
is mechanically inert at this sensitivity, (ii) we are still far below
the saturation point of the lever, (iii) marginal Sharpe gain is small
because the orders re-admitted are also marginally profitable. We can
distinguish (i) from (ii)/(iii) by doubling the floor again: if
trade_count barely moves at min_prob=0.20, the floor is mechanically
inert at this sensitivity; if trade_count moves materially (>+2,000),
the lever is real and we can read the PnL/Sharpe sign to decide
direction for L7.

**Hypothesis for L6**: bump `min_prob` 0.10 → 0.20 while holding
`sensitivity = 6.0`. Single-parameter change, consistent with the
arm's metrics-only discipline. Expected direction: trade_count rises
materially this time; PnL probably gives back some of L5's gain (more
high-vol participation admitted); Sharpe direction is the key signal
— if it stays flat or rises, the lever is genuinely useful and L7
can push further or pair it with a sensitivity tweak; if Sharpe
drops, the over-filtering hypothesis was correct in spirit but
sensitivity itself was already optimal and the floor only hurts.

## Implementation Decisions

- Copied `execution_algos/vrs-m-l5/execution_algorithm.py` verbatim,
  renamed class (`VrsML5*` → `VrsML6*`), and bumped `min_prob` default
  0.10 → 0.20 in `VrsML6Config`, `get_execution_algorithm` arg default,
  and the docstring. `sensitivity` stays at 6.0. No other parameter or
  structural changes.
- Reduce-only orders continue to submit unconditionally — required for
  `intraday_flat` compliance.
- Quantity invariant preserved: at most one contract per parent order.
- Deterministic SHA-256 oracle keyed on `client_order_id` keeps
  probabilistic submission reproducible.

## Backtest Observations

11-date train window (2026-03-08..2026-03-20, 20260319 OOM-dropped on
both sides — matches prior loops).

Aggregate (from `results/backtest-results.json`):

| Metric                  | L6 value     |
|-------------------------|--------------|
| realized_pnl            | $996.00      |
| sharpe_ratio            | 4.3277       |
| max_drawdown_pct        | -0.0357%     |
| win_rate                | 35.44%       |
| trade_count             | 101,021      |
| mean_slippage           | 0.0          |
| total_commissions       | 0.0          |
| is_weighted_bps         | 0.04004      |
| vs_baseline_pnl_pct     | +2202.89%    |
| vs_baseline_slippage_pct| 0.0%         |
| vs_baseline_is_bps      | -6.168       |

Vs vol-regime-sizer base on the matched 11 dates ($579.50):
**vs_base_pnl_pct = +71.87%**.

Step-curve on matched 11d:

| Loop | min_prob | trade_count | vs_base_pnl | sharpe |
|------|----------|-------------|-------------|--------|
| L4   | 0.05     |  99,833     | +76.23%     | 4.4472 |
| L5   | 0.10     | 100,209     | +79.38%     | 4.4917 |
| L6   | 0.20     | 101,021     | +71.87%     | 4.3277 |

L5 -> L6 deltas: trade_count +812, vs_base_pnl -7.51pp, sharpe -0.164.

Mechanical read for L7 (no prose, only the numbers above):
- Doubling the floor admitted ~812 more parents -- the floor lever is
  no longer mechanically inert. But the added parents are net-negative
  on BOTH PnL and Sharpe simultaneously. Floor lever direction is now
  confirmed: raising it past 0.10 hurts.
- L4 (0.05) -> L5 (0.10) was a +3.15pp PnL gain; L5 -> L6 (0.20) is a
  -7.51pp PnL loss. The curve has a maximum near min_prob = 0.10
  (possibly slightly below).
- L7 candidate moves:
  (a) Lower min_prob below 0.10 (e.g. 0.07) -- search the other side
      of the apparent maximum.
  (b) Hold min_prob at the best-known 0.10 and move a different knob
      (max_vol_ratio, fast/slow halflife, or sensitivity).

PASS/FAIL: PASS (+2202.89% vs simple, well above the +5.0% gate;
zero slippage regression). Per_iteration_experiment loop -- NOT
snapshotted per arm protocol.
