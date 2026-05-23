"""Position-tier + book-imbalance gate execution algorithm.

Stacks two gates on the OPEN leg of each oracle signal:

  1. Positional gate (inherited from `position-tier-gate`, position_cap=1):
     skip the open leg when the current absolute net position is at or above
     `position_cap` contracts. The netting OMS reports the concurrent
     CLOSE+OPEN pair sequentially, so cap=1 reliably blocks the doubled-up
     entry that would otherwise compound directional error on noisy oracle.
  2. Top-of-book imbalance gate (new): on flat-entry orders that pass the
     positional gate, additionally skip when the top-of-book imbalance is
     adverse to the order direction:

         imbalance = bid_size / (bid_size + ask_size)        in [0, 1]

         BUY  order: SKIP when imbalance < skip_threshold
                     (asks dominate — adverse to buying)
         SELL order: SKIP when imbalance > 1 - skip_threshold
                     (bids dominate — adverse to selling)

     Skipped when total top-of-book size is below `min_total_size`
     (thin-book guard — too noisy a signal).

Reduce-only (position-closing) orders always execute unconditionally so
intraday_flat is never violated and exposure can always be reduced.

No look-ahead: the positional gate reads `self.cache.positions_open()` and
the imbalance gate reads `self.cache.quote_tick()`. Both reflect events
strictly in the past relative to the order's ts_init at on_order() time.

No quantity modification: quantity invariant always preserved — orders are
either submitted intact or skipped entirely.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PositionTierImbalanceGateConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the position-tier + imbalance gate algorithm.

    Parameters
    ----------
    position_cap : int
        Maximum absolute net position size (contracts) at which new open-leg
        orders are still allowed. When the current net qty >= position_cap,
        the open leg is gated.  Default 1 — the tightest integer gate, which
        blocks all cascade opens while flat positions can always enter.
    skip_threshold : float
        Top-of-book imbalance threshold for the imbalance gate. Imbalance
        is defined as `bid_size / (bid_size + ask_size)` in [0, 1].
        For BUY  orders: SKIP when imbalance <  skip_threshold       (asks dominate).
        For SELL orders: SKIP when imbalance > 1 - skip_threshold    (bids dominate).
        Default 0.40 — moderate; skips entries where the book leans
        materially against the order direction (asks have >= 60% share
        for a BUY, bids have >= 60% share for a SELL).
    min_total_size : float
        Activate the imbalance gate only when bid_size + ask_size >=
        min_total_size. Below this, the book is too thin to read a
        meaningful imbalance signal; treat as neutral (do not skip).
        Default 2.0 contracts.
    """

    position_cap: int = 1
    skip_threshold: float = 0.40
    min_total_size: float = 2.0


class PositionTierImbalanceGateAlgorithm(ExecAlgorithm):
    """Execution algorithm: position-tier gate + top-of-book imbalance filter.

    Opening orders (is_reduce_only == False):
      - If current absolute net position >= position_cap: SKIP (gated by
        positional cap).
      - Else, read top-of-book imbalance from the latest quote in cache:
          imbalance = bid_size / (bid_size + ask_size)
          BUY:  SKIP when imbalance <      skip_threshold
          SELL: SKIP when imbalance > 1 -  skip_threshold
        Skip is suppressed (treated as neutral) when total size <
        min_total_size, or when no quote is available yet.
      - Otherwise: SUBMIT.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is ever modified. Quantity invariant always preserved.
    """

    def __init__(self, config: PositionTierImbalanceGateConfig) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        self._skip_threshold: float = config.skip_threshold
        self._min_total_size: float = config.min_total_size

        # Subscription tracking (need quote ticks for imbalance signal)
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"PositionTierImbalanceGateAlgorithm started "
            f"(position_cap={self._position_cap}, "
            f"skip_threshold={self._skip_threshold:.2f}, "
            f"min_total_size={self._min_total_size:.1f})."
        )

    def on_reset(self) -> None:
        self._subscribed.clear()

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

        Uses self.cache.positions_open() which returns the list of currently
        open positions in the netting OMS. Returns 0.0 when flat.
        """
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        total = sum(float(str(p.quantity)) for p in open_positions)
        return total

    # ------------------------------------------------------------------
    # Imbalance evaluator
    # ------------------------------------------------------------------

    def _imbalance_is_adverse(self, order, quote) -> bool:
        """Return True if top-of-book imbalance is adverse to order direction.

        BUY  order: adverse when imbalance <  skip_threshold       (asks dominate)
        SELL order: adverse when imbalance > 1 - skip_threshold    (bids dominate)

        Returns False (do not skip) when:
          - quote is None (warm-up; no fresh quote in cache)
          - bid_size + ask_size < min_total_size (thin book — noisy signal)
        """
        if quote is None:
            return False

        try:
            bid_size = float(str(quote.bid_size))
            ask_size = float(str(quote.ask_size))
        except Exception:
            return False

        total = bid_size + ask_size
        if total < self._min_total_size or total <= 0.0:
            return False

        imbalance = bid_size / total

        if order.side == OrderSide.BUY:
            if imbalance < self._skip_threshold:
                self.log.debug(
                    f"BUY adverse imbalance: imb={imbalance:.3f} < "
                    f"threshold={self._skip_threshold:.3f}; SKIP."
                )
                return True
        else:  # SELL
            adverse_threshold = 1.0 - self._skip_threshold
            if imbalance > adverse_threshold:
                self.log.debug(
                    f"SELL adverse imbalance: imb={imbalance:.3f} > "
                    f"threshold={adverse_threshold:.3f}; SKIP."
                )
                return True

        return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip via position-tier + imbalance gates."""
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

        # --- Top-of-book imbalance gate -------------------------------
        quote = self.cache.quote_tick(order.instrument_id)
        if self._imbalance_is_adverse(order, quote):
            side = "BUY" if order.side == OrderSide.BUY else "SELL"
            self.log.info(
                f"SKIP {order.client_order_id} — adverse book imbalance "
                f"(side={side})."
            )
            return

        # Both gates pass — submit.
        self.log.debug(
            f"SUBMIT {order.client_order_id} — both gates passed "
            f"(net_qty={net_qty:.1f})."
        )
        self.submit_order(order)

    def on_quote_tick(self, tick) -> None:
        """Receive quote ticks — no state to update (read directly from cache)."""
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    skip_threshold: float = 0.40,
    min_total_size: float = 2.0,
) -> PositionTierImbalanceGateAlgorithm:
    """Instantiate and return the PositionTierImbalanceGateAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    position_cap : int
        Maximum absolute net position (contracts) before skipping new opens.
        Default 1.
    skip_threshold : float
        Top-of-book imbalance threshold for the imbalance gate. Default 0.40.
    min_total_size : float
        Minimum total top-of-book size before the imbalance gate activates.
        Default 2.0.
    """
    config = PositionTierImbalanceGateConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        skip_threshold=skip_threshold,
        min_total_size=min_total_size,
    )
    return PositionTierImbalanceGateAlgorithm(config=config)
