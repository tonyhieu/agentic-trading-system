# Algorithm Notes: imbalance-open-filter

## Hypothesis

**Mechanism**: Conditional submission — at `on_order` time, inspect the current
top-of-book bid/ask size ratio (imbalance) from the cache. Opening orders are
submitted only when the imbalance confirms the order direction; reduce-only
(closing) orders always pass through immediately with no gating. Opening orders
that fail the imbalance check are dropped (not deferred), letting the oracle
strategy re-enter naturally on the next signal cycle (~1 second later) if the
signal persists.

**Inefficiency exploited**: The oracle signal has `sigma=0.5` Gaussian noise
on a 30-second forward price forecast. Marginal signals (edge barely above
`entry_threshold=0.5`) that fire against a strongly adversarial book are more
likely to be noise-driven than true-positive. Book imbalance
(bid_size / (bid_size + ask_size)) at decision time provides a secondary,
noise-independent signal about short-term directional pressure. By requiring
the book to confirm the open order direction, we skip marginal entries where
the oracle noise is more likely to dominate.

**Why it survives costs**: The fill model reports zero commissions and zero
slippage for all algos under the current backtest setup (see `research/NOTES.md`
DATA ISSUE). The only channel through which this algorithm can improve realized
P&L is by skipping trades that would have realized losses (or smaller wins),
thereby raising realized P&L per trade and net P&L. The filter is directional
(it does not delay execution, so it cannot improve slippage in the current
fill model). Trades are not lost permanently — the oracle re-fires and a
new open order arrives within ~1 second if the underlying signal persists.

**Builds on**: none — original hypothesis (the prior algorithm
`reduce-only-cooldown` applied a close-side deferral; this algorithm takes a
completely different mechanism: open-side conditional filtering).

**Alternatives considered**:
- *Defer opens until imbalance confirms (vs. skip)*: deferral would keep the
  order alive and wait for a confirming quote; rejected for this iteration
  because the reduce-only-cooldown showed that deferred orders get superseded
  when the strategy reverses inside the wait window. Skipping is cleaner and
  allows natural re-entry.
- *Apply filter to close orders as well*: rejected — filtering closes creates
  the same supersession/trade-count-drop problem as `reduce-only-cooldown`.
  The prior algorithm's NOTES.md flagged this as a fragile assumption.
- *Order-book depth (multiple levels) instead of top-of-book*: rejected —
  data loaded is L1 QuoteTick; `subscription_quote_ticks()` gives the BBO
  only. Depth would require the full L2 feed which isn't surfaced by the
  current data loader.
- *Filter both opens and closes by imbalance*: rejected — same concerns as
  filtering closes alone.

---

## Implementation Decisions

- `imbalance_threshold` is the only kwarg, default `0.45`. A BUY order is
  submitted when `bid_size / (bid_size + ask_size) >= threshold`; a SELL
  order is submitted when `ask_size / (bid_size + ask_size) >= threshold`
  (i.e., `bid_size / (bid_size + ask_size) <= 1 - threshold`). A threshold
  of 0.45 means the book just needs to not be extremely against you — it's a
  loose filter that avoids the most adversarial conditions.
- The algorithm subscribes to `quote_ticks` for the order's instrument in
  `on_start`. The instrument_id is extracted from the first order seen and
  the subscription is made lazily if `on_start` cannot preregister (the
  instrument_id is not known at construction time). Subscription populates
  `self.cache.quote_tick(instrument_id)`.
- Fallback: if no quote tick is cached for the instrument yet (e.g., on the
  very first order before any quote arrives), the order is submitted
  unconditionally to avoid missing the session start.
- Close/reduce-only orders bypass the filter entirely — they always pass
  through immediately, identical to the `simple` baseline for closes.
- No deferred state is kept — there is no `_deferred` dict. The algorithm
  is stateless between orders (except for the subscription flag).
- `top_of_book_only` constraint: the oracle strategy submits market orders
  for qty=1. The participation cap floor is `floor(0.05 × top_of_book_qty)`.
  With typical bid_size and ask_size of 1–42 lots, floor(0.05 × 1) = 0 so
  the cap could technically be 0. However, the simple baseline never splits
  orders (it submits qty=1 directly), so this is an existing framework
  behavior. This algorithm makes the same submission — qty=1 market order —
  so the constraint is met equivalently.

**Concerns**:
- *Look-ahead bias*: none. The imbalance check reads `self.cache.quote_tick()`
  which holds the most recent quote at the current backtest timestamp — i.e.,
  the BBO that exists when the oracle signal fired. No future data is read.
- *Instrument_id extraction from order*: `order.instrument_id` is set by
  the strategy before routing to the exec algorithm — this is present on all
  order types and is safe to read in `on_order`.
- *Session-end position management*: the strategy closes all positions via
  `close_positions_on_stop`, which emits reduce-only orders. These pass
  through unconditionally in this algorithm, so the `intraday_flat` constraint
  is respected.
- *Overfitting risk*: threshold=0.45 is a design choice, not an in-sample
  fit. Sweeping thresholds would overfit to training dates. A single
  principled threshold is used for this iteration.

---

## Backtest Observations

Run on the same partitions as the previous iteration (3 train + 1 test):
train = {20260309, 20260313, 20260317}; test = {20260406}. `imbalance_threshold=0.45`.

| split | date     | algo                   | pnl     | trades | win_rate | sharpe  |
|-------|----------|------------------------|---------|--------|----------|---------|
| train | 20260309 | simple                 | 3092.00 | 1194   | 0.846    | 382.7   |
| train | 20260309 | imbalance-open-filter  | 3050.50 | 1137   | 0.855    | 378.1   |
| train | 20260313 | simple                 | 2297.00 | 2031   | 0.733    | 444.2   |
| train | 20260313 | imbalance-open-filter  | 2274.75 | 1752   | 0.765    | 445.7   |
| train | 20260317 | simple                 | 2022.75 | 4168   | 0.642    | 545.3   |
| train | 20260317 | imbalance-open-filter  | 2059.25 | 3358   | 0.710    | 566.3   |
| test  | 20260406 | simple                 | 2520.75 | 4396   | 0.674    | 503.6   |
| test  | 20260406 | imbalance-open-filter  | 2540.00 | 3707   | 0.722    | 513.4   |

**Train aggregates** (sum P&L, mean slippage):
- simple                : pnl_sum = 7411.75, mean_slip = 0.0
- imbalance-open-filter : pnl_sum = 7384.50, mean_slip = 0.0
- `delta_pnl_pct` (train) = (7384.50 − 7411.75) / 7411.75 × 100 = **−0.368%**
- `delta_slip_pct` = 0 (both algos report zero slippage — known fill model issue).

**Test (1 date — RESULT WARNING, same as prior iteration)**:
- `delta_pnl_pct` (test) = (2540.00 − 2520.75) / 2520.75 × 100 = **+0.764%**

**Gate** (`min_pnl_improvement_pct = 5.0`, `close_margin_pct = 2.0`):
- Train P&L delta is **−0.368%** vs the required **+5.0%** → fails the P&L gate.
- Distance from PASS on the P&L axis = 5.368pp, which exceeds `close_margin_pct = 2.0`.
- Distance from CLOSE = 5.368pp − 2.0pp = 3.368pp. **FAIL**, not CLOSE.
- Slippage gate: both 0.0 → trivially passes (uninformative; see research/NOTES.md).

**What drove improvement**: On 20260317 the filter boosted P&L by +1.8% and win rate
by +6.9pp (0.642→0.710). This suggests that on high-volume days the imbalance signal
has more predictive content — perhaps because wider spreads or thinner books on 20260317
(46k oracle signals vs 6.9k on 20260309) make imbalance more informative. The test date
(20260406) showed a modest +0.764% improvement with win rate +4.8pp.

**What underperformed**: On 20260309 and 20260313 the filter hurt P&L by −1.3% and −1.0%
respectively. The filter removed some winning trades by mistakenly classifying
"adversarial" books: with threshold=0.45, ~36% of ticks fail the buy-side check
(bid_ratio < 0.45) even though the oracle forecast was correct. The filter accuracy is
too low to produce a net positive on these dates.

Win rate improved consistently across all 4 dates (+0.9pp, +3.2pp, +6.9pp, +4.8pp),
confirming the filter does remove some losing trades. But it removes roughly as many
(or more) winning trades at threshold=0.45, producing a net P&L loss.

**Hypothesis verdict**: PARTIALLY supported. The mechanism (imbalance filtering of
opening orders) does improve win rate consistently and P&L on some dates. The effect
size is too small and too variable at threshold=0.45 to reliably beat the +5% gate.
A stronger threshold (0.55+) would filter more aggressively and might extract larger
improvements on favorable dates — but at the risk of over-filtering on quiet days.

**Suggested next attempt**: Two directions worth exploring:
1. *Higher imbalance threshold (e.g., 0.55)* — filter more aggressively; accept fewer
   opens; concentrate on higher-conviction setups. Higher variance, higher expected
   P&L delta when it works. Risk: over-filtering on low-volume dates.
2. *Volatility-conditional threshold* — use a tighter imbalance threshold on high-signal
   days (identified by, e.g., oracle-signal count or spread width) and a looser one on
   quiet days. This adapts the filter to the regime rather than using a fixed value.
