"""sip-ptg-l4 execution algorithm.

Position-tier gate with a LOSS-CORRECTIVE OVERRIDE.

Hypothesis (see NOTES.md):
  The base `position-tier-gate` unconditionally skips OPEN orders at
  same-`ts_init` flip moments (when the cache shows the in-flight
  position still open at flip time). The base treats every flip
  identically, regardless of whether the in-flight position is winning
  or losing.

  This algorithm OVERRIDES the base skip when the in-flight position is
  currently UNDERWATER by more than 1 MES tick ($0.25 per contract) at
  the flip moment. The reasoning: a flip that arrives while the prior
  position is losing money means the price has already moved against the
  prior direction; the new opposite-side OPEN is corrective. By contrast,
  flips arriving while the prior position is profitable or near-flat are
  more likely noise reversals; preserve the base skip there.

  Conditioning axis: SIGN AND MAGNITUDE of in-flight unrealized PnL per
  contract at on_order() time. This is a portfolio-state + market-state
  HYBRID axis — different from loops 2/3 (both spread-only axes).

Constraints:
  - Quantity invariant: only skips/submits, never changes quantity.
  - top_of_book_only: never walks the book.
  - participation_cap: order quantity is unchanged from strategy emission.
  - intraday_flat: reduce-only orders always submit unconditionally.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import PositionSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class SipPtgL4Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for sip-ptg-l4.

    Parameters
    ----------
    position_cap : int
        Inherited from base `position-tier-gate`. Without the override,
        OPEN orders are skipped when absolute net position >= position_cap.
        Default 1.
    loss_threshold : float
        Magnitude (USD per contract) of in-flight unrealized loss above
        which a base-would-skip OPEN is OVERRIDDEN (submitted instead of
        skipped). Default 0.25 USD = 1 MES minimum tick. The override
        fires when `unrealized_per_contract < -loss_threshold`.
    """

    position_cap: int = 1
    loss_threshold: float = 0.25


class SipPtgL4Algorithm(ExecAlgorithm):
    """Position-tier gate with loss-corrective override.

    Order routing:
      - Reduce-only: submit unconditionally.
      - OPEN with net_qty < position_cap: submit (base behavior).
      - OPEN with net_qty >= position_cap:
          - If quote unavailable OR positions list empty: skip (preserve
            base — fail closed on missing data).
          - If in-flight unrealized PnL per contract < -loss_threshold:
            OVERRIDE -> submit (corrective re-entry).
          - Otherwise: skip (preserve base).

    The mid is computed from `self.cache.quote_tick(instrument_id)` as
    (ask + bid) / 2. The in-flight entry price is `position.avg_px_open`.
    Sign-adjusted unrealized PnL per contract is
    `(mid - entry) * side_factor` where side_factor = +1 for LONG, -1
    for SHORT.

    No order quantity modification — quantity invariant preserved.
    No book walking — top-of-book-only preserved.
    """

    def __init__(self, config: SipPtgL4Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        self._loss_threshold: float = config.loss_threshold

    def on_start(self) -> None:
        self.log.info(
            f"SipPtgL4Algorithm started "
            f"(position_cap={self._position_cap} contracts, "
            f"loss_threshold={self._loss_threshold} USD/contract)."
        )

    def on_reset(self) -> None:
        pass  # No mutable state — all conditioning lives in the cache.

    def _current_net_qty(self, instrument_id) -> float:
        """Return absolute net position quantity for the instrument."""
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        total = sum(float(str(p.quantity)) for p in open_positions)
        return total

    def _in_flight_unrealized_per_contract(self, instrument_id) -> float | None:
        """Return sign-adjusted unrealized PnL per contract for the
        currently in-flight position, or None if undefined.

        Computed as (mid - avg_px_open) * side_factor where side_factor =
        +1 for LONG positions and -1 for SHORT positions. Returns None
        when:
          - no positions are open (caller should treat as base-submit
            branch — this method is only called when net_qty >= cap),
          - no quote tick is in the cache (start-of-session),
          - the quote has bid > ask (crossed book).
        Callers treat None as "data unavailable -> preserve base skip."
        """
        positions = self.cache.positions_open(instrument_id=instrument_id)
        if not positions:
            return None  # Caller guarantees cap-check passed; this is defensive.
        pos = positions[0]  # Netting OMS: at most one position per instrument.

        quote = self.cache.quote_tick(instrument_id)
        if quote is None:
            return None
        try:
            ask = float(quote.ask_price)
            bid = float(quote.bid_price)
            entry = float(pos.avg_px_open)
        except (AttributeError, TypeError, ValueError):
            return None
        if ask < bid:
            return None  # Crossed book — treat as unavailable.

        mid = (ask + bid) / 2.0
        if pos.side == PositionSide.LONG:
            return mid - entry
        if pos.side == PositionSide.SHORT:
            return entry - mid
        return None  # FLAT or unknown side — defensive.

    def on_order(self, order) -> None:
        """Route order: submit or skip based on portfolio state + loss override."""

        # Reduce-only orders bypass all gates (intraday_flat compliance).
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Base submit branch: cache shows below cap.
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty < self._position_cap:
            self.log.debug(
                f"SUBMIT {order.client_order_id} — position below cap "
                f"(net_qty={net_qty:.1f} < cap={self._position_cap})."
            )
            self.submit_order(order)
            return

        # Base would skip (net_qty >= position_cap). Check loss-corrective override.
        unrealized = self._in_flight_unrealized_per_contract(order.instrument_id)
        if unrealized is not None and unrealized < -self._loss_threshold:
            self.log.debug(
                f"OVERRIDE-SUBMIT {order.client_order_id} — in-flight underwater "
                f"(unrealized={unrealized:.4f} < -threshold={-self._loss_threshold:.4f}, "
                f"net_qty={net_qty:.1f})."
            )
            self.submit_order(order)
            return

        # Default: preserve base skip.
        self.log.debug(
            f"SKIP {order.client_order_id} — position cap reached and "
            f"in-flight not sufficiently underwater "
            f"(net_qty={net_qty:.1f}, unrealized={unrealized})."
        )
        return


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    loss_threshold: float = 0.25,
) -> SipPtgL4Algorithm:
    """Instantiate and return the SipPtgL4Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    position_cap : int
        Maximum absolute net position (contracts) before triggering the
        base's skip rule on new OPEN orders. Default 1.
    loss_threshold : float
        Magnitude (USD per contract) of in-flight unrealized loss above
        which a base-would-skip OPEN is overridden and submitted instead.
        Default 0.25 USD = 1 MES tick.
    """
    config = SipPtgL4Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        loss_threshold=loss_threshold,
    )
    return SipPtgL4Algorithm(config=config)
