"""Mid-price momentum conditioned skip execution algorithm.

For each open (non-reduce-only) order at submission time:
  - Read the rolling mid-price history accumulated from recent quote ticks.
  - Compute drift = (mid[-1] - mid[0]) / (window - 1) in raw price units.
  - For a BUY order: skip if drift > +momentum_threshold
    (price has been rising — buying into a completed move).
  - For a SELL order: skip if drift < -momentum_threshold
    (price has been falling — selling into a completed move).
  - If window too small or no quote: submit immediately (baseline fallback).

Reduce-only (close) orders are always submitted to maintain intraday_flat.

The quantity invariant is preserved — no order quantity is ever modified.
Skipped orders result in sum(child_fills) < parent.quantity, allowed by §3.

See execution_algos/momentum-skip/NOTES.md for the full hypothesis.
"""
from __future__ import annotations

from collections import defaultdict, deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class MomentumSkipConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the momentum-conditioned skip execution algorithm.

    Parameters
    ----------
    window_size : int
        Number of recent quote ticks to use for the mid-price drift estimate.
        Default 5 — short enough to capture recent momentum without noise.
    min_window : int
        Minimum number of quote ticks required before the skip logic activates.
        If fewer samples are available, submit immediately (baseline fallback).
        Default 3.
    momentum_threshold : float
        Minimum absolute drift (in raw price units, i.e. 1e-9 USD per
        price-increment) required to trigger a skip. Expressed as a fraction
        of a minimum tick: 0.5 means half a minimum-price-increment per tick
        of price history. For MES futures at $0.25 per tick the raw price
        unit is 2.5e8 (0.25 * 1e9), so 0.5 ticks ≈ 1.25e8.
        Default 1.25e8 (half a MES tick in raw price units).
    """

    window_size: int = 5
    min_window: int = 3
    momentum_threshold: float = 1.25e8  # 0.5 MES tick in raw price units (1/2 of $0.25)


class MomentumSkipAlgorithm(ExecAlgorithm):
    """Execution algorithm that skips orders when the mid-price momentum
    indicates the trade would be buying into a rising market or selling into
    a falling market (i.e., the oracle signal is likely already consumed).

    Opening orders (is_reduce_only == False):
      - Maintain a per-instrument rolling window of recent mid-prices.
      - Compute drift over the window.
      - Skip if drift is adverse (positive for BUY, negative for SELL) and
        exceeds momentum_threshold.
      - Otherwise submit immediately.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is modified. Quantity invariant always preserved.
    """

    def __init__(self, config: MomentumSkipConfig) -> None:
        super().__init__(config=config)
        self._window_size: int = config.window_size
        self._min_window: int = config.min_window
        self._momentum_threshold: float = config.momentum_threshold
        # instrument_id string → deque of recent mid prices (raw int units)
        self._mid_history: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=self._window_size)
        )
        # instruments we have already subscribed to quote ticks
        self._subscribed: set[str] = set()

    def on_start(self) -> None:
        self.log.info(
            f"MomentumSkipAlgorithm started "
            f"(window_size={self._window_size}, "
            f"min_window={self._min_window}, "
            f"momentum_threshold={self._momentum_threshold:.3e})."
        )

    def on_reset(self) -> None:
        self._mid_history.clear()
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
    # Momentum computation
    # ------------------------------------------------------------------

    def _compute_drift(self, instrument_id) -> float | None:
        """Return the per-tick drift of mid-price over the rolling window.

        drift = (mid[-1] - mid[0]) / (n - 1)   in raw price units per tick

        Returns None if the window has fewer than min_window samples.
        Positive drift → price rising; negative drift → price falling.
        """
        key = str(instrument_id)
        history = self._mid_history[key]
        n = len(history)
        if n < self._min_window:
            return None

        mids = list(history)
        drift = (mids[-1] - mids[0]) / (n - 1)
        return drift

    # ------------------------------------------------------------------
    # Quote tick handler — accumulates mid-price history
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        """Record mid-price for each incoming quote tick."""
        key = str(tick.instrument_id)
        # Use the .raw integer (1e-9 price units) for precision-safe arithmetic.
        # Falls back to float * 1e9 if .raw is unavailable on older Nautilus builds.
        try:
            bid_raw = tick.bid_price.raw
            ask_raw = tick.ask_price.raw
        except AttributeError:
            bid_raw = round(float(tick.bid_price) * 1_000_000_000)
            ask_raw = round(float(tick.ask_price) * 1_000_000_000)

        mid = (bid_raw + ask_raw) // 2
        self._mid_history[key].append(mid)

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route the order: submit immediately or skip if momentum is adverse."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders are always submitted — intraday_flat.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Compute drift over the rolling window.
        drift = self._compute_drift(order.instrument_id)

        if drift is None:
            # Insufficient history — submit immediately (baseline fallback).
            self.log.info(
                f"Insufficient mid-price history for {order.instrument_id}; "
                f"submitting {order.client_order_id} immediately (no-history fallback)."
            )
            self.submit_order(order)
            return

        # Determine whether this order faces adverse momentum.
        adverse = False
        if order.side == OrderSide.BUY and drift > self._momentum_threshold:
            # Price rising → buying into strength → adverse.
            adverse = True
        elif order.side == OrderSide.SELL and drift < -self._momentum_threshold:
            # Price falling → selling into weakness → adverse.
            adverse = True

        if adverse:
            self.log.info(
                f"SKIP order {order.client_order_id} "
                f"(side={order.side.name}, drift={drift:.3e}, "
                f"threshold=±{self._momentum_threshold:.3e}) — adverse momentum."
            )
            # Do NOT call submit_order — order is intentionally not executed.
        else:
            self.log.debug(
                f"SUBMIT order {order.client_order_id} "
                f"(side={order.side.name}, drift={drift:.3e}) — favourable momentum."
            )
            self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_size: int = 5,
    min_window: int = 3,
    momentum_threshold: float = 1.25e8,
) -> MomentumSkipAlgorithm:
    """Instantiate and return the MomentumSkipAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_size : int
        Rolling window length for mid-price drift. Default 5 ticks.
    min_window : int
        Minimum samples before skip logic activates. Default 3 ticks.
    momentum_threshold : float
        Minimum adverse drift (raw price units per tick) to trigger a skip.
        Default 1.25e8 (~half a MES futures tick of $0.25).
    """
    config = MomentumSkipConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_size=window_size,
        min_window=min_window,
        momentum_threshold=momentum_threshold,
    )
    return MomentumSkipAlgorithm(config=config)
