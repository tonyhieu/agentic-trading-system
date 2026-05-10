"""Post-loss regime skip execution algorithm.

When the most recently completed position suffered a per-trade realized P&L
<= -pnl_skip_threshold (default -3.0 USD, a >= 12-tick adverse move), the
immediately following OPEN order is skipped. Reduce-only (close) orders are
always submitted.

Rationale:
- With sigma=5, the oracle is near-random (~47-49% win rate).
- A very large adverse outcome (12+ ticks) suggests the oracle is in a
  persistently bad-noise regime for the current epoch.
- Skipping the next open avoids the follow-on loss.

IMPLEMENTATION APPROACH:
Rather than relying on `on_order_filled` callbacks (which fire AFTER the
same-timestamp on_order calls, creating sequencing issues), this algorithm
tracks the per-trade P&L directly by:
  1. Recording the fill price and direction of each OPEN order at submission time
     using self.cache.quote_tick() for the current top-of-book price.
  2. When the next OPEN order arrives, the previous position has just closed.
     The close price ≈ current top-of-book price (fill at ask/bid for BUY/SELL).
     Per-trade P&L ≈ (close_price - open_price) × direction

This avoids the fill-event sequencing problem and gives the correct per-trade
P&L at the exact moment we need it.

No quantity is ever modified. Skipped orders result in
sum(child_fills) < parent.quantity, which is allowed by the quantity
invariant (OBJECTIVE.md §3).

See execution_algos/pnl-regime-skip/NOTES.md for the full hypothesis.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_pnl_threshold() -> float:
    """Read the PnL skip threshold from config.yaml if present, else default."""
    config_path = _REPO_ROOT / "research" / "config.yaml"
    try:
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        ec = cfg.get("execution_constraints", {})
        return float(ec.get("pnl_skip_threshold", -3.0))
    except Exception:
        return -3.0


class PnLRegimeSkipConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the PnL-regime-conditioned skip execution algorithm.

    Parameters
    ----------
    pnl_skip_threshold : float
        Per-trade realized P&L threshold (USD) below which the next open
        order is skipped. Must be <= 0. Default -3.0 (skip after >= 12-tick
        adverse move at tick_value=0.25 USD/tick).
    """

    pnl_skip_threshold: float = -3.0


class PnLRegimeSkipAlgorithm(ExecAlgorithm):
    """Execution algorithm that skips open orders following a large-loss close.

    Opening orders (is_reduce_only == False):
      - Compute the per-trade P&L of the most recently completed position
        using cached quote-tick data:
            close_price ≈ current bid (for a BUY close) or ask (for a SELL close)
            pnl = (close_price - prev_open_price) × direction
      - If that estimated pnl <= pnl_skip_threshold: SKIP this open order.
      - If we're currently in a skipped regime (have no open position, prev
        reduction was of a non-existent position): ALWAYS SUBMIT to re-enter.
      - Otherwise (or if no prior open): submit immediately.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is ever modified.
    """

    def __init__(self, config: PnLRegimeSkipConfig) -> None:
        super().__init__(config=config)
        self._pnl_skip_threshold: float = config.pnl_skip_threshold

        # State from the previous open order we executed
        self._prev_open_price: float | None = None  # price of the last executed open
        self._prev_direction: int | None = None      # +1 for BUY, -1 for SELL

        # Whether we are currently in "no position" state (we skipped the last open)
        self._position_flat: bool = True

        # Instruments we have subscribed to quote ticks.
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"PnLRegimeSkipAlgorithm started "
            f"(pnl_skip_threshold={self._pnl_skip_threshold})."
        )

    def on_reset(self) -> None:
        self._prev_open_price = None
        self._prev_direction = None
        self._position_flat = True
        self._subscribed.clear()

    # ------------------------------------------------------------------
    # Subscription helpers (keeps quote cache warm)
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Estimate close price from current quote tick
    # ------------------------------------------------------------------

    def _get_close_price(self, order, for_prev_direction: int) -> float | None:
        """Estimate the close price for the just-ended position.

        The close order is reduce_only: a BUY close ends a SHORT (prev_direction=-1),
        a SELL close ends a LONG (prev_direction=+1).

        The fill price ≈ current ask (for BUY) or bid (for SELL).
        Since the close fires before the open (same timestamp), and the quote
        is subscribed, the current quote gives a good approximation.
        """
        quote = self.cache.quote_tick(order.instrument_id)
        if quote is None:
            return None

        if for_prev_direction == 1:
            # LONG → close is a SELL → fills at bid
            return float(str(quote.bid_price).split()[0]) if hasattr(quote.bid_price, '__str__') else float(quote.bid_price)
        else:
            # SHORT → close is a BUY → fills at ask
            return float(str(quote.ask_price).split()[0]) if hasattr(quote.ask_price, '__str__') else float(quote.ask_price)

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route the order: submit immediately or skip if post-loss regime."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders are always submitted — intraday_flat.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Open order logic below.
        # If no previous open, submit immediately (first order of the day).
        if self._prev_open_price is None:
            self.log.info(
                f"No prior open; submitting {order.client_order_id} immediately."
            )
            self._record_open(order)
            return

        # If we don't have an active position (we skipped the last open),
        # we are currently flat. We should re-enter to avoid getting stuck.
        if self._position_flat:
            self.log.info(
                f"No active position (prev open was skipped); submitting "
                f"{order.client_order_id} to re-enter."
            )
            self._record_open(order)
            return

        # Estimate the P&L of the position that just closed.
        # The close price ≈ current top-of-book from the cached quote.
        quote = self.cache.quote_tick(order.instrument_id)
        if quote is None:
            # No quote available; submit conservatively.
            self.log.info(
                f"No quote tick available; submitting {order.client_order_id} immediately."
            )
            self._record_open(order)
            return

        # Close price: for a BUY open (closes a SELL), close was a BUY → filled at ask.
        # For a SELL open (closes a BUY), close was a SELL → filled at bid.
        # The NEW open order gives us the direction. The close was the OPPOSITE.
        # Actually: if the new order is BUY, the previous was SELL (direction=-1).
        # close_order = BUY → fills at ask.
        try:
            if self._prev_direction == -1:
                # Previous was SELL (short position). Close = BUY at ask.
                close_price_raw = quote.ask_price
            else:
                # Previous was BUY (long position). Close = SELL at bid.
                close_price_raw = quote.bid_price

            close_price = float(str(close_price_raw))
        except Exception as exc:
            self.log.warning(f"Could not parse quote price: {exc}; submitting immediately.")
            self._record_open(order)
            return

        # Per-trade P&L estimate:
        # BUY (prev_direction=+1): pnl = (close_price - open_price) * 1
        # SELL (prev_direction=-1): pnl = (open_price - close_price) * 1
        per_trade_pnl = (close_price - self._prev_open_price) * self._prev_direction

        self.log.debug(
            f"Estimated prev position pnl: {per_trade_pnl:.4f} "
            f"(prev_open={self._prev_open_price:.2f}, close_est={close_price:.2f}, "
            f"direction={self._prev_direction})"
        )

        # Apply skip rule.
        if per_trade_pnl <= self._pnl_skip_threshold:
            self.log.info(
                f"SKIP order {order.client_order_id} "
                f"(est_pnl={per_trade_pnl:.4f} <= threshold={self._pnl_skip_threshold:.4f}) "
                f"— post-loss regime."
            )
            # Mark position as flat (skipped this open).
            self._position_flat = True
            # Do NOT call submit_order — quantity invariant allows sum(fills) < parent.qty.
        else:
            self.log.debug(
                f"SUBMIT order {order.client_order_id} "
                f"(est_pnl={per_trade_pnl:.4f}) — normal regime."
            )
            self._record_open(order)

    def _record_open(self, order) -> None:
        """Submit the order and record its entry price."""
        # Get fill price estimate from current quote.
        quote = self.cache.quote_tick(order.instrument_id)
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
        self._position_flat = False
        self.submit_order(order)

    def on_quote_tick(self, tick) -> None:
        """Consume quote ticks to keep the cache populated."""
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    pnl_skip_threshold: float | None = None,
) -> PnLRegimeSkipAlgorithm:
    """Instantiate and return the PnLRegimeSkipAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    pnl_skip_threshold : float or None
        Per-trade P&L threshold below which the next open order is skipped.
        If None, reads from config.yaml or defaults to -3.0.
    """
    if pnl_skip_threshold is None:
        pnl_skip_threshold = _load_pnl_threshold()

    config = PnLRegimeSkipConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        pnl_skip_threshold=pnl_skip_threshold,
    )
    return PnLRegimeSkipAlgorithm(config=config)
