"""ptg-f-l5: directional-aware position cap.

Only skip opens that would ADD to position in the SAME direction.
Counter-direction opens (which hedge or reverse) always submit.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import PositionSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PositionTierGateL5Config(ExecAlgorithmConfig, frozen=True):
    position_cap: int = 1  # max same-direction positions allowed


class PositionTierGateL5Algorithm(ExecAlgorithm):
    """Directional position gate: only block same-direction concurrent opens.

    Logic:
    - If no open position: submit.
    - If existing position is SAME direction as new order: check cap (skip if qty >= cap).
    - If existing position is OPPOSITE direction: submit (counter-direction allowed).
    """

    def __init__(self, config: PositionTierGateL5Config) -> None:
        super().__init__(config=config)
        self._position_cap = config.position_cap

    def on_start(self) -> None:
        self.log.info(f"ptg-f-l5 directional-aware started (cap={self._position_cap})")

    def on_reset(self) -> None:
        pass

    def _get_position_info(self, instrument_id):
        """Return (net_qty_same_dir, existing_side) for open positions."""
        positions = self.cache.positions_open(instrument_id=instrument_id)
        if not positions:
            return 0.0, None
        # In a netting OMS, there's at most one open position per instrument
        pos = positions[0]
        qty = float(str(pos.quantity))
        side = pos.side  # PositionSide.LONG or PositionSide.SHORT
        return qty, side

    def on_order(self, order) -> None:
        if order.is_reduce_only:
            self.submit_order(order)
            return

        net_qty, pos_side = self._get_position_info(order.instrument_id)

        if net_qty == 0.0 or pos_side is None:
            # No existing position — submit normally
            self.submit_order(order)
            return

        # Check if same direction
        order_side = order.side
        same_dir = (
            (order_side == OrderSide.BUY and pos_side == PositionSide.LONG) or
            (order_side == OrderSide.SELL and pos_side == PositionSide.SHORT)
        )

        if same_dir and net_qty >= self._position_cap:
            self.log.debug(f"SKIP {order.client_order_id} — same-dir cap (qty={net_qty:.1f})")
            return

        # Either opposite direction or below cap — submit
        self.submit_order(order)


def get_execution_algorithm(exec_id: str = "MY_GENERIC_ALGO", position_cap: int = 1):
    cfg = PositionTierGateL5Config(exec_algorithm_id=ExecAlgorithmId(exec_id), position_cap=position_cap)
    return PositionTierGateL5Algorithm(config=cfg)
