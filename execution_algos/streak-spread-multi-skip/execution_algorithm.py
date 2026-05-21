"""Consecutive-loss streak + spread conditioned skip with multi-skip re-entry.

Building on streak-spread-tight (PASS, +140.52% vs baseline).

ONE targeted change vs streak-spread-tight:
  Replace the hard "forced re-entry after exactly 1 skip" guarantee with
  "forced re-entry after at most max_consecutive_skips=3 consecutive skips."

All other logic (spread_multiplier=1.1, spread_window=60, min_spread_window=10,
streak_lookback=2, quantity invariant) is identical.

Rationale:
  In streak-spread-tight, the _position_flat flag forces re-entry on the VERY
  NEXT open order after any skip. Since the oracle signal cadence is 1 second
  and spread is autocorrelated at that scale, the forced re-entry often fires
  into the same elevated-spread condition that triggered the skip. This defeats
  the filter. Allowing up to 3 consecutive skips lets the autocorrelation decay
  before re-entering, while the cap guarantees eventual participation and
  intraday_flat compliance.

Skips the OPEN leg of an oracle signal when EITHER:
  (a) the last TWO consecutive closed positions BOTH had negative estimated
      PnL (consecutive-loss streak), OR
  (b) the current bid-ask spread exceeds 1.1x the rolling 60-tick median
      spread.

Reduce-only (close) orders are always submitted.

After max_consecutive_skips consecutive skips, the next OPEN order is always
submitted regardless of conditions (anti-cascade guarantee).
"""
from __future__ import annotations

import statistics
from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class StreakSpreadMultiSkipConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the streak + spread multi-skip algorithm.

    Parameters
    ----------
    spread_multiplier : float
        Skip when current spread > spread_multiplier * rolling-median spread.
        Default 1.1 (same as streak-spread-tight).
    spread_window : int
        Number of recent spread observations for the rolling median. Default 60.
    min_spread_window : int
        Minimum observations before spread logic activates. Default 10.
    streak_lookback : int
        Number of consecutive prior losses required to trigger streak skip.
        Default 2 (both prev_pnl_1 and prev_pnl_2 must be negative).
    max_consecutive_skips : int
        Maximum consecutive open orders that may be skipped before the next
        open is forced through regardless of conditions. Default 3.
        This is the ONE targeted change vs streak-spread-tight (was implicitly 1).
    """

    spread_multiplier: float = 1.1
    spread_window: int = 60
    min_spread_window: int = 10
    streak_lookback: int = 2
    max_consecutive_skips: int = 3


class StreakSpreadMultiSkipAlgorithm(ExecAlgorithm):
    """Execution algorithm: streak+spread skip with multi-skip re-entry.

    Opening orders (is_reduce_only == False):
      - Track the estimated PnL of the two most recently completed positions.
      - Compute the current spread from the top-of-book quote and compare
        to rolling median of recent spreads (last spread_window ticks).
      - Skip if EITHER:
          (a) both _prev_pnl_1 < 0 AND _prev_pnl_2 < 0 (consecutive-loss streak)
          (b) spread > 1.1 * median_spread (spread elevated, >= 10 samples)
      - After max_consecutive_skips consecutive skips, the NEXT open is always
        submitted regardless of conditions (anti-cascade guarantee).
      - _consecutive_skips counter is reset to 0 after any submission.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is ever modified. Quantity invariant always preserved.
    """

    def __init__(self, config: StreakSpreadMultiSkipConfig) -> None:
        super().__init__(config=config)
        self._spread_multiplier: float = config.spread_multiplier
        self._spread_window: int = config.spread_window
        self._min_spread_window: int = config.min_spread_window
        self._max_consecutive_skips: int = config.max_consecutive_skips

        # PnL streak tracking
        self._prev_pnl_1: float | None = None   # most recently closed trade
        self._prev_pnl_2: float | None = None   # second most recently closed trade

        # Entry price tracking for PnL estimation
        self._prev_open_price: float | None = None
        self._prev_direction: int | None = None  # +1 for BUY, -1 for SELL

        # Consecutive skip counter (replaces _position_flat bool from streak-spread-tight)
        self._consecutive_skips: int = 0

        # Spread history
        self._spread_history: deque[float] = deque(maxlen=self._spread_window)

        # Subscription tracking
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"StreakSpreadMultiSkipAlgorithm started "
            f"(spread_mult={self._spread_multiplier}, "
            f"spread_window={self._spread_window}, "
            f"min_window={self._min_spread_window}, "
            f"max_consecutive_skips={self._max_consecutive_skips})."
        )

    def on_reset(self) -> None:
        self._prev_pnl_1 = None
        self._prev_pnl_2 = None
        self._prev_open_price = None
        self._prev_direction = None
        self._consecutive_skips = 0
        self._spread_history.clear()
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
    # Spread logic
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        """Accumulate spread history from every incoming quote tick."""
        try:
            ask = float(str(tick.ask_price))
            bid = float(str(tick.bid_price))
            spread = ask - bid
            if spread >= 0:
                self._spread_history.append(spread)
        except Exception:
            pass

    def _spread_triggered(self, quote) -> bool:
        """Return True if current spread exceeds the threshold."""
        if len(self._spread_history) < self._min_spread_window:
            return False

        try:
            ask = float(str(quote.ask_price))
            bid = float(str(quote.bid_price))
            spread = ask - bid
        except Exception:
            return False

        median_spread = statistics.median(self._spread_history)
        if median_spread <= 0:
            return False

        triggered = spread > self._spread_multiplier * median_spread
        if triggered:
            self.log.debug(
                f"Spread trigger: {spread:.6f} > {self._spread_multiplier}x "
                f"median {median_spread:.6f}."
            )
        return triggered

    # ------------------------------------------------------------------
    # PnL estimation
    # ------------------------------------------------------------------

    def _estimate_prev_pnl(self, quote) -> float | None:
        """Estimate per-trade P&L of the most recently closed position.

        Uses current top-of-book quote as the close price approximation for
        the previous position. This is observable at open-order decision time.

        Long position (prev_direction == +1):
            PnL estimate = current_bid - prev_open_ask
        Short position (prev_direction == -1):
            PnL estimate = prev_open_bid - current_ask
        """
        if self._prev_open_price is None or self._prev_direction is None:
            return None

        try:
            if self._prev_direction == 1:
                close_price = float(str(quote.bid_price))
            else:
                close_price = float(str(quote.ask_price))
        except Exception:
            return None

        return (close_price - self._prev_open_price) * self._prev_direction

    def _streak_triggered(self, quote) -> bool:
        """Return True if consecutive-loss streak condition is met."""
        if self._prev_open_price is None:
            return False

        prev_pnl = self._estimate_prev_pnl(quote)
        if prev_pnl is None:
            return False

        # Shift history
        self._prev_pnl_2 = self._prev_pnl_1
        self._prev_pnl_1 = prev_pnl

        triggered = (
            self._prev_pnl_1 is not None
            and self._prev_pnl_2 is not None
            and self._prev_pnl_1 < 0
            and self._prev_pnl_2 < 0
        )
        if triggered:
            self.log.debug(
                f"Streak trigger: pnl_1={self._prev_pnl_1:.4f}, "
                f"pnl_2={self._prev_pnl_2:.4f} — both negative."
            )
        return triggered

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route the order: submit or skip based on spread/streak conditions."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Fetch current quote for all signal computations.
        quote = self.cache.quote_tick(order.instrument_id)

        # No prior position info — submit immediately (first trade of session).
        if self._prev_open_price is None:
            self.log.info(
                f"No prior open; submitting {order.client_order_id} immediately."
            )
            self._record_open(order, quote)
            return

        # Forced re-entry after max_consecutive_skips — anti-cascade guarantee.
        if self._consecutive_skips >= self._max_consecutive_skips:
            self.log.info(
                f"Forced re-entry after {self._consecutive_skips} consecutive skips; "
                f"submitting {order.client_order_id}."
            )
            self._record_open(order, quote)
            return

        # Evaluate both signals.
        spread_skip = False
        streak_skip = False

        if quote is not None:
            spread_skip = self._spread_triggered(quote)
            streak_skip = self._streak_triggered(quote)

        if spread_skip or streak_skip:
            self._consecutive_skips += 1
            trigger_label = (
                "streak+spread" if (streak_skip and spread_skip)
                else ("streak" if streak_skip else "spread")
            )
            self.log.info(
                f"SKIP order {order.client_order_id} "
                f"(trigger={trigger_label}, consecutive_skips={self._consecutive_skips}) "
                f"— adverse regime."
            )
            # Do NOT call submit_order — quantity invariant preserved
        else:
            self.log.debug(
                f"SUBMIT order {order.client_order_id} — normal regime."
            )
            self._record_open(order, quote)

    def _record_open(self, order, quote) -> None:
        """Submit the order, record the expected open fill price, reset skip counter."""
        if quote is not None:
            try:
                if order.side == OrderSide.BUY:
                    self._prev_open_price = float(str(quote.ask_price))
                else:
                    self._prev_open_price = float(str(quote.bid_price))
            except Exception:
                self._prev_open_price = None
        self._prev_direction = 1 if order.side == OrderSide.BUY else -1
        self._consecutive_skips = 0  # reset after any successful submission
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    spread_multiplier: float = 1.1,
    spread_window: int = 60,
    min_spread_window: int = 10,
    streak_lookback: int = 2,
    max_consecutive_skips: int = 3,
) -> StreakSpreadMultiSkipAlgorithm:
    """Instantiate and return the StreakSpreadMultiSkipAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    spread_multiplier : float
        Threshold multiplier applied to rolling median spread. Default 1.1.
    spread_window : int
        Rolling window length for median spread history. Default 60 ticks.
    min_spread_window : int
        Minimum samples before spread logic activates. Default 10.
    streak_lookback : int
        Number of consecutive losses to trigger streak skip. Default 2.
    max_consecutive_skips : int
        Maximum consecutive skips before forced re-entry. Default 3.
        ONE targeted change vs streak-spread-tight (was implicitly 1).
    """
    config = StreakSpreadMultiSkipConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        spread_multiplier=spread_multiplier,
        spread_window=spread_window,
        min_spread_window=min_spread_window,
        streak_lookback=streak_lookback,
        max_consecutive_skips=max_consecutive_skips,
    )
    return StreakSpreadMultiSkipAlgorithm(config=config)
