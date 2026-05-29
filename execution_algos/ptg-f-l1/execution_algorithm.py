"""ptg-f-l1 execution algorithm.

Per-iteration experiment, base_algo `position-tier-gate`, context mode
`full-trace`, loop 1. Starting point: `position-tier-gate` base algo.

Single behavioural change vs base:
  **position_cap: 1 (base) -> 2 (loop 1).**

The base algo serializes entries by skipping all open-leg orders when any
position is already open (cap=1). Loop 1 asks whether allowing one additional
concurrent position (cap=2) captures more of the oracle's directional signal
when the oracle fires multiple same-direction signals in quick succession.

All other behaviours preserved unchanged:
- Reduce-only (close) orders always execute.
- Net position queried from self.cache.positions_open().
- Quantity invariant preserved (orders submitted or skipped whole).
- No look-ahead: cache reflects pre-fill state at decision time.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PositionTierGateL1Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for ptg-f-l1.

    Parameters
    ----------
    position_cap : int
        Maximum absolute net position size (in contracts) at which new
        open-leg orders are still allowed. When the current net qty >=
        position_cap, the open leg is skipped.
        Default 2 (loop 1 treatment): allows up to 2 concurrent open
        contracts before gating. The base algo uses cap=1 (serialized entry).
    """

    position_cap: int = 2


class PositionTierGateL1Algorithm(ExecAlgorithm):
    """Position-tier gate with cap=2 (one additional concurrent position vs base cap=1).

    Opening orders (is_reduce_only == False):
      - Query current absolute net position for the instrument.
      - If net_qty >= position_cap (default 2): SKIP.
      - Else: SUBMIT.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is ever modified. Quantity invariant always preserved.
    """

    def __init__(self, config: PositionTierGateL1Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap

    def on_start(self) -> None:
        self.log.info(
            f"PositionTierGateL1Algorithm started "
            f"(position_cap={self._position_cap} contracts)."
        )

    def on_reset(self) -> None:
        pass

    def _current_net_qty(self, instrument_id) -> float:
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        return sum(float(str(p.quantity)) for p in open_positions)

    def on_order(self, order) -> None:
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        net_qty = self._current_net_qty(order.instrument_id)

        if net_qty >= self._position_cap:
            self.log.debug(
                f"SKIP {order.client_order_id} — position cap reached "
                f"(net_qty={net_qty:.1f} >= cap={self._position_cap})."
            )
            return

        self.log.debug(
            f"SUBMIT {order.client_order_id} — position below cap "
            f"(net_qty={net_qty:.1f} < cap={self._position_cap})."
        )
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 2,
) -> PositionTierGateL1Algorithm:
    """Instantiate and return the PositionTierGateL1Algorithm."""
    config = PositionTierGateL1Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
    )
    return PositionTierGateL1Algorithm(config=config)
