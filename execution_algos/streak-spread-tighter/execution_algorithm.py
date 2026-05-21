"""Consecutive-loss streak + tighter-spread conditioned skip execution algorithm.

ONE targeted change vs streak-spread-tight:
  spread_multiplier default reduced from 1.1 -> 1.0.

All other logic (streak_lookback=2, spread_window=60, min_spread_window=10,
_position_flat re-entry guarantee, quantity invariant) is identical.

Rationale:
  streak-spread-tight (PASS, +140.52%) uses spread_multiplier=1.1, skipping
  only the top ~10-20% of spread observations. Setting multiplier to 1.0
  fires whenever spread is strictly above the rolling median, approximately
  50% of ticks. On high-trade-count dates (20260316-17) with win rates
  33-35%, more aggressive filtering is expected to remove more adverse
  entries since the oracle is near-random in the spread dimension.

Skips the OPEN leg of an oracle signal when EITHER:
  (a) the last TWO consecutive closed positions BOTH had negative estimated
      PnL (consecutive-loss streak), OR
  (b) the current bid-ask spread exceeds 1.0x the rolling 60-tick median
      spread (i.e., strictly above median).

Reduce-only (close) orders are always submitted.

After any skip, the next OPEN order is always submitted to prevent cascade
(_position_flat re-entry guarantee).
"""
from __future__ import annotations

import statistics
from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class StreakSpreadTighterConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the streak + tightest-spread skip algorithm.

    Parameters
    ----------
    spread_multiplier : float
        Skip when current spread > spread_multiplier * rolling-median spread.
        Default 1.0 (skip when spread is strictly above the rolling median).
    spread_window : int
        Number of recent spread observations for the rolling median. Default 60.
    min_spread_window : int
        Minimum observations before spread logic activates. Default 10.
    streak_lookback : int
        Number of consecutive prior losses required to trigger streak skip.
        Default 2 (both prev_pnl_1 and prev_pnl_2 must be negative).
    """

    spread_multiplier: float = 1.0
    spread_window: int = 60
    min_spread_window: int = 10
    streak_lookback: int = 2


class StreakSpreadTighterAlgorithm(ExecAlgorithm):
    """Execution algorithm that skips on consecutive-loss streak OR above-median spread.

    Opening orders (is_reduce_only == False):
      - Track the estimated PnL of the two most recently completed positions.
      - Compute the current spread from the top-of-book quote and compare
        to rolling median of recent spreads (last spread_window ticks).
      - Skip if EITHER:
          (a) both _prev_pnl_1 < 0 AND _prev_pnl_2 < 0 (consecutive-loss streak)
          (b) spread > 1.0 * median_spread, i.e., strictly above median (>= 10 samples)
      - After any skip, _position_flat = True: the NEXT open is always submitted
        regardless of signals to prevent cascade.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is ever modified. Quantity invariant always preserved.
    """

    def __init__(self, config: StreakSpreadTighterConfig) -> None:
        super().__init__(config=config)
        self._spread_multiplier: float = config.spread_multiplier
        self._spread_window: int = config.spread_window
        self._min_spread_window: int = config.min_spread_window

        # PnL streak tracking
        self._prev_pnl_1: float | None = None   # most recently closed trade
        self._prev_pnl_2: float | None = None   # second most recently closed trade

        # Entry price tracking for PnL estimation
        self._prev_open_price: float | None = None
        self._prev_direction: int | None = None  # +1 for BUY, -1 for SELL

        # Forced re-entry after any skip
        self._position_flat: bool = True

        # Spread history
        self._spread_history: deque[float] = deque(maxlen=self._spread_window)

        # Subscription tracking
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"StreakSpreadTighterAlgorithm started "
            f"(spread_mult={self._spread_multiplier}, "
            f"spread_window={self._spread_window}, "
            f"min_window={self._min_spread_window})."
        )

    def on_reset(self) -> None:
        self._prev_pnl_1 = None
        self._prev_pnl_2 = None
        self._prev_open_price = None
        self._prev_direction = None
        self._position_flat = True
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
        """Return True if current spread strictly exceeds the threshold."""
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

        # Forced re-entry after a skip — always submit to prevent cascade.
        if self._position_flat:
            self.log.info(
                f"Re-entry after skip; submitting {order.client_order_id}."
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
            trigger_label = (
                "streak+spread" if (streak_skip and spread_skip)
                else ("streak" if streak_skip else "spread")
            )
            self.log.info(
                f"SKIP order {order.client_order_id} "
                f"(trigger={trigger_label}) — adverse regime."
            )
            self._position_flat = True
            # Do NOT call submit_order — quantity invariant preserved
        else:
            self.log.debug(
                f"SUBMIT order {order.client_order_id} — normal regime."
            )
            self._record_open(order, quote)

    def _record_open(self, order, quote) -> None:
        """Submit the order and record the expected open fill price."""
        if quote is not None:
            try:
                if order.side == OrderSide.BUY:
                    self._prev_open_price = float(str(quote.ask_price))
                else:
                    self._prev_open_price = float(str(quote.bid_price))
            except Exception:
                self._prev_open_price = None
        self._prev_direction = 1 if order.side == OrderSide.BUY else -1
        self._position_flat = False
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    spread_multiplier: float = 1.0,
    spread_window: int = 60,
    min_spread_window: int = 10,
    streak_lookback: int = 2,
) -> StreakSpreadTighterAlgorithm:
    """Instantiate and return the StreakSpreadTighterAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    spread_multiplier : float
        Threshold multiplier applied to rolling median spread. Default 1.0
        (skip when spread is strictly above rolling median).
    spread_window : int
        Rolling window length for median spread history. Default 60 ticks.
    min_spread_window : int
        Minimum samples before spread logic activates. Default 10.
    streak_lookback : int
        Number of consecutive losses to trigger streak skip. Default 2.
    """
    config = StreakSpreadTighterConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        spread_multiplier=spread_multiplier,
        spread_window=spread_window,
        min_spread_window=min_spread_window,
        streak_lookback=streak_lookback,
    )
    return StreakSpreadTighterAlgorithm(config=config)
