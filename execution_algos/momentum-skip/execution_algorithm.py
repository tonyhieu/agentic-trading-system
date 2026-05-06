"""Momentum-conditioned order skip execution algorithm.

For each open (non-reduce-only) order:
  - Read the current mid-price from the cached quote tick.
  - Compare to the mid-price recorded at the previous order decision.
  - Compute mid_change = current_mid - prev_decision_mid  (Nautilus int64 units)

  For a BUY order:
    - If mid_change > min_tick_move * tick_size_int (price ran up since last decision)
      -> SKIP the order (oracle edge partially consumed by the upward move)
    - Otherwise -> submit immediately

  For a SELL order:
    - If mid_change < -(min_tick_move * tick_size_int) (price fell since last decision)
      -> SKIP the order (oracle edge partially consumed by the downward move)
    - Otherwise -> submit immediately

  - If no previous decision mid available (first order of session): submit immediately.

Reduce-only (close) orders are always submitted to maintain intraday_flat.

Design note on timing: `_order_mid` is updated only inside on_order (after the
skip/submit decision), so we compare consecutive order-decision mid-prices.
We do NOT update on every quote tick — doing so would zero out mid_change most
of the time (the latest quote and cached quote would match at decision time).

See execution_algos/momentum-skip/NOTES.md for the full hypothesis.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId

# MES/MESM6 futures: tick size = 0.25 index points.
# In Nautilus raw int64 price units: verified empirically via
# Price.from_str('5800.25').raw - Price.from_str('5800.00').raw = 2_500_000_000_000_000.
_MES_TICK_SIZE_INT = 2_500_000_000_000_000


class MomentumSkipConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the momentum-conditioned skip execution algorithm.

    Parameters
    ----------
    min_tick_move : float
        Minimum number of ticks of mid-price movement in the oracle's
        predicted direction required to trigger a skip. Default 1.0 means
        skip only when mid moved at least 1 full tick in the adverse direction
        since the previous order decision. Lower values = more aggressive skipping.
    """

    min_tick_move: float = 1.0


class MomentumSkipAlgorithm(ExecAlgorithm):
    """Execution algorithm that skips orders when the mid-price has already
    moved in the oracle's predicted direction since the last order decision.

    Opening orders (is_reduce_only == False):
      - Compute current mid = (bid_price.raw + ask_price.raw) // 2.
      - Compare to mid recorded at the previous on_order call (_order_mid).
      - For BUY: skip if mid_change > min_tick_move * tick_size_int
        (price already ran up — adverse entry).
      - For SELL: skip if mid_change < -(min_tick_move * tick_size_int)
        (price already fell — adverse entry).
      - If no previous order mid (first signal of session): submit immediately.
      - After decision: update _order_mid to current_mid.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).
      - Do NOT update _order_mid (close orders are housekeeping, not oracle signals).

    No order quantity is ever modified. Skipped orders result in
    sum(child_fills) < parent.quantity, which is allowed by the quantity
    invariant (OBJECTIVE.md §3).
    """

    def __init__(self, config: MomentumSkipConfig) -> None:
        super().__init__(config=config)
        self._min_tick_move: float = config.min_tick_move
        self._threshold_int: int = int(self._min_tick_move * _MES_TICK_SIZE_INT)
        # Mid-price at the previous open-order decision, per instrument (int64 units).
        # Updated at the end of every on_order call for open orders.
        # Reduce-only orders do not update this reference.
        self._order_mid: dict[str, int] = {}
        # Instruments already subscribed to quote ticks (needed to populate cache).
        self._subscribed: set[str] = set()

    def on_start(self) -> None:
        self.log.info(
            f"MomentumSkipAlgorithm started "
            f"(min_tick_move={self._min_tick_move}, "
            f"threshold_int={self._threshold_int})."
        )

    def on_reset(self) -> None:
        self._order_mid.clear()
        self._subscribed.clear()

    # ------------------------------------------------------------------
    # Subscription helpers
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Mid-price helpers
    # ------------------------------------------------------------------

    def _current_mid_int(self, order) -> int | None:
        """Return the current mid-price in Nautilus int64 units, or None."""
        quote = self.cache.quote_tick(order.instrument_id)
        if quote is None:
            return None
        # bid_price and ask_price are Price objects; .raw gives int64 raw value.
        bid = quote.bid_price.raw
        ask = quote.ask_price.raw
        return (bid + ask) // 2

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route the order: submit immediately or skip if momentum is adverse."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always submitted — intraday_flat compliance.
        # Do NOT update _order_mid from close orders (they don't carry oracle signal).
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        instrument_key = str(order.instrument_id)
        current_mid = self._current_mid_int(order)

        if current_mid is None:
            # No quote cached — first signal of the day. Submit immediately.
            self.log.info(
                f"No quote for {order.instrument_id}; "
                f"submitting {order.client_order_id} immediately (no-quote fallback)."
            )
            self.submit_order(order)
            return

        prev_mid = self._order_mid.get(instrument_key)
        if prev_mid is None:
            # First open order we've seen — no prior reference mid.
            # Submit immediately; set the reference for next time.
            self.log.info(
                f"No prior order mid for {order.instrument_id}; "
                f"submitting {order.client_order_id} immediately (first-order fallback)."
            )
            self._order_mid[instrument_key] = current_mid
            self.submit_order(order)
            return

        mid_change = current_mid - prev_mid

        # Determine adverse momentum since last order decision.
        adverse = False
        if order.side == OrderSide.BUY and mid_change > self._threshold_int:
            # Price already ran up — oracle BUY edge is partially consumed.
            adverse = True
        elif order.side == OrderSide.SELL and mid_change < -self._threshold_int:
            # Price already fell — oracle SELL edge is partially consumed.
            adverse = True

        if adverse:
            self.log.info(
                f"SKIP order {order.client_order_id} "
                f"(side={order.side.name}, mid_change_ticks={mid_change / _MES_TICK_SIZE_INT:.2f}, "
                f"threshold_ticks={self._min_tick_move:.2f}) "
                f"— price already moved in oracle direction."
            )
            # Do NOT call submit_order — order is intentionally not executed.
        else:
            self.log.debug(
                f"SUBMIT order {order.client_order_id} "
                f"(side={order.side.name}, "
                f"mid_change_ticks={mid_change / _MES_TICK_SIZE_INT:.2f}) "
                f"— momentum not adverse."
            )
            self.submit_order(order)

        # Update reference mid for the next open-order decision.
        self._order_mid[instrument_key] = current_mid

    def on_quote_tick(self, tick) -> None:
        """Consume quote ticks to keep the cache populated (no active logic here).

        We intentionally do NOT update _order_mid here. Updating on every quote tick
        would zero out mid_change when on_order is called (cached quote == latest tick),
        making the filter inactive. The reference mid is updated only at order decisions.
        """
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    min_tick_move: float = 1.0,
) -> MomentumSkipAlgorithm:
    """Instantiate and return the MomentumSkipAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    min_tick_move : float
        Minimum tick movement of mid-price since the last order decision
        needed to trigger a skip. Default 1.0 (skip when price moved >= 1 tick).
    """
    config = MomentumSkipConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        min_tick_move=min_tick_move,
    )
    return MomentumSkipAlgorithm(config=config)
