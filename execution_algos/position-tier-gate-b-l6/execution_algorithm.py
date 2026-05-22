"""Position-tier-gate-b-l6 execution algorithm.

Per-iteration experiment — arm: base_algo=position-tier-gate,
mode=brief-summary, loop 6. Starting point: `position-tier-gate-b-l5`
(this file is a modified copy of that algorithm).

WHAT CHANGED FROM LOOP 5
------------------------
Loop 5 introduced a passive-then-aggressive order TRANSFORMATION: each OPEN
leg rests a post-only LIMIT child at the SAME-SIDE TOUCH (BUY at the cached
bid, SELL at the cached ask) for `passive_timeout_ms`; on timeout, if still
unfilled, the held-back primary MARKET order sweeps the position. That move
drove `is_weighted_bps` to 0.0336 — the first algo in this arm to beat both
the base (0.045) and `simple` (0.039) on implementation shortfall — but
realized P&L still fell 11.1% vs base.

Loop 5's `next` directive names the highest-leverage execution-objective
change explicitly: post one tick INSIDE the touch to trade fill-rate against
price improvement. This loop takes exactly that move.

THE CHANGE — POST ONE TICK INSIDE THE TOUCH
-------------------------------------------
Loop 5 rested the passive limit AT the touch. This loop rests it ONE TICK
INSIDE the touch (toward the mid):

  - BUY:  rest at `bid_price + 1 tick`  (loop 5: `bid_price`).
  - SELL: rest at `ask_price - 1 tick`  (loop 5: `ask_price`).

The tick size is `instrument.price_increment`, read from the cache.

THE TRADE-OFF BEING MEASURED
----------------------------
`backtest_engine/arrival_price.py` defines

    is_bps = (fill_px - arrival_mid) * direction / arrival_mid * 10_000

- IS per passive fill gets slightly worse. A BUY filled at `bid+1tick`
  costs `+1tick` more IS than a BUY filled at the bid — the fill price moved
  one tick toward the mid. The passive fill still beats the market fallback
  (which fills at the far touch, `+half_spread`); it just captures
  `half_spread - 1tick` of price improvement instead of the full
  `half_spread`.
- Fill-rate should rise. A price one tick more aggressive sits closer to
  where trades cross, so it is hit by the same flow that hits the touch PLUS
  the marginal flow that trades through only the first tick of depth. Higher
  passive fill-rate means fewer orders fall through to the market fallback.
- Net effect on `is_weighted_bps` is the experiment. If the fill-rate gain
  outweighs the per-fill IS loss, aggregate IS improves vs loop 5; if not it
  regresses toward base. Either way it measures the fill-rate /
  price-improvement frontier.

P&L is expected to stay in the loop-5 envelope: order-execution choice only
redistributes a cost small relative to the directional loss under sigma=200,
and trade_count is the ungated upper bound. The TARGET metric here is the
execution objective `is_weighted_bps`, not realized P&L.

EVERYTHING ELSE IS UNCHANGED FROM LOOP 5
----------------------------------------
The hold-back primary as deferred market fallback, the `passive_timeout_ms`
time alert, the CLOSE-leg straight-to-market path, the fail-open warmup
path, and the `reduce_primary=False` full-quantity child spawn are all
identical to loop 5.

INVARIANTS
----------
- Quantity: exactly one of {passive limit, primary market} fills the 1-lot
  parent intent. The primary is submitted on the timeout path ONLY when the
  limit is still open (unfilled); if the limit filled, the primary is never
  submitted. Total filled quantity == parent quantity.
- intraday_flat: CLOSE orders never enter the passive path; the passive
  window on opens (`passive_timeout_ms`) is short and far inside session.
- No look-ahead: the touch price comes from `cache.quote_tick()` at
  `on_order()` time — the most recent quote at or before the order's
  `ts_init`. No future data is read.
- No cross: the limit is one tick INSIDE the near touch, strictly inside the
  spread unless the book is locked one-tick-wide; `post_only=True` makes the
  venue reject the limit (rather than crossing) in that edge case, and the
  timeout path still honours the parent intent via the market fallback.
- Fail-open: if no quote OR no instrument definition is cached yet (session
  warmup), the primary is submitted immediately as a plain MARKET order —
  identical to base / loop 5's warmup path.
"""
from __future__ import annotations

import pandas as pd

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PositionTierGateBL6Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the position-tier-gate-b-l6 execution algorithm.

    Parameters
    ----------
    passive_timeout_ms : int
        How long (milliseconds) a post-only limit may rest before the market
        fallback fires. Held at loop 5's value so this loop isolates the
        price-offset variable.
    inside_ticks : int
        How many ticks INSIDE the near touch (toward the mid) the passive
        limit is posted. 0 reproduces loop 5 (post at the touch); 1 is this
        loop's change.
    """

    passive_timeout_ms: int = 750
    inside_ticks: int = 1


class PositionTierGateBL6Algorithm(ExecAlgorithm):
    """Passive-then-aggressive execution algorithm, posting one tick inside
    the touch.

    Each OPEN leg first rests a post-only limit (a child order) `inside_ticks`
    ticks inside the same-side touch; if it is unfilled after
    `passive_timeout_ms` the held-back primary market order is submitted to
    sweep the position. Reduce-only CLOSE legs route straight to market. See
    the module docstring for the IS rationale.
    """

    def __init__(self, config: PositionTierGateBL6Config) -> None:
        super().__init__(config=config)
        self._timeout = pd.Timedelta(milliseconds=config.passive_timeout_ms)
        self._inside_ticks = int(config.inside_ticks)
        # Map: time-alert name -> (primary order, spawned limit order).
        self._pending: dict[str, tuple] = {}
        self._alert_seq: int = 0
        # Diagnostic counters (per session) — do not affect routing.
        self._n_open: int = 0
        self._n_close: int = 0
        self._n_passive_spawned: int = 0
        self._n_market_fallback: int = 0
        self._n_fail_open: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self._reset_state()
        self.log.info(
            "PositionTierGateBL6Algorithm started "
            f"(passive-then-aggressive, timeout={self._timeout}, "
            f"inside_ticks={self._inside_ticks})."
        )

    def on_reset(self) -> None:
        self._reset_state()

    def on_stop(self) -> None:
        self.clock.cancel_timers()
        self.log.info(
            "PositionTierGateBL6Algorithm stopped — "
            f"opens={self._n_open}, closes={self._n_close}, "
            f"passive_spawned={self._n_passive_spawned}, "
            f"market_fallback={self._n_market_fallback}, "
            f"fail_open={self._n_fail_open}."
        )

    def _reset_state(self) -> None:
        self._pending = {}
        self._alert_seq = 0
        self._n_open = 0
        self._n_close = 0
        self._n_passive_spawned = 0
        self._n_market_fallback = 0
        self._n_fail_open = 0

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route CLOSE legs to market; OPEN legs through the passive path."""
        # --- CLOSE legs: never delayed (intraday_flat). -----------------
        if order.is_reduce_only:
            self._n_close += 1
            self.submit_order(order)
            return

        self._n_open += 1

        # --- OPEN legs: try to provide liquidity one tick inside the
        #     touch. -------------------------------------------------------
        quote = self.cache.quote_tick(order.instrument_id)
        instrument = self.cache.instrument(order.instrument_id)
        if quote is None or instrument is None:
            # Session warmup — no quote / instrument cached yet. Fail open:
            # behave exactly like the base / loop 5 (immediate market).
            self._n_fail_open += 1
            self.submit_order(order)
            return

        # `Price +/- Decimal` arithmetic returns a `decimal.Decimal`, which
        # `spawn_limit` rejects — it requires a `Price`. Compute the offset
        # price as a Decimal, then rebuild a properly-quantised `Price`
        # object via `instrument.make_price()`.
        tick = instrument.price_increment
        offset = tick * self._inside_ticks

        if order.side == OrderSide.BUY:
            # One tick inside the bid (toward the mid).
            limit_price = instrument.make_price(quote.bid_price + offset)
        elif order.side == OrderSide.SELL:
            # One tick inside the ask (toward the mid).
            limit_price = instrument.make_price(quote.ask_price - offset)
        else:  # pragma: no cover - defensive
            self.submit_order(order)
            return

        # Spawn a post-only LIMIT child for the full parent quantity one tick
        # inside the same-side touch. `reduce_primary=False` leaves the
        # primary intact at full quantity so it can serve as the deferred
        # market fallback. post_only guarantees the limit can never cross the
        # spread — if the inside-the-touch price would lock/cross the book
        # the venue rejects it and the timeout path's market fallback still
        # honours the parent intent.
        limit = self.spawn_limit(
            primary=order,
            quantity=order.quantity,
            price=limit_price,
            time_in_force=TimeInForce.GTC,
            post_only=True,
            reduce_primary=False,
        )
        self.submit_order(limit)
        self._n_passive_spawned += 1

        # Schedule the market-fallback sweep. The primary itself is held
        # back (NOT submitted here) — it becomes the fallback order.
        self._alert_seq += 1
        alert_name = f"ptg_b_l6_sweep_{self._alert_seq}"
        self._pending[alert_name] = (order, limit)
        self.clock.set_time_alert(
            name=alert_name,
            alert_time=self.clock.utc_now() + self._timeout,
            callback=self._on_passive_timeout,
        )

    # ------------------------------------------------------------------
    # Time-alert callback — market fallback for an unfilled passive limit
    # ------------------------------------------------------------------

    def _on_passive_timeout(self, event) -> None:
        """If the passive limit is still open, cancel it and sweep the
        position with the held-back primary market order."""
        entry = self._pending.pop(event.name, None)
        if entry is None:
            return
        primary, limit = entry

        # Re-fetch the live limit order from the cache — the local handle
        # may be stale w.r.t. fill / cancel state.
        live_limit = self.cache.order(limit.client_order_id)

        if live_limit is not None and live_limit.is_closed:
            # The passive limit already resolved. If it FILLED, the 1-lot
            # parent intent is satisfied and the held-back primary must NOT
            # be submitted (that would double the position). If it was
            # canceled/rejected/expired for any reason, fall through to the
            # market sweep so the parent intent is still honoured.
            if live_limit.is_open or getattr(live_limit, "filled_qty", None):
                if live_limit.filled_qty and live_limit.filled_qty > 0:
                    return  # passive fill captured — done.

        if live_limit is not None and live_limit.is_open:
            # Still resting and unfilled — cancel it before sweeping.
            self.cancel_order(live_limit)

        # Submit the held-back primary MARKET order to sweep the position.
        live_primary = self.cache.order(primary.client_order_id)
        if live_primary is None:
            return
        if not live_primary.is_open and live_primary.is_closed:
            # Primary already resolved (defensive — should not happen since
            # it is held back). Nothing to do.
            return

        self.submit_order(live_primary)
        self._n_market_fallback += 1


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
) -> PositionTierGateBL6Algorithm:
    """Instantiate and return the PositionTierGateBL6Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    """
    config = PositionTierGateBL6Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
    )
    return PositionTierGateBL6Algorithm(config=config)
