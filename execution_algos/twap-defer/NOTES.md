# Algorithm Notes: twap-defer

## Hypothesis

**Mechanism**: Participation-cap-compliant deferred execution. When an open
order arrives and the current top-of-book quantity is too thin (floor(cap ×
book_qty) == 0), the algorithm queues the order and retries on each subsequent
quote tick for up to `max_defer_ticks` ticks. If the book thickens (cap >= 1)
within that window, the order is submitted. If the window expires, the order
is submitted anyway (to avoid total P&L loss from skipping). Reduce-only
(close) orders are always submitted immediately to maintain intraday_flat
compliance and avoid position desync.

**Inefficiency exploited**: The `simple` baseline submits all orders
immediately regardless of book depth, violating the participation cap silently
on thin-book ticks (~32% of oracle order events per 20260317 analysis). These
are operationally invalid fills. On thin-book sessions (20260309, 20260313),
the baseline runs thousands of trades because it ignores the cap; a
cap-compliant algorithm that defers rather than skips can still participate
in those trades — just slightly later — without losing the opportunity.
Unlike `cap-boost`, we do NOT inflate order quantity; we stay at the original
1-lot parent size (quantity invariant preserved).

**Why it survives costs**: In the zero-slippage fill model, every 1-lot fill
contributes the same P&L regardless of which tick it executes on (within the
oracle's 30-second horizon window). Deferring up to K=3 ticks (3 seconds) is
well within the 30-second signal validity and should yield nearly identical
P&L to immediate submission. The participation-cap compliance is the execution
quality improvement — we are not introducing additional P&L cost, just
re-timing within the oracle window. This avoids the quantity-inflation problem
of `cap-boost` (which inflated to 2 lots, violating the quantity invariant)
while preserving cap compliance.

**Builds on**: none — original hypothesis (first logged iteration). This is
the first entry in the program database.

**Alternatives considered**:
- *Simple with cap enforcement (skip cap=0)*: would drastically reduce trade
  count and P&L on thin-book sessions. Rejected because skipping discards
  valid oracle opportunities.
- *Cap-boost (size inflation)*: inflates to 2-lot orders on thick-book ticks.
  Violates the quantity invariant per OBJECTIVE.md §3 (child_fills > parent
  quantity). Prior exploratory runs showed poor performance on thin-book days.
  Rejected.
- *TWAP split*: would fragment 1-lot orders into sub-1-lot child orders. Since
  minimum tick size is 1 contract, splitting is not feasible for this
  instrument. Rejected.
- *Momentum-aligned timing within the oracle window*: would require inspecting
  price moves and deferring based on direction — risks introducing subtle
  look-ahead bias if the timing happens to correlate with future fills.
  Rejected in favour of the simpler cap-only deferral.

---

## Implementation Decisions

- `participation_cap` is read from `config.yaml` at runtime (not hardcoded),
  consistent with OBJECTIVE.md §3 ("Read the constraint values from config.yaml").
- `max_defer_ticks`: default 3 (3 seconds if quotes arrive at ~1 Hz). This is
  well within the 30-second oracle horizon. Kept short to avoid holding pending
  orders across signal changes.
- Pending order queue: a `dict[str, list[Order]]` keyed by instrument_id.
  Each new quote tick for the instrument fires `on_quote_tick`, which drains
  any pending orders that can now be submitted (cap >= 1).
- Defer count: each pending order carries a tick counter. When the counter
  reaches `max_defer_ticks`, the order is submitted unconditionally (avoids
  discarding the trade entirely).
- Reduce-only orders: submitted immediately. Tracking when a reduce-only order
  could arrive but the corresponding open was still pending would add
  complexity; since intraday_flat is a hard constraint, we prioritize closing
  positions promptly. The reduce-only order will close the still-open 1-lot
  position or, if no position is open, have no effect.
- No quantity modification: the algorithm never changes parent order size.
  child_fills == parent.quantity == 1 always.

**Concerns**:
- If the oracle's close + open both arrive within the same tick window and the
  open gets deferred, the close order arrives first (by oracle design) and may
  try to close a position that hasn't been opened yet. This is fine —
  reduce-only closes with nothing open have no effect on position.
- No look-ahead: the book size check uses the LAST quote tick (observable
  in real-time). No future price or size information is used.
- On days where the book is thin throughout (cap=0 for all ticks), all orders
  will expire their defer window and submit anyway, matching baseline behavior.

---

## Backtest Observations

*(to be filled in after §5 step 6)*

**What drove improvement**:
**What underperformed**:
**Hypothesis verdict**:
**Suggested next attempt**:
