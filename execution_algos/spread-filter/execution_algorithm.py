"""Spread-filter execution algorithm.

Skips open (non-reduce-only) parent orders when the current bid-ask spread is
wider than `spread_threshold × median(recent_spreads)`. Reduce-only orders
always execute immediately. Close orders always execute immediately.

The spread is a proxy for regime uncertainty: when market-makers widen the
spread, short-term price predictability is lower and the oracle's edge is
more likely to be absent.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


def _median(values: list[float]) -> float:
    """Compute median without numpy dependency."""
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


class SpreadFilterConfig(ExecAlgorithmConfig, frozen=True):
    window_size: int = 60          # number of recent quotes to track
    spread_threshold: float = 2.0  # skip if spread > threshold × median
    min_window: int = 10           # minimum history before filter is active


class SpreadFilterAlgorithm(ExecAlgorithm):
    """Execution algorithm that skips open orders during wide-spread (uncertain) regimes."""

    def __init__(self, config: SpreadFilterConfig) -> None:
        super().__init__(config=config)
        self._window_size: int = config.window_size
        self._spread_threshold: float = config.spread_threshold
        self._min_window: int = config.min_window
        self._spread_history: deque[float] = deque(maxlen=self._window_size)
        self._instrument_id = None  # InstrumentId once first order arrives
        self._submitted_count: int = 0
        self._skipped_count: int = 0

    def on_start(self) -> None:
        self.log.info(
            f"SpreadFilterAlgorithm started: window_size={self._window_size}, "
            f"spread_threshold={self._spread_threshold}, "
            f"min_window={self._min_window}"
        )

    def on_reset(self) -> None:
        self._spread_history.clear()
        self._submitted_count = 0
        self._skipped_count = 0
        self._instrument_id = None

    def on_order(self, order) -> None:  # noqa: ANN001
        """Handle a parent order from the strategy."""
        # Always execute reduce-only orders (position closing) without filter.
        if order.is_reduce_only:
            self.log.debug(
                f"SpreadFilter: reduce-only order {order.client_order_id} — submitting immediately"
            )
            self.submit_order(order)
            self._submitted_count += 1
            return

        # Subscribe to quote ticks for this instrument on first order, so our
        # on_quote_tick handler populates _spread_history.
        if self._instrument_id is None:
            self._instrument_id = order.instrument_id
            self.subscribe_quote_ticks(self._instrument_id)
            self.log.info(
                f"SpreadFilter: subscribed to quote ticks for {self._instrument_id}"
            )

        # Read the latest quote from cache to get current spread.
        latest_quote = self.cache.quote_tick(order.instrument_id)
        if latest_quote is None:
            # No quote available yet — submit immediately.
            self.submit_order(order)
            self._submitted_count += 1
            return

        # Spread in instrument price units.
        ask_px = float(latest_quote.ask_price)
        bid_px = float(latest_quote.bid_price)
        current_spread = ask_px - bid_px

        # Ensure the spread is valid.
        if current_spread <= 0.0:
            self.submit_order(order)
            self._submitted_count += 1
            return

        # Not enough history — submit immediately.
        if len(self._spread_history) < self._min_window:
            self.submit_order(order)
            self._submitted_count += 1
            return

        # Compute median of recent spreads.
        median_spread = _median(list(self._spread_history))
        if median_spread <= 0.0:
            self.submit_order(order)
            self._submitted_count += 1
            return

        # Skip if spread is anomalously wide.
        if current_spread > self._spread_threshold * median_spread:
            self.log.debug(
                f"SpreadFilter: SKIP order {order.client_order_id} — "
                f"spread={current_spread:.4f} > threshold={self._spread_threshold:.1f} "
                f"× median={median_spread:.4f}"
            )
            self._skipped_count += 1
            # Do not call submit_order — order is silently dropped.
            return

        # Normal regime — submit immediately.
        self.log.debug(
            f"SpreadFilter: SUBMIT order {order.client_order_id} — "
            f"spread={current_spread:.4f} ≤ threshold × median={self._spread_threshold * median_spread:.4f}"
        )
        self.submit_order(order)
        self._submitted_count += 1

    def on_quote_tick(self, tick) -> None:  # noqa: ANN001
        """Update the rolling spread history on each incoming quote."""
        ask_px = float(tick.ask_price)
        bid_px = float(tick.bid_price)
        spread = ask_px - bid_px
        if spread > 0.0:
            self._spread_history.append(spread)

    def on_stop(self) -> None:
        self.log.info(
            f"SpreadFilter stopped: submitted={self._submitted_count}, "
            f"skipped={self._skipped_count}, "
            f"skip_rate={self._skipped_count / max(1, self._submitted_count + self._skipped_count):.2%}"
        )


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_size: int = 60,
    spread_threshold: float = 2.0,
    min_window: int = 10,
) -> SpreadFilterAlgorithm:
    """Factory function — registered in execution_algos/__init__.py.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
        Must match the exec_algorithm_id used by the oracle strategy (MY_GENERIC_ALGO).
    window_size : int
        Rolling window of recent quote ticks used to compute median spread.
    spread_threshold : float
        Skip open orders when spread > spread_threshold × median_spread.
    min_window : int
        Minimum quote ticks needed before filter activates (baseline fallback otherwise).
    """
    config = SpreadFilterConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_size=window_size,
        spread_threshold=spread_threshold,
        min_window=min_window,
    )
    return SpreadFilterAlgorithm(config=config)
