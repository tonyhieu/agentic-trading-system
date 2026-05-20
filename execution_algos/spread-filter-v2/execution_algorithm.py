"""Spread-filter-v2 execution algorithm.

Skips open (non-reduce-only) parent orders when the current bid-ask spread is
wider than `spread_threshold × median(recent_spreads)`. Reduce-only orders
always execute immediately.

This is a single-parameter refinement of `spread-filter` (threshold 2.0x→1.3x).
The lower threshold fires more frequently, increasing the skip rate from ~0.2%
to an estimated ~2-5%, targeting the 5% realized-P&L gate.

See execution_algos/spread-filter-v2/NOTES.md for the full hypothesis.
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


class SpreadFilterV2Config(ExecAlgorithmConfig, frozen=True):
    window_size: int = 60          # number of recent quotes in rolling window
    spread_threshold: float = 1.3  # skip if spread > threshold × median (lowered from 2.0)
    min_window: int = 10           # minimum history before filter activates


class SpreadFilterV2Algorithm(ExecAlgorithm):
    """Execution algorithm that skips open orders during moderately wide-spread regimes.

    Compared to spread-filter (threshold=2.0x), this variant uses threshold=1.3x
    to fire more aggressively — skipping orders when the spread is even mildly
    elevated vs. the recent rolling median. The intent is to achieve a higher
    skip rate (~2-5% vs. ~0.2%) and accumulate more P&L improvement in the
    near-random oracle environment (sigma=5, ~48% win rate).

    Constraints respected:
    - top_of_book_only: algorithm never modifies order quantities or prices.
    - participation_cap: algorithm only skips or submits; no new child orders.
    - intraday_flat: reduce-only orders are always submitted immediately.
    - quantity invariant: sum(child_fills) <= parent.quantity (skipped orders
      contribute zero fills; submitted orders contribute exactly one full fill).
    """

    def __init__(self, config: SpreadFilterV2Config) -> None:
        super().__init__(config=config)
        self._window_size: int = config.window_size
        self._spread_threshold: float = config.spread_threshold
        self._min_window: int = config.min_window
        self._spread_history: deque[float] = deque(maxlen=self._window_size)
        self._instrument_id = None
        self._submitted_count: int = 0
        self._skipped_count: int = 0

    def on_start(self) -> None:
        self.log.info(
            f"SpreadFilterV2Algorithm started: window_size={self._window_size}, "
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
        # Always execute reduce-only orders — intraday_flat compliance.
        if order.is_reduce_only:
            self.log.debug(
                f"SpreadFilterV2: reduce-only {order.client_order_id} — submitting immediately"
            )
            self.submit_order(order)
            self._submitted_count += 1
            return

        # Subscribe to quote ticks on first order for this instrument.
        if self._instrument_id is None:
            self._instrument_id = order.instrument_id
            self.subscribe_quote_ticks(self._instrument_id)
            self.log.info(
                f"SpreadFilterV2: subscribed to quote ticks for {self._instrument_id}"
            )

        # Read latest quote from cache.
        latest_quote = self.cache.quote_tick(order.instrument_id)
        if latest_quote is None:
            # No quote yet — submit immediately (baseline fallback).
            self.submit_order(order)
            self._submitted_count += 1
            return

        ask_px = float(latest_quote.ask_price)
        bid_px = float(latest_quote.bid_price)
        current_spread = ask_px - bid_px

        # Protect against zero/negative spread (data anomaly).
        if current_spread <= 0.0:
            self.submit_order(order)
            self._submitted_count += 1
            return

        # Wait for minimum window before activating filter.
        if len(self._spread_history) < self._min_window:
            self.submit_order(order)
            self._submitted_count += 1
            return

        # Compute rolling median spread.
        median_spread = _median(list(self._spread_history))
        if median_spread <= 0.0:
            self.submit_order(order)
            self._submitted_count += 1
            return

        # Skip if spread is elevated above the rolling median.
        if current_spread > self._spread_threshold * median_spread:
            self.log.debug(
                f"SpreadFilterV2: SKIP {order.client_order_id} — "
                f"spread={current_spread:.4f} > {self._spread_threshold:.2f}"
                f"×median={median_spread:.4f}"
            )
            self._skipped_count += 1
            # Do NOT call submit_order — order is intentionally not executed.
            return

        # Normal regime — submit immediately.
        self.log.debug(
            f"SpreadFilterV2: SUBMIT {order.client_order_id} — "
            f"spread={current_spread:.4f} ≤ threshold×median"
        )
        self.submit_order(order)
        self._submitted_count += 1

    def on_quote_tick(self, tick) -> None:  # noqa: ANN001
        """Update rolling spread history on each incoming quote."""
        ask_px = float(tick.ask_price)
        bid_px = float(tick.bid_price)
        spread = ask_px - bid_px
        if spread > 0.0:
            self._spread_history.append(spread)

    def on_stop(self) -> None:
        total = self._submitted_count + self._skipped_count
        skip_rate = self._skipped_count / max(1, total)
        self.log.info(
            f"SpreadFilterV2 stopped: submitted={self._submitted_count}, "
            f"skipped={self._skipped_count}, skip_rate={skip_rate:.2%}"
        )


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_size: int = 60,
    spread_threshold: float = 1.3,
    min_window: int = 10,
) -> SpreadFilterV2Algorithm:
    """Factory function — registered in execution_algos/__init__.py.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier for Nautilus.
    window_size : int
        Rolling window of recent quotes for median spread computation.
    spread_threshold : float
        Skip open orders when spread > spread_threshold × median_spread.
        Default 1.3 (lowered from spread-filter's 2.0 for higher skip rate).
    min_window : int
        Minimum quote count before filter activates (fallback to submit).
    """
    config = SpreadFilterV2Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_size=window_size,
        spread_threshold=spread_threshold,
        min_window=min_window,
    )
    return SpreadFilterV2Algorithm(config=config)
