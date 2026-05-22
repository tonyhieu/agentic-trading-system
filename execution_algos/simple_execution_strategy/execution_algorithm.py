"""Passive (maker) baseline execution algorithm.

Converts the oracle strategy's market orders into resting limit orders at the
touch (buy at the bid, sell at the ask) so the baseline *earns* the bid-ask
spread instead of *paying* it. If a limit has not fully filled by the time the
strategy's next order arrives, or after `passive_timeout_seconds`, the unfilled
remainder is crossed with a market order so every order still executes.

Rationale: in the target regime (sigma ~217, R^2 ~1 bp) the per-trade forecast
edge is smaller than the bid-ask spread, so crossing the spread on every trade
(market orders) is a structural loss. Posting passively flips the spread from a
cost toward a credit on the legs that fill as MAKER. See research/NOTES.md.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class SimpleExecutionAlgorithmConfig(ExecAlgorithmConfig, frozen=True):
    """Baseline config.

    Parameters
    ----------
    passive_timeout_seconds : float
        How long a resting limit order may rest before its unfilled remainder
        is crossed with a market order. Default 10.0.
    """

    passive_timeout_seconds: float = 10.0


class SimpleExecutionAlgorithm(ExecAlgorithm):
    """Passive-then-aggressive baseline execution algorithm.

    For each order the strategy sends, post a limit at the touch (MAKER fill if
    the market trades to it). If the limit has not fully filled by the time the
    next order arrives, or after `passive_timeout_seconds`, cancel it and cross
    the unfilled remainder with a market order (TAKER). At most one limit is
    outstanding at a time, so the realised position never desyncs from the
    strategy.

    Uses only `spawn_limit` / `spawn_market` / `submit_order` / `cancel_order`
    with `reduce_primary=False`; the parent order is never submitted and its
    quantity is never modified, so `sum(child_fills) <= parent.quantity` holds.
    """

    def __init__(self, config: SimpleExecutionAlgorithmConfig) -> None:
        super().__init__(config=config)
        self._timeout_ns: int = int(config.passive_timeout_seconds * 1_000_000_000)
        self._limit = None      # outstanding spawned limit order, or None
        self._parent = None     # the strategy order the limit was spawned from
        self._post_ts: int = 0  # ts_init of that order
        self._subscribed: set[str] = set()

    def on_start(self) -> None:
        self.log.info(
            f"SimpleExecutionAlgorithm started "
            f"(passive, timeout={self._timeout_ns / 1e9:.1f}s)."
        )

    def on_reset(self) -> None:
        self._clear()
        self._subscribed.clear()

    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    def _clear(self) -> None:
        self._limit = None
        self._parent = None
        self._post_ts = 0

    def _resolve_outstanding(self) -> None:
        """Cancel the outstanding limit and cross any unfilled remainder."""
        limit = self._limit
        parent = self._parent
        self._clear()
        if limit is None or limit.is_closed:
            return  # already fully filled or cancelled — nothing to do
        remaining = limit.leaves_qty  # quantity - filled_qty, > 0 while open
        self.cancel_order(limit)
        market = self.spawn_market(
            parent,
            remaining,
            reduce_only=parent.is_reduce_only,
            reduce_primary=False,
        )
        self.submit_order(market)

    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Post a passive limit for `order`, resolving any prior limit first."""
        self._ensure_subscribed(order.instrument_id)

        if self._limit is not None:
            self._resolve_outstanding()

        quote = self.cache.quote_tick(order.instrument_id)
        if quote is None:
            # No quote available yet — cross immediately so the order is not lost.
            market = self.spawn_market(
                order,
                order.quantity,
                reduce_only=order.is_reduce_only,
                reduce_primary=False,
            )
            self.submit_order(market)
            return

        price = quote.bid_price if order.side == OrderSide.BUY else quote.ask_price
        limit = self.spawn_limit(
            order,
            order.quantity,
            price=price,
            reduce_only=order.is_reduce_only,
            reduce_primary=False,
        )
        self.submit_order(limit)
        self._limit = limit
        self._parent = order
        self._post_ts = order.ts_init

    def on_quote_tick(self, tick) -> None:
        """Clear the outstanding limit once it fills, or resolve it on timeout."""
        if self._limit is None:
            return
        if self._limit.is_closed:
            self._clear()
            return
        if tick.ts_event - self._post_ts >= self._timeout_ns:
            self._resolve_outstanding()


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    passive_timeout_seconds: float = 10.0,
) -> SimpleExecutionAlgorithm:
    """Instantiate and return the passive baseline execution algorithm."""
    config = SimpleExecutionAlgorithmConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        passive_timeout_seconds=passive_timeout_seconds,
    )
    return SimpleExecutionAlgorithm(config=config)
