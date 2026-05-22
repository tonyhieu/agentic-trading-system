# position-tier-gate-b-l6

Per-iteration experiment — arm: `base_algo=position-tier-gate`,
`mode=brief-summary`, loop 6. Starting point: `position-tier-gate-b-l5`
(this algorithm is a modified copy of that one).

## Hypothesis

Loop 5 built a passive-then-aggressive order transformation: each OPEN leg
rests a post-only LIMIT child **at the same-side touch** (BUY at the cached
bid, SELL at the cached ask) for `passive_timeout_ms`; on timeout, if still
unfilled, the held-back primary MARKET order sweeps the position. That move
drove `is_weighted_bps` to 0.0336 — the first algo in this arm to beat both
the base (0.045) and `simple` (0.039) on implementation shortfall — but
realized P&L still fell 11.1% vs base.

Loop 5's `next` directive names the highest-leverage execution-objective
change explicitly: **post one tick inside the touch to trade fill-rate
against price improvement.**

This loop takes exactly that move. Instead of resting the passive limit AT
the touch, rest it ONE TICK INSIDE the touch:

- BUY: rest at `bid_price + 1 tick` (was `bid_price`).
- SELL: rest at `ask_price - 1 tick` (was `ask_price`).

Mechanism and the trade-off being measured:

- **IS per passive fill gets slightly worse.** A BUY filled at `bid+1tick`
  costs `+1tick` more in implementation shortfall than a BUY filled at the
  bid: `is_bps = (fill_px - arrival_mid) * dir / arrival_mid * 1e4`, and the
  fill price moved 1 tick toward the mid. The passive fill still beats the
  market fallback (which fills at the far touch, `+half_spread`), it just
  captures `half_spread - 1tick` of price improvement instead of the full
  `half_spread`.
- **Fill-rate should rise.** A price one tick more aggressive sits closer to
  where trades actually cross. A limit one tick inside the touch is hit by
  the same flow that would hit the touch PLUS the marginal flow that trades
  through only the first tick of depth. Higher passive fill-rate means fewer
  orders fall through to the market fallback (which pays the full
  `+half_spread`).
- **Net effect on `is_weighted_bps` is the experiment.** If the fill-rate
  gain (more orders avoid the `+half_spread` market fallback) outweighs the
  per-fill IS loss (each passive fill is `+1tick` worse than loop-5's),
  aggregate IS improves vs loop-5. If not, IS regresses toward base. Either
  outcome is an informative measurement of the fill-rate / price-improvement
  frontier.

Constraint acknowledged from loop 5's `next`: order-execution choice only
redistributes a cost that is small relative to the directional loss under
sigma=200 — it cannot move P&L positive. P&L is expected to stay in the
loop-5 envelope (trade_count is the ungated 152300 upper bound; the
structurally-negative per-trade edge dominates). The target metric for this
loop is the EXECUTION objective, `is_weighted_bps`, not realized P&L.

Safety: `bid+1tick` for a BUY and `ask-1tick` for a SELL are both still
strictly inside the spread (one tick inside the near touch never reaches the
far touch unless the market is locked one-tick-wide; `post_only=True`
guarantees the limit is rejected rather than crossing if that ever happens,
preserving the no-cross invariant). The tick size is read from the
instrument definition in the cache; if the instrument or quote is
unavailable at `on_order()` time the algo fails open to an immediate market
order, identical to loop 5 and the base.

## Implementation Decisions

- Single structural change vs loop 5: the passive limit price is offset one
  `instrument.price_increment` toward the mid. Everything else — the
  hold-back primary as deferred market fallback, the `passive_timeout_ms`
  time alert, the CLOSE-leg straight-to-market path, the fail-open warmup
  path, the `reduce_primary=False` full-quantity child spawn — is unchanged
  from loop 5.
- `passive_timeout_ms` is kept at loop 5's 750 ms. Loop 5's `next` listed
  timeout tuning as an *alternative* to the inside-the-touch move; this loop
  isolates the price-offset variable, so the timeout is held constant.
- The instrument is fetched via `self.cache.instrument(order.instrument_id)`
  to read `price_increment`. If it is `None` (should not happen once data is
  loaded), the algo fails open to an immediate market order rather than
  guessing a tick size.
- A post-only limit one tick inside the touch is still post-only: if the
  offset price would lock or cross the book the venue rejects the limit
  (post_only), and the timeout path's market fallback still honours the
  parent intent. No double-fill: exactly one of {passive limit, primary
  market} fills the 1-lot parent.

### Bug found and fixed during this loop

Two pre-existing defects in `scripts/run_research_backtest.py` surfaced and
were fixed (they are unrelated to the algorithm under study; both are
cosmetic-print bugs that aborted otherwise-successful dates):

1. `spawn_limit(price=...)` requires a `nautilus_trader` `Price` object.
   `quote.bid_price + offset` returns a `decimal.Decimal` (Price +/- Decimal
   arithmetic widens to Decimal). Fixed in the algo by wrapping the offset
   price in `instrument.make_price(...)`.
2. The runner's per-date `OK` / `CACHE` print lines did
   `m['sharpe_ratio']`, but every per-date `metrics.json` (algo AND cached
   baseline) carries the key as `sharpe_ratio_intraday`. The bare access
   raised `KeyError('sharpe_ratio')` *inside* the date's `try` block, so the
   date was logged as `FAIL 'sharpe_ratio'` even though the backtest itself
   succeeded and wrote `metrics.json`. Fixed both print lines (algo path and
   cached-baseline path) to fall back across both keys, matching the
   normalization the non-cached baseline path at line ~1006 already used.
   `aggregate()` itself never needed the per-date key — it recomputes
   `sharpe_ratio` from per-date P&L — so this was purely a logging defect.

## Backtest Observations

Command: `python scripts/run_research_backtest.py --algo
position-tier-gate-b-l6 --use-cached-baseline`. All 12 train dates
(2026-03-08 .. 2026-03-21) completed; per-date trade counts 449-28377, no
low-sample date.

Aggregate (train window), vs base `position-tier-gate`:

| metric            | loop-6   | base ptg | loop-5   |
|-------------------|----------|----------|----------|
| realized_pnl      | -7563.72 | -5892.25 | -6548.25 |
| sharpe_ratio      | -19.93   | -27.23   | -16.56   |
| max_drawdown_pct  | -0.1514  | -0.0986  | -0.1461  |
| win_rate          | 0.3286   | 0.3285   | 0.3286   |
| trade_count       | 152300   | 101304   | 152300   |
| mean_slippage     | 0.0      | 0.0      | 0.0      |
| is_weighted_bps   | 0.03857  | 0.04501  | 0.03359  |

- `vs_base_pnl_pct = -28.37%` (-7563.72 vs -5892.25).
- `vs_base_slippage_pct = 0.0%` (mean_slippage identically 0.0 on every algo
  in this arm — there is nothing to win on the slippage metric).
- FAILs the config pass gate vs the `simple` baseline (realized_pnl
  -7563.72 vs +156.00).

THE HYPOTHESIS WAS WRONG — the trade-off resolved against the change.
Posting one tick inside the touch was meant to lift fill-rate enough to
offset the +1-tick per-fill IS cost. It did not:

- `is_weighted_bps` rose to 0.03857 — a 14.8% REGRESSION vs loop-5's
  0.03359. It still beats base (-14.3%) and edges `simple`'s 0.03893
  (-0.94%), but loop-5 already beat both by a wider margin (loop-5 was
  -25.4% vs base and -13.7% vs simple). Loop-6 is strictly worse on the
  execution objective than the algo it was built from.
- Interpretation: the +1-tick per-fill IS penalty is a deterministic cost
  paid on EVERY passive fill, whereas the fill-rate gain is at best
  marginal — the marginal flow that trades through exactly the first tick of
  depth is small relative to the flow that already hit loop-5's touch. The
  per-fill penalty dominates: pushing the limit toward the mid moves every
  passive fill's price closer to the arrival mid (less price improvement
  captured), and that direct cost is not recovered by converting a few
  would-be market fallbacks into passive fills. The IS-optimal passive
  resting price within this passive-then-aggressive structure is therefore
  AT the touch (loop-5), not inside it — loop-6 is the empirical evidence
  that `inside_ticks=0` beats `inside_ticks=1`.
- P&L fell further too (-28.4% vs base, vs loop-5's -11.1%), consistent with
  loop-5's standing constraint: execution-side price changes only
  redistribute a cost small relative to the sigma=200 directional loss, and
  here the redistribution went the wrong way.

CONSTRAINT carried forward: within the loop-5 passive-then-aggressive
structure, moving the passive limit AWAY from the touch (toward the mid)
strictly worsens IS — the price-improvement-per-fill term dominates the
fill-rate term. The remaining execution-objective levers are the OTHER
direction loop-5 named: tune `passive_timeout_ms` (a longer window lets more
limits fill AT the touch — more loop-5-quality fills, no per-fill price
penalty — at the cost of signal staleness / adverse selection), or revert
to `inside_ticks=0` and accept loop-5 as the IS frontier for this structure.
P&L remains unmovable by any execution-side choice under sigma=200.
