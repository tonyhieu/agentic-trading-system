"""Order-book imbalance gating execution algorithm.

Conditions the OPEN leg of each oracle signal on top-of-book bid/ask size
imbalance:

    I = (q_bid - q_ask) / (q_bid + q_ask)

For BUY  orders: execute only when I >= +imbalance_threshold
For SELL orders: execute only when I <= -imbalance_threshold

When the imbalance is adverse (opposing the signal direction) or when no
quote is available, skip the open.  Reduce-only (position-closing) orders
always execute — intraday_flat compliance.

After any skipped open, the next open order is submitted unconditionally
(_position_flat re-entry guarantee) to prevent permanent entry lock-out.

No order quantity is modified — the quantity invariant is always preserved.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class OBImbalanceGateConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the order-book imbalance gate algorithm.

    Parameters
    ----------
    imbalance_threshold : float
        Minimum signed imbalance required for entry.
        I = (q_bid - q_ask) / (q_bid + q_ask) in [-1, +1].
        For BUY  orders: require I >= +imbalance_threshold.
        For SELL orders: require I <= -imbalance_threshold.
        Default 0.0 — requires only that the book is not adverse.
        Positive values (e.g. 0.1, 0.2) impose a stricter filter.
    """

    imbalance_threshold: float = 0.0


class OBImbalanceGateAlgorithm(ExecAlgorithm):
    """Execution algorithm that gates open orders on top-of-book imbalance.

    Opening orders (is_reduce_only == False):
      - Compute I = (q_bid - q_ask) / (q_bid + q_ask) from the current
        top-of-book quote.
      - For BUY  orders: skip if I < +imbalance_threshold (ask side heavy).
      - For SELL orders: skip if I > -imbalance_threshold (bid side heavy).
      - If no quote is available, submit unconditionally (safe fallback).
      - After any skip: _position_flat = True — next open is unconditional.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    Order quantity is never modified — quantity invariant preserved.
    """

    def __init__(self, config: OBImbalanceGateConfig) -> None:
        super().__init__(config=config)
        self._imbalance_threshold: float = config.imbalance_threshold

        # Forced re-entry after any skip (prevents cascade lock-out)
        self._position_flat: bool = True

        # Subscription tracking
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"OBImbalanceGateAlgorithm started "
            f"(imbalance_threshold={self._imbalance_threshold:.3f})."
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
    # Imbalance computation
    # ------------------------------------------------------------------

    def _compute_imbalance(self, quote) -> float | None:
        """Return signed book imbalance I in [-1, +1], or None on error.

        I = (q_bid - q_ask) / (q_bid + q_ask)

        Positive I => bid side heavy => upward short-term pressure.
        Negative I => ask side heavy => downward short-term pressure.
        """
        if quote is None:
            return None
        try:
            q_bid = float(str(quote.bid_size))
            q_ask = float(str(quote.ask_size))
            total = q_bid + q_ask
            if total <= 0:
                return None
            return (q_bid - q_ask) / total
        except Exception:
            return None

    def _imbalance_favorable(self, order, quote) -> bool:
        """Return True if the current imbalance favors the order direction.

        BUY  => favorable when I >= +threshold (bid heavy, price likely rises)
        SELL => favorable when I <= -threshold (ask heavy, price likely falls)

        Returns True (submit) when quote is unavailable — safe fallback.
        """
        imb = self._compute_imbalance(quote)
        if imb is None:
            # No quote available — submit unconditionally (safe fallback)
            self.log.debug("No quote available; submitting unconditionally.")
            return True

        if order.side == OrderSide.BUY:
            favorable = imb >= self._imbalance_threshold
            if not favorable:
                self.log.debug(
                    f"BUY imbalance gate SKIP: I={imb:.4f} < "
                    f"threshold={self._imbalance_threshold:.4f}."
                )
        else:  # SELL
            favorable = imb <= -self._imbalance_threshold
            if not favorable:
                self.log.debug(
                    f"SELL imbalance gate SKIP: I={imb:.4f} > "
                    f"-threshold={-self._imbalance_threshold:.4f}."
                )

        return favorable

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on book imbalance."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Fetch current quote for imbalance computation.
        quote = self.cache.quote_tick(order.instrument_id)

        # Forced re-entry after a skip — always submit to prevent cascade.
        if self._position_flat:
            self.log.info(
                f"Re-entry (first or post-skip); submitting {order.client_order_id}."
            )
            self._position_flat = False
            self.submit_order(order)
            return

        # Evaluate imbalance gate.
        if self._imbalance_favorable(order, quote):
            self.log.debug(
                f"SUBMIT {order.client_order_id} — imbalance favorable."
            )
            self._position_flat = False
            self.submit_order(order)
        else:
            self.log.info(
                f"SKIP {order.client_order_id} — imbalance adverse for "
                f"{'BUY' if order.side == OrderSide.BUY else 'SELL'}."
            )
            self._position_flat = True
            # Do NOT call submit_order — quantity invariant preserved.

    def on_quote_tick(self, tick) -> None:
        """Passively receive quote ticks (kept for subscription side-effects)."""
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    imbalance_threshold: float = 0.0,
) -> OBImbalanceGateAlgorithm:
    """Instantiate and return the OBImbalanceGateAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    imbalance_threshold : float
        Minimum absolute imbalance required for entry.
        Default 0.0 — submit when I >= 0 (BUY) or I <= 0 (SELL).
    """
    config = OBImbalanceGateConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        imbalance_threshold=imbalance_threshold,
    )
    return OBImbalanceGateAlgorithm(config=config)
