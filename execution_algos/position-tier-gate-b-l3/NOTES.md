# position-tier-gate-b-l3

Per-iteration experiment — arm: `base_algo=position-tier-gate`,
`mode=brief-summary`, loop 3. Starting point: `position-tier-gate-b-l2`.

## Hypothesis

The loop-2 brief summary concluded that equity-feedback gating is exhausted:
loops 1 and 2 both gated OPEN legs on a portfolio-equity circuit breaker, and
the loop-2 finding was that loop-1's +71.6% vs base was pure *volume
suppression* — under sigma=200 the per-trade edge is structurally negative
(~-5.8 USD per 100 trades), so trading less loses less and trading more loses
more. The loop-2 re-arming breaker restored volume and the P&L promptly fell
to -50.3% vs base. An equity breaker cannot distinguish a good entry from a
bad one; it only throttles a *random* subset of orders.

The loop-2 `next` directive is explicit: gate on an order-time
signal-quality / market-state feature (spread, top-of-book imbalance, recent
realized volatility) so the algo skips *genuinely worse* entries rather than a
random subset.

Loop 3 acts on that directive. It replaces the equity circuit breaker
entirely with a **microstructure entry filter** evaluated at order time from
the latest top-of-book quote (`cache.quote_tick(instrument_id)`):

1. **Spread filter.** Compute the bid-ask spread in ticks. A wide spread at
   entry means a worse fill and a larger immediate mark-to-market loss before
   the position can be closed. When the spread exceeds `max_spread_ticks` the
   OPEN leg is skipped — this should remove the entries that are most
   structurally disadvantaged by execution cost.

2. **Top-of-book imbalance filter.** Compute imbalance
   `imb = (bid_size - ask_size) / (bid_size + ask_size)`, in [-1, +1]. A buy
   OPEN into a book that is heavily ask-stacked (imb strongly negative) is
   leaning against visible resting supply; a sell OPEN into a heavily
   bid-stacked book (imb strongly positive) leans against resting demand.
   When the OPEN leg's direction is on the unfavourable side of the book by
   more than `imb_threshold`, the leg is skipped.

Closing / reduce-only orders always submit unconditionally — intraday_flat
compliance is unaffected; exposure reduction is never gated.

Expected effect: unlike the loop-1/loop-2 equity gate, this filter removes a
*non-random* subset of opens — the ones taken at wide spreads or against the
book. If the structural -5.8 USD/100-trade drag is concentrated in those
microstructure-disadvantaged entries, P&L per remaining trade should improve
and total P&L should beat the equity-gate loops. If the drag is uniform
across entries (i.e. driven purely by the sigma=200 signal noise and not by
execution conditions), filtering will again look like volume suppression and
P&L vs base will mostly track the skip fraction — that itself is a useful
negative result distinguishing signal noise from execution cost.

### Implementation decisions

- Features are read at `on_order()` time from `cache.quote_tick(...)`, which
  returns the most recent quote already processed by the engine — strictly in
  the past relative to the current order's `ts_init`. No look-ahead.
- When no quote is cached yet (session warm-up, before the first quote
  arrives), the order is submitted (fail-open) rather than skipped, so the
  filter never silently halts the whole session.
- OPEN-leg direction is taken from `order.side` (BUY vs SELL). The imbalance
  sign convention: positive imbalance = bid-heavy. A BUY is unfavourable when
  imbalance is strongly negative (ask-stacked); a SELL is unfavourable when
  imbalance is strongly positive (bid-stacked).
- Spread in ticks uses the instrument's `price_increment`; falls back to a
  raw price-unit comparison if the instrument is not in cache.
- No order quantity is ever modified — orders are submitted or skipped only.

## Diagnosis and design correction (during loop 3)

The first loop-3 implementation gated on **two** features — a bid-ask spread
filter and the top-of-book imbalance filter. That version's full backtest
exposed two coupled failures:

1. **Engine crash on 6 of 12 train dates.** The runner reported
   `_run_one_in_process raised: 'side'`. The traceback locates this in
   `backtest_engine/backtest_low_level.py:39`, `_unrealized_pnl()`, which
   does `positions["side"]` on the positions DataFrame. When the algo
   produces **zero positions** for a date, `reports.positions` is an empty
   DataFrame with no `"side"` column, so the access raises `KeyError`. This
   is a latent pre-existing engine bug, but it is triggered only by an
   execution algorithm that skips 100% of opens on a date — which the
   two-filter loop-3 version did.

2. **trade_count collapsed to 1 per day on the dates that did complete.**
   45634 open-leg orders on 20260316, exactly 1 filled; the other 45633
   stayed `INITIALIZED` (received but never submitted). Open-leg sides were
   ~50/50 BUY/SELL, ruling out a directional artifact.

A skip-reason instrumentation run on 20260316 found the **spread filter** was
the sole blocker (`spread_skip=45633`, `imb_skip=0`). The cause: the spread
of the quote returned by `cache.quote_tick()` in this backtest pipeline is
heavily quantized and far wider than a real MES book — percentiles on 45,634
quotes were p1..p75 = 25 ticks, p90..p99 = 50 ticks, max 75 ticks. The
`max_spread_ticks=2.0` threshold (calibrated for a real 1-tick MES book)
therefore rejected every open. More fundamentally, a spread-in-ticks filter
is useless here regardless of threshold: with only ~three discrete spread
values it can pass all, ~76%, or none — it cannot finely rank entries.

**Correction.** The spread filter was removed. The loop-3 algo now gates on
the **imbalance filter only**, whose distribution *is* genuinely continuous
(-0.94..+0.94, median ~0.03 on 20260316). With `imb_threshold=0.5` a
re-instrumented single-date run produced `trade_count=19267`,
`realized_pnl=-892.75` on 20260316 — non-degenerate, no crash. The full
paired backtest below uses this corrected imbalance-only design.

This is the honest record: the original spread premise did not survive
contact with the data, and the loop-3 result reflects the imbalance filter
alone.

## Backtest Observations

Full paired backtest, 12 train dates (2026-03-08 .. 2026-03-20), oracle
strategy, `imb_threshold=0.5`. All 12 dates completed cleanly — no crash, no
dropped dates.

Aggregate (vs base_algo `position-tier-gate`):

| metric            | loop-3      | base position-tier-gate | delta            |
|-------------------|-------------|-------------------------|------------------|
| realized_pnl      | -6509.25    | -5892.25                | -10.47% vs base  |
| mean_slippage     | 0.0         | 0.0                     | 0.0% (both flat) |
| sharpe_ratio      | -22.4682    | -27.2287                | +4.76 absolute   |
| max_drawdown_pct  | -0.1264     | -0.0986                 | worse by 0.028pp |
| win_rate          | 0.3398      | 0.3285                  | +1.13 pp         |
| trade_count       | 131232      | 101304                  | +29928           |

vs the configured `simple` baseline the runner reports realized_pnl
-6509.25 vs +156.00 — the suggested verdict is FAIL.

Per-date trade counts ranged 432 (20260308) to 24178 (20260319); every date
cleared the 30-trade reliability floor, so Sharpe and win_rate are not
flagged as low-sample. Per-date P&L was negative on all 12 dates
(-73.50 to -1259.50).

**Interpretation.** The imbalance filter is a genuine non-random entry
filter — it skips a continuous-feature-defined subset of opens, and
trade_count (131k) sits between base (101k) and simple (~137k), not
collapsed. Yet realized P&L is -10.5% vs base. This is the negative result
loop-2's summary anticipated: under sigma=200 the per-trade edge is
structurally negative and that drag is **not** concentrated in
imbalance-disadvantaged entries — skipping orders that lean against the book
does not remove the loss-making subset, it removes a roughly representative
slice. Win rate barely moved (+1.1 pp) and Sharpe, while less negative than
base (-22.5 vs -27.2), is still deeply negative. Order-time book imbalance
is therefore not a usable signal-quality discriminator for this oracle
strategy at this noise level.

The slightly higher Sharpe and win_rate vs base, against lower total P&L, is
consistent with the filter trimming variance (fewer extreme entries) without
trimming the mean loss — it does not constitute an execution improvement.
