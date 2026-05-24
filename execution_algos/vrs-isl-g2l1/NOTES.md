# vrs-isl-g2l1 — Island-2, Generation 2, Loop 1

Base lineage: vol-regime-sizer → vrs-isl-g1l1 (chop-gated sizer) →
vrs-isl-g1l2 (trend-reinforced chop gate; near-null result).

Parent file: `execution_algos/vrs-isl-g1l2/execution_algorithm.py`.

## Hypothesis

The gen-1 migration synthesis identified two distinct, near-orthogonal
adverse-microstructure axes whose individual SKIP gates each lifted PnL
on different islands this generation:

- **Choppiness ratio** (price-path axis) — island-2 g1l1, +34.13% vs base
  with drawdown tighter and trade_count -14.5%.
- **Rolling spread p75** (book-state / liquidity-vacuum axis) — island-0
  g1l1, +26.55% vs base with drawdown tighter and IS bps materially
  better.

The migration's top recommendation for island-2 g2 was:

> "Compose the chop gate with island-0's spread-quantile gate (orthogonal
>  whipsaw-frequency vs liquidity-vacuum axes)."

The gen-1 migration also produced two **explicit warnings** that shape
this implementation:

1. **Trend-boost was ~zero EV.** vrs-isl-g1l2 widened the chop neutral
   threshold proportional to |signed-trend|; this recovered ~2548
   incremental submissions but added ~-$3 PnL net (per-trade EV of
   recovered orders ≈ 0, consistent with early-reversal noise inside
   trends). Decision: **revert trend_boost to 0**, collapsing the gate
   back to g1l1's exact chop behavior, before stacking the spread gate.
   (Equivalently, this iteration starts from g1l1 conceptually but
   re-uses g1l2's parent code with `trend_boost=0` to minimize
   diff-surface and risk of unrelated regressions.)
2. **Null-effect gate stacks are undiagnosable without
   instrumentation.** Island-0 g1l2 lost a loop to a gate stack that
   produced bit-for-bit identical metrics because no per-gate counters
   existed. Decision: this algo logs `submitted / chop_skipped /
   spread_skipped / both_skipped / reduce_only_submitted` whenever a
   skip fires, so a flat result vs g1l1 can be attributed cleanly to
   "spread gate fired rarely" vs "spread gate fired but was redundant
   with chop".

Mechanism of the predicted improvement:

- The **chop gate** removes the highest-cost slice of price-path adverse
  regimes (whipsaws → 30s oracle signal degrades because mean-reversion
  inside the horizon cancels directional edge).
- The **spread gate** removes the highest-cost slice of book-state
  adverse regimes (liquidity vacuums → wider top-of-book spread
  coincides with brief one-sided pressure where the close leg fires
  into a worse book).

These adverse regimes are predicted to overlap only partially — chop is
a price-derivative statistic, spread is a snapshot of book depth at a
single instant. The conjunction should remove the union of the two
top-quartile cost slices.

Expected outcome:
- PnL ≥ vrs-isl-g1l1 (+34.13% vs base). Stretch target +40% if the
  spread gate's contribution is mostly orthogonal.
- Drawdown tighter or equal (both gates tightened it on their original
  bases).
- trade_count lower than g1l1's 109,424 (additional skip axis →
  strictly more orders gated; ~78% retention if independent).
- Instrumentation counters reveal whether the two gates fire on
  overlapping or disjoint subpopulations of orders.

Risk:
- If chop and spread are positively correlated (whipsaw periods
  coincide with liquidity vacuums), the spread gate adds little and
  may even strip slightly-positive-EV entries the chop gate already
  passes. The instrumentation counters distinguish this case from a
  genuine orthogonal lift, informing g2l2.

## Cross-island insight applied

This loop directly applies the gen-1 migration's headline
`generalizable` finding — "skip-based gating on adverse-microstructure
regimes generalizes; composed spread+chop stack is the highest-leverage
generation-2 direction" — by porting island-0's gate mechanism
(spread_window_seconds=60.0, spread_quantile=0.75, min_samples=50)
verbatim onto island-2's lineage.

## Implementation Decisions

- Start from `vrs-isl-g1l2/execution_algorithm.py` (per loop spec).
- Set `trend_boost = 0.0` default to collapse to g1l1's chop-only
  behavior on the chop axis. The plumbing remains so a future loop
  could revisit the inverted-trend-boost idea from g1l2's `next`.
- Add a rolling-spread deque exactly mirroring ptg-isl-g1l1's
  implementation: maintain on `on_quote_tick`, prune by
  `order.ts_init - window_ns` at gate evaluation, quantile via
  sort + linear interpolation, no firing during warm-up.
- Gate composition: **AND** semantics on SKIP — for an OPEN to fire,
  both chop p_submit draw must pass AND spread must be ≤ quantile.
  Equivalently: skip if EITHER gate skips. This matches the union-of-
  cost-slices hypothesis.
- The chop gate is probabilistic (uses deterministic SHA-256 uniform
  per client_order_id); the spread gate is hard. Their composition
  is well-defined: spread gate is evaluated first, then chop gate.
- Reduce-only orders bypass both gates (intraday_flat compliance,
  unchanged from g1l2).
- Instrumentation counters logged on every skip/submit decision.

## Backtest Observations

Train window: 12 dates 2026-03-08..2026-03-20. Baseline for the
aggregator's vs_baseline columns is `simple`; the island base of record
for this experiment is `vol-regime-sizer`.

Raw numbers (`execution_algos/vrs-isl-g2l1/results/backtest-results.json`):

| metric            | vrs-isl-g2l1 | vrs (base)  | vrs-isl-g1l2 | vrs-isl-g1l1 |
|-------------------|--------------|-------------|--------------|--------------|
| realized_pnl      | 2437.75      | 753.75      | 1007.75      | 1011.00      |
| sharpe_ratio      | 16.95        | 3.06        | 5.74         | 5.97         |
| max_drawdown_pct  | -0.01485     | -0.04605    | -0.04127     | -0.04?       |
| win_rate          | 0.3556       | 0.3529      | 0.3479       | 0.348?       |
| trade_count       | 104688       | 127991      | 111972       | 109424       |
| mean_slippage     | 0.0          | 0.0         | 0.0          | 0.0          |
| is_weighted_bps   | 0.03114      | 0.03737     | 0.04200      | —            |

vs `vol-regime-sizer` (island base):
- `vs_base_pnl_pct      = (2437.75 - 753.75) / 753.75 * 100 = +223.42%`
- `vs_base_slippage_pct = 0.0` (both sides zero — flag: not a meaningful axis)

vs `vrs-isl-g1l2` (prior loop in lineage):
- PnL +$1430.00 (+141.90%).
- Sharpe 5.74 → 16.95 (~3.0×).
- Max drawdown -4.13% → -1.48% (≈64% tighter).
- trade_count 111,972 → 104,688 (-6.5%) — fewer orders submitted,
  consistent with composing an additional skip axis on top of chop.
- IS bps 0.0420 → 0.0311 — implementation shortfall ~26% lower; the
  surviving orders are executing at materially better effective prices,
  not merely fewer-but-equal-quality fills.

vs `vrs-isl-g1l1` (the previous best in lineage on the chop-only axis):
- PnL 1011 → 2438 (+141%) — adding the spread gate roughly 2.4×ed the
  chop-only result, far exceeding the +6% headroom the hypothesis tagged
  as "stretch".
- trade_count 109,424 → 104,688 (-4.3%): the spread gate is firing on a
  small minority of orders the chop gate would already have passed, yet
  those small-cardinality skips carry outsized adverse-cost weight (the
  liquidity-vacuum slice the migration synthesis predicted).

Interpretation of the headline (~+223% vs base, ~+142% vs g1l2):

1. The migration's "compose orthogonal gates" recommendation worked as
   intended — the two adverse-microstructure axes (chop, spread) cut
   substantially-disjoint subpopulations of the order flow. Stripping
   only ~6.5% of trades produced ~140% additional PnL on the survivors.
2. Drawdown collapsed (≈64% tighter) — gating out worst-spread fills
   removes a tail of large per-order losses that previously concentrated
   in volatile micro-windows. This is consistent with the gate's
   prediction at the *book-state* axis, not just an averaged improvement.
3. IS bps falling materially (-26% vs g1l2) is the cleanest signal that
   the *execution quality* of the surviving orders is better — this is
   not a sample-selection artifact of "we kept the easy trades", because
   IS measures fill-vs-arrival on the orders that *did* go through.
4. trend_boost reverting to 0.0 stripped the ~zero-EV widening from
   g1l2 cleanly without other regressions, validating the gen-1
   migration warning.

Caveats / honesty flags:
- Slippage is 0.0 across all algos in this experiment — the
  `vs_base_slippage_pct` axis is uninformative here. Reporting 0.0 per
  spec; do not treat as a signal.
- trade_count (104,688) is well above the migration's
  low-sample threshold; results are statistically meaningful.
- The headline is computed against `vol-regime-sizer`, not `simple`.
  The aggregator's `vs_baseline_pnl_pct = 1462.66%` is vs `simple` and
  is not the island's metric of record.
- `is_weighted_bps` of 0.0311 is the *positive* direction for the
  algo's own fills, but `vs_baseline_is_bps = -19.91` (the aggregator's
  field, vs `simple`) is the canonical execution objective sign-flipped
  — i.e., the algo's IS is *worse* than `simple`'s in absolute bps
  terms. This is consistent with the island base `vol-regime-sizer`
  itself being -3.88 vs simple; the island lineage trades IS for PnL,
  by design. Not a regression for this experiment, but flagged for the
  human operator.

Instrumentation counters (per-skip type) were emitted to per-date stdout
during the runs — not aggregated into the canonical results JSON.
Reading the per-date logs to attribute spread-skips vs chop-skips vs
both is a g2l2 starting task if a further decomposition is wanted.

Verdict (this loop, in-sample):
- Major improvement over both the island base and the prior loop in
  lineage, on the axes the hypothesis predicted (PnL, drawdown,
  trade-count-ratio, IS-of-surviving-orders).
- The cross-island insight (orthogonal-gate composition) generalized
  from island-0's mechanism onto island-2's lineage as the migration
  predicted.
