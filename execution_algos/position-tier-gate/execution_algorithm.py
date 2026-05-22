"""Position-tier-gate execution algorithm.

Conditions the OPEN leg of each oracle signal on the current net portfolio
position size. If the absolute net quantity already at or above `position_cap`
contracts, the open-leg order is skipped. Reduce-only / position-closing
orders always execute unconditionally.

Hypothesis:
  The oracle signal has noise (sigma=5) and fires at 1-second intervals.
  Multiple concurrent open legs compound directional error: if the signal
  is wrong, a larger gross position amplifies the loss. Capping at a small
  number of contracts (default 2) limits this compounding effect while
  still allowing the initial entry (which carries the most directional
  information) to execute.

Algorithm:
  - At each `on_order()` call:
    - If `order.is_reduce_only`: submit unconditionally (intraday_flat).
    - Otherwise: query `self.cache.positions_open(instrument_id=...)`.
      Compute net_qty = sum of absolute quantities across open positions.
      If net_qty >= position_cap: SKIP (do not submit).
      Else: SUBMIT.

No look-ahead: `self.cache` at `on_order()` time reflects fills that have
already been processed by the engine (strictly in the past relative to the
order's ts_init). The current order has not yet been submitted — there is
no future information.

No quantity modification: quantity invariant always preserved.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PositionTierGateConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the position-tier-gate execution algorithm.

    Parameters
    ----------
    position_cap : int
        Maximum absolute net position size (in contracts) at which new
        open-leg orders are still allowed. When the current net qty >=
        position_cap, the open leg is skipped.
        Default 1: skip all new opens while any position is already open.
        This enforces serialized entry — each oracle entry must close before
        the next can open. The oracle fires simultaneous CLOSE+OPEN at the
        same timestamp; because the cache reflects the pre-fill state (old
        position still showing), cap=1 reliably blocks the concurrent OPEN.
    """

    position_cap: int = 1


class PositionTierGateAlgorithm(ExecAlgorithm):
    """Execution algorithm that gates open orders on current portfolio exposure.

    Opening orders (is_reduce_only == False):
      - Query current absolute net position for the instrument.
      - If net_qty >= position_cap: SKIP.
      - Else: SUBMIT.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance, exposure
        reduction is always allowed).

    No order quantity is ever modified. Quantity invariant always preserved.
    """

    def __init__(self, config: PositionTierGateConfig) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"PositionTierGateAlgorithm started "
            f"(position_cap={self._position_cap} contracts)."
        )

    def on_reset(self) -> None:
        pass  # No mutable state to reset — position info comes from cache.

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _current_net_qty(self, instrument_id) -> float:
        """Return absolute net position quantity for the instrument.

        Uses self.cache.positions_open() which returns the list of currently
        open positions in the netting OMS (at most one per instrument).
        Returns 0.0 when flat (no open positions).
        """
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        # Netting OMS: typically one position per instrument.
        # Sum absolute quantities defensively (handles any edge case).
        total = sum(float(str(p.quantity)) for p in open_positions)
        return total

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on current portfolio exposure."""

        # Reduce-only (close) orders always execute — intraday_flat compliance,
        # and they reduce exposure rather than adding to it.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Query current position for this instrument.
        net_qty = self._current_net_qty(order.instrument_id)

        if net_qty >= self._position_cap:
            self.log.debug(
                f"SKIP {order.client_order_id} — position cap reached "
                f"(net_qty={net_qty:.1f} >= cap={self._position_cap})."
            )
            # Do NOT call submit_order — quantity invariant preserved.
            return

        # Position is below the cap — submit.
        self.log.debug(
            f"SUBMIT {order.client_order_id} — position below cap "
            f"(net_qty={net_qty:.1f} < cap={self._position_cap})."
        )
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
) -> PositionTierGateAlgorithm:
    """Instantiate and return the PositionTierGateAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    position_cap : int
        Maximum absolute net position (contracts) before skipping new open legs.
        Default 1 contract (skip all opens while any position is already open).
    """
    config = PositionTierGateConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
    )
    return PositionTierGateAlgorithm(config=config)
