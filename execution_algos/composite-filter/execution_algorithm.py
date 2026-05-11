"""Composite spread+momentum conditional skip execution algorithm.

For each incoming parent order:
  1. Compute the current bid-ask spread from the order's instrument quote.
  2. Compare to a rolling median of recent spreads.
  3. Compute mid-price momentum over a recent window of quote observations.
  4. Skip the order if BOTH conditions hold:
       a. spread > spread_mult * median(recent_spreads)  (elevated uncertainty)
       b. recent mid-price move is adverse to the trade direction
  5. Otherwise submit the order immediately.

Reduce-only (close) orders are always submitted to maintain intraday_flat.

Quantity invariant: no order quantities are modified.  Skipped orders result
in sum(child_fills) < parent.quantity, which is allowed by OBJECTIVE.md §3.

See execution_algos/composite-filter/NOTES.md for full hypothesis and design.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class CompositeFilterConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the composite spread+momentum filter.

    Parameters
    ----------
    spread_window : int
        Rolling window length for spread median computation.
        Default 60 — approximately 1 minute of quote updates.
    spread_mult : float
        Multiplier applied to the rolling median spread to form the
        threshold.  Spread > spread_mult * median fires the spread condition.
        Default 1.5 — lower than spread-filter's 2.0 for higher skip rate.
    momentum_window : int
        Number of mid-price observations to track for momentum computation.
        Default 5 — covers ~5 seconds at 1 Hz signal cadence.
    momentum_threshold : float
        Minimum adverse mid-price move (in price units) to fire the momentum
        condition.  0.0 means any adverse move qualifies.
        Default 0.0.
    """

    spread_window: int = 60
    spread_mult: float = 1.5
    momentum_window: int = 5
    momentum_threshold: float = 0.0


class CompositeFilterAlgorithm(ExecAlgorithm):
    """Execution algorithm that skips orders when spread and adverse momentum coincide.

    Opening orders (is_reduce_only == False):
      - Record current spread in rolling spread history.
      - Record current mid-price in rolling mid-price history.
      - Compute spread condition: spread > spread_mult * median(recent_spreads).
      - Compute momentum condition: recent mid-price moved adversely.
      - Skip if BOTH conditions hold; otherwise submit.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).
      - Spread/momentum state is still updated to avoid stale windows.

    No order quantity is ever modified.  Quantity invariant always preserved.
    """

    def __init__(self, config: CompositeFilterConfig) -> None:
        super().__init__(config=config)
        self._spread_window: int = config.spread_window
        self._spread_mult: float = config.spread_mult
        self._momentum_window: int = config.momentum_window
        self._momentum_threshold: float = config.momentum_threshold

        self._spread_history: deque[float] = deque(maxlen=self._spread_window)
        self._mid_history: deque[float] = deque(maxlen=self._momentum_window)

    def on_start(self) -> None:
        self.log.info(
            f"CompositeFilterAlgorithm started "
            f"(spread_window={self._spread_window}, "
            f"spread_mult={self._spread_mult}, "
            f"momentum_window={self._momentum_window}, "
            f"momentum_threshold={self._momentum_threshold})."
        )

    def on_reset(self) -> None:
        self._spread_history.clear()
        self._mid_history.clear()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _median(values: list[float]) -> float:
        """Compute the median of a list of floats."""
        n = len(values)
        if n == 0:
            return 0.0
        sorted_vals = sorted(values)
        mid = n // 2
        if n % 2 == 1:
            return sorted_vals[mid]
        return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0

    def _update_and_get_spread_condition(self, spread: float) -> bool:
        """Record spread; return True if spread condition fires."""
        self._spread_history.append(spread)
        n = len(self._spread_history)
        if n < 2:
            return False  # not enough history
        med = self._median(list(self._spread_history))
        if med <= 0.0:
            return False  # degenerate spread
        return spread > self._spread_mult * med

    def _update_and_get_momentum_condition(self, mid: float, is_buy: bool) -> bool:
        """Record mid-price; return True if adverse momentum condition fires."""
        self._mid_history.append(mid)
        n = len(self._mid_history)
        if n < 2:
            return False  # not enough history

        earliest = self._mid_history[0]
        latest = self._mid_history[-1]
        net_move = latest - earliest  # positive = price rose

        if is_buy:
            # Adverse for a BUY = price FELL (net_move < 0)
            # Wait — we want to skip BUYs where the market moved DOWN already
            # (suggesting the signal may be stale and further downside risk).
            # Actually, re-reading: if price fell before a buy, we're buying low —
            # that's potentially GOOD, not bad, for a mean-reverting signal.
            # For a trending oracle, buying after a price RISE is adverse
            # (chasing momentum, adverse fill).
            # We skip BUY when recent price ROSE (net_move > threshold),
            # meaning we'd be buying into rising prices — worse entry.
            return net_move > self._momentum_threshold
        else:
            # Adverse for a SELL = price ROSE (we'd be selling into rising prices —
            # worse entry for our sell). Skip SELL when net_move < -threshold.
            return net_move < -self._momentum_threshold

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route the order: skip if composite spread+momentum condition fires."""
        # Get current top-of-book quote for spread and mid computation.
        try:
            quote = self.cache.quote_tick(order.instrument_id)
        except Exception:
            quote = None

        if quote is None:
            # No quote available — cannot evaluate conditions, submit immediately.
            self.log.info(
                f"No quote for {order.instrument_id}; submitting "
                f"{order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Prices from quote are in fixed-point int (1e-9 USD), convert to float.
        bid = float(quote.bid_price)
        ask = float(quote.ask_price)
        spread = ask - bid
        mid = (ask + bid) / 2.0

        # Update state even for reduce-only orders (keep windows current).
        spread_fires = self._update_and_get_spread_condition(spread)
        is_buy = order.side == OrderSide.BUY
        momentum_fires = self._update_and_get_momentum_condition(mid, is_buy)

        # Reduce-only orders are always submitted — required for intraday_flat.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Skip only if BOTH conditions fire simultaneously.
        if spread_fires and momentum_fires:
            self.log.info(
                f"SKIP order {order.client_order_id} "
                f"(side={'BUY' if is_buy else 'SELL'}, "
                f"spread={spread:.6f}, spread_fires={spread_fires}, "
                f"momentum_fires={momentum_fires}) — composite filter triggered."
            )
            # Do NOT call submit_order — order intentionally not executed.
        else:
            self.log.debug(
                f"SUBMIT order {order.client_order_id} "
                f"(spread_fires={spread_fires}, momentum_fires={momentum_fires})."
            )
            self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    spread_window: int = 60,
    spread_mult: float = 1.5,
    momentum_window: int = 5,
    momentum_threshold: float = 0.0,
) -> CompositeFilterAlgorithm:
    """Instantiate and return a CompositeFilterAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    spread_window : int
        Rolling window length for spread median.  Default 60.
    spread_mult : float
        Spread threshold multiplier.  Default 1.5.
    momentum_window : int
        Rolling window length for mid-price momentum.  Default 5.
    momentum_threshold : float
        Minimum adverse price move to fire momentum condition.  Default 0.0.
    """
    config = CompositeFilterConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        spread_window=spread_window,
        spread_mult=spread_mult,
        momentum_window=momentum_window,
        momentum_threshold=momentum_threshold,
    )
    return CompositeFilterAlgorithm(config=config)
