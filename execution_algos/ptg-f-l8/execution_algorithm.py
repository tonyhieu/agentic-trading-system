"""ptg-f-l8: position-tier gate (cap=1) + very short minimum reentry time (0.5s).

Final loop of the arm. Combines cap=1 with a 0.5s min reentry time.
Oracle signals fire every 1s, so 0.5s blocks only ultra-rapid same-second
re-entries. Expected to be near-identical to base (since oracle signal_interval=1s).
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PositionTierGateL8Config(ExecAlgorithmConfig, frozen=True):
    position_cap: int = 1
    min_reentry_seconds: float = 0.5


class PositionTierGateL8Algorithm(ExecAlgorithm):
    def __init__(self, config: PositionTierGateL8Config) -> None:
        super().__init__(config=config)
        self._position_cap = config.position_cap
        self._min_reentry_ns = int(config.min_reentry_seconds * 1_000_000_000)
        self._last_close_ts_ns: int = 0

    def on_start(self) -> None:
        self.log.info(f"ptg-f-l8 started (cap={self._position_cap}, min_reentry={self._min_reentry_ns/1e9:.2f}s)")

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

        if self._last_close_ts_ns > 0:
            elapsed_ns = order.ts_init - self._last_close_ts_ns
            if elapsed_ns < self._min_reentry_ns:
                return

        self.submit_order(order)


def get_execution_algorithm(exec_id: str = "MY_GENERIC_ALGO", position_cap: int = 1,
                             min_reentry_seconds: float = 0.5):
    cfg = PositionTierGateL8Config(exec_algorithm_id=ExecAlgorithmId(exec_id),
                                    position_cap=position_cap, min_reentry_seconds=min_reentry_seconds)
    return PositionTierGateL8Algorithm(config=cfg)
