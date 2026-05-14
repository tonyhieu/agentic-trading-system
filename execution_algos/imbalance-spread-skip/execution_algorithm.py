"""Book imbalance + spread conditioned skip execution algorithm.

ONE targeted change vs streak-spread-tight:
  Replace the consecutive-loss streak signal with a book imbalance signal.
  All spread parameters identical: spread_multiplier=1.1, spread_window=60,
  min_spread_window=10.

Skips the OPEN leg of an oracle signal when EITHER:
  (a) the current bid-ask spread exceeds 1.1x the rolling 60-tick median spread, OR
  (b) the top-of-book book imbalance is adversely aligned with the order direction
      by at least imbalance_threshold (default 0.2):
        I = (q_bid - q_ask) / (q_bid + q_ask)
        skip BUY  when I < -imbalance_threshold  (ask-heavy, price likely falling)
        skip SELL when I > +imbalance_threshold  (bid-heavy, price likely rising)

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


class ImbalanceSpreadSkipConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the book imbalance + spread skip algorithm.

    Parameters
    ----------
    imbalance_threshold : float
        Skip when adverse imbalance exceeds this magnitude.
        I = (q_bid - q_ask) / (q_bid + q_ask), skip BUY when I < -threshold,
        skip SELL when I > +threshold. Default 0.2.
    spread_multiplier : float
        Skip when current spread > spread_multiplier * rolling-median spread.
        Default 1.1 (identical to streak-spread-tight).
    spread_window : int
        Number of recent spread observations for the rolling median. Default 60.
    min_spread_window : int
        Minimum observations before spread logic activates. Default 10.
    """

    imbalance_threshold: float = 0.2
    spread_multiplier: float = 1.1
    spread_window: int = 60
    min_spread_window: int = 10


class ImbalanceSpreadSkipAlgorithm(ExecAlgorithm):
    """Execution algorithm that skips on adverse book imbalance OR elevated spread.

    Opening orders (is_reduce_only == False):
      - Compute book imbalance from current top-of-book quote and check if
        it is adversely aligned with the order direction by >= imbalance_threshold.
      - Compute spread from top-of-book quote and compare to rolling median of
        recent spreads (last spread_window ticks).
      - Skip if EITHER:
          (a) spread > spread_multiplier * median_spread  (spread elevated, >= min_spread_window samples)
          (b) I * direction < -imbalance_threshold          (imbalance adverse)
      - After any skip, _position_flat = True: the NEXT open is always submitted
        regardless of signals to prevent cascade.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is ever modified. Quantity invariant always preserved.
    """

    def __init__(self, config: ImbalanceSpreadSkipConfig) -> None:
        super().__init__(config=config)
        self._imbalance_threshold: float = config.imbalance_threshold
        self._spread_multiplier: float = config.spread_multiplier
        self._spread_window: int = config.spread_window
        self._min_spread_window: int = config.min_spread_window

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
            f"ImbalanceSpreadSkipAlgorithm started "
            f"(imbalance_thresh={self._imbalance_threshold}, "
            f"spread_mult={self._spread_multiplier}, "
            f"spread_window={self._spread_window}, "
            f"min_window={self._min_spread_window})."
        )

    def on_reset(self) -> None:
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
        """Route the order: submit or skip based on imbalance/spread conditions."""
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

        # Forced re-entry after a skip — always submit to prevent cascade.
        if self._position_flat:
            self.log.info(
                f"Re-entry after skip (or first order); submitting {order.client_order_id}."
            )
            self._position_flat = False
            self.submit_order(order)
            return

        # Evaluate both signals.
        spread_skip = False
        imbalance_skip = False

        if quote is not None:
            spread_skip = self._spread_triggered(quote)
            imbalance_skip = self._imbalance_triggered(quote, order.side)

        if spread_skip or imbalance_skip:
            trigger_label = (
                "spread+imbalance" if (spread_skip and imbalance_skip)
                else ("imbalance" if imbalance_skip else "spread")
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
            self._position_flat = False
            self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    imbalance_threshold: float = 0.2,
    spread_multiplier: float = 1.1,
    spread_window: int = 60,
    min_spread_window: int = 10,
) -> ImbalanceSpreadSkipAlgorithm:
    """Instantiate and return the ImbalanceSpreadSkipAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    imbalance_threshold : float
        Skip when adverse imbalance magnitude exceeds this value. Default 0.2.
        I = (q_bid - q_ask) / (q_bid + q_ask); skip BUY when I < -threshold.
    spread_multiplier : float
        Threshold multiplier applied to rolling median spread. Default 1.1.
    spread_window : int
        Rolling window length for median spread history. Default 60 ticks.
    min_spread_window : int
        Minimum samples before spread logic activates. Default 10.
    """
    config = ImbalanceSpreadSkipConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        imbalance_threshold=imbalance_threshold,
        spread_multiplier=spread_multiplier,
        spread_window=spread_window,
        min_spread_window=min_spread_window,
    )
    return ImbalanceSpreadSkipAlgorithm(config=config)
