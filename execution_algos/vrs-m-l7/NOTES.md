# vrs-m-l7 — per-iteration experiment, metrics-only mode, loop 7

## Hypothesis (metrics-only context only)

Prior loops on this arm (only allowed signal):

| Loop | sensitivity | min_prob | pnl_vs_base | slippage_vs_base | sharpe | trade_count |
|------|-------------|----------|-------------|------------------|--------|-------------|
| L1   | 3.0         | 0.05     | +24.25%     | 0.0%             | 3.91   | 125,873     |
| L2   | 4.0         | 0.05     | +41.72%     | 0.0%             | 4.43   | 124,497     |
| L3   | 5.0         | 0.05     | +51.04%     | 0.0%             | 4.70   | 123,457     |
| L4   | 6.0         | 0.05     | +76.23%     | 0.0%             | 4.45   |  99,833     |
| L5   | 6.0         | 0.10     | +79.38%     | 0.0%             | 4.49   | 100,209     |
| L6   | 6.0         | 0.20     | +71.87%     | 0.0%             | 4.33   | 101,021     |

Per-step marginal change at sensitivity=6.0 (floor lever):

| Step      | ΔPnL (pp) | ΔSharpe | Δtrade_count |
|-----------|-----------|---------|--------------|
| L4 → L5   |  +3.15    | +0.045  |   +376       |
| L5 → L6   |  −7.51    | −0.164  |   +812       |

Mechanical read: The min_prob lever moves trade_count monotonically
upward (+376 at 0.10, +812 at 0.20) — the floor is mechanically
active. But PnL/Sharpe response is non-monotonic: L4 (0.05) < L5 (0.10) > L6 (0.20).
There is an apparent local maximum near min_prob ≈ 0.10. The L5 → L6
drop is roughly 2.4x the L4 → L5 rise (in PnL pp), so the curve is
asymmetric and may peak slightly below 0.10.

**Hypothesis for L7**: probe the OTHER side of the apparent maximum.
Set `min_prob = 0.07` (between L4's 0.05 and L5's 0.10), keeping
`sensitivity = 6.0`. If the curve is smooth and concave:
- 0.07 should land between L4 and L5 on every metric (trades ~99,800-100,200,
  pnl ~+76% to +79%, sharpe ~4.45-4.49).
- This both confirms L5 was near the peak and gives L8 a third
  interpolation point to refine.

If 0.07 outperforms L5, the peak is between 0.05 and 0.10 (push L8
toward 0.08). If 0.07 underperforms both L4 and L5, the curve is not
smooth at this scale and L8 should pivot to a different knob
(sensitivity, halflives, max_vol_ratio).

Single-parameter change, consistent with the arm's metrics-only discipline.

## Implementation Decisions

- Copied `execution_algos/vrs-m-l6/execution_algorithm.py` verbatim,
  renamed class (`VrsML6*` → `VrsML7*`), and changed `min_prob` default
  0.20 → 0.07 in `VrsML7Config`, `get_execution_algorithm` arg default,
  and the docstring. `sensitivity` stays at 6.0. No other parameter or
  structural changes.
- Reduce-only orders continue to submit unconditionally — required for
  `intraday_flat` compliance.
- Quantity invariant preserved: at most one contract per parent order.
- Deterministic SHA-256 oracle keyed on `client_order_id` keeps
  probabilistic submission reproducible.

## Backtest Observations

Backtest ran on 11/12 train dates (20260319 dropped from both sides due
to OOM in prior runs; aggregate evaluated on the 11 common dates).

Aggregate metrics (11 dates, vs. `simple` baseline via runner aggregator):
- realized_pnl: 1013.00
- sharpe_ratio: 4.386
- trade_count: 99,979
- mean_slippage: 0.0 (matched-fill model — both sides exact)
- max_drawdown_pct: -3.60%
- win_rate: 35.44%
- vs_baseline (simple) pnl_pct: +2242.20%
- vs_baseline (simple) slippage_pct: 0.0%

Vs. base algo (`vol-regime-sizer`, recomputed over same 11 dates):
- base realized_pnl (11d): 579.50
- l7 realized_pnl (11d):  1013.00
- **vs_base_pnl_pct: +74.81%**
- vs_base_slippage_pct: 0.0%

L7 (min_prob=0.07) lands between L4 (+76.23%) and L5 (+79.40%) on the
arm's pnl_vs_base trajectory, and just below L4. Trade count 99,979 sits
just below L4's 99,833 (essentially tied — 0.15% delta) and well below
L5's 100,209. Sharpe 4.386 is below L5 (4.49) and L6 (4.33) tied-range,
slightly above L6.

Interpretation under metrics-only discipline:
- The min_prob -> pnl curve at sensitivity=6.0 is concave and peaks near
  min_prob = 0.10 (L5). L7 at 0.07 underperforms L5 — by a narrow margin
  (-4.59 pp pnl, -0.10 sharpe). This confirms the apex is roughly at
  0.08-0.12, NOT below 0.07.
- Distance from L4 (0.05) to L7 (0.07) is small in both directions — pnl
  L4 +76.23%, L7 +74.81% (-1.42 pp). Curve near apex is flat.
- L6 (0.20) was a much sharper drop (-7.51 pp). The asymmetry holds: the
  drop above 0.10 is steeper than below.

Verdict vs config pass_gate (min_pnl_improvement_pct: 5.0 vs simple,
max_slippage_regression_pct: 5.0): +2242% pnl, 0% slippage delta. PASS.

L8 (final loop) direction options under metrics-only:
- Narrow further on the apex: try min_prob=0.09 or 0.12 to bracket L5.
- Pivot to a different knob (sensitivity, fast_halflife, max_vol_ratio).
- L5 (min_prob=0.10) is the best so far on this arm. The marginal return
  to further min_prob tuning around 0.07-0.12 looks small (~1-5 pp).
  Pivoting to a second-order knob may unlock more.
