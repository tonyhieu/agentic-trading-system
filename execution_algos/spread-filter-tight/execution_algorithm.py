"""Bid-ask spread conditioned skip execution algorithm (tight threshold variant).

For each open (non-reduce-only) order at submission time:
  1. Compute the current bid-ask spread from the most recent quote tick.
  2. Compare against a rolling median of the last spread_window recent spreads.
  3. Skip the order when spread > spread_multiplier * median(recent_spreads).
  4. If fewer than min_window spread observations are available, submit
     immediately (baseline fallback — no history yet).

Reduce-only (close) orders are always submitted to maintain intraday_flat.

One targeted change vs spread-filter: spread_multiplier default is 1.3
(was 2.0). All other logic is identical.

See execution_algos/spread-filter-tight/NOTES.md for the full hypothesis.
"""
from __future__ import annotations

import statistics
from collections import defaultdict, deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class SpreadFilterTightConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the tight spread-conditioned skip execution algorithm.

    Parameters
    ----------
    spread_multiplier : float
        Skip the order when current spread > spread_multiplier * median(recent).
        Lower values fire more often. Default 1.3 (was 2.0 in spread-filter).
    spread_window : int
        Number of recent spread observations kept in the rolling window.
        Default 60 (~60 seconds of tick history).
    min_window : int
        Minimum number of spread observations before skip logic activates.
        If fewer samples, submit immediately (baseline fallback).
        Default 10.
    """

    spread_multiplier: float = 1.3
    spread_window: int = 60
    min_window: int = 10


class SpreadFilterTightAlgorithm(ExecAlgorithm):
    """Execution algorithm that skips open orders when the current bid-ask
    spread is elevated relative to the recent rolling median.

    Opening orders (is_reduce_only == False):
      - Record the latest spread from the most recent quote tick.
      - Skip if current spread > spread_multiplier * median(last spread_window).
      - Otherwise submit immediately.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is modified. Quantity invariant always preserved.
    """

    def __init__(self, config: SpreadFilterTightConfig) -> None:
        super().__init__(config=config)
        self._spread_multiplier: float = config.spread_multiplier
        self._spread_window: int = config.spread_window
        self._min_window: int = config.min_window

        # instrument_id string → deque of recent spread values (raw int units)
        self._spread_history: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=self._spread_window)
        )
        # Most recent spread value per instrument (for order submission check)
        self._last_spread: dict[str, int] = {}
        # instruments we have already subscribed to quote ticks
        self._subscribed: set[str] = set()

    def on_start(self) -> None:
        self.log.info(
            f"SpreadFilterTightAlgorithm started "
            f"(spread_multiplier={self._spread_multiplier}, "
            f"spread_window={self._spread_window}, "
            f"min_window={self._min_window})."
        )

    def on_reset(self) -> None:
        self._spread_history.clear()
        self._last_spread.clear()
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
    # Quote tick handler — accumulates spread history
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        """Record the bid-ask spread for each incoming quote tick."""
        key = str(tick.instrument_id)
        try:
            bid_raw = tick.bid_price.raw
            ask_raw = tick.ask_price.raw
        except AttributeError:
            bid_raw = round(float(tick.bid_price) * 1_000_000_000)
            ask_raw = round(float(tick.ask_price) * 1_000_000_000)

        spread = ask_raw - bid_raw
        self._spread_history[key].append(spread)
        self._last_spread[key] = spread

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route the order: submit immediately or skip if spread is elevated."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders are always submitted — intraday_flat.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        key = str(order.instrument_id)
        history = self._spread_history[key]

        # Insufficient history — submit immediately (baseline fallback).
        if len(history) < self._min_window:
            self.log.info(
                f"Insufficient spread history ({len(history)}/{self._min_window}) "
                f"for {order.instrument_id}; submitting {order.client_order_id} "
                f"immediately (no-history fallback)."
            )
            self.submit_order(order)
            return

        # Compute rolling median of recent spreads.
        median_spread = statistics.median(history)

        # Get current spread (most recent observation).
        current_spread = self._last_spread.get(key, 0)

        threshold = self._spread_multiplier * median_spread

        if current_spread > threshold:
            self.log.info(
                f"SKIP order {order.client_order_id} "
                f"(spread={current_spread}, threshold={threshold:.0f}, "
                f"median={median_spread:.0f}) — elevated spread."
            )
            # Do NOT call submit_order — order is intentionally not executed.
        else:
            self.log.debug(
                f"SUBMIT order {order.client_order_id} "
                f"(spread={current_spread}, threshold={threshold:.0f}) — normal spread."
            )
            self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    spread_multiplier: float = 1.3,
    spread_window: int = 60,
    min_window: int = 10,
) -> SpreadFilterTightAlgorithm:
    """Instantiate and return the SpreadFilterTightAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    spread_multiplier : float
        Threshold multiplier applied to the rolling median spread.
        Default 1.3. Lower fires more often; higher fires less often.
    spread_window : int
        Rolling window length for spread history. Default 60 ticks.
    min_window : int
        Minimum samples before skip logic activates. Default 10 ticks.
    """
    config = SpreadFilterTightConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        spread_multiplier=spread_multiplier,
        spread_window=spread_window,
        min_window=min_window,
    )
    return SpreadFilterTightAlgorithm(config=config)
