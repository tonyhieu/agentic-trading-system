"""2-skip window variant of the combined PnL-regime + spread conditioned skip.

After an OR trigger fires (post-loss OR wide-spread), skip the next 2
consecutive OPEN orders before re-entering — compared to the parent
`pnl-spread-skip` which skips only 1 open per trigger.

Skip conditions:
  (a) The immediately preceding closed position suffered a realized P&L
      <= pnl_skip_threshold (default -3.0 USD), OR
  (b) The current bid-ask spread exceeds spread_multiplier times the rolling
      median spread over the last spread_window ticks (default 1.5x, 60 ticks).

When either condition fires, _skips_remaining is set to 2. Each subsequent
open order decrements the counter by 1 and is skipped. When the counter
reaches 0, normal execution resumes. A trigger that fires while the counter
is already > 0 does not reset the counter (no stacking).

Reduce-only (close) orders are always submitted immediately (intraday_flat).

No order quantity is ever modified. Skipped orders result in
sum(child_fills) < parent.quantity, allowed by OBJECTIVE.md §3.

See execution_algos/pnl-spread-skip-2win/NOTES.md for the full hypothesis.
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


def _load_config_values() -> tuple[float, float, int]:
    """Read skip parameters from config.yaml if present, else defaults.

    Returns
    -------
    tuple of (pnl_skip_threshold, spread_multiplier, spread_window)
    """
    config_path = _REPO_ROOT / "research" / "config.yaml"
    try:
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        ec = cfg.get("execution_constraints", {})
        pnl_threshold = float(ec.get("pnl_skip_threshold", -3.0))
        spread_mult = float(ec.get("spread_multiplier", 1.5))
        spread_win = int(ec.get("spread_window", 60))
        return pnl_threshold, spread_mult, spread_win
    except Exception:
        return -3.0, 1.5, 60


class PnLSpreadSkip2WinConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the 2-skip-window variant of PnL+spread skip.

    Parameters
    ----------
    pnl_skip_threshold : float
        Per-trade realized P&L threshold (USD) below which the next 2 open
        orders are skipped. Must be <= 0. Default -3.0.
    spread_multiplier : float
        Skip when spread exceeds this multiple of the rolling median.
        Default 1.5.
    spread_window : int
        Number of recent spread observations used for the rolling median.
        Default 60.
    skip_window : int
        Number of consecutive open orders to skip after each trigger.
        Default 2.
    """

    pnl_skip_threshold: float = -3.0
    spread_multiplier: float = 1.5
    spread_window: int = 60
    skip_window: int = 2


class PnLSpreadSkip2WinAlgorithm(ExecAlgorithm):
    """Execution algorithm with a 2-open skip window after PnL+spread triggers.

    Opening orders (is_reduce_only == False):
      - Compute spread from top-of-book and update rolling history.
      - Compute estimated PnL of the most recently closed position.
      - If EITHER pnl <= threshold OR spread > multiplier*median fires:
          set _skips_remaining = skip_window (default 2).
      - If _skips_remaining > 0: skip this order, decrement _skips_remaining.
      - Otherwise: submit the order.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is ever modified.
    """

    def __init__(self, config: PnLSpreadSkip2WinConfig) -> None:
        super().__init__(config=config)
        self._pnl_skip_threshold: float = config.pnl_skip_threshold
        self._spread_multiplier: float = config.spread_multiplier
        self._spread_window: int = config.spread_window
        self._skip_window: int = config.skip_window

        # PnL tracking
        self._prev_open_price: float | None = None
        self._prev_direction: int | None = None

        # Skip counter: 0 = normal; >0 = skip and decrement
        self._skips_remaining: int = 0

        # Spread tracking
        self._spread_history: deque[float] = deque(maxlen=self._spread_window)

        # Subscription tracking
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"PnLSpreadSkip2WinAlgorithm started "
            f"(pnl_threshold={self._pnl_skip_threshold}, "
            f"spread_mult={self._spread_multiplier}, "
            f"spread_window={self._spread_window}, "
            f"skip_window={self._skip_window})."
        )

    def on_reset(self) -> None:
        self._prev_open_price = None
        self._prev_direction = None
        self._skips_remaining = 0
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
    # Spread computation
    # ------------------------------------------------------------------

    def _update_and_check_spread(self, quote) -> bool:
        """Update the spread history and return True if spread triggers a skip."""
        try:
            ask = float(str(quote.ask_price))
            bid = float(str(quote.bid_price))
            spread = ask - bid
        except Exception:
            return False

        self._spread_history.append(spread)

        # Warm-up guard: need at least 10 observations for a stable median.
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
        """Route the order: skip (decrement counter) or submit."""
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

        # Update spread history (always, regardless of skip decision).
        spread_trigger = False
        if quote is not None:
            spread_trigger = self._update_and_check_spread(quote)

        # First open of the session: no prior data, submit immediately.
        if self._prev_open_price is None:
            self.log.info(
                f"No prior open; submitting {order.client_order_id} immediately."
            )
            self._record_open(order, quote)
            return

        # If already in a skip window, skip this order and decrement.
        if self._skips_remaining > 0:
            self.log.info(
                f"SKIP order {order.client_order_id} "
                f"(skip window: {self._skips_remaining} remaining)."
            )
            self._skips_remaining -= 1
            # Do NOT call submit_order.
            return

        # Evaluate PnL trigger.
        pnl_trigger = False
        if quote is not None:
            prev_pnl = self._estimate_prev_pnl(quote)
            if prev_pnl is not None and prev_pnl <= self._pnl_skip_threshold:
                pnl_trigger = True
                self.log.debug(
                    f"PnL trigger: {prev_pnl:.4f} <= {self._pnl_skip_threshold:.4f}."
                )

        # Apply skip: OR of the two conditions.
        if pnl_trigger or spread_trigger:
            trigger_label = (
                "pnl+spread" if (pnl_trigger and spread_trigger)
                else ("pnl" if pnl_trigger else "spread")
            )
            self.log.info(
                f"SKIP order {order.client_order_id} "
                f"(trigger={trigger_label}) — setting skip_window={self._skip_window}."
            )
            # Skip this order and arm the counter for (skip_window - 1) more skips.
            # (This order itself is already skipped by not calling submit_order.)
            self._skips_remaining = self._skip_window - 1
            # Do NOT call submit_order.
        else:
            self.log.debug(
                f"SUBMIT order {order.client_order_id} — normal regime."
            )
            self._record_open(order, quote)

    def _record_open(self, order, quote) -> None:
        """Submit the order and record its entry price for future PnL estimation."""
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
        self._skips_remaining = 0
        self.submit_order(order)

    def on_quote_tick(self, tick) -> None:
        """Consume quote ticks to keep the cache populated."""
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    pnl_skip_threshold: float | None = None,
    spread_multiplier: float | None = None,
    spread_window: int | None = None,
    skip_window: int | None = None,
) -> PnLSpreadSkip2WinAlgorithm:
    """Instantiate and return the PnLSpreadSkip2WinAlgorithm.

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
    skip_window : int or None
        Number of consecutive opens to skip after each trigger. Default 2.
    """
    cfg_pnl, cfg_mult, cfg_win = _load_config_values()

    if pnl_skip_threshold is None:
        pnl_skip_threshold = cfg_pnl
    if spread_multiplier is None:
        spread_multiplier = cfg_mult
    if spread_window is None:
        spread_window = cfg_win
    if skip_window is None:
        skip_window = 2

    config = PnLSpreadSkip2WinConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        pnl_skip_threshold=pnl_skip_threshold,
        spread_multiplier=spread_multiplier,
        spread_window=spread_window,
        skip_window=skip_window,
    )
    return PnLSpreadSkip2WinAlgorithm(config=config)
