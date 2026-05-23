"""Position-tier + EMA-smoothed book-imbalance gate execution algorithm.

Builds on `position-tier-imbalance-gate` (iter 1 PASS). The only change is
the imbalance gate input: instead of reading the SINGLE most-recent quote's
imbalance at order-decision time, the gate reads an exponentially-weighted
moving average of imbalance across recent quote ticks. Everything else
(positional cap, reduce-only fast-path, thin-book guard) is inherited
verbatim.

Why EMA-smoothed imbalance:
  Single-tick top-of-book imbalance is noisy at the quote-by-quote level.
  Lipton-Pesavento documents imbalance as a directional predictor over
  short but multi-tick horizons; Kolm/Turiel/Westray find the effective
  alpha horizon of order-flow signals is ~2 price changes (i.e., not a
  single tick). A short EMA (alpha=0.30, ~6-tick equivalent window) gives
  the gate a more reliable read of the persistent book lean while
  suppressing tick-level flicker.

No look-ahead: the EMA is updated incrementally in `on_quote_tick(tick)`
as the engine processes quotes in chronological order. At `on_order()`
time, the EMA reflects only quotes already processed (strictly past
relative to the order's ts_init).

No quantity modification: every parent order is either submitted intact
or skipped entirely. Quantity invariant always preserved.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PositionTierImbalanceEmaGateConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the position-tier + EMA-imbalance gate algorithm.

    Parameters
    ----------
    position_cap : int
        Maximum absolute net position size (contracts) at which new
        open-leg orders are still allowed. Default 1.
    skip_threshold : float
        EMA-imbalance threshold for the imbalance gate. Imbalance is
        `bid_size / (bid_size + ask_size)` in [0, 1]; the EMA of this
        quantity is compared to the threshold.
          BUY  orders: SKIP when ema_imbalance <      skip_threshold
          SELL orders: SKIP when ema_imbalance > 1 -  skip_threshold
        Default 0.40 (matches prior `position-tier-imbalance-gate`).
    min_total_size : float
        Minimum bid_size + ask_size required for a quote to (a) be
        considered when evaluating the gate at order time and (b) update
        the EMA. Below this, the book is too thin to read a meaningful
        imbalance. Default 2.0 contracts.
    ema_alpha : float
        EMA smoothing factor in (0, 1]. The recursion is
        `ema_t = alpha * imbalance_t + (1 - alpha) * ema_{t-1}`.
        Larger alpha = faster response, smaller alpha = more smoothing.
        Default 0.30 (~6-tick equivalent simple-moving-average window),
        approximately matching the Kolm/Turiel/Westray "two price
        changes" alpha horizon for typical FX-futures quote cadence.
    """

    position_cap: int = 1
    skip_threshold: float = 0.40
    min_total_size: float = 2.0
    ema_alpha: float = 0.30


class PositionTierImbalanceEmaGateAlgorithm(ExecAlgorithm):
    """Execution algo: position-tier gate + EMA-smoothed top-of-book imbalance.

    Opening orders (is_reduce_only == False):
      - If current absolute net position >= position_cap: SKIP.
      - Else, read the per-instrument EMA imbalance:
          BUY:  SKIP when ema <      skip_threshold
          SELL: SKIP when ema > 1 -  skip_threshold
        If the EMA has not been seeded yet (no eligible quote observed),
        treat as neutral (do not skip).
      - Otherwise: SUBMIT.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    Quote ticks (on_quote_tick):
      - Maintain a per-instrument EMA of `bid_size / (bid_size + ask_size)`,
        updated only when bid_size + ask_size >= min_total_size.
    """

    def __init__(self, config: PositionTierImbalanceEmaGateConfig) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        self._skip_threshold: float = config.skip_threshold
        self._min_total_size: float = config.min_total_size
        self._ema_alpha: float = config.ema_alpha

        # Subscription tracking (quote ticks needed for imbalance signal).
        self._subscribed: set[str] = set()

        # Per-instrument EMA imbalance state. Key: str(instrument_id).
        # Value: latest EMA value in [0, 1]. Absent key = not yet seeded.
        self._ema_imbalance: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"PositionTierImbalanceEmaGateAlgorithm started "
            f"(position_cap={self._position_cap}, "
            f"skip_threshold={self._skip_threshold:.2f}, "
            f"min_total_size={self._min_total_size:.1f}, "
            f"ema_alpha={self._ema_alpha:.2f})."
        )

    def on_reset(self) -> None:
        self._subscribed.clear()
        self._ema_imbalance.clear()

    # ------------------------------------------------------------------
    # Subscription helper
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Position helper
    # ------------------------------------------------------------------

    def _current_net_qty(self, instrument_id) -> float:
        """Return absolute net position quantity for the instrument.

        Uses `self.cache.positions_open()` which returns the list of
        currently open positions in the netting OMS. Returns 0.0 when flat.
        """
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        total = sum(float(str(p.quantity)) for p in open_positions)
        return total

    # ------------------------------------------------------------------
    # EMA update + read
    # ------------------------------------------------------------------

    def _update_ema(self, instrument_id, bid_size: float, ask_size: float) -> None:
        """Update the per-instrument EMA imbalance from one quote tick.

        Skip the update when total size is below min_total_size — too thin
        to be a meaningful signal. The EMA effectively pauses on thin
        ticks and resumes from its last value when a normal tick arrives.
        """
        total = bid_size + ask_size
        if total < self._min_total_size or total <= 0.0:
            return

        imbalance = bid_size / total
        key = str(instrument_id)
        prev = self._ema_imbalance.get(key)
        if prev is None:
            # First valid reading: seed with the observation itself
            # (avoids imposing a 0.5 neutral prior).
            self._ema_imbalance[key] = imbalance
        else:
            self._ema_imbalance[key] = (
                self._ema_alpha * imbalance + (1.0 - self._ema_alpha) * prev
            )

    def _ema_is_adverse(self, order) -> bool:
        """Return True if the per-instrument EMA imbalance is adverse to
        the order direction.

        Returns False (do not skip) when:
          - EMA not yet seeded for this instrument (warm-up).
        """
        key = str(order.instrument_id)
        ema = self._ema_imbalance.get(key)
        if ema is None:
            return False

        if order.side == OrderSide.BUY:
            if ema < self._skip_threshold:
                self.log.debug(
                    f"BUY adverse EMA imbalance: ema={ema:.3f} < "
                    f"threshold={self._skip_threshold:.3f}; SKIP."
                )
                return True
        else:  # SELL
            adverse_threshold = 1.0 - self._skip_threshold
            if ema > adverse_threshold:
                self.log.debug(
                    f"SELL adverse EMA imbalance: ema={ema:.3f} > "
                    f"threshold={adverse_threshold:.3f}; SKIP."
                )
                return True

        return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip via position-tier + EMA-imbalance gates."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # --- Positional gate ------------------------------------------
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty >= self._position_cap:
            self.log.debug(
                f"SKIP {order.client_order_id} — position cap reached "
                f"(net_qty={net_qty:.1f} >= cap={self._position_cap})."
            )
            return

        # --- EMA-smoothed imbalance gate ------------------------------
        if self._ema_is_adverse(order):
            side = "BUY" if order.side == OrderSide.BUY else "SELL"
            self.log.info(
                f"SKIP {order.client_order_id} — adverse EMA imbalance "
                f"(side={side})."
            )
            return

        # Both gates pass — submit.
        self.log.debug(
            f"SUBMIT {order.client_order_id} — both gates passed "
            f"(net_qty={net_qty:.1f})."
        )
        self.submit_order(order)

    # ------------------------------------------------------------------
    # Quote tick handler
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        """Update the per-instrument EMA imbalance from each new quote tick."""
        try:
            bid_size = float(str(tick.bid_size))
            ask_size = float(str(tick.ask_size))
        except Exception:
            return
        self._update_ema(tick.instrument_id, bid_size, ask_size)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    skip_threshold: float = 0.40,
    min_total_size: float = 2.0,
    ema_alpha: float = 0.30,
) -> PositionTierImbalanceEmaGateAlgorithm:
    """Instantiate and return the PositionTierImbalanceEmaGateAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    position_cap : int
        Maximum absolute net position (contracts) before skipping new opens.
        Default 1.
    skip_threshold : float
        EMA-imbalance threshold for the gate. Default 0.40.
    min_total_size : float
        Minimum bid_size + ask_size before a quote contributes to the EMA
        and the gate fires. Default 2.0.
    ema_alpha : float
        EMA smoothing factor in (0, 1]. Default 0.30.
    """
    config = PositionTierImbalanceEmaGateConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        skip_threshold=skip_threshold,
        min_total_size=min_total_size,
        ema_alpha=ema_alpha,
    )
    return PositionTierImbalanceEmaGateAlgorithm(config=config)
