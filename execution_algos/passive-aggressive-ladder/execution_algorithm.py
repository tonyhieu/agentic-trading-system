"""Passive-then-aggressive order laddering execution algorithm.

For each open-leg oracle entry:
1. Post a passive LIMIT order at the same-side top of book
   (BUY at bid_px, SELL at ask_px) using spawn_limit with
   reduce_primary=False. This collects the spread when filled.
2. After passive_timeout_ticks quote ticks without a fill,
   cancel the passive limit and submit the original primary
   MarketOrder directly (aggressive fallback) — same notional,
   same direction.

Reduce-only (close-leg) orders ALWAYS execute aggressively to
guarantee intraday_flat compliance and avoid close-leg risk.

Engine feasibility note:
The Nautilus backtest FillModel defaults to fill_limit_inside_spread()=False.
A BUY LIMIT at bid_price fills only when the ask drops to or below
bid_price — genuine passive/resting-order behavior. The engine correctly
simulates queue/crossing without treating the limit as immediately
marketable. Verified at design time.

Quantity management:
- spawn_limit with reduce_primary=False keeps the primary MarketOrder INITIALIZED.
- On timeout: cancel_order(passive_child) then submit_order(primary).
  The primary is still INITIALIZED (never submitted), so submit_order works.
- On passive fill: mark primary as done; do NOT call submit_order(primary).
- This avoids the Nautilus restriction that spawn_market cannot reduce
  primary quantity to 0 (raises ValueError for non-positive quantity).

Quantity invariant: each parent is 1 contract. We fill exactly 1 contract
per parent (passive child or primary fallback) — never more.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import ExecAlgorithmId, ClientOrderId
from nautilus_trader.model.objects import Price


class PassiveAggressiveLadderConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the passive-aggressive laddering algorithm.

    Parameters
    ----------
    passive_timeout_ticks : int
        Number of quote-tick updates to wait for a passive fill before
        escalating to an aggressive market order. Default 5 (~200-500ms
        of real market time at MES tick rates).
    """

    passive_timeout_ticks: int = 5


class PassiveAggressiveLadderAlgorithm(ExecAlgorithm):
    """Execution algorithm that tries passive limit fills before crossing.

    Opening orders (is_reduce_only == False):
    - Spawn a passive LIMIT at bid_px (BUY) or ask_px (SELL) using
      reduce_primary=False. Primary MarketOrder stays INITIALIZED.
    - On each subsequent quote tick, advance the tick counter for each live
      passive child. If counter >= passive_timeout_ticks: cancel the child.
    - on_order_canceled: if the passive child was not filled, directly
      submit the original primary order (aggressive market fallback).
    - on_order_filled: if the passive child filled, mark the primary as
      completed so the fallback is never triggered.

    Closing orders (is_reduce_only == True):
    - Submit as market order immediately (aggressive).
    """

    def __init__(self, config: PassiveAggressiveLadderConfig) -> None:
        super().__init__(config=config)
        self._passive_timeout_ticks: int = config.passive_timeout_ticks

        # Maps passive_child_order_id -> [primary_order, tick_count]
        self._passive_children: dict[ClientOrderId, list] = {}
        # Set of primary_order_ids that have already been completed (passive fill)
        self._completed_primaries: set[ClientOrderId] = set()

        # Subscription tracking
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"PassiveAggressiveLadderAlgorithm started "
            f"(passive_timeout_ticks={self._passive_timeout_ticks})."
        )

    def on_reset(self) -> None:
        self._passive_children.clear()
        self._completed_primaries.clear()
        self._subscribed.clear()

    # ------------------------------------------------------------------
    # Subscription helper
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: aggressive for reduces, passive-first for opens."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders: always aggressive.
        if order.is_reduce_only:
            self.log.debug(
                f"Reduce-only: submitting {order.client_order_id} aggressively."
            )
            self.submit_order(order)
            return

        # Opening order: try passive fill first.
        quote = self.cache.quote_tick(order.instrument_id)

        if quote is None:
            # No quote available: fall back to aggressive immediately.
            self.log.debug(
                f"No quote for {order.instrument_id}; submitting aggressively."
            )
            self.submit_order(order)
            return

        # Determine passive limit price: BUY at bid, SELL at ask.
        try:
            if order.side == OrderSide.BUY:
                passive_px = Price(
                    float(str(quote.bid_price)), quote.bid_price.precision
                )
            else:
                passive_px = Price(
                    float(str(quote.ask_price)), quote.ask_price.precision
                )
        except Exception as e:
            self.log.warning(
                f"Cannot compute passive price for {order.client_order_id}: {e}. "
                "Submitting aggressively."
            )
            self.submit_order(order)
            return

        # Spawn passive limit with reduce_primary=False.
        # Primary stays INITIALIZED — available for aggressive fallback via submit_order.
        try:
            child_limit = self.spawn_limit(
                primary=order,
                quantity=order.leaves_qty,
                price=passive_px,
                time_in_force=TimeInForce.GTC,
                reduce_primary=False,
            )
        except Exception as e:
            self.log.warning(
                f"spawn_limit failed for {order.client_order_id}: {e}. "
                "Submitting aggressively."
            )
            self.submit_order(order)
            return

        # Submit the passive child to the venue.
        self.submit_order(child_limit)

        # Track: passive_child_id -> [primary, tick_count]
        self._passive_children[child_limit.client_order_id] = [order, 0]
        self.log.debug(
            f"PASSIVE spawned {child_limit.client_order_id} at {passive_px} "
            f"from primary {order.client_order_id}."
        )

    # ------------------------------------------------------------------
    # Quote tick handler: advance tick counters, trigger timeout escalation
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        """Advance tick counters; escalate passive-to-aggressive on timeout."""
        if not self._passive_children:
            return

        to_cancel = []
        for child_id, state in self._passive_children.items():
            child_order = self.cache.order(child_id)
            if child_order is None or child_order.is_closed:
                # Already filled or canceled externally; will be cleaned in callbacks.
                continue
            state[1] += 1  # increment tick_count
            if state[1] >= self._passive_timeout_ticks:
                to_cancel.append(child_id)

        for child_id in to_cancel:
            child_order = self.cache.order(child_id)
            if child_order is not None and not child_order.is_closed:
                self.log.debug(
                    f"Timeout: canceling passive child {child_id} after "
                    f"{self._passive_timeout_ticks} ticks."
                )
                self.cancel_order(child_order)

    # ------------------------------------------------------------------
    # Fill callback: mark primary as completed
    # ------------------------------------------------------------------

    def on_order_filled(self, event) -> None:
        """Handle fill event. If a passive child fills, mark primary done."""
        child_id = event.client_order_id
        if child_id not in self._passive_children:
            return

        state = self._passive_children.pop(child_id)
        primary = state[0]
        self._completed_primaries.add(primary.client_order_id)
        self.log.info(
            f"PASSIVE FILL: child {child_id} filled at {event.last_px}. "
            f"Primary {primary.client_order_id} completed (not submitted)."
        )

    # ------------------------------------------------------------------
    # Cancel callback: escalate to aggressive market order
    # ------------------------------------------------------------------

    def on_order_canceled(self, event) -> None:
        """Handle cancel. If passive child canceled unfilled, submit primary."""
        child_id = event.client_order_id
        if child_id not in self._passive_children:
            return

        state = self._passive_children.pop(child_id)
        primary = state[0]

        # If the primary already completed (passive filled before cancel event),
        # do nothing.
        if primary.client_order_id in self._completed_primaries:
            return

        # Aggressive fallback: submit the original primary MarketOrder.
        # It is still INITIALIZED (never submitted via submit_order, reduce_primary=False).
        try:
            self.submit_order(primary)
            self.log.debug(
                f"AGGRESSIVE fallback: submitting primary {primary.client_order_id} "
                "after passive timeout."
            )
        except Exception as e:
            self.log.error(
                f"submit_order(primary) failed for {primary.client_order_id}: {e}. "
                "Entry lost!"
            )


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    passive_timeout_ticks: int = 5,
) -> PassiveAggressiveLadderAlgorithm:
    """Instantiate and return the PassiveAggressiveLadderAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    passive_timeout_ticks : int
        Number of quote ticks to wait for a passive fill before escalating.
        Default 5.
    """
    config = PassiveAggressiveLadderConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        passive_timeout_ticks=passive_timeout_ticks,
    )
    return PassiveAggressiveLadderAlgorithm(config=config)
