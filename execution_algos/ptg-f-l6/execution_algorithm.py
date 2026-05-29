"""ptg-f-l6: position-tier gate (cap=1) + minimum reentry time (2s after close)."""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PositionTierGateL6Config(ExecAlgorithmConfig, frozen=True):
    position_cap: int = 1
    min_reentry_seconds: float = 2.0


class PositionTierGateL6Algorithm(ExecAlgorithm):
    def __init__(self, config: PositionTierGateL6Config) -> None:
        super().__init__(config=config)
        self._position_cap = config.position_cap
        self._min_reentry_ns = int(config.min_reentry_seconds * 1_000_000_000)
        self._last_close_ts_ns: int = 0

    def on_start(self) -> None:
        self.log.info(f"ptg-f-l6 started (cap={self._position_cap}, min_reentry={self._min_reentry_ns/1e9:.1f}s)")

    def on_reset(self) -> None:
        self._last_close_ts_ns = 0

    def _current_net_qty(self, instrument_id) -> float:
        pos = self.cache.positions_open(instrument_id=instrument_id)
        return sum(float(str(p.quantity)) for p in pos) if pos else 0.0

    def on_order(self, order) -> None:
        if order.is_reduce_only:
            self._last_close_ts_ns = order.ts_init
            self.submit_order(order)
            return

        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty >= self._position_cap:
            return

        # Minimum reentry time gate
        if self._last_close_ts_ns > 0:
            elapsed_ns = order.ts_init - self._last_close_ts_ns
            if elapsed_ns < self._min_reentry_ns:
                self.log.debug(f"SKIP {order.client_order_id} — reentry too soon ({elapsed_ns/1e9:.3f}s < {self._min_reentry_ns/1e9:.1f}s)")
                return

        self.submit_order(order)


def get_execution_algorithm(exec_id: str = "MY_GENERIC_ALGO", position_cap: int = 1,
                             min_reentry_seconds: float = 2.0):
    cfg = PositionTierGateL6Config(exec_algorithm_id=ExecAlgorithmId(exec_id),
                                    position_cap=position_cap, min_reentry_seconds=min_reentry_seconds)
    return PositionTierGateL6Algorithm(config=cfg)
