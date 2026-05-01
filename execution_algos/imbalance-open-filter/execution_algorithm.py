"""Imbalance-gated open-order execution algorithm.

Only submit opening (non-reduce-only) orders when the top-of-book bid/ask
size ratio confirms the order direction. Reduce-only (closing) orders always
pass through immediately — identical to the simple baseline for closes.

See execution_algos/imbalance-open-filter/NOTES.md for the full hypothesis.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class ImbalanceOpenFilterConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the imbalance-gated open-order filter.

    Parameters
    ----------
    imbalance_threshold : float
        Minimum bid/(bid+ask) ratio required to submit a BUY open order.
        For SELL open orders the mirror condition is checked:
        ask/(bid+ask) >= threshold.
        Default 0.45 — a loose filter that only blocks strongly adversarial books.
    """

    imbalance_threshold: float = 0.45


class ImbalanceOpenFilterAlgorithm(ExecAlgorithm):
    """Execution algorithm that gates opening orders on top-of-book imbalance.

    Opening orders are only submitted when the book favours the order side
    (imbalance >= threshold).  Reduce-only closing orders bypass the filter
    and are submitted immediately — identical to the simple baseline.

    The algorithm subscribes to QuoteTicks for each instrument it sees so
    that self.cache.quote_tick() returns the current BBO at decision time.
    """

    def __init__(self, config: ImbalanceOpenFilterConfig) -> None:
        super().__init__(config=config)
        self._threshold: float = config.imbalance_threshold
        self._subscribed_instruments: set = set()

    def on_start(self) -> None:
        self.log.info(
            f"ImbalanceOpenFilterAlgorithm started "
            f"(imbalance_threshold={self._threshold:.3f})."
        )

    def on_reset(self) -> None:
        self._subscribed_instruments.clear()

    def _ensure_subscribed(self, instrument_id) -> None:
        """Subscribe to quote ticks for instrument_id if not already done.

        This populates self.cache.quote_tick(instrument_id) with the
        current BBO so that on_order can read it without look-ahead.
        """
        if instrument_id not in self._subscribed_instruments:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed_instruments.add(instrument_id)

    def _imbalance_confirms(self, order) -> bool:
        """Return True if the top-of-book imbalance confirms the order direction.

        If no quote tick is available yet (session start, data gap), returns
        True so that we don't accidentally block all early orders.
        """
        instrument_id = order.instrument_id
        if not self.cache.has_quote_ticks(instrument_id):
            # No quote cached yet — submit unconditionally (safe fallback).
            self.log.warning(
                f"No quote tick in cache for {instrument_id}; "
                "submitting order unconditionally."
            )
            return True

        quote = self.cache.quote_tick(instrument_id)
        bid_sz = float(quote.bid_size)
        ask_sz = float(quote.ask_size)
        total = bid_sz + ask_sz
        if total == 0:
            return True  # degenerate book — submit unconditionally

        bid_ratio = bid_sz / total  # in [0, 1]

        if order.is_buy:
            # Need bid pressure to support an upward move.
            return bid_ratio >= self._threshold
        else:
            # For SELL, need ask pressure (bid_ratio <= 1 - threshold).
            return bid_ratio <= (1.0 - self._threshold)

    def on_order(self, order) -> None:
        """Gate opening orders on imbalance; always pass through closes."""
        # Ensure quote ticks are routed to the cache for this instrument.
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (closing) orders bypass the filter entirely.
        if order.is_reduce_only:
            self.submit_order(order)
            return

        # Opening order — check imbalance.
        if self._imbalance_confirms(order):
            self.submit_order(order)
        else:
            # Imbalance is against the order side — skip this open.
            # The oracle strategy will re-emit an open on the next signal
            # cycle (~1 second) if the underlying forecast persists.
            self.log.debug(
                f"Skipping open order {order.client_order_id} "
                f"({'BUY' if order.is_buy else 'SELL'}) — "
                f"imbalance does not confirm direction "
                f"(threshold={self._threshold:.3f})."
            )


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    imbalance_threshold: float = 0.45,
) -> ImbalanceOpenFilterAlgorithm:
    """Instantiate and return the imbalance-open-filter execution algorithm."""
    config = ImbalanceOpenFilterConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        imbalance_threshold=imbalance_threshold,
    )
    return ImbalanceOpenFilterAlgorithm(config=config)
