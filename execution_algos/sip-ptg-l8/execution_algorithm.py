"""PTG + Rolling Win-Rate Gate execution algorithm (sip-ptg-l8).

Extends position-tier-gate with a rolling win-rate filter: when the
estimated win rate over the last `window` completed round-trips falls
below `win_rate_threshold`, new OPEN orders are skipped.

Hypothesis:
    The oracle's directional accuracy varies across intraday regimes.
    Per-date analysis of the PTG lineage shows that on high-volume dates
    (20260316–20260317) the aggregate win rate drops to 31–34%, driving
    large losses (-$522, -$247). By tracking a rolling window of the last
    `window` estimated round-trip P&Ls and skipping OPENs when win_rate <
    threshold (35%), the algorithm reduces participation during adverse
    oracle regimes while maintaining full participation when the oracle is
    performing well (win_rate >= 35%).

Algorithm:
    On each non-reduce-only order:
      1. Base PTG gate: skip if net_qty >= position_cap (same as base).
      2. Forced re-entry: if _position_flat is True (immediately after a
         win-rate skip), always submit to prevent cascade-skip starvation.
      3. Estimate the most recently completed round-trip P&L using the
         current top-of-book quote and the recorded entry price/direction
         (same method as streak-spread-tight). Append to rolling history.
      4. If len(history) >= min_window AND win_rate(history) < threshold:
         SKIP; set _position_flat = True.
      5. Else: SUBMIT; record entry price and direction.

PnL estimation:
    Long (prev_direction == +1): estimated_close = current bid_price.
    Short (prev_direction == -1): estimated_close = current ask_price.
    PnL = (estimated_close - prev_open_price) * prev_direction.

Re-entry guarantee (_position_flat):
    After any win-rate skip, the immediately following solo OPEN is always
    submitted regardless of win-rate. This prevents the algorithm from
    staying flat indefinitely when the win-rate remains depressed.

Constraints:
    - No opposing positions: skip leaves algo flat.
    - quantity_invariant: qty=1, never modified.
    - top_of_book_only: unchanged.
    - participation_cap: qty=1, never binds.
    - intraday_flat: reduce-only always submitted.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class SipPtgL8Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for sip-ptg-l8.

    Parameters
    ----------
    position_cap : int
        Same as base PTG. Default 1 (serialize entries).
    window : int
        Rolling history size (number of completed round-trips). Default 20.
    win_rate_threshold : float
        Skip OPENs when rolling win rate < this value. Default 0.35 (35%).
    min_window : int
        Minimum history before the win-rate filter activates. Default 10.
    """

    position_cap: int = 1
    window: int = 20
    win_rate_threshold: float = 0.35
    min_window: int = 10


class SipPtgL8Algorithm(ExecAlgorithm):
    """Execution algorithm: PTG + rolling win-rate gate.

    Opening orders (is_reduce_only == False):
      1. If net_qty >= position_cap: SKIP (same as base PTG).
      2. If _position_flat (re-entry after win-rate skip): SUBMIT unconditionally.
      3. Estimate last round-trip PnL, append to history.
      4. If enough history AND win_rate < threshold: SKIP; _position_flat = True.
      5. Else: SUBMIT; record entry price/direction.

    Closing orders (is_reduce_only == True):
      Always submit (intraday_flat).
    """

    def __init__(self, config: SipPtgL8Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        self._window: int = config.window
        self._win_rate_threshold: float = config.win_rate_threshold
        self._min_window: int = config.min_window

        # Rolling P&L history (estimated per round-trip).
        self._pnl_history: deque[float] = deque(maxlen=self._window)

        # Entry tracking for PnL estimation.
        self._prev_open_price: float | None = None
        self._prev_direction: int | None = None  # +1 BUY, -1 SELL

        # Re-entry guarantee: True immediately after a win-rate skip.
        self._position_flat: bool = True

        # Quote subscription tracking.
        self._subscribed: set[str] = set()

    def on_start(self) -> None:
        self.log.info(
            f"SipPtgL8Algorithm started "
            f"(position_cap={self._position_cap}, "
            f"window={self._window}, "
            f"win_rate_threshold={self._win_rate_threshold:.0%}, "
            f"min_window={self._min_window})."
        )

    def on_reset(self) -> None:
        self._pnl_history.clear()
        self._prev_open_price = None
        self._prev_direction = None
        self._position_flat = True
        self._subscribed.clear()

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    def on_quote_tick(self, tick) -> None:
        pass  # Quotes consumed via cache.quote_tick() in on_order().

    def _current_net_qty(self, instrument_id) -> float:
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        return sum(float(str(p.quantity)) for p in open_positions)

    def _estimate_last_pnl(self, quote) -> float | None:
        """Estimate the most recently completed round-trip P&L.

        Uses current top-of-book quote as the close-price approximation for
        the previous position — observable at on_order() time (no look-ahead).
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

    def _rolling_win_rate(self) -> float | None:
        """Return rolling win rate; None if history is below min_window."""
        if len(self._pnl_history) < self._min_window:
            return None
        wins = sum(1 for p in self._pnl_history if p > 0)
        return wins / len(self._pnl_history)

    def _record_open(self, order, quote) -> None:
        """Submit the order and record entry price/direction."""
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

    def on_order(self, order) -> None:
        """Route order: PTG gate → re-entry check → win-rate gate → submit."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only orders always execute.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Base PTG gate: skip paired OPENs when already in a position.
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty >= self._position_cap:
            self.log.debug(
                f"SKIP {order.client_order_id} — PTG cap "
                f"(net_qty={net_qty:.1f} >= cap={self._position_cap})."
            )
            return

        # Fetch current quote for PnL estimation.
        quote = self.cache.quote_tick(order.instrument_id)

        # First trade of session: no history to estimate from — submit.
        if self._prev_open_price is None:
            self.log.info(
                f"No prior open; submitting {order.client_order_id} (first trade)."
            )
            self._record_open(order, quote)
            return

        # Re-entry guarantee: always submit the trade immediately after a skip.
        if self._position_flat:
            self.log.info(
                f"Re-entry after win-rate skip; submitting {order.client_order_id}."
            )
            # Still update history so we don't inflate the win rate artificially.
            if quote is not None:
                pnl = self._estimate_last_pnl(quote)
                if pnl is not None:
                    self._pnl_history.append(pnl)
            self._record_open(order, quote)
            return

        # Estimate last round-trip P&L and append to history.
        if quote is not None:
            pnl = self._estimate_last_pnl(quote)
            if pnl is not None:
                self._pnl_history.append(pnl)

        # Win-rate gate.
        win_rate = self._rolling_win_rate()
        if win_rate is not None and win_rate < self._win_rate_threshold:
            self.log.info(
                f"SKIP {order.client_order_id} — win-rate gate "
                f"(win_rate={win_rate:.1%} < threshold={self._win_rate_threshold:.0%}, "
                f"n={len(self._pnl_history)})."
            )
            self._position_flat = True
            return

        self.log.debug(
            f"SUBMIT {order.client_order_id} — gates passed "
            f"(win_rate={win_rate:.1%} >= {self._win_rate_threshold:.0%} "
            f"or n={len(self._pnl_history)} < min_window={self._min_window})."
            if win_rate is not None
            else f"SUBMIT {order.client_order_id} — warming up "
            f"(n={len(self._pnl_history)} < min_window={self._min_window})."
        )
        self._record_open(order, quote)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    window: int = 20,
    win_rate_threshold: float = 0.35,
    min_window: int = 10,
) -> SipPtgL8Algorithm:
    """Instantiate and return the SipPtgL8Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    position_cap : int
        PTG position cap. Default 1 (serialize entries).
    window : int
        Rolling win-rate history length (round-trips). Default 20.
    win_rate_threshold : float
        Win rate below which OPENs are skipped. Default 0.35.
    min_window : int
        Minimum history before the gate activates. Default 10.
    """
    config = SipPtgL8Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        window=window,
        win_rate_threshold=win_rate_threshold,
        min_window=min_window,
    )
    return SipPtgL8Algorithm(config)
