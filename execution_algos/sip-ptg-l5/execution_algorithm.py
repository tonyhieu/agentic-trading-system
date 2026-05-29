"""Position-tier-gate with position_cap=2 execution algorithm (sip-ptg-l5).

Modification: position_cap increased from 1 (base PTG default) to 2.

Hypothesis:
  The base PTG with cap=1 skips ALL OPEN legs of CLOSE+OPEN pairs because the
  cache shows the old position (net_qty=1) when the OPEN is evaluated at the same
  ts_init. These skipped OPENs (direction-flip trades) have a mean realized PnL
  of +$0.0151 per position (from static analysis of baseline artifacts: 44,124
  flip positions earned $667.25 total across 12 training dates). Increasing the
  cap to 2 allows these paired OPENs to submit, adding profitable trades.

Mechanism:
  - position_cap = 2 (changed from default of 1)
  - Standalone OPENs (when flat, net_qty=0): 0 < 2 → submit (unchanged)
  - Paired OPENs (net_qty=1 from existing position): 1 < 2 → submit (NEW)
  - Third OPEN while net_qty=2: 2 >= 2 → skip (cap maintained)
  - Reduce-only CLOSE orders: always submit (intraday_flat compliance)

Constraints:
  - quantity_invariant: qty always 1, never modified
  - top_of_book_only: submits at ask_px/bid_px, no book walking
  - participation_cap: qty=1, never binds (confirmed from data)
  - intraday_flat: reduce-only orders always submitted

Empirical pre-check (Step 4c):
  N_predicted = 7,000 fires/day. Actual = 7,535 fires/day. PASS.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class SipPtgL5Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for sip-ptg-l5: position-tier-gate with cap=2.

    Parameters
    ----------
    position_cap : int
        Maximum absolute net position size (in contracts) at which new
        open-leg orders are still allowed. Default 2 (vs base PTG default of 1).
        With cap=2: allows paired OPENs to fire when net_qty=1.
    """

    position_cap: int = 2


class SipPtgL5Algorithm(ExecAlgorithm):
    """Execution algorithm: position-tier-gate with cap=2.

    Opening orders (is_reduce_only == False):
      - Query current absolute net position for the instrument.
      - If net_qty >= position_cap (2): SKIP.
      - Else: SUBMIT.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    Identical to position-tier-gate except position_cap defaults to 2 instead of 1.
    """

    def __init__(self, config: SipPtgL5Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap

    def on_start(self) -> None:
        self.log.info(
            f"SipPtgL5Algorithm started "
            f"(position_cap={self._position_cap} contracts)."
        )

    def on_reset(self) -> None:
        pass

    def _current_net_qty(self, instrument_id) -> float:
        """Return absolute net position quantity for the instrument."""
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        total = sum(float(str(p.quantity)) for p in open_positions)
        return total

    def on_order(self, order) -> None:
        """Route order: submit or skip based on current portfolio exposure."""

        # Reduce-only (close) orders always execute.
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
            return

        # Position is below the cap — submit.
        self.log.debug(
            f"SUBMIT {order.client_order_id} — position below cap "
            f"(net_qty={net_qty:.1f} < cap={self._position_cap})."
        )
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 2,
) -> SipPtgL5Algorithm:
    """Instantiate and return the SipPtgL5Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    position_cap : int
        Maximum absolute net position (contracts) before skipping new open legs.
        Default 2 contracts (vs base PTG default of 1).
    """
    config = SipPtgL5Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
    )
    return SipPtgL5Algorithm(config=config)
