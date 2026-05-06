# Algorithm Notes: momentum-skip

## Hypothesis

**Mechanism**: At order-submission time, compare the current mid-price to
the previous mid-price (from the last cached quote tick). If the price has
already moved in the oracle's predicted direction by more than a threshold
(`min_tick_move`), skip the order — the oracle edge has been partially or
fully "consumed" by the market before we fill. If the price has not yet
moved (or moved in the wrong direction, which is even more favorable), submit
immediately.

    mid = (bid_px + ask_px) / 2
    mid_change = current_mid - previous_mid   [in price units]

For a BUY order: skip if mid_change > min_tick_move * tick_size
  (price already ran up — adverse: we'd buy at elevated price)
For a SELL order: skip if mid_change < -min_tick_move * tick_size
  (price already fell — adverse: we'd sell into a falling bid)
Reduce-only (close) orders: always submit — intraday_flat compliance.

**Inefficiency exploited**: The `simple` baseline submits every oracle signal
immediately regardless of whether the market has already priced in the direction.
The oracle has a 30s forward-looking horizon; if the mid-price already moved
1-2 ticks in the oracle's direction in the interval since the previous signal
(~1s), the expected remaining edge is reduced. Skipping those "late" fills
preserves only entries where the full oracle edge is still intact.

**Why it survives costs**: In the zero-slippage fill model (see research/NOTES.md),
the only P&L lever is trade selection quality. Skipping fills where the oracle
edge is already priced-in should raise the average P&L per trade. The oracle
fills already show an 84-85% win rate (imbalance-skip NOTES); we are trying to
increase the quality of the ~15% losing trades, which are most likely the
"too late" fills where the price moved before we arrived.

**Builds on**: imbalance-skip (prior iteration). That algo used book-depth
imbalance as the adverse-selection signal — directionally correct but
discrimination power too low at threshold=0.5 (only ~1-2% of trades skipped,
+0.10% P&L delta). This algo uses a different signal (price momentum across
consecutive ticks) which is more directly connected to oracle-edge decay.
The lesson from twap-defer: do NOT retime or defer fills — pure skip only.

**Alternatives considered**:
- Imbalance at higher threshold (0.8/0.9): same signal as imbalance-skip
  with more aggressive filtering. Would address discrimination power but might
  over-filter and hurt volume. Pursuing a different signal is higher information.
- Spread-based filter: in zero-slippage model, spread doesn't directly hurt
  P&L. Ruled out.
- Volatility-based skip (skip if recent price range is large): related but
  noisier; a large range includes both favorable and adverse moves.

---

## Implementation Decisions

- **Tick size**: MES futures trade in 0.25-index-point ticks. In the Nautilus
  raw int64 price representation, 0.25 points = 2_500_000_000_000_000 raw units
  (verified empirically: Price.from_str('5800.25').raw - Price.from_str('5800.00').raw).
  The algo reads prices from quote ticks (bid_price.raw, ask_price.raw) which are
  already in Nautilus native int64 units. The `min_tick_move` parameter is expressed
  in units of ticks, so the threshold is `min_tick_move * 2_500_000_000_000_000` in int64.
  Alternative: express threshold as a fraction of current mid-price. Using
  absolute tick counts is simpler and more interpretable.
- **Previous mid tracking**: maintained as instance state (`_prev_mid` per
  instrument). Updated after every quote tick. At algorithm start, `_prev_mid`
  is None; on first order with no prior quote, submit immediately (same as
  imbalance-skip no-quote fallback).
- **Tick size source**: hardcoded as 0.25 index points for MES/MESM6 =
  2_500_000_000_000_000 raw units (verified: Price.from_str('5800.25').raw -
  Price.from_str('5800.00').raw = 2_500_000_000_000_000). Future improvement:
  read from instrument definition. Flagged in Concerns.
- **min_tick_move default**: 1 tick (0.25 points). Hypothesis: fills where
  price moved at least 1 tick in the oracle direction are adversely selected.
  This is conservative — only skip when there's been a meaningful price move,
  not noise.
- **No deferral**: pure skip. Quantity invariant preserved.

**Concerns**:
- The tick size (0.25 points for MES) is hardcoded. If the instrument changes
  or the dataset includes other instruments, this would be wrong. For the
  current iteration (MESM6 only) this is acceptable; a future agent should
  read from the instrument definition.
- Using quote-tick timestamps to track sequential mid-price changes assumes
  the backtest engine feeds quote ticks in time order, which is standard for
  Nautilus. No look-ahead bias: we only use the current and previous cached
  quotes, both of which arrived before the order decision.
- The skip decision is made at decision time (when `on_order` fires) using
  only the latest and previous cached quotes — no future information.

---

## Backtest Observations

**Train dates run**: 20260308, 20260309, 20260310 (full train window).

**Per-date results (momentum-skip vs simple)**:

| Date     | Algo PnL  | Base PnL  | Delta PnL% | Skipped | Skip% | Algo Trades | Base Trades | Algo Win% | Base Win% |
|----------|-----------|-----------|------------|---------|-------|-------------|-------------|-----------|-----------|
| 20260308 | $372.50   | $389.00   | -4.24%     | 6       | 4.3%  | 134         | 140         | 80.60%    | 80.71%    |
| 20260309 | $3,114.50 | $3,092.00 | +0.73%     | 17      | 1.4%  | 1177        | 1194        | 85.39%    | 84.59%    |
| 20260310 | $2,245.50 | $2,244.00 | +0.07%     | 17      | 1.8%  | 950         | 967         | 85.58%    | 85.01%    |
| **AGG**  | $5,732.50 | $5,725.00 | **+0.13%** | 40      | 1.7%  | 2261        | 2301        | 85.18%    | 84.53%    |

**Gate**: required +5.0% pnl improvement; slippage tied at 0.0 on both sides.
**Decision**: FAIL — +0.13% is far below the +5.0% gate (also below CLOSE range ≥3.0%).

**What drove improvement**:
Win rate improved +0.65pp across all dates (85.18% vs 84.53%), confirming the
directional hypothesis: skipping fills where price ran 1+ tick in oracle direction
does remove some losing trades. On 20260309 (+0.73%), the filter worked as
intended — skipping 17 trades at threshold=1 tick captured a few more losers
than winners.

**What underperformed**:
The skip rate is extremely low: only 1.7% of trades skipped overall (4.3%,
1.4%, 1.8% by date). A threshold of 1 full tick (0.25 points) between consecutive
oracle signals (every ~1 second) means the filter almost never fires — mid-price
rarely moves 0.25 points in ~1 second between consecutive signal events. On
20260308, the filter actually skipped 6 winners (net -4.24%), showing the
discrimination is noise, not signal, at this threshold.

This is structurally the same failure mode as imbalance-skip (threshold=0.5):
too few orders are filtered, so the P&L delta is negligible. The oracle's
~84-85% baseline win rate means any coarse filter will remove roughly 84-85%
winners for every 15-16% losers it removes, making it very hard to discriminate.

**Hypothesis verdict**: The "price-ran = stale signal" hypothesis is directionally
plausible (win rate improves), but the 1-tick threshold is too conservative —
price rarely moves a full tick between consecutive oracle signals, so the filter
barely activates. The skip rate must be higher (or discrimination must be
much stronger per skip) to produce a 5%+ P&L delta.

**Suggested next attempt**:
The fundamental challenge across all three iterations is that oracle signals
already have ~84-85% win rate, making it very hard to screen out losing fills
with a coarse filter. Two directions:

1. **Batch/group execution** — rather than acting on each signal independently,
   batch signals over a short window (e.g., 5 seconds) and execute only the
   net direction. This would reduce the number of round-trips and might improve
   P&L per trade if same-direction signals cluster. Risk: may miss favorable
   entries that don't cluster.

2. **Accept all signals but split in time** — instead of skipping, submit a
   fraction of the order now and the rest 0.5s later. If the 0.5s mid-move is
   adverse, cancel the second child. This preserves P&L volume while optionally
   improving execution on some subset. Requires careful quantity-invariant
   management.

3. **Fix the signal design** — the oracle fires every second regardless of
   book state. A filter at the signal level (not execution level) would need
   strategy access, which is out-of-scope. Within execution, only the fill
   quality matters.

The highest-value next attempt is probably option 1: signal batching. If
signals over a 5s window net to BUY, submit 1 contract; if they cancel out
(mixed direction), skip. This dramatically reduces order count and focuses
execution on the clearest signals.
