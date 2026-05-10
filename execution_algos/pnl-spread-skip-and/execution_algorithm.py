"""Combined PnL-regime + spread conditioned skip (AND combination).

Skips the OPEN leg of an oracle signal when BOTH:
  (a) the immediately preceding closed position suffered a per-trade
      realized P&L <= pnl_skip_threshold (default -3.0 USD), AND
  (b) the current bid-ask spread exceeds spread_multiplier times the
      rolling median spread over the last spread_window ticks (default
      1.5x over 60 ticks).

Compared to pnl-spread-skip (OR combination), the AND variant requires
both signals to fire simultaneously — fewer skips, higher precision.

Reduce-only (close) orders are always submitted.

A _position_flat flag prevents cascade: after any skip, the next open
order is always submitted regardless of both signals.

Rationale:
- OR variant (pnl-spread-skip) fires on either adverse condition,
  maximising recall but potentially skipping profitable oracle signals.
- AND variant targets the intersection: ticks where BOTH the temporal
  regime signal (bad recent P&L) AND the contemporaneous microstructure
  signal (wide spread) are adverse simultaneously. Higher precision,
  fewer false-positive skips.

No quantity is ever modified. Skipped orders result in
sum(child_fills) < parent.quantity, which is allowed by the quantity
invariant (OBJECTIVE.md §3).

See execution_algos/pnl-spread-skip-and/NOTES.md for the full hypothesis.
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


class PnLSpreadSkipAndConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the AND-combination PnL-regime + spread skip algorithm.

    Parameters
    ----------
    pnl_skip_threshold : float
        Per-trade realized P&L threshold (USD) below which the AND-skip
        condition's PnL leg is triggered. Must be <= 0. Default -3.0.
    spread_multiplier : float
        The spread must exceed this multiple of the rolling median spread
        to trigger the AND-skip condition's spread leg. Default 1.5.
    spread_window : int
        Number of recent spread observations used for the rolling median.
        Default 60.
    """

    pnl_skip_threshold: float = -3.0
    spread_multiplier: float = 1.5
    spread_window: int = 60


class PnLSpreadSkipAndAlgorithm(ExecAlgorithm):
    """Execution algorithm that skips open orders on post-loss AND wide-spread signals.

    Opening orders (is_reduce_only == False):
      - Compute the per-trade P&L of the most recently completed position
        (same technique as pnl-regime-skip: quote-tick-based estimation).
      - Compute the current spread from the top-of-book quote and compare
        to rolling median of recent spreads.
      - Skip ONLY IF BOTH: pnl <= pnl_skip_threshold AND spread > spread_multiplier
        x median_spread (with warm-up guard >= 10 observations).
      - After any skip, _position_flat = True: the NEXT open is always submitted
        to prevent cascade.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is ever modified. This is the AND-combination variant of
    pnl-spread-skip (which uses OR).
    """

    def __init__(self, config: PnLSpreadSkipAndConfig) -> None:
        super().__init__(config=config)
        self._pnl_skip_threshold: float = config.pnl_skip_threshold
        self._spread_multiplier: float = config.spread_multiplier
        self._spread_window: int = config.spread_window

        # PnL tracking (from pnl-regime-skip)
        self._prev_open_price: float | None = None
        self._prev_direction: int | None = None
        self._position_flat: bool = True

        # Spread tracking (from spread-filter)
        self._spread_history: deque[float] = deque(maxlen=self._spread_window)

        # Subscription tracking
        self._subscribed: set[str] = set()

        # Skip count tracking for honesty reporting
        self._skip_count: int = 0
        self._submit_count: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"PnLSpreadSkipAndAlgorithm started "
            f"(pnl_threshold={self._pnl_skip_threshold}, "
            f"spread_mult={self._spread_multiplier}, "
            f"spread_window={self._spread_window}, "
            f"combination=AND)."
        )

    def on_reset(self) -> None:
        self._prev_open_price = None
        self._prev_direction = None
        self._position_flat = True
        self._spread_history.clear()
        self._subscribed.clear()
        self._skip_count = 0
        self._submit_count = 0

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
        """Update the spread history and return True if spread triggers skip leg.

        Returns False if the history is too short (warm-up) or spread is normal.
        """
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
                f"Spread leg triggered: {spread:.6f} > {self._spread_multiplier:.1f}x "
                f"median {median_spread:.6f}."
            )
        return triggered

    # ------------------------------------------------------------------
    # PnL estimation
    # ------------------------------------------------------------------

    def _estimate_prev_pnl(self, quote) -> float | None:
        """Estimate per-trade P&L of the most recently closed position.

        Uses the same approach as pnl-regime-skip: close price ≈ top-of-book
        at open-order decision time (before the open fills).
        """
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
        """Route the order: submit immediately, or skip on PnL AND spread signal."""
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

        # Update spread history (always, regardless of whether we skip).
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

        # Re-entry after a skip: force submit to prevent cascade.
        if self._position_flat:
            self.log.info(
                f"Re-entering after skip; submitting {order.client_order_id}."
            )
            self._record_open(order, quote)
            return

        # Estimate PnL of the just-closed position.
        pnl_trigger = False
        if quote is not None:
            prev_pnl = self._estimate_prev_pnl(quote)
            if prev_pnl is not None and prev_pnl <= self._pnl_skip_threshold:
                pnl_trigger = True
                self.log.debug(
                    f"PnL leg triggered: {prev_pnl:.4f} <= {self._pnl_skip_threshold:.4f}."
                )

        # Apply skip: AND of the two conditions (both must be true).
        if pnl_trigger and spread_trigger:
            self.log.info(
                f"SKIP order {order.client_order_id} "
                f"(trigger=pnl+spread AND) — both adverse conditions present."
            )
            self._skip_count += 1
            self._position_flat = True
            # Do NOT call submit_order — quantity invariant allows sum(fills) < parent.qty.
        else:
            self.log.debug(
                f"SUBMIT order {order.client_order_id} "
                f"(pnl_trigger={pnl_trigger}, spread_trigger={spread_trigger})."
            )
            self._submit_count += 1
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
        self._position_flat = False
        self.submit_order(order)

    def on_quote_tick(self, tick) -> None:
        """Consume quote ticks to keep the cache populated."""
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    pnl_skip_threshold: float | None = None,
    spread_multiplier: float | None = None,
    spread_window: int | None = None,
) -> PnLSpreadSkipAndAlgorithm:
    """Instantiate and return the PnLSpreadSkipAndAlgorithm (AND combination).

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    pnl_skip_threshold : float or None
        Per-trade P&L threshold (USD) below which the PnL leg of the AND
        condition is triggered. If None, reads from config.yaml or defaults to -3.0.
    spread_multiplier : float or None
        Spread leg triggers when spread > spread_multiplier x rolling median.
        Default 1.5.
    spread_window : int or None
        Rolling window length for median spread computation. Default 60.
    """
    cfg_pnl, cfg_mult, cfg_win = _load_config_values()

    if pnl_skip_threshold is None:
        pnl_skip_threshold = cfg_pnl
    if spread_multiplier is None:
        spread_multiplier = cfg_mult
    if spread_window is None:
        spread_window = cfg_win

    config = PnLSpreadSkipAndConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        pnl_skip_threshold=pnl_skip_threshold,
        spread_multiplier=spread_multiplier,
        spread_window=spread_window,
    )
    return PnLSpreadSkipAndAlgorithm(config=config)
