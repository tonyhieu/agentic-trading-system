"""Probe — behaviorally identical to position-tier-gate.

Used only to produce orders.csv at a separate path so we can count
flicker-window events for the sip-ptg-l5 empirical pre-check. This is
not a research candidate; it is throw-away infrastructure.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class FlickerProbeConfig(ExecAlgorithmConfig, frozen=True):
    position_cap: int = 1


class FlickerProbeAlgorithm(ExecAlgorithm):
    """Mirror of position-tier-gate; identical submit/skip behavior."""

    def __init__(self, config: FlickerProbeConfig) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap

    def on_start(self) -> None:
        self.log.info(
            f"FlickerProbeAlgorithm started (position_cap={self._position_cap})."
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
            self.submit_order(order)
            return
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty >= self._position_cap:
            return
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
) -> FlickerProbeAlgorithm:
    config = FlickerProbeConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
    )
    return FlickerProbeAlgorithm(config=config)
