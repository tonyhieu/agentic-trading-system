"""ptg-m-l4 execution algorithm.

Per-iteration experiment loop-4 variant of `position-tier-gate`
(context mode: metrics-only).

Copied mechanically from `ptg-m-l3`. Routes the OPEN leg of each oracle
signal through a single positional gate; the post-open cooldown gate
present in ptg-m-l2/l3 has been removed.

  1. Positional gate (inherited from `position-tier-gate`):
     skip the open leg when the current absolute net position is at or
     above `position_cap` contracts.

Reduce-only (position-closing) orders always execute unconditionally so
intraday_flat is never violated and exposure can always be reduced.

Change vs ptg-m-l3 (see NOTES.md):
  The prior loops show a monotone link between trade_count and
  pnl_vs_base — every throttle that removed opens lost P&L. This loop
  removes the cooldown gate entirely and raises `position_cap` so the
  positional gate also stops discarding opens, restoring the full
  open-order flow back toward the base trade count.

No look-ahead: the positional gate reads `self.cache.positions_open()`,
which at `on_order()` time reflects only already-processed fills — never
future information.

No quantity modification: quantity invariant always preserved — orders are
either submitted intact or skipped entirely.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PtgML4Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the ptg-m-l4 execution algorithm.

    Parameters
    ----------
    position_cap : int
        Maximum absolute net position size (contracts) at which new open-leg
        orders are still allowed. When current net qty >= position_cap, the
        open leg is skipped. Default 5 — relaxed relative to the loop-3
        setting (1) so the positional gate rarely fires and the full
        open-order flow is restored.
    """

    position_cap: int = 5


class PtgML4Algorithm(ExecAlgorithm):
    """Execution algorithm gating open orders on exposure only.

    Opening orders (is_reduce_only == False):
      - If current absolute net position >= position_cap: SKIP.
      - Else: SUBMIT.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is ever modified. Quantity invariant always preserved.
    """

    def __init__(self, config: PtgML4Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"PtgML4Algorithm started "
            f"(position_cap={self._position_cap} contracts)."
        )

    def on_reset(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Helpers
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
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on exposure only."""

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

        # Gate passed — submit.
        self.log.debug(
            f"SUBMIT {order.client_order_id} — gate passed "
            f"(net_qty={net_qty:.1f} < cap={self._position_cap})."
        )
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 5,
) -> PtgML4Algorithm:
    """Instantiate and return the PtgML4Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    position_cap : int
        Maximum absolute net position (contracts) before skipping new opens.
    """
    config = PtgML4Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
    )
    return PtgML4Algorithm(config=config)
