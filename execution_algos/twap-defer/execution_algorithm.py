"""Participation-cap-compliant deferred execution algorithm.

For each open (non-reduce-only) order:
  - Check the current top-of-book quantity via the quote-tick cache.
  - Compute ``allowed = floor(participation_cap * relevant_book_qty)``.
  - If allowed >= 1: submit the order immediately.
  - If allowed == 0 (book too thin): queue the order. On each subsequent quote
    tick, retry up to ``max_defer_ticks`` times.
    * If the book thickens within the window, submit.
    * If the window expires, submit unconditionally (avoids losing the trade).

For reduce-only (close) orders: submit immediately to maintain intraday_flat
compliance. Never modifies order quantity — quantity invariant is preserved.

See execution_algos/twap-defer/NOTES.md for the full hypothesis.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_participation_cap() -> float:
    """Read participation_cap from config.yaml at runtime (not hardcoded)."""
    config_path = _REPO_ROOT / "research" / "config.yaml"
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    return float(cfg["execution_constraints"]["participation_cap"])


@dataclass
class _PendingOrder:
    """Wrapper around a deferred open order with a retry counter."""

    order: object  # nautilus Order
    ticks_waited: int = 0


class TwapDeferConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the participation-cap-compliant deferred execution algorithm.

    Parameters
    ----------
    participation_cap : float
        Maximum fraction of top-of-book quantity to trade per tick.
        Default is read from ``research/config.yaml``; override only for testing.
    max_defer_ticks : int
        Maximum number of quote ticks to wait for the book to thicken before
        submitting unconditionally. Default 3.
    """

    participation_cap: float = 0.05
    max_defer_ticks: int = 3


class TwapDeferAlgorithm(ExecAlgorithm):
    """Execution algorithm that defers thin-book orders until the book thickens.

    Opening orders (is_reduce_only == False):
      - Check floor(participation_cap × relevant_book_qty).
      - If >= 1: submit immediately.
      - If == 0: queue the order. On each subsequent quote tick for that
        instrument, increment ticks_waited; if book now allows or
        ticks_waited >= max_defer_ticks, submit.

    Closing orders (is_reduce_only == True):
      - Submit immediately (intraday_flat compliance).

    No order quantity is modified — quantity invariant is always preserved.
    """

    def __init__(self, config: TwapDeferConfig) -> None:
        super().__init__(config=config)
        self._participation_cap: float = config.participation_cap
        self._max_defer_ticks: int = config.max_defer_ticks
        # instrument_id string → list of _PendingOrder (FIFO)
        self._pending: dict[str, list[_PendingOrder]] = defaultdict(list)
        # instruments we have already subscribed to
        self._subscribed: set[str] = set()

    def on_start(self) -> None:
        self.log.info(
            f"TwapDeferAlgorithm started "
            f"(participation_cap={self._participation_cap}, "
            f"max_defer_ticks={self._max_defer_ticks})."
        )

    def on_reset(self) -> None:
        self._pending.clear()
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
    # Participation cap check
    # ------------------------------------------------------------------

    def _allowed_qty(self, order) -> int:
        """Return floor(cap × book_qty) using the last cached quote tick.

        Returns -1 if no quote is available (no tick seen yet for this
        instrument — treated as "allow" so the first order is not lost).
        """
        quote = self.cache.quote_tick(order.instrument_id)
        if quote is None:
            return -1

        # BUY orders fill against the ASK side; SELL against the BID side.
        if order.side == OrderSide.BUY:
            book_qty = float(str(quote.ask_size))
        else:
            book_qty = float(str(quote.bid_size))

        return int(self._participation_cap * book_qty)

    # ------------------------------------------------------------------
    # Quote tick handler — drains the pending queue
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        """Called for every quote tick on a subscribed instrument.

        For each pending open order on this instrument:
          - Increment ticks_waited.
          - If the book now allows (allowed >= 1) OR the defer limit is
            reached, submit the order.
        """
        key = str(tick.instrument_id)
        if not self._pending[key]:
            return

        remaining = []
        for pending in self._pending[key]:
            pending.ticks_waited += 1
            order = pending.order
            allowed = self._allowed_qty(order)

            if allowed == -1 or allowed >= 1 or pending.ticks_waited >= self._max_defer_ticks:
                # Book has thickened, or no quote available, or timeout.
                reason = (
                    "book thickened"
                    if allowed >= 1
                    else ("timeout" if pending.ticks_waited >= self._max_defer_ticks else "no-quote")
                )
                self.log.info(
                    f"Submitting deferred order {order.client_order_id} "
                    f"after {pending.ticks_waited} tick(s) wait ({reason})."
                )
                self.submit_order(order)
            else:
                remaining.append(pending)

        self._pending[key] = remaining

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route the order: submit immediately or defer if book is thin."""
        self._ensure_subscribed(order.instrument_id)
        instrument_key = str(order.instrument_id)

        # Reduce-only orders (closes) are submitted immediately.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Opening order: check participation cap.
        allowed = self._allowed_qty(order)

        if allowed == -1:
            # No quote cached yet — first tick of the day. Submit immediately
            # (baseline fallback) rather than risk losing the first trade.
            self.log.info(
                f"No quote cached for {order.instrument_id}; "
                "submitting open order immediately (no-quote fallback)."
            )
            self.submit_order(order)

        elif allowed >= 1:
            # Book is thick enough — submit immediately.
            self.log.debug(
                f"Book allows {allowed} lot(s); submitting {order.client_order_id} immediately."
            )
            self.submit_order(order)

        else:
            # Book too thin (cap=0) — defer.
            self.log.info(
                f"Book too thin (cap=0) for {order.client_order_id}; "
                f"deferring up to {self._max_defer_ticks} ticks."
            )
            self._pending[instrument_key].append(_PendingOrder(order=order))


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    participation_cap: float | None = None,
    max_defer_ticks: int = 3,
) -> TwapDeferAlgorithm:
    """Instantiate and return the TwapDeferAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    participation_cap : float, optional
        Override for the participation cap. If None, reads from config.yaml.
    max_defer_ticks : int
        Maximum quote ticks to wait before submitting unconditionally. Default 3.
    """
    if participation_cap is None:
        participation_cap = _load_participation_cap()

    config = TwapDeferConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        participation_cap=participation_cap,
        max_defer_ticks=max_defer_ticks,
    )
    return TwapDeferAlgorithm(config=config)
