"""sip-ptg-l7 — Deferred pair OPEN via on_order_filled.

Structural change vs position-tier-gate:
  Instead of skipping pair OPENs (orders that arrive at same ts_init as a
  CLOSE when the cache still shows the prior position), store them and submit
  via on_order_filled(close_fill) — after the close fills and the OMS cache
  updates to flat.

Hypothesis:
  The base PTG abandons the oracle's directional signal at pair time and waits
  for the next solo OPEN (1–4 seconds later). If the oracle direction at pair
  time is informative, the earlier entry from the deferred pair OPEN captures
  more of the predicted price move.

Mechanism:
  on_order(OPEN, net_qty >= cap): store order in self._pending_open[instrument_id].
  on_order_filled(fill_event) for a reduce_only fill: if pending OPEN exists for
    that instrument, submit it.
  on_order(solo_OPEN, net_qty=0): standard PTG behavior (submit immediately).
    After the deferred pair OPEN fills and is reflected in cache (net_qty=1), a
    subsequent solo OPEN would arrive with net_qty=1 >= cap=1 and be skipped.

No simultaneous opposing positions:
  The deferred OPEN submits only after on_order_filled fires for the close, which
  means the close has already cleared the position from the cache. At that moment
  net_qty=0 for the instrument — the deferred OPEN creates a fresh position in
  the new direction. No opposing positions exist simultaneously.

Quantity invariant:
  The algorithm only calls submit_order(order) on the original parent order
  object with its original quantity. No quantity modification ever occurs.

Constraints:
  top_of_book_only: the deferred OPEN is a market order that fills at ask/bid
    at the fill tick. No book-walking.
  participation_cap: unchanged — all orders are quantity=1 against a deep book.
  intraday_flat: reduce_only orders submit unconditionally; deferred OPENs are
    submitted only after their paired close clears the position.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class SipPtgL7Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for sip-ptg-l7.

    Parameters
    ----------
    position_cap : int
        Maximum absolute net position size at which new open-leg orders are
        deferred (not skipped). Default 1 — matches the base PTG gate threshold.
    """

    position_cap: int = 1


class SipPtgL7Algorithm(ExecAlgorithm):
    """Deferred pair OPEN via on_order_filled hook.

    For pair OPENs (arriving when net_qty >= cap): store the order and submit
    it in on_order_filled when the corresponding close fills.

    For solo OPENs (arriving when net_qty < cap): submit immediately (same as PTG).
    """

    def __init__(self, config: SipPtgL7Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        # Stores pending pair OPENs keyed by instrument_id.
        # At most one pending OPEN per instrument at any time (netting OMS).
        self._pending_open: dict = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"SipPtgL7Algorithm started "
            f"(position_cap={self._position_cap}; deferred-pair-open enabled)."
        )

    def on_reset(self) -> None:
        self._pending_open = {}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _current_net_qty(self, instrument_id) -> float:
        """Return absolute net position quantity for the instrument."""
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        total = sum(float(str(p.quantity)) for p in open_positions)
        return total

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit, defer (store for on_order_filled), or skip."""

        # Reduce-only orders always submit unconditionally — intraday_flat compliance.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id}."
            )
            self.submit_order(order)
            return

        # Query current position for this instrument.
        net_qty = self._current_net_qty(order.instrument_id)

        if net_qty >= self._position_cap:
            # Structural change: DEFER instead of skip.
            # This fires when a pair OPEN arrives while the prior position is
            # still in the cache (close submitted but not yet filled).
            # Store for deferred submission in on_order_filled.
            instrument_id = order.instrument_id
            self._pending_open[instrument_id] = order
            self.log.debug(
                f"DEFER {order.client_order_id} — stored for deferred submit "
                f"(net_qty={net_qty:.1f} >= cap={self._position_cap}). "
                f"Will submit in on_order_filled."
            )
            # Do NOT submit now — wait for close fill.
            return

        # Position below cap — submit immediately (same as PTG solo OPEN behavior).
        self.log.debug(
            f"SUBMIT {order.client_order_id} — position below cap "
            f"(net_qty={net_qty:.1f} < cap={self._position_cap})."
        )
        self.submit_order(order)

    # ------------------------------------------------------------------
    # Fill handler — submit deferred OPEN after close fills
    # ------------------------------------------------------------------

    def on_order_filled(self, event) -> None:
        """Submit the deferred OPEN when a reduce_only close fills."""
        # Identify the filled order.
        order = self.cache.order(event.client_order_id)
        if order is None:
            return

        # Only trigger for reduce_only fills (close orders).
        if not order.is_reduce_only:
            return

        instrument_id = order.instrument_id

        # Check if there is a deferred pair OPEN waiting for this instrument.
        pending = self._pending_open.pop(instrument_id, None)
        if pending is None:
            return

        # At this point: the close has filled, the OMS cache should reflect flat
        # (net_qty=0) for the instrument. Submit the deferred OPEN.
        self.log.debug(
            f"DEFERRED SUBMIT {pending.client_order_id} — submitting after "
            f"close {order.client_order_id} filled for instrument {instrument_id}."
        )
        self.submit_order(pending)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
) -> SipPtgL7Algorithm:
    """Instantiate and return the SipPtgL7Algorithm."""
    config = SipPtgL7Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
    )
    return SipPtgL7Algorithm(config=config)
