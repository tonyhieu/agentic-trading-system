"""ptg-f-l7: position-tier gate (cap=1) + oracle cluster filter.

Skips opens if >= cluster_threshold oracle opens have been submitted
in the last cluster_window_seconds seconds (signal clustering filter).
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PositionTierGateL7Config(ExecAlgorithmConfig, frozen=True):
    position_cap: int = 1
    cluster_window_seconds: float = 5.0
    cluster_threshold: int = 3


class PositionTierGateL7Algorithm(ExecAlgorithm):
    def __init__(self, config: PositionTierGateL7Config) -> None:
        super().__init__(config=config)
        self._position_cap = config.position_cap
        self._cluster_window_ns = int(config.cluster_window_seconds * 1_000_000_000)
        self._cluster_threshold = config.cluster_threshold
        self._submitted_opens: deque[int] = deque()  # ts_init of submitted opens

    def on_start(self) -> None:
        self.log.info(f"ptg-f-l7 started (cap={self._position_cap}, cluster_window={self._cluster_window_ns/1e9:.1f}s, threshold={self._cluster_threshold})")

    def on_reset(self) -> None:
        self._submitted_opens.clear()

    def _current_net_qty(self, instrument_id) -> float:
        pos = self.cache.positions_open(instrument_id=instrument_id)
        return sum(float(str(p.quantity)) for p in pos) if pos else 0.0

    def _n_recent_opens(self, current_ts_ns: int) -> int:
        cutoff = current_ts_ns - self._cluster_window_ns
        while self._submitted_opens and self._submitted_opens[0] < cutoff:
            self._submitted_opens.popleft()
        return len(self._submitted_opens)

    def on_order(self, order) -> None:
        if order.is_reduce_only:
            self.submit_order(order)
            return

        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty >= self._position_cap:
            return

        # Cluster filter
        n_recent = self._n_recent_opens(order.ts_init)
        if n_recent >= self._cluster_threshold:
            self.log.debug(f"SKIP {order.client_order_id} — cluster gate ({n_recent} opens in window >= {self._cluster_threshold})")
            return

        self._submitted_opens.append(order.ts_init)
        self.submit_order(order)


def get_execution_algorithm(exec_id: str = "MY_GENERIC_ALGO", position_cap: int = 1,
                             cluster_window_seconds: float = 5.0, cluster_threshold: int = 3):
    cfg = PositionTierGateL7Config(exec_algorithm_id=ExecAlgorithmId(exec_id),
                                    position_cap=position_cap, cluster_window_seconds=cluster_window_seconds,
                                    cluster_threshold=cluster_threshold)
    return PositionTierGateL7Algorithm(config=cfg)
