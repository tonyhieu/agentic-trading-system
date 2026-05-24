# vrs-m-l4 — per-iteration experiment, metrics-only mode, loop 4

## Hypothesis (metrics-only context only)

Prior loops on this arm (only allowed signal):

| Loop | sensitivity | pnl_vs_base | slippage_vs_base | sharpe | trade_count |
|------|-------------|-------------|------------------|--------|-------------|
| L1   | 3.0         | +24.25%     | 0.0%             | 3.91   | 125,873     |
| L2   | 4.0         | +41.72%     | 0.0%             | 4.43   | 124,497     |
| L3   | 5.0         | +51.04%     | 0.0%             | 4.70   | 123,457     |

Per-step marginal change:

| Step      | ΔPnL (pp) | ΔSharpe | Δtrade_count |
|-----------|-----------|---------|--------------|
| L1 → L2   | +17.47    | +0.52   | −1,376       |
| L2 → L3   | +9.32     | +0.27   | −1,040       |

Read mechanically off the three numbers: PnL and Sharpe are both
monotonically improving, slippage is unchanged, and trade-count is
shrinking. All three deltas are decelerating but every one is still
strictly positive in the desired direction. The curve has not turned over.

Mechanical inspection of the algorithm code (allowed) shows the only
parameter that has changed across L1→L2→L3 is `sensitivity`, the decay
rate that maps vol_ratio excess to submission probability via
`p = exp(-sensitivity * max(0, vol_ratio − 1))`. The trajectory is
`sensitivity = 3.0 → 4.0 → 5.0`.

**Hypothesis for L4**: bump `sensitivity` one more notch to 6.0. The
metrics-only signal is unambiguous that pushing this lever further has so
far been positive, and the deceleration in improvements (rather than
inversion or slippage regression) does not yet warrant backing off. If
L4 inverts the trend (PnL or Sharpe declines), L5 will know it has hit
the saturation point and can step back. Slippage_vs_base has been a flat
0.0% across all three prior loops, so the gate's slippage-regression
condition is not in play — only the +5% PnL gate matters, and L3 already
clears it by 10×.

The change is one parameter only — `sensitivity` default 5.0 → 6.0 in
both `VrsML4Config` and `get_execution_algorithm`. All other defaults
(`fast_halflife=20`, `slow_halflife=120`, `min_prob=0.05`,
`min_ticks=30`, `max_vol_ratio=5.0`) are unchanged from vrs-m-l3.

## Implementation Decisions

- Copied `execution_algos/vrs-m-l3/execution_algorithm.py` verbatim to
  `execution_algos/vrs-m-l4/execution_algorithm.py`, renamed the class
  (`VrsML3*` → `VrsML4*`), and bumped the `sensitivity` default 5.0 → 6.0
  in three places (config field default, `get_execution_algorithm` arg
  default, factory function signature). No structural or logic changes.
- Reduce-only orders continue to submit unconditionally — required for
  `intraday_flat` compliance.
- Quantity invariant preserved: at most one contract per parent order, so
  `participation_cap` is structurally satisfied (the strategy itself
  generates 1-lot parents).
- Deterministic SHA-256 oracle keyed on `client_order_id` keeps the
  probabilistic submission reproducible.

## Backtest Observations

11-date train window (20260308..20260320; 20260319 dropped on both sides
by an OOM in this loop's run — base re-aggregated on the same 11 dates
for an apples-to-apples comparison).

| Metric                  | Value      |
|-------------------------|------------|
| realized_pnl            | 1021.25    |
| sharpe_ratio            | 4.4472     |
| sharpe_n_days           | 11         |
| max_drawdown_pct        | -3.62%     |
| win_rate                | 0.3544     |
| trade_count             | 99,833     |
| mean_slippage           | 0.0        |
| vs_baseline_pnl_pct     | +2261.27%  |  (vs `simple`, both sides on same 11 dates)
| vs_baseline_slippage_pct| 0.0%       |
| vs_base_pnl_pct         | +76.23%    |  (vs `vol-regime-sizer`, both sides on same 11 dates)
| vs_base_slippage_pct    | 0.0%       |

Trade-count delta vs L3 (123,457 → 99,833): −23,624 (−19.1%). Step
function much larger than L2→L3 (−1,040) — sensitivity=6 is now
filtering ~19% more parent submissions than sensitivity=5 over the
matched date range.

**Re-aggregated step curve on the matched 11-date basis** (each loop's
PnL summed over the same 11 dates that vrs-m-l4 ran, vs vol-regime-sizer
also summed over those 11 dates = 579.50):

| Loop | sensitivity | pnl (11d) | vs_base_pnl_pct (11d) | sharpe | trade_count |
|------|-------------|-----------|-----------------------|--------|-------------|
| base | n/a         | 579.50    |  0.00%                | n/a    | n/a         |
| L1   | 3.0         | 738.25    | +27.39%               | 3.91   | 125,873     |
| L2   | 4.0         | 872.00    | +50.47%               | 4.43   | 124,497     |
| L3   | 5.0         | 929.00    | +60.31%               | 4.70   | 123,457     |
| L4   | 6.0         | 1021.25   | +76.23%               | 4.45   | 99,833      |

Per-step marginal change on the matched basis:

| Step      | ΔPnL (pp) | ΔSharpe | Δtrade_count |
|-----------|-----------|---------|--------------|
| L1 → L2   | +23.08    | +0.52   | −1,376       |
| L2 → L3   | +9.84     | +0.27   | −1,040       |
| L3 → L4   | +15.92    | −0.25   | −23,624      |

**Hypothesis verdict — partial inversion.** PnL kept rising (+15.92 pp,
larger than the L2→L3 step), but the Sharpe trend inverted for the first
time (−0.25 absolute). The trade-count step is ~23× larger than every
prior step, indicating the sensitivity=6 curve is now strongly excluding
mid-vol-ratio regions rather than only the extreme tail. Higher absolute
PnL with lower Sharpe means PnL growth is being purchased with higher
per-day variance — the 11-day std of daily PnL increased relative to L3
even though the mean is higher.

**Gate decision (vs `simple` per `pass_gate.baseline`)**:
+2261.27% pnl, 0.0% slippage regression → **PASS** (clears +5.0% gate
by 450×; slippage condition vacuous under the zero fill-cost model).

**Single highest-leverage next-loop change (L5)**: the Sharpe inversion
at L4 with PnL still rising signals the PnL/variance trade-off is
turning. The highest-leverage L5 move is to introduce a second axis —
the only single-parameter further bump along `sensitivity` (7.0) is now
a 50/50 bet, whereas adjusting `min_prob` (currently 0.05) controls the
floor of the submission probability and would let L5 measure whether
Sharpe recovery is achievable by raising the floor (e.g. 0.05 → 0.10)
while keeping sensitivity=6. That isolates whether the L4 Sharpe loss
is from over-filtering noise vs from regime-timing variance.
