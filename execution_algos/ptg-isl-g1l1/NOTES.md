# Algorithm Notes: ptg-isl-g1l1

## Hypothesis

**Builds on**: `position-tier-gate` (island-0 base). The base scores +204.9%
vs simple on the 12-date train window (sharpe 17.6, mean_slippage 0). Its
mechanism: skip any OPEN order while the cache still shows a non-flat
position (cap=1). This serializes oracle entries.

**Mechanism (this loop)**: Add a SECOND gate on top of the base. After the
position-cap gate passes, evaluate the current top-of-book spread against
its own rolling distribution over the last 60 seconds. If the latest
observed spread exceeds the rolling p75 of that window, SKIP the open.
Both gates must pass for an OPEN to fire.

**Inefficiency exploited**: Many of the residual losing entries in the
base algo likely fire during transient wide-spread regimes:
- Wide-spread moments coincide with brief liquidity vacuums where the
  oracle's 30-second forward signal is more likely to reverse before the
  CLOSE leg fires (adverse selection).
- Even in this simulator (where `mean_slippage = 0` because fills use
  top-of-book), wide spreads inflate `is_weighted_bps` — the canonical
  execution-cost objective.

Skipping the top quartile of spread observations should preserve ~75% of
post-position-gate entries while filtering out the most cost-heavy and
adverse-selection-prone slice.

**Why it survives costs**: The conditioning axis is the algorithm's own
recent spread distribution, computed online from quote ticks in a 60s
rolling window. It does not require external data, magic numbers, or
historical calibration — the quantile is a relative-to-recent measure
that auto-adapts to regime shifts.

**Why this hypothesis and not another (island g1l1)**: For the first loop
of generation 1, no migration reports exist. The base's hypothesis verdict
calls out that the residual losses cluster on high-noise days
(20260312/13/16/17) — those are exactly the days where adverse
microstructure is most likely to be the discriminator. A spread gate is
the simplest microstructure conditioning variable to add cleanly on top
of the existing portfolio-state gate.

## Implementation Decisions

- **Quantile = 0.75**: gate the upper quartile. Stricter (0.5) would skip
  too many fills and risk losing trade-count by half (the base already
  trades ~34% fewer orders than simple). Looser (0.9) might not filter
  enough.
- **Window = 60s**: long enough to span hundreds of quote updates at MES
  futures cadence, short enough to react to regime change within a couple
  of minutes.
- **min_samples = 50**: ensures the quantile is statistically meaningful
  before the gate activates. Below this threshold the gate is a no-op
  (warm-up).
- **spread units**: raw price-difference (`ask_price - bid_price`). No
  conversion to tick units — the comparison is purely against the algo's
  own recent history, so units are internally consistent and we avoid
  importing instrument tick-size metadata.
- **Quantile algorithm**: sort-and-interpolate. The deque size is bounded
  by the per-second quote volume × 60s; sorting at every OPEN is cheap
  compared to the simulator's per-tick cost. O(n log n) per gate
  evaluation, n ~ a few hundred typically.
- **Position-cap mechanic preserved verbatim** from base: cache-based net
  position, cap=1, reduce-only pass-through. Both gates run sequentially;
  spread gate evaluated only after position gate passes.
- **Look-ahead audit**: `on_quote_tick` populates the deque in chronological
  replay order. `on_order` reads `order.ts_init` for the prune cutoff. The
  `_latest_spread` is the spread of the most recently delivered quote
  (strictly past). No future information used.

## Backtest Observations

Train window: 12 dates (2026-03-08 .. 2026-03-20).

| metric              | base (position-tier-gate) | ptg-isl-g1l1 | delta vs base |
|---------------------|---------------------------|--------------|---------------|
| realized_pnl        | 4262.50                   | 5394.25      | +26.55%       |
| mean_slippage       | 0.0                       | 0.0          | 0.0 (both exactly 0; sim uses top-of-book fills) |
| sharpe_ratio        | 17.619                    | 23.168       | +5.55         |
| max_drawdown_pct    | -0.01727                  | -0.00610     | +0.0112 (less drawdown) |
| win_rate            | 0.3720                    | 0.3806       | +0.86 pp      |
| trade_count         | 90,433                    | 87,319       | -3,114 (-3.4%) |
| is_weighted_bps     | 0.0389                    | 0.0285       | -26.8% (better execution cost) |

**Hypothesis verdict**: SUPPORTED. Adding the rolling-spread p75 gate on top of
position-tier-gate raised realized P&L by +26.55% and Sharpe by +5.55 while
reducing trades by only -3.4%. Drawdown also tightened (-0.0173 -> -0.0061).
The 3.4% trade-count drop is far below the ~25% naive expectation of filtering
the upper quartile; this implies the position-cap gate already eliminated the
overwhelming majority of OPEN-eligible ticks, so the p75 spread gate only
applies to the relatively small slice that survives the cap, and even within
that slice many ticks have already cleared the p75 window because
post-position-gate ticks tend to cluster in calmer regimes. Wide-spread
filtering thus removed a small slice that was disproportionately P&L-negative.

**Slippage caveat (honesty flag)**: `mean_slippage` is 0.0 on both sides
because the simulator fills at top-of-book; slippage cannot regress in this
simulator regardless of algo behavior. The relevant execution-cost proxy here
is `is_weighted_bps` (0.0389 -> 0.0285, -26.8%) — the spread gate did reduce
implementation shortfall meaningfully.

**Trade-count check**: 87,319 trades well above any low-N concern threshold;
results are statistically meaningful.

**Where it likely helps most**: high-noise days (20260312, 20260313, 20260316,
20260317) where the base accumulated the bulk of its residual losses.

**Migration-ready insight (for cross-island report)**: a rolling-quantile
spread gate composes cleanly on top of an entry-cadence gate. The mechanism is
generic — filter OPEN attempts during local micro-volatility — and should
transfer to islands whose base algo does not already condition on spread.
