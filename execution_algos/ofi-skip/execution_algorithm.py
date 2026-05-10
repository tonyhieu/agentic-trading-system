"""Order-Flow-Imbalance conditioned order skip execution algorithm.

For each open (non-reduce-only) order arriving via on_order():
  - Read the EMA of Order Flow Imbalance (OFI) computed from recent quote ticks.
  - OFI_t = (bid_size_t - bid_size_{t-1}) - (ask_size_t - ask_size_{t-1})
  - For a BUY order: adverse condition = EMA(OFI) < -ofi_skip_threshold
    (net selling flow dominant — adverse for buying).
  - For a SELL order: adverse condition = EMA(OFI) > +ofi_skip_threshold
    (net buying flow dominant — adverse for selling).
  - If adverse AND warmup complete: SKIP the order entirely.
  - Otherwise: submit immediately.

Reduce-only (close) orders are always submitted to maintain intraday_flat.

See execution_algos/ofi-skip/NOTES.md for the full hypothesis.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class OFISkipConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the OFI-conditioned skip execution algorithm.

    Parameters
    ----------
    ofi_skip_threshold : float
        EMA(OFI) magnitude beyond which orders are skipped.
        OFI is measured in lots (integers). A threshold of 0.5 skips when
        average net flow is adverse by >= 0.5 lots per tick in the EMA window.
        Default 0.5.
    ema_n : int
        Number of ticks in the EMA window. alpha = 2 / (ema_n + 1).
        Default 20 (roughly 5-20 seconds of quote tick history).
    min_quotes_warmup : int
        Minimum number of quote ticks before the OFI filter activates.
        Orders arriving before warmup submit immediately (conservative fallback).
        Default 5.
    """

    ofi_skip_threshold: float = 0.5
    ema_n: int = 20
    min_quotes_warmup: int = 5


class OFISkipAlgorithm(ExecAlgorithm):
    """Execution algorithm that skips orders when order-flow imbalance is adverse.

    Opening orders (is_reduce_only == False):
      - Compute the EMA of OFI from recent quote ticks.
      - For BUY: skip if EMA(OFI) < -ofi_skip_threshold (selling flow dominant).
      - For SELL: skip if EMA(OFI) > +ofi_skip_threshold (buying flow dominant).
      - Otherwise: submit immediately.
      - Warmup not yet complete: submit immediately (conservative fallback).

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is ever modified. Skipped orders result in
    sum(child_fills) < parent.quantity, which is allowed by the quantity
    invariant (OBJECTIVE.md §3).
    """

    def __init__(self, config: OFISkipConfig) -> None:
        super().__init__(config=config)
        self._ofi_threshold: float = config.ofi_skip_threshold
        self._alpha: float = 2.0 / (config.ema_n + 1)
        self._min_warmup: int = config.min_quotes_warmup

        # State updated in on_quote_tick()
        self._ema_ofi: float = 0.0
        self._prev_bid_size: float | None = None
        self._prev_ask_size: float | None = None
        self._quote_count: int = 0

        # Instruments we have already subscribed to quote ticks
        self._subscribed: set[str] = set()

    def on_start(self) -> None:
        self.log.info(
            f"OFISkipAlgorithm started "
            f"(ofi_skip_threshold={self._ofi_threshold}, "
            f"ema_n={int(round(2.0 / self._alpha - 1))}, "
            f"min_warmup={self._min_warmup})."
        )

    def on_reset(self) -> None:
        self._ema_ofi = 0.0
        self._prev_bid_size = None
        self._prev_ask_size = None
        self._quote_count = 0
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
    # Quote tick handler — updates OFI EMA
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        """Update OFI EMA from each arriving quote tick.

        OFI_t = (bid_size_t - bid_size_{t-1}) - (ask_size_t - ask_size_{t-1})

        Uses only the current and immediately prior quote — no look-ahead.
        """
        bid_size = float(str(tick.bid_size))
        ask_size = float(str(tick.ask_size))

        if self._prev_bid_size is None:
            # First quote tick: initialise reference without computing OFI
            self._prev_bid_size = bid_size
            self._prev_ask_size = ask_size
            self._quote_count += 1
            return

        # Compute OFI for this tick
        ofi = (bid_size - self._prev_bid_size) - (ask_size - self._prev_ask_size)

        # Update EMA
        self._ema_ofi = self._alpha * ofi + (1.0 - self._alpha) * self._ema_ofi

        # Store previous for next tick
        self._prev_bid_size = bid_size
        self._prev_ask_size = ask_size
        self._quote_count += 1

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route the order: submit immediately or skip if OFI is adverse."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders are always submitted — intraday_flat.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Before warmup: submit immediately (conservative fallback).
        if self._quote_count < self._min_warmup:
            self.log.info(
                f"Warmup not complete ({self._quote_count}/{self._min_warmup} quotes); "
                f"submitting {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Determine whether OFI is adverse to this order direction.
        ema_ofi = self._ema_ofi
        adverse = False

        if order.side == OrderSide.BUY and ema_ofi < -self._ofi_threshold:
            # Selling flow dominant: adverse for a BUY — skip.
            adverse = True
        elif order.side == OrderSide.SELL and ema_ofi > self._ofi_threshold:
            # Buying flow dominant: adverse for a SELL — skip.
            adverse = True

        if adverse:
            # SKIP: quantity invariant allows sum(fills) < parent.qty.
            self.log.info(
                f"SKIP order {order.client_order_id} "
                f"(side={order.side.name}, ema_ofi={ema_ofi:.4f}, "
                f"threshold={self._ofi_threshold:.4f}) — adverse order flow."
            )
            # Do NOT call submit_order — order is intentionally not executed.
        else:
            # OFI is neutral or favourable — submit immediately.
            self.log.debug(
                f"SUBMIT order {order.client_order_id} "
                f"(side={order.side.name}, ema_ofi={ema_ofi:.4f}) — favourable flow."
            )
            self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    ofi_skip_threshold: float = 0.5,
    ema_n: int = 20,
    min_quotes_warmup: int = 5,
) -> OFISkipAlgorithm:
    """Instantiate and return the OFISkipAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    ofi_skip_threshold : float
        EMA(OFI) magnitude in lots above which orders are skipped.
        Default 0.5.
    ema_n : int
        EMA window length in quote ticks.
        Default 20.
    min_quotes_warmup : int
        Minimum quote ticks before the filter activates.
        Default 5.
    """
    config = OFISkipConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        ofi_skip_threshold=ofi_skip_threshold,
        ema_n=ema_n,
        min_quotes_warmup=min_quotes_warmup,
    )
    return OFISkipAlgorithm(config=config)
