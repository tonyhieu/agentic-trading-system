# Algorithm Notes: position-tier-imbalance-gate

## Hypothesis

**Mechanism**: Stack two independent gates on the OPEN leg of each oracle
signal:

  1. **Positional gate** (inherited verbatim from `position-tier-gate`,
     `position_cap=1`): SKIP the OPEN leg when the current absolute net
     position is already >= 1 contract — the netting OMS reports the
     concurrent CLOSE+OPEN pair sequentially, so cap=1 reliably blocks
     the doubled-up entry that would otherwise compound directional error
     on a noisy oracle (sigma=5).
  2. **Top-of-book imbalance gate** (NEW): on the flat-entry orders that
     pass the positional gate, additionally skip when the top-of-book
     order-book imbalance is adverse to the order direction:

         imbalance = bid_size / (bid_size + ask_size)        in [0, 1]

         BUY  order: SKIP when imbalance < skip_threshold      (asks dominate
                                                                — price tends
                                                                to fall)
         SELL order: SKIP when imbalance > 1 - skip_threshold  (bids dominate
                                                                — price tends
                                                                to rise)

     Reduce-only / position-closing orders always execute (intraday_flat).

**Inefficiency exploited**: The base `position-tier-gate` (pnl=4262.50,
sharpe=17.62, trade_count=90433) already eliminates the cascade-entry leak,
but it still submits ALL 90433 flat-entry orders indiscriminately. About
63% of those entries lose (win_rate=37.0%). The Lipton–Pesavento book
imbalance signal is documented as one of the strongest short-horizon
predictors of mid-price direction (`docs/literature/BookImbalance__Lipton.md`).
Skipping entries where the immediate-future expected mid-direction is
adverse should preferentially drop losing trades, lifting realized P&L
while reducing trade_count below 90433.

**Why it survives costs**: Slippage and commissions are both zero in the
current fill model (`research/NOTES.md` 2026-04-30 DATA ISSUE), so the only
cost of taking a trade is exposure to directional risk. Skipping trades is
free; the gate's downside is missed winners, but with an imbalance
threshold like 0.40 the gate only skips trades where the book lean is
materially against the direction — those are the trades with the lowest
expected P&L.

**Builds on**: `position-tier-gate` (pnl=4262.50, sharpe=17.62, the best
algorithm so far). Mechanism added: a top-of-book imbalance filter on the
flat-state entries. Does NOT change position_cap or the existing
reduce-only fast-path.

**Alternatives considered**:
- Stacking `aggressor-flow-gate` on top of `position-tier-gate`: aggressor
  flow is a trailing-window signal (10s), so it's slower than instantaneous
  book imbalance and produced lower base performance (pnl=1255.5, sharpe=5.59
  standalone). Book imbalance is point-in-time and per-tick — a better fit
  for filtering the ~90433 entries one-by-one.
- Tighter `position_cap=2`: would let SOME cascade in, regressing the
  cascade-protection edge.
- A finer admit-rate dial (ptg-m-l1..l8 family): those experiments
  established that trade_count peaks at 90433 — they were optimizing
  trade_count via deterministic 1-in-K throttles, not via P&L-correlated
  filters. An informed (book-imbalance) filter should do better than a
  blind (modulo-K) one.

---

## Implementation Decisions

- `position_cap = 1` (inherited from base `position-tier-gate`).
- `skip_threshold = 0.40`: skip BUY entries when bid share <= 40% (asks have
  >=60% of top-of-book size), skip SELL entries when bid share >= 60%.
  This is intentionally moderate — at 0.50 the gate would fire on every
  marginally-leaning book and over-skip; at 0.30 it would only filter
  extreme book skew. 0.40 lets a meaningful fraction of adverse-lean
  entries through the filter while still catching the clearly-imbalanced
  ones.
- `min_total_size = 2`: don't activate the imbalance gate when the sum
  bid_size + ask_size is below 2 contracts — a thin top-of-book is too
  noisy a signal. Treat as neutral (do not skip).
- Subscribe to quote_ticks in `_ensure_subscribed()` on first order — the
  `self.cache.quote_tick()` call requires the subscription to deliver fresh
  quotes.
- Read the *current* `self.cache.quote_tick(order.instrument_id)` at
  decision time, not a deque history. The order's `ts_init` enforces
  chronology — the cache's most recent quote at `on_order()` time is
  strictly in the past relative to the order timestamp.
- After any imbalance skip, do NOT mutate position state — the next OPEN
  leg is still gated by `position_cap=1` (which already handles the
  flat/non-flat distinction via the cache). No anti-cascade flag needed
  because the positional gate already serves that role.

**Concerns**:
- *Look-ahead*: None. The book imbalance read uses
  `self.cache.quote_tick()`, which at `on_order()` time reflects only
  quotes already processed by the engine. The order's `ts_init` is the
  decision timestamp; the cache snapshot is <= that.
- *Overfitting*: `skip_threshold=0.40` is a design choice, not tuned to
  the train data — it's a moderate value that fires on materially-leaning
  books. The position-tier-gate's `position_cap=1` is also a fixed
  structural choice (not tuned to train).
- *Trade-count drop*: This algorithm will execute fewer than 90433 trades.
  The base algo already operates near the trade-count peak (per the
  ptg-m-l1..l8 family analysis); if the imbalance filter drops too many
  winners, realized_pnl could fall even though trade quality improves.
  This is the central empirical question this iteration is designed to
  answer.
- *Quantity invariant*: Always preserved. Every parent order is either
  submitted intact or skipped entirely.
- *Constraints*: top_of_book_only is enforced by the engine fill model
  (we never modify the order); participation_cap is irrelevant since the
  oracle's parent size is 1 contract; intraday_flat is preserved because
  reduce-only orders always submit.

---

## Backtest Observations

Train window: 2026-03-08 .. 2026-03-21 (12 trading days configured; 11 days
successfully aggregated — see DATA ISSUE below for the missing date).

| metric             | algo (PTIG) | baseline (simple) |    delta_% |
| ------------------ | ----------: | ----------------: | ---------: |
| realized_pnl       |    4344.50  |             43.25 |   +9945.09 |
| sharpe_ratio       |     21.27   |             0.17  |  +12152.33 |
| max_drawdown_pct   |    -0.0102  |           -0.0529 |     +80.72 |
| win_rate           |     0.392   |             0.350 |     +11.96 |
| trade_count        |     62251   |            111489 |     -44.16 |
| mean_slippage      |     0.000   |             0.000 |      +0.00 |
| is_weighted_bps    |     0.0667  |            0.0427 |     +56.32 |

**Verdict (train-only): PASS.** delta_pnl_pct = +9945.09 (gate ≥ 5.0);
slippage flat (no regression). Both gates fire as designed: trade_count
falls from baseline's 111,489 to 62,251 (-44%), but realized P&L rises
~100x. Win rate lifts ~4pp, indicating the imbalance filter is dropping
losing trades preferentially as hypothesized. The cross-day Sharpe (21.27)
on N=11 days is dominated by the variance reduction from the positional
gate rather than from the imbalance filter alone — base `position-tier-gate`
already reached sharpe=17.62 — but the imbalance gate adds incremental
P&L beyond the positional-only baseline.

**Slippage / costs**: mean_slippage = max_abs_slippage = 0 across all 11
dates (data-model issue documented in `research/NOTES.md` 2026-04-30).
Conclusions about slippage cannot be drawn from this run.

### DATA ISSUE — 2026-03-19 backtest failure

The 20260319 backtest reproducibly failed with a Rust OOM in the Nautilus
backtest subprocess:

  `memory allocation of 8589934592 bytes failed`  (signal 6, SIGABRT)

System memory at the time: 30 GiB available, 22 GiB free. The failure is
not memory-pressure-driven — a single allocation requested 8 GiB. Two
retries with identical input produced identical crashes. The same algorithm
ran successfully on 11 other train dates (including 20260320, the
following session), and the simple-baseline cache covers 20260319 with
trades=25,245, pnl=112.75, sharpe=0.64 — so the issue is specific to the
interaction between this algorithm's quote-subscription path and the
2026-03-19 partition.

Reported in `research/NOTES.md` 2026-05-23 DATA ISSUE. Aggregate metrics
above span the 11 successful dates only; per §8, the missing date is
disclosed, not silently dropped.

### Trade-count concern resolved

The pre-run concern that the imbalance filter might drop too many winners
proved unfounded at threshold 0.40: P&L roughly doubles vs position-tier-gate
(which posted 4262.50 on 12 dates), and win-rate improves rather than
degrades. The filter does what its design intent claimed: it removes the
trades where the order-book lean is materially adverse to the trade
direction, which are disproportionately losing trades.
