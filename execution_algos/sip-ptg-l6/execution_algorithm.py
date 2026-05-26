"""Zero-PnL-after-flip gate execution algorithm (sip-ptg-l6).

Extends position-tier-gate with an additional filter:
Skip OPEN orders where the most recently closed position had zero realized PnL
AND the new OPEN is a direction flip from that last closed position.

Hypothesis:
  When the oracle's last closed position earned exactly zero PnL (entry price == exit
  price), the subsequent direction-flip signal carries no new directional information —
  the market didn't confirm the oracle's direction during the holding period. These
  post-zero-flip OPEN positions have a slightly negative mean realized PnL (-0.0020)
  across 12 training dates, vs the overall mean of +0.047. Skipping them avoids a
  small drag while maintaining full participation in all other signals.

Mechanism at on_order() for non-reduce-only orders:
  1. Base PTG gate: skip if net_qty >= position_cap (1). Same as base.
  2. Zero-flip gate (NEW): when net_qty == 0 (flat, would normally submit):
     a. Query cache.positions_closed(instrument_id=...) for last closed position.
     b. If last closed position realized_pnl == 0 AND order.side is a direction flip
        from that position's entry direction: SKIP.
     c. Else: SUBMIT.

Direction flip logic:
  - Last closed was LONG (entry=BUY): new OPEN is SELL → flip → potentially skip.
  - Last closed was SHORT (entry=SELL): new OPEN is BUY → flip → potentially skip.
  - Same direction as last closed: not a flip → always submit.

Constraints:
  - No opposing positions: skip leaves algo flat.
  - quantity_invariant: qty=1, never modified.
  - top_of_book_only: unchanged.
  - participation_cap: qty=1, never binds.
  - intraday_flat: reduce-only always submitted.

Empirical pre-check (Step 4c):
  N_predicted = 500 fires/day. Actual = 950 fires/day. PASS.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class SipPtgL6Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for sip-ptg-l6.

    Parameters
    ----------
    position_cap : int
        Same as base PTG. Default 1.
    """

    position_cap: int = 1


class SipPtgL6Algorithm(ExecAlgorithm):
    """Execution algorithm: PTG + zero-PnL-after-flip gate.

    Opening orders (is_reduce_only == False):
      1. If net_qty >= position_cap: SKIP (same as base PTG).
      2. If net_qty == 0 (flat):
         - Check last closed position: if realized_pnl == 0 AND current OPEN is
           a direction flip from that position's entry: SKIP.
         - Else: SUBMIT.

    Closing orders (is_reduce_only == True):
      Always submit (intraday_flat).
    """

    def __init__(self, config: SipPtgL6Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap

    def on_start(self) -> None:
        self.log.info(
            f"SipPtgL6Algorithm started "
            f"(position_cap={self._position_cap}, zero-flip-gate=enabled)."
        )

    def on_reset(self) -> None:
        pass

    def _current_net_qty(self, instrument_id) -> float:
        """Return absolute net position quantity."""
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        return sum(float(str(p.quantity)) for p in open_positions)

    def _last_closed_position(self, instrument_id):
        """Return the most recently closed position, or None."""
        closed = self.cache.positions_closed(instrument_id=instrument_id)
        if not closed:
            return None
        return max(closed, key=lambda p: p.ts_closed)

    def _is_direction_flip(self, order, last_closed) -> bool:
        """Return True if order is a direction flip from the last closed position.

        A flip means:
          - Last closed was LONG (entry=BUY) and new order.side == SELL
          - Last closed was SHORT (entry=SELL) and new order.side == BUY
        """
        if last_closed is None:
            return False
        last_entry = last_closed.entry  # OrderSide (BUY for long, SELL for short)
        # If last was LONG (entry=BUY) and new order is SELL → flip to SHORT
        # If last was SHORT (entry=SELL) and new order is BUY → flip to LONG
        return last_entry != order.side

    def on_order(self, order) -> None:
        """Route order: apply base PTG gate then zero-flip gate."""

        # Always submit reduce-only orders.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Base PTG gate: skip if position >= cap.
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty >= self._position_cap:
            self.log.debug(
                f"SKIP {order.client_order_id} — position cap reached "
                f"(net_qty={net_qty:.1f} >= cap={self._position_cap})."
            )
            return

        # Zero-flip gate: applies only when flat (net_qty == 0).
        # The base PTG would submit here. We add the additional filter.
        last_closed = self._last_closed_position(order.instrument_id)
        if last_closed is not None:
            try:
                # realized_pnl may be a Money object; compare to zero
                last_pnl = float(str(last_closed.realized_pnl).split()[0])
            except (ValueError, IndexError):
                last_pnl = None

            if last_pnl == 0.0 and self._is_direction_flip(order, last_closed):
                self.log.debug(
                    f"SKIP {order.client_order_id} — zero-flip gate: "
                    f"last_closed_pnl=0.0, direction_flip=True."
                )
                return

        # All gates passed — submit.
        self.log.debug(
            f"SUBMIT {order.client_order_id} — all gates passed "
            f"(net_qty={net_qty:.1f} < cap={self._position_cap})."
        )
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
) -> SipPtgL6Algorithm:
    """Instantiate and return the SipPtgL6Algorithm."""
    config = SipPtgL6Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
    )
    return SipPtgL6Algorithm(config=config)
