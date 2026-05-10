"""Combined PnL-regime + spread conditioned 2-skip execution algorithm.

Extends pnl-spread-skip: after an OR trigger fires (PnL <= threshold OR
spread > multiplier x median), skips the next 2 consecutive OPEN orders
(instead of 1) before forcing re-entry.

Forced re-entry is preserved: after exactly `max_skips` consecutive skips,
the next open order is always submitted unconditionally. This prevents the
cascade suppression observed in pnl-spread-skip-2win (which dropped forced
re-entry and suppressed 79% of trades).

Hypothesis: the adverse regime that causes an OR trigger persists for
~2 oracle cycles (~2 seconds), so skipping 2 consecutive orders after a
trigger filters more losing trades than the 1-skip parent while the forced
re-entry still prevents cascade.

Reduce-only (close) orders are always submitted.
"""
from __future__ import annotations

import statistics
from collections import deque
from pathlib import Path

import yaml

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_config_values() -> tuple[float, float, int, int]:
    """Read skip parameters from config.yaml if present, else defaults.

    Returns
    -------
    tuple of (pnl_skip_threshold, spread_multiplier, spread_window, max_skips)
    """
    config_path = _REPO_ROOT / "research" / "config.yaml"
    try:
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        ec = cfg.get("execution_constraints", {})
        pnl_threshold = float(ec.get("pnl_skip_threshold", -3.0))
        spread_mult = float(ec.get("spread_multiplier", 1.5))
        spread_win = int(ec.get("spread_window", 60))
        max_skips = int(ec.get("max_skips", 2))
        return pnl_threshold, spread_mult, spread_win, max_skips
    except Exception:
        return -3.0, 1.5, 60, 2


class PnLSpreadSkip2SkipConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the combined PnL-regime + spread 2-skip algorithm.

    Parameters
    ----------
    pnl_skip_threshold : float
        Per-trade realized P&L threshold (USD) below which a skip window is
        armed. Must be <= 0. Default -3.0.
    spread_multiplier : float
        The spread must exceed this multiple of the rolling median spread
        to arm a skip window. Default 1.5.
    spread_window : int
        Number of recent spread observations used for the rolling median.
        Default 60.
    max_skips : int
        Number of consecutive OPEN orders to skip after a trigger fires.
        After max_skips, the next open is forced through unconditionally.
        Default 2.
    """

    pnl_skip_threshold: float = -3.0
    spread_multiplier: float = 1.5
    spread_window: int = 60
    max_skips: int = 2


class PnLSpreadSkip2SkipAlgorithm(ExecAlgorithm):
    """Execution algorithm: 2-skip window with forced re-entry on OR(pnl,spread) triggers.

    State machine for open orders:
    - _skips_remaining == -1: normal state, check triggers.
      * If trigger fires: set _skips_remaining = max_skips - 1, skip.
      * Else: submit, record entry.
    - _skips_remaining > 0: inside skip window, decrement and skip.
    - _skips_remaining == 0: forced re-entry — submit unconditionally, reset to -1.

    Closing orders (is_reduce_only == True): always submitted.
    """

    def __init__(self, config: PnLSpreadSkip2SkipConfig) -> None:
        super().__init__(config=config)
        self._pnl_skip_threshold: float = config.pnl_skip_threshold
        self._spread_multiplier: float = config.spread_multiplier
        self._spread_window: int = config.spread_window
        self._max_skips: int = config.max_skips

        # PnL tracking
        self._prev_open_price: float | None = None
        self._prev_direction: int | None = None

        # Spread tracking
        self._spread_history: deque[float] = deque(maxlen=self._spread_window)

        # Skip window state: -1 = normal; 0 = forced re-entry next; N > 0 = N more skips.
        self._skips_remaining: int = -1

        # Subscription tracking
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"PnLSpreadSkip2SkipAlgorithm started "
            f"(pnl_threshold={self._pnl_skip_threshold}, "
            f"spread_mult={self._spread_multiplier}, "
            f"spread_window={self._spread_window}, "
            f"max_skips={self._max_skips})."
        )

    def on_reset(self) -> None:
        self._prev_open_price = None
        self._prev_direction = None
        self._spread_history.clear()
        self._subscribed.clear()
        self._skips_remaining = -1

    # ------------------------------------------------------------------
    # Subscription helpers
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Spread computation
    # ------------------------------------------------------------------

    def _update_and_check_spread(self, quote) -> bool:
        """Update spread history and return True if spread triggers a skip."""
        try:
            ask = float(str(quote.ask_price))
            bid = float(str(quote.bid_price))
            spread = ask - bid
        except Exception:
            return False

        self._spread_history.append(spread)

        if len(self._spread_history) < 10:
            return False

        median_spread = statistics.median(self._spread_history)
        if median_spread <= 0:
            return False

        triggered = spread > self._spread_multiplier * median_spread
        if triggered:
            self.log.debug(
                f"Spread trigger: {spread:.6f} > {self._spread_multiplier:.1f}x "
                f"median {median_spread:.6f}."
            )
        return triggered

    # ------------------------------------------------------------------
    # PnL estimation
    # ------------------------------------------------------------------

    def _estimate_prev_pnl(self, quote) -> float | None:
        """Estimate per-trade P&L of the most recently closed position."""
        if self._prev_open_price is None or self._prev_direction is None:
            return None

        try:
            if self._prev_direction == -1:
                # Previous was SELL (short). Close = BUY at ask.
                close_price = float(str(quote.ask_price))
            else:
                # Previous was BUY (long). Close = SELL at bid.
                close_price = float(str(quote.bid_price))
        except Exception:
            return None

        return (close_price - self._prev_open_price) * self._prev_direction

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route the order: submit immediately, or skip/force based on skip window."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only orders always execute — intraday_flat compliance.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Get current quote for spread and PnL estimation.
        quote = self.cache.quote_tick(order.instrument_id)

        # Always update spread history.
        if quote is not None:
            self._update_and_check_spread(quote)

        # First open of the session: no prior data, submit immediately.
        if self._prev_open_price is None:
            self.log.info(
                f"No prior open; submitting {order.client_order_id} immediately."
            )
            self._record_open(order, quote)
            return

        # FORCED RE-ENTRY: skip window exhausted — submit unconditionally.
        if self._skips_remaining == 0:
            self.log.info(
                f"Forced re-entry after {self._max_skips}-skip window; "
                f"submitting {order.client_order_id}."
            )
            self._skips_remaining = -1  # Reset to normal state.
            self._record_open(order, quote)
            return

        # INSIDE SKIP WINDOW: more skips remaining.
        if self._skips_remaining > 0:
            self._skips_remaining -= 1
            self.log.info(
                f"SKIP order {order.client_order_id} "
                f"(skips_remaining={self._skips_remaining} after decrement)."
            )
            return  # Do not call submit_order.

        # NORMAL STATE (_skips_remaining == -1): check triggers.
        # Re-read spread trigger from the deque state (already updated above).
        spread_trigger = False
        if quote is not None and len(self._spread_history) >= 10:
            try:
                ask = float(str(quote.ask_price))
                bid = float(str(quote.bid_price))
                spread = ask - bid
                median_spread = statistics.median(self._spread_history)
                if median_spread > 0:
                    spread_trigger = spread > self._spread_multiplier * median_spread
            except Exception:
                pass

        pnl_trigger = False
        if quote is not None:
            prev_pnl = self._estimate_prev_pnl(quote)
            if prev_pnl is not None and prev_pnl <= self._pnl_skip_threshold:
                pnl_trigger = True
                self.log.debug(
                    f"PnL trigger: {prev_pnl:.4f} <= {self._pnl_skip_threshold:.4f}."
                )

        if pnl_trigger or spread_trigger:
            trigger_label = (
                "pnl+spread" if (pnl_trigger and spread_trigger)
                else ("pnl" if pnl_trigger else "spread")
            )
            # Arm skip window: max_skips - 1 because we're counting this as skip #1.
            self._skips_remaining = self._max_skips - 1
            self.log.info(
                f"SKIP order {order.client_order_id} "
                f"(trigger={trigger_label}, skips_remaining={self._skips_remaining} after)."
            )
            # Do NOT call submit_order.
        else:
            self.log.debug(
                f"SUBMIT order {order.client_order_id} — normal regime."
            )
            self._record_open(order, quote)

    def _record_open(self, order, quote) -> None:
        """Submit the order and record entry price for future PnL estimation."""
        if quote is not None:
            try:
                if order.side == OrderSide.BUY:
                    fill_price = float(str(quote.ask_price))
                else:
                    fill_price = float(str(quote.bid_price))
                self._prev_open_price = fill_price
            except Exception:
                self._prev_open_price = None

        self._prev_direction = 1 if order.side == OrderSide.BUY else -1
        self.submit_order(order)

    def on_quote_tick(self, tick) -> None:
        """Consume quote ticks to keep cache populated."""
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    pnl_skip_threshold: float | None = None,
    spread_multiplier: float | None = None,
    spread_window: int | None = None,
    max_skips: int | None = None,
) -> PnLSpreadSkip2SkipAlgorithm:
    """Instantiate and return the PnLSpreadSkip2SkipAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    pnl_skip_threshold : float or None
        Per-trade P&L threshold (USD) below which a skip window is armed.
        If None, reads from config.yaml or defaults to -3.0.
    spread_multiplier : float or None
        Skip when spread > spread_multiplier x rolling median. Default 1.5.
    spread_window : int or None
        Rolling window length for median spread computation. Default 60.
    max_skips : int or None
        Number of consecutive open orders to skip per trigger. Default 2.
    """
    cfg_pnl, cfg_mult, cfg_win, cfg_max = _load_config_values()

    if pnl_skip_threshold is None:
        pnl_skip_threshold = cfg_pnl
    if spread_multiplier is None:
        spread_multiplier = cfg_mult
    if spread_window is None:
        spread_window = cfg_win
    if max_skips is None:
        max_skips = cfg_max

    config = PnLSpreadSkip2SkipConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        pnl_skip_threshold=pnl_skip_threshold,
        spread_multiplier=spread_multiplier,
        spread_window=spread_window,
        max_skips=max_skips,
    )
    return PnLSpreadSkip2SkipAlgorithm(config=config)
