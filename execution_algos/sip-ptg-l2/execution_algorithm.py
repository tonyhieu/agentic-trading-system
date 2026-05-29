"""sip-ptg-l2 execution algorithm.

Position-tier gate + pre-submit spread guard.

Hypothesis (see NOTES.md):
  The base `position-tier-gate` filters by portfolio state only — it treats
  every OPEN that passes the position gate identically, regardless of the
  current market environment. Empirical analysis of the base's own positions
  across the 12 train dates shows that positions whose fill price was outside
  +/- 1 tick of the arrival mid (i.e., the top-of-book spread at on_order()
  time was wider than one minimum tick) collectively LOSE money: 10,785 such
  positions yield -$1,017.25 total PnL (mean -$0.094 per position).

  This algorithm adds a pre-submit spread guard layered on top of the base
  gate: when the current top-of-book spread at on_order() time exceeds a
  threshold (default 0.25 USD = 1 MES tick), skip the OPEN. Reduce-only
  (close) orders bypass the guard unconditionally (intraday_flat).

Constraints:
  - Quantity invariant: only skips/submits, never changes quantity.
  - top_of_book_only: never walks the book.
  - participation_cap: unchanged from base.
  - intraday_flat: reduce-only orders always submit unconditionally.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class SipPtgL2Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for sip-ptg-l2.

    Parameters
    ----------
    position_cap : int
        Inherited from base `position-tier-gate`. Skip OPEN orders when
        absolute net position >= position_cap. Default 1.
    spread_threshold : float
        Top-of-book spread (USD) above which OPEN orders are skipped.
        Default 0.25 USD = 1 MES tick (strict: skip when spread > 1 tick).
    """

    position_cap: int = 1
    spread_threshold: float = 0.25


class SipPtgL2Algorithm(ExecAlgorithm):
    """Position-tier gate + pre-submit spread guard.

    Order routing:
      - Reduce-only: submit unconditionally.
      - OPEN with net_qty >= position_cap: skip (base gate).
      - OPEN with current spread > spread_threshold: skip (new guard).
      - Otherwise: submit.

    The spread is read from `self.cache.quote_tick(instrument_id)`. If no
    quote is in the cache (start of session before first quote tick is
    processed), the algorithm fails OPEN -- submit the order rather than
    block on missing data.

    No order quantity modification -- quantity invariant preserved.
    No book walking -- top-of-book-only preserved.
    """

    def __init__(self, config: SipPtgL2Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        self._spread_threshold: float = config.spread_threshold

    def on_start(self) -> None:
        self.log.info(
            f"SipPtgL2Algorithm started "
            f"(position_cap={self._position_cap} contracts, "
            f"spread_threshold={self._spread_threshold} USD)."
        )

    def on_reset(self) -> None:
        pass  # No mutable state -- all conditioning lives in the cache.

    def _current_net_qty(self, instrument_id) -> float:
        """Return absolute net position quantity for the instrument."""
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        total = sum(float(str(p.quantity)) for p in open_positions)
        return total

    def _current_spread(self, instrument_id) -> float | None:
        """Return top-of-book spread (USD) from the latest cached quote tick.

        Returns None when the cache has no quote yet for the instrument
        (start-of-session edge case). Callers treat None as "spread unknown
        -- do not block."
        """
        quote = self.cache.quote_tick(instrument_id)
        if quote is None:
            return None
        try:
            ask = float(quote.ask_price)
            bid = float(quote.bid_price)
        except (AttributeError, TypeError, ValueError):
            return None
        spread = ask - bid
        if spread < 0:
            return None  # Crossed book -- treat as unknown.
        return spread

    def on_order(self, order) -> None:
        """Route order: submit or skip based on portfolio state + book spread."""

        # Reduce-only orders bypass all gates (intraday_flat compliance).
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Base gate: skip OPEN while a position is already in flight in the cache.
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty >= self._position_cap:
            self.log.debug(
                f"SKIP {order.client_order_id} -- position cap reached "
                f"(net_qty={net_qty:.1f} >= cap={self._position_cap})."
            )
            return

        # New guard: skip OPEN when the top-of-book spread is wider than threshold.
        spread = self._current_spread(order.instrument_id)
        if spread is not None and spread > self._spread_threshold:
            self.log.debug(
                f"SKIP {order.client_order_id} -- wide spread "
                f"(spread={spread:.4f} > threshold={self._spread_threshold:.4f})."
            )
            return

        # Both gates pass -- submit.
        self.log.debug(
            f"SUBMIT {order.client_order_id} -- flat & tight book "
            f"(net_qty={net_qty:.1f}, spread={spread})."
        )
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    spread_threshold: float = 0.25,
) -> SipPtgL2Algorithm:
    """Instantiate and return the SipPtgL2Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    position_cap : int
        Maximum absolute net position (contracts) before skipping new
        open-leg orders. Default 1.
    spread_threshold : float
        Top-of-book spread (USD) above which OPEN orders are skipped.
        Default 0.25 USD (1 MES minimum tick).
    """
    config = SipPtgL2Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        spread_threshold=spread_threshold,
    )
    return SipPtgL2Algorithm(config=config)
