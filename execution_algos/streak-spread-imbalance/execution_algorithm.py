"""Triple-signal OR conditioned skip execution algorithm.

Extends streak-spread-tight (PASS, +140.52% vs baseline) with a third signal:
book imbalance. ONE targeted change from streak-spread-tight: add book imbalance
as an additional OR condition.

Skips the OPEN leg of an oracle signal when ANY of three conditions holds:
  (a) current bid-ask spread > 1.1x rolling 60-tick median spread (spread signal)
  (b) both last 2 consecutive closed positions had negative estimated PnL (streak signal)
  (c) book imbalance I = (q_bid - q_ask)/(q_bid + q_ask) is adversely aligned
      with order direction by >= imbalance_threshold:
        skip BUY  when I < -imbalance_threshold  (ask-heavy, price likely to fall)
        skip SELL when I > +imbalance_threshold  (bid-heavy, price likely to rise)

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


class StreakSpreadImbalanceConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the triple-signal (streak + spread + imbalance) skip algorithm.

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
        Default 2.
    imbalance_threshold : float
        Skip when adverse imbalance magnitude >= this value. Default 0.2.
        I = (q_bid - q_ask) / (q_bid + q_ask).
    """

    spread_multiplier: float = 1.1
    spread_window: int = 60
    min_spread_window: int = 10
    streak_lookback: int = 2
    imbalance_threshold: float = 0.2


class StreakSpreadImbalanceAlgorithm(ExecAlgorithm):
    """Execution algorithm that skips on streak OR spread OR adverse imbalance.

    Opening orders (is_reduce_only == False):
      - Track estimated PnL of the two most recently completed positions (streak).
      - Compute spread from top-of-book quote vs rolling median (spread).
      - Compute book imbalance and check if adversely aligned with order direction.
      - Skip if ANY signal triggers (OR logic).
      - After any skip, _position_flat = True: the NEXT open is always submitted.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is ever modified. Quantity invariant always preserved.
    """

    def __init__(self, config: StreakSpreadImbalanceConfig) -> None:
        super().__init__(config=config)
        self._spread_multiplier: float = config.spread_multiplier
        self._spread_window: int = config.spread_window
        self._min_spread_window: int = config.min_spread_window
        self._imbalance_threshold: float = config.imbalance_threshold

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
            f"StreakSpreadImbalanceAlgorithm started "
            f"(spread_mult={self._spread_multiplier}, "
            f"spread_window={self._spread_window}, "
            f"min_window={self._min_spread_window}, "
            f"imbalance_thresh={self._imbalance_threshold})."
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
    # PnL estimation / streak logic
    # ------------------------------------------------------------------

    def _estimate_prev_pnl(self, quote) -> float | None:
        """Estimate per-trade P&L of the most recently closed position.

        Uses current top-of-book quote as the close price approximation.
        Observable at open-order decision time (no look-ahead).

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
    # Book imbalance logic
    # ------------------------------------------------------------------

    def _imbalance_triggered(self, quote, order_side: OrderSide) -> bool:
        """Return True if book imbalance is adversely aligned with order direction.

        I = (q_bid - q_ask) / (q_bid + q_ask)
        Skip BUY  when I < -imbalance_threshold  (ask-heavy, price likely to fall)
        Skip SELL when I > +imbalance_threshold  (bid-heavy, price likely to rise)
        """
        try:
            bid_qty = float(str(quote.bid_size))
            ask_qty = float(str(quote.ask_size))
        except Exception:
            return False

        total = bid_qty + ask_qty
        if total <= 0:
            return False

        imbalance = (bid_qty - ask_qty) / total

        if order_side == OrderSide.BUY:
            # Adverse for BUY: ask-heavy (imbalance < -threshold)
            triggered = imbalance < -self._imbalance_threshold
            if triggered:
                self.log.debug(
                    f"Imbalance trigger (BUY adverse): I={imbalance:.3f} < "
                    f"-{self._imbalance_threshold}."
                )
        else:
            # Adverse for SELL: bid-heavy (imbalance > +threshold)
            triggered = imbalance > self._imbalance_threshold
            if triggered:
                self.log.debug(
                    f"Imbalance trigger (SELL adverse): I={imbalance:.3f} > "
                    f"+{self._imbalance_threshold}."
                )

        return triggered

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route the order: submit or skip based on streak/spread/imbalance conditions."""
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

        # Evaluate all three signals.
        spread_skip = False
        streak_skip = False
        imbalance_skip = False

        if quote is not None:
            spread_skip = self._spread_triggered(quote)
            streak_skip = self._streak_triggered(quote)
            imbalance_skip = self._imbalance_triggered(quote, order.side)

        if spread_skip or streak_skip or imbalance_skip:
            active = []
            if spread_skip:
                active.append("spread")
            if streak_skip:
                active.append("streak")
            if imbalance_skip:
                active.append("imbalance")
            trigger_label = "+".join(active)
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
    spread_multiplier: float = 1.1,
    spread_window: int = 60,
    min_spread_window: int = 10,
    streak_lookback: int = 2,
    imbalance_threshold: float = 0.2,
) -> StreakSpreadImbalanceAlgorithm:
    """Instantiate and return the StreakSpreadImbalanceAlgorithm.

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
    imbalance_threshold : float
        Adverse imbalance magnitude to trigger imbalance skip. Default 0.2.
    """
    config = StreakSpreadImbalanceConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        spread_multiplier=spread_multiplier,
        spread_window=spread_window,
        min_spread_window=min_spread_window,
        streak_lookback=streak_lookback,
        imbalance_threshold=imbalance_threshold,
    )
    return StreakSpreadImbalanceAlgorithm(config=config)
