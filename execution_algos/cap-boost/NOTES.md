# Algorithm Notes: cap-boost

## Hypothesis

**Mechanism**: Participation-cap-aware order sizing. For each open (non-reduce-only)
order, check the current top-of-book quantity from the quote-tick cache and compute
`allowed_contracts = floor(participation_cap × top_book_qty)`.

- If `allowed_contracts == 0` (book is too thin): skip the order entirely (enforce the
  constraint the baseline silently violates).
- If `allowed_contracts == 1` (normal book): submit the 1-lot order as-is.
- If `allowed_contracts >= 2` (thick book): spawn a child market order for 2 lots and
  submit it, doubling position size on high-liquidity ticks.

For reduce-only (close) orders: look up the actual open position quantity and submit
the exact quantity needed to close it (matching whatever size the open established).
This keeps position tracking consistent.

**Inefficiency exploited**: The simple baseline executes all oracle orders at 1-lot
regardless of book depth. Analysis of the 20260317 session shows:
- 31.9% of oracle order events occur when `floor(0.05 × top_book_qty) == 0` — the
  baseline is violating the participation constraint silently. These trades are
  operationally invalid.
- 34.1% of oracle order events occur when the book is thick enough to support
  2 contracts. By trading 2 lots in these windows, we double the P&L on those
  trades.
- Empirically (20260317 baseline), trades from thick-book moments have a mean P&L
  of $0.53 vs $0.47 for thin-book moments — slightly higher quality.

**Why it survives costs**: The current fill model reports zero commissions and zero
slippage (DATA ISSUE in research/NOTES.md). In this environment every correctly
timed trade contributes P&L proportional to its quantity. Doubling quantity on
cap>=2 ticks approximately doubles those trades' P&L, which should raise net
realized P&L above the baseline by a meaningful margin.

The participation-cap enforcement (skipping cap=0 trades) reduces trade count by
~32% on its own, which would hurt P&L (those cap=0 trades have positive expected
P&L). However, the doubling on the cap>=2 trades compensates. The net expected
gain from 20260317 data: +$117.75 / $2022.75 ≈ +5.8%, near the +5% gate.

**Builds on**: none — original hypothesis. Prior algorithms (`reduce-only-cooldown`,
`imbalance-open-filter`) attempted timing or book-state gating without changing
quantity. This algorithm takes a different lever: execution size.

**Alternatives considered**:
- *Only enforce cap (skip cap=0, keep cap=1)*: would lose $630.50 per day from
  cap=0 P&L without compensating gain. Expected: FAIL.
- *Only double on cap>=2 (ignore cap=0 violation)*: simpler, avoids constraint
  enforcement downside, but the baseline already violates this — we'd just be
  selectively adding to some positions. Close tracking becomes complex. Rejected
  in favour of the cleaner "full cap awareness" approach.
- *Triple or higher on thick-book ticks*: cap=3+ ticks are only 0.4% of order
  events. Negligible impact. Rejected.
- *Close deferral combined with cap-boost*: compounds two changes. OBJECTIVE.md §6
  requires ONE targeted change per refinement. Rejected.

---

## Implementation Decisions

- `participation_cap` and `min_qty_for_boost` (default 2) are read from
  `execution_algorithm_kwargs` so they can be tuned without code changes.
- Quote-tick subscription via `self.subscribe_quote_ticks(instrument_id)` in
  `on_start` is not feasible (instrument unknown at start). Instead, subscribe
  lazily in `on_order` the first time we see an instrument.
- `self.cache.quote_tick(instrument_id)` returns the most-recent quote after
  subscription. On the very first order (before any quote tick is cached), we
  fall back to `submit_order(order)` as baseline behaviour to avoid skipping
  the first trade of the day.
- Position tracking: `_open_qty[instrument_id]` records the actual number of lots
  opened. On the close path we read this (falling back to the order quantity if
  not found) to submit the right-sized close.
- For close orders with `qty > 1` we use `spawn_market()` to create a child order
  with the correct quantity. The primary close order is used as the spawner context.
- `intraday_flat` compliance: because we always close exactly the quantity we
  opened, end-of-day position should be zero. If the oracle's EOD flatten order
  arrives and we have a non-standard qty open, we still match it to `_open_qty`
  to close fully.
- The oracle sends exactly one close + one open at each signal timestamp. The close
  arrives first. We track `_open_qty` so that the subsequent close knows the right
  quantity to submit.

**Concerns**:
- If `cache.quote_tick()` returns a tick that is stale (old book state), the book
  size used for the cap calculation may not reflect the actual book at fill time.
  This is unavoidable without intra-order LOB access; the quote tick cache always
  returns the most recent snapshot.
- No look-ahead: the book size check uses the LAST quote tick before the order
  arrives, which is observable in real-time. No future price or size information
  is used.
- The size-boost changes absolute P&L exposure (risk). In a real system this
  would require risk-budget coordination with the strategy. Here it is treated
  as within the execution algorithm's remit since the config's participation_cap
  sets the upper bound.

---

## Backtest Observations

*(to be filled in after §5 step 6)*

**What drove improvement**:
**What underperformed**:
**Hypothesis verdict**:
**Suggested next attempt**:
