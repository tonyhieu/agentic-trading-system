"""Microprice-divergence-gate execution algorithm.

Conditions the OPEN leg of each oracle signal on the signed divergence of the
size-weighted microprice from the mid price.

    microprice = (bid_px * ask_sz + ask_px * bid_sz) / (bid_sz + ask_sz)
    mid        = (bid_px + ask_px) / 2
    delta      = microprice - mid

Conditioning:
  delta > +deadband  (upward book pressure)
      → favor BUY, skip SELL
  delta < -deadband  (downward book pressure)
      → favor SELL, skip BUY
  |delta| <= deadband (neutral)
      → submit unconditionally

Reduce-only (position-closing) orders always execute — intraday_flat
compliance. After any skipped open, the next open is forced through
unconditionally (_position_flat re-entry guarantee).

No order quantity is modified — the quantity invariant is always preserved.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class MicropriceDivergenceGateConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the microprice-divergence-gate algorithm.

    Parameters
    ----------
    microprice_deadband : float
        Minimum absolute microprice divergence (in price units) required to
        trigger directional gating. Below this threshold the book is
        considered neutral and the order is submitted unconditionally.
        Default 0.0 — any nonzero divergence triggers directional skipping.
    """

    microprice_deadband: float = 0.0


class MicropriceDivergenceGateAlgorithm(ExecAlgorithm):
    """Execution algorithm that gates open orders on microprice-vs-mid divergence.

    Opening orders (is_reduce_only == False):
      - Compute microprice and mid from the current top-of-book quote.
      - delta = microprice - mid
      - If delta > +deadband (upward pressure):  submit BUY, skip SELL.
      - If delta < -deadband (downward pressure): submit SELL, skip BUY.
      - If |delta| <= deadband (neutral):         submit unconditionally.
      - If no quote available: submit unconditionally (safe fallback).
      - After any skip: _position_flat = True (forced re-entry on next open).

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    Order quantity is never modified — quantity invariant preserved.
    """

    def __init__(self, config: MicropriceDivergenceGateConfig) -> None:
        super().__init__(config=config)
        self._deadband: float = config.microprice_deadband

        # Forced re-entry after any skip (prevents cascade lock-out)
        self._position_flat: bool = True

        # Subscription tracking
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"MicropriceDivergenceGateAlgorithm started "
            f"(microprice_deadband={self._deadband:.6f})."
        )

    def on_reset(self) -> None:
        self._position_flat = True
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
    # Microprice computation
    # ------------------------------------------------------------------

    def _compute_microprice_delta(self, quote) -> float | None:
        """Return microprice - mid in price units, or None if unavailable.

        microprice = (bid_px * ask_sz + ask_px * bid_sz) / (bid_sz + ask_sz)
        mid        = (bid_px + ask_px) / 2
        delta      = microprice - mid

        Positive delta: bid side of the book is pressing price upward
                        (buyers are taking size at the ask).
        Negative delta: ask side pressing price downward
                        (sellers absorbing bids).
        Zero delta: perfectly balanced book — mid == microprice.
        """
        if quote is None:
            return None
        try:
            # Nautilus prices are Price objects; convert to float via str.
            bid_px = float(str(quote.bid_price))
            ask_px = float(str(quote.ask_price))
            bid_sz = float(str(quote.bid_size))
            ask_sz = float(str(quote.ask_size))

            total_sz = bid_sz + ask_sz
            if total_sz <= 0:
                return None

            microprice = (bid_px * ask_sz + ask_px * bid_sz) / total_sz
            mid = (bid_px + ask_px) / 2.0
            return microprice - mid
        except Exception:
            return None

    def _microprice_favorable(self, order, quote) -> bool:
        """Return True if microprice direction favors submitting this order.

        Upward pressure (delta > +deadband):
            BUY  => favorable (price likely rising)
            SELL => adverse   (selling into upward pressure)

        Downward pressure (delta < -deadband):
            SELL => favorable (price likely falling)
            BUY  => adverse   (buying into downward pressure)

        Neutral (|delta| <= deadband): always favorable — submit unconditionally.

        No quote available: always favorable — submit unconditionally.
        """
        delta = self._compute_microprice_delta(quote)

        if delta is None:
            self.log.debug("No quote available; submitting unconditionally.")
            return True

        if delta > self._deadband:
            # Upward book pressure: favor BUY, skip SELL
            favorable = order.side == OrderSide.BUY
            if not favorable:
                self.log.debug(
                    f"SELL skipped: microprice delta={delta:.6f} > deadband={self._deadband:.6f} "
                    f"(upward pressure, adverse SELL entry)."
                )
            return favorable

        if delta < -self._deadband:
            # Downward book pressure: favor SELL, skip BUY
            favorable = order.side == OrderSide.SELL
            if not favorable:
                self.log.debug(
                    f"BUY skipped: microprice delta={delta:.6f} < -deadband={-self._deadband:.6f} "
                    f"(downward pressure, adverse BUY entry)."
                )
            return favorable

        # Neutral zone: |delta| <= deadband
        self.log.debug(
            f"Neutral microprice delta={delta:.6f}; submitting unconditionally."
        )
        return True

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on microprice-vs-mid divergence."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Fetch current quote for microprice computation.
        quote = self.cache.quote_tick(order.instrument_id)

        # Forced re-entry after a skip — always submit to prevent cascade.
        if self._position_flat:
            self.log.info(
                f"Re-entry (first or post-skip); submitting {order.client_order_id}."
            )
            self._position_flat = False
            self.submit_order(order)
            return

        # Evaluate microprice divergence gate.
        if self._microprice_favorable(order, quote):
            self.log.debug(
                f"SUBMIT {order.client_order_id} — microprice favorable."
            )
            self._position_flat = False
            self.submit_order(order)
        else:
            self.log.info(
                f"SKIP {order.client_order_id} — microprice adverse for "
                f"{'BUY' if order.side == OrderSide.BUY else 'SELL'}."
            )
            self._position_flat = True
            # Do NOT call submit_order — quantity invariant preserved.

    def on_quote_tick(self, tick) -> None:
        """Passively receive quote ticks (kept for subscription side-effects)."""
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    microprice_deadband: float = 0.0,
) -> MicropriceDivergenceGateAlgorithm:
    """Instantiate and return the MicropriceDivergenceGateAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    microprice_deadband : float
        Minimum absolute microprice-vs-mid divergence (price units) to
        trigger directional gating. Default 0.0 — any nonzero divergence
        triggers directional skipping.
    """
    config = MicropriceDivergenceGateConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        microprice_deadband=microprice_deadband,
    )
    return MicropriceDivergenceGateAlgorithm(config=config)
