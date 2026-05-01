"""Imbalance-conditioned order skip execution algorithm.

For each open (non-reduce-only) order:
  - Read the current top-of-book bid/ask sizes from the quote-tick cache.
  - Compute order-book imbalance:
        imbalance = (bid_size - ask_size) / (bid_size + ask_size)   in [-1, +1]
  - For a BUY order: adverse condition = imbalance > skip_threshold
    (bid-heavy book: buying pressure, price likely to rise further, ask thin)
  - For a SELL order: adverse condition = imbalance < -skip_threshold
    (ask-heavy book: selling pressure, bid thin)
  - If adverse: SKIP the order entirely (quantity invariant allows < parent.qty).
  - If not adverse (or no quote cached): submit immediately.

Reduce-only (close) orders are always submitted to maintain intraday_flat.

See execution_algos/imbalance-skip/NOTES.md for the full hypothesis.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_config_values() -> dict:
    """Read relevant fields from config.yaml at runtime (not hardcoded)."""
    config_path = _REPO_ROOT / "research" / "config.yaml"
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    return cfg["execution_constraints"]


class ImbalanceSkipConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the imbalance-conditioned skip execution algorithm.

    Parameters
    ----------
    skip_threshold : float
        Imbalance threshold in [0, 1). An open order is skipped when the
        signed imbalance in the adverse direction exceeds this value.
        Default 0.5 (skips when one side has >3x the qty of the other in
        the adversarial direction — approximately the top 15-20% of events).
    """

    skip_threshold: float = 0.5


class ImbalanceSkipAlgorithm(ExecAlgorithm):
    """Execution algorithm that skips orders when the order book imbalance
    signals adverse selection risk.

    Opening orders (is_reduce_only == False):
      - Compute signed book imbalance using the latest cached quote tick.
      - For BUY: skip if imbalance > skip_threshold (bid-heavy — adverse).
      - For SELL: skip if imbalance < -skip_threshold (ask-heavy — adverse).
      - Otherwise: submit immediately.
      - No quote cached yet: submit immediately (baseline fallback).

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is ever modified. Skipped orders result in
    sum(child_fills) < parent.quantity, which is allowed by the quantity
    invariant (OBJECTIVE.md §3).
    """

    def __init__(self, config: ImbalanceSkipConfig) -> None:
        super().__init__(config=config)
        self._skip_threshold: float = config.skip_threshold
        # instruments we have already subscribed to quote ticks
        self._subscribed: set[str] = set()

    def on_start(self) -> None:
        self.log.info(
            f"ImbalanceSkipAlgorithm started "
            f"(skip_threshold={self._skip_threshold})."
        )

    def on_reset(self) -> None:
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
    # Imbalance computation
    # ------------------------------------------------------------------

    def _imbalance(self, order) -> float | None:
        """Return signed order-book imbalance in [-1, +1], or None if no quote.

        imbalance = (bid_size - ask_size) / (bid_size + ask_size)

        Positive  -> bid-heavy (buying pressure, adverse for BUY orders)
        Negative  -> ask-heavy (selling pressure, adverse for SELL orders)
        """
        quote = self.cache.quote_tick(order.instrument_id)
        if quote is None:
            return None

        bid_size = float(str(quote.bid_size))
        ask_size = float(str(quote.ask_size))
        total = bid_size + ask_size
        if total <= 0:
            return None

        return (bid_size - ask_size) / total

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route the order: submit immediately or skip if adversely imbalanced."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders are always submitted — intraday_flat.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Compute current imbalance.
        imbalance = self._imbalance(order)

        if imbalance is None:
            # No quote cached — first signal of the day. Submit immediately.
            self.log.info(
                f"No quote for {order.instrument_id}; "
                f"submitting {order.client_order_id} immediately (no-quote fallback)."
            )
            self.submit_order(order)
            return

        # Determine whether this order faces adverse book imbalance.
        adverse = False
        if order.side == OrderSide.BUY and imbalance > self._skip_threshold:
            # Bid-heavy: buying pressure already consuming the ask — adverse for BUY.
            adverse = True
        elif order.side == OrderSide.SELL and imbalance < -self._skip_threshold:
            # Ask-heavy: selling pressure already consuming the bid — adverse for SELL.
            adverse = True

        if adverse:
            # SKIP: quantity invariant allows sum(fills) < parent.qty.
            self.log.info(
                f"SKIP order {order.client_order_id} "
                f"(side={order.side.name}, imbalance={imbalance:.3f}, "
                f"threshold={self._skip_threshold:.3f}) — adverse book state."
            )
            # Do NOT call submit_order — order is intentionally not executed.
        else:
            # Book is balanced or favourable — submit immediately.
            self.log.debug(
                f"SUBMIT order {order.client_order_id} "
                f"(side={order.side.name}, imbalance={imbalance:.3f}) — favourable book."
            )
            self.submit_order(order)

    def on_quote_tick(self, tick) -> None:
        """Consume quote ticks to keep the cache populated (no active logic here)."""
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    skip_threshold: float = 0.5,
) -> ImbalanceSkipAlgorithm:
    """Instantiate and return the ImbalanceSkipAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    skip_threshold : float
        Imbalance magnitude in [0, 1) above which orders are skipped.
        Default 0.5 — conservative, skips only strongly imbalanced books.
    """
    config = ImbalanceSkipConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        skip_threshold=skip_threshold,
    )
    return ImbalanceSkipAlgorithm(config=config)
