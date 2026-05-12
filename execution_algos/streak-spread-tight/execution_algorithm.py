"""Consecutive-loss streak + tighter-spread conditioned skip execution algorithm.

ONE targeted change vs streak-spread-skip:
  spread_multiplier default reduced from 1.3 -> 1.1.

All other logic (streak_lookback=2, spread_window=60, min_spread_window=10,
_position_flat re-entry guarantee, quantity invariant) is identical.

Rationale:
  The full 12-date train window has many high-volume days with win rates
  32-37% (vs the 47-49% seen in the 3-date window that calibrated
  streak-spread-skip). A tighter spread threshold fires more often on
  adverse ticks, selectively skipping more of the losing signals that
  dominate on those days.

Skips the OPEN leg of an oracle signal when EITHER:
  (a) the last TWO consecutive closed positions BOTH had negative estimated
      PnL (consecutive-loss streak), OR
  (b) the current bid-ask spread exceeds 1.1x the rolling 60-tick median
      spread.

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


class StreakSpreadTightConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the streak + tighter-spread skip algorithm.

    Parameters
    ----------
    spread_multiplier : float
        Skip when current spread > spread_multiplier * rolling-median spread.
        Default 1.1 (tighter than streak-spread-skip's 1.3).
    spread_window : int
        Number of recent spread observations for the rolling median. Default 60.
    min_spread_window : int
        Minimum observations before spread logic activates. Default 10.
    streak_lookback : int
        Number of consecutive prior losses required to trigger streak skip.
        Default 2 (both prev_pnl_1 and prev_pnl_2 must be negative).
    """

    spread_multiplier: float = 1.1
    spread_window: int = 60
    min_spread_window: int = 10
    streak_lookback: int = 2


class StreakSpreadTightAlgorithm(ExecAlgorithm):
    """Execution algorithm that skips on consecutive-loss streak OR elevated spread (1.1x).

    Opening orders (is_reduce_only == False):
      - Track the estimated PnL of the two most recently completed positions.
      - Compute the current spread from the top-of-book quote and compare
        to rolling median of recent spreads (last spread_window ticks).
      - Skip if EITHER:
          (a) both _prev_pnl_1 < 0 AND _prev_pnl_2 < 0 (consecutive-loss streak)
          (b) spread > 1.1 * median_spread (spread elevated, >= 10 samples)
      - After any skip, _position_flat = True: the NEXT open is always submitted
        regardless of signals to prevent cascade.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is ever modified. Quantity invariant always preserved.
    """

    def __init__(self, config: StreakSpreadTightConfig, skip_recorder=None) -> None:
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

        # Per-run skip recorder (issue #66). May be None when the
        # algorithm is constructed outside the research harness.
        self._skip_recorder = skip_recorder

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"StreakSpreadTightAlgorithm started "
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
            self._record_skip(order, quote, trigger_label)
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

    def _record_skip(self, order, quote, trigger: str) -> None:
        """Log a skip event to the per-run SkipRecorder (issue #66).

        Captures top-of-book at decision time so the post-run attribution
        can simulate the counterfactual fill. Silently no-ops when no
        recorder is attached (e.g. tests instantiating the algorithm
        directly) or when the cached quote is missing.
        """
        if self._skip_recorder is None or quote is None:
            return
        try:
            bid = float(str(quote.bid_price))
            ask = float(str(quote.ask_price))
            ts_event = int(getattr(quote, "ts_event", 0)) or int(order.ts_init)
            self._skip_recorder.record(
                ts_event=ts_event,
                instrument_id=order.instrument_id,
                parent_order_id=order.client_order_id,
                side="BUY" if order.side == OrderSide.BUY else "SELL",
                quantity=float(str(order.quantity)),
                bid=bid,
                ask=ask,
                trigger=trigger,
            )
        except Exception as exc:  # noqa: BLE001 — attribution must never break the run
            self.log.warning(f"skip-recorder failed: {exc}")


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    spread_multiplier: float = 1.1,
    spread_window: int = 60,
    min_spread_window: int = 10,
    streak_lookback: int = 2,
    skip_recorder=None,
) -> StreakSpreadTightAlgorithm:
    """Instantiate and return the StreakSpreadTightAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    spread_multiplier : float
        Threshold multiplier applied to rolling median spread. Default 1.1
        (tighter than streak-spread-skip's 1.3).
    spread_window : int
        Rolling window length for median spread history. Default 60 ticks.
    min_spread_window : int
        Minimum samples before spread logic activates. Default 10.
    streak_lookback : int
        Number of consecutive losses to trigger streak skip. Default 2.
    skip_recorder : SkipRecorder | None
        Optional per-run buffer that records each skip decision for
        counterfactual P&L attribution (issue #66). Injected by the
        research harness; absent when the algorithm is wired up
        manually.
    """
    config = StreakSpreadTightConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        spread_multiplier=spread_multiplier,
        spread_window=spread_window,
        min_spread_window=min_spread_window,
        streak_lookback=streak_lookback,
    )
    return StreakSpreadTightAlgorithm(config=config, skip_recorder=skip_recorder)
