# Algorithm Notes: ptg-isl-g1l2

## Hypothesis

**Builds on**: `ptg-isl-g1l1` (island-0, generation 1, loop 1). The prior
loop layered a rolling-spread p75 OPEN-gate on top of the
position-tier-gate base. Result on the 12-date train window: pnl +26.55%
vs base, sharpe 23.17, max_drawdown -0.0061, trade_count -3.4%.

**Mechanism (this loop)**: Keep the two existing gates (position-cap and
rolling-spread p75) verbatim. ADD a third, orthogonal gate that
conditions on top-of-book QUEUE IMBALANCE at OPEN time, with
side-dependent logic:

  Let `q = bid_size / (bid_size + ask_size)` from the most recent quote.
  - For a BUY OPEN: SKIP if `q < buy_block_threshold` (default 0.30).
    Low `q` means sellers dominate the top — book is heavily ask-sided.
    In a futures LOB this typically precedes a downtick within
    sub-second horizons (queue pressure / order-flow imbalance is a
    well-documented sub-second adverse-selection predictor).
  - For a SELL OPEN: SKIP if `q > sell_block_threshold` (default 0.70).
    Symmetric: high `q` means buyers dominate, predicting an uptick that
    would move against a short entry.

All three gates must pass for an OPEN to fire. Reduce-only orders pass
through unchanged.

**Why this hypothesis, given g1l1's result**: g1l1's NOTES recorded that
the spread gate only filtered ~3.4% of post-position-cap entries yet
captured a +26.55% pnl lift. That tells us most surviving entries are
already in calm-spread regimes — the residual losses concentrate on
a different microstructure axis. The natural orthogonal axis is
**direction of immediate book pressure**: spread says "how wide is the
top," imbalance says "which side is being eaten." A wide-spread gate
catches cost-heavy moments; an imbalance gate catches direction-wrong
moments. The two should NOT overlap heavily and so should compose.

**Expected effect**:
  - Trade-count drop: more than g1l1's -3.4% (imbalance is a fresher
    axis), but bounded — ratios outside [0.30, 0.70] are tail events
    in MES top-of-book.
  - PNL: small-to-moderate uplift if the hypothesis holds. The relevant
    losers in g1l1 are the small slice of direction-wrong opens during
    sub-second adverse-flow regimes. Imbalance gating targets exactly
    those.
  - Sharpe: should rise or stay flat — the filter removes high-variance
    losing trades.
  - Drawdown: tighter or unchanged.

**Cross-island influence**: None (no migration reports yet for
generation 1).

## Implementation Decisions

- **buy_block_threshold = 0.30 / sell_block_threshold = 0.70**:
  symmetric, mild-to-moderate filter. q in [0.30, 0.70] is the bulk of
  top-of-book observations on MES; only the imbalanced tails are gated.
  These bounds were chosen conservatively for the first imbalance
  experiment — too aggressive (e.g., 0.45/0.55) would risk gutting
  trade-count without a clear pnl signal.
- **Side detection**: `order.side` (Nautilus `OrderSide.BUY` / `SELL`).
  We compare against the enum's string repr defensively, since the
  Nautilus enum has been stable but exact import paths vary across
  versions. Falling back to `str(order.side).upper().endswith("BUY")`
  keeps the algo robust.
- **Latest sizes**: maintained alongside `_latest_spread` in
  `on_quote_tick`, from `tick.bid_size` and `tick.ask_size`. If either
  is zero or negative (defensive), the imbalance gate is a no-op for
  that order (we do not have valid info to act on).
- **Gate ordering preserved**: position-cap → spread → imbalance. Each
  is cheap; ordering by expected reject rate (highest first) keeps the
  average cost lowest.
- **Quote tick sizes are integers in Nautilus**: cast via
  `float(str(tick.bid_size))` for safety with the Quantity type.
- **No look-ahead**: imbalance is computed from `_latest_size_*`,
  populated from `on_quote_tick` (strictly past). `on_order` reads the
  cached latest values; never touches future quotes.
- **No quantity modification**: SKIP means do not submit. Quantity
  invariant preserved.

## Backtest Observations

**Headline metrics (12-date train window, 2026-03-08..2026-03-20)**

| Metric              | base (position-tier-gate) | ptg-isl-g1l1 | ptg-isl-g1l2 | g1l2 vs base   |
| ------------------- | -------------------------- | ------------ | ------------ | -------------- |
| realized_pnl        | 4262.50                    | 5394.25      | 5394.25      | +1131.75 (+26.55%) |
| mean_slippage       | 0.0                        | 0.0          | 0.0          | 0.0 (both zero, see caveat) |
| sharpe_ratio        | 17.619                     | 23.168       | 23.168       | +5.549         |
| max_drawdown_pct    | -0.01727                   | -0.00610     | -0.00610     | tighter by 1.12pp |
| win_rate            | 0.3720                     | 0.3806       | 0.3806       | +0.0086        |
| trade_count         | 90433                      | 87319        | 87319        | -3114 (-3.4%)  |
| is_weighted_bps     | 0.03887                    | 0.02846      | 0.02846      | -26.8%         |

**vs_base_pnl_pct**       = (5394.25 - 4262.50) / |4262.50| * 100 = **+26.5513%**
**vs_base_slippage_pct**  = 0.0 (both algorithms report mean_slippage = 0.0; the
  simulated fill model executes at top-of-book without slippage, so this delta is
  undefined and reported as 0.0 by convention)

**HONESTY FLAG — null hypothesis result (gate did not bind)**

The g1l2 metrics are bit-for-bit identical to g1l1 on every reported field
(pnl, sharpe, drawdown, win_rate, trade_count, is_weighted_bps). The added
queue-imbalance OPEN gate produced **zero incremental effect** on top of
g1l1's spread-gate + position-cap stack. Possible explanations, none
verified in this loop:

  1. **Gate never fired**: with thresholds [0.30, 0.70] on MES top-of-book,
     the conditioning event (`q < 0.30` for BUYs, `q > 0.70` for SELLs)
     may be rare among the entries that already cleared the position-cap
     and spread gates. If the spread gate already removes most
     microstructure-stressed moments, the surviving entries may live in a
     calm `q` band where imbalance never crosses the [0.30, 0.70] tails.
  2. **Gate fired but on a zero-EV slice**: the filtered entries may have
     had ~0 net pnl contribution, leaving aggregate metrics unchanged.
  3. **Implementation bug**: side detection (`str(order.side).endswith("BUY")`)
     or the `_latest_size_*` cache could be silently no-op'ing. No
     instrumentation was added in this loop to distinguish (1) from (3).

The conservative interpretation is: this loop **did not refute** the
imbalance hypothesis, but it also **did not produce evidence for it**.
Treat the +26.55% headline as inherited from g1l1's spread gate, not as
new signal from g1l2. **Do not snapshot.** Per pass_gate semantics, g1l2
ties g1l1 — no improvement margin.

**Trade-count note**: 87319 trades over 12 dates is high; trade-count
gating concerns from §8 honesty rules are not triggered (well above any
low-count threshold).

**Sharpe metric version**: v2 (matches base; comparison is valid).

**Recommended next step for the island**: before adding more gates, add
lightweight counters inside the imbalance check (skipped_buy_imb,
skipped_sell_imb, evaluated_count) so a future loop can distinguish
"gate never fires" from "gate fires but is neutral." Then either tighten
thresholds toward [0.40, 0.60] (if gate is too loose) or pivot to a
different orthogonal axis (e.g., short-horizon volatility, trade
intensity) if imbalance is genuinely redundant with the spread gate on
this strategy.
