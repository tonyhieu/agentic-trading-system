"""ptg-f-l4: position-tier gate (cap=1) + short-window flow gate (5s, threshold=1)."""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PositionTierGateL4Config(ExecAlgorithmConfig, frozen=True):
    position_cap: int = 1
    window_seconds: float = 5.0
    flow_threshold: float = 1.0


class PositionTierGateL4Algorithm(ExecAlgorithm):
    def __init__(self, config: PositionTierGateL4Config) -> None:
        super().__init__(config=config)
        self._position_cap = config.position_cap
        self._window_ns = int(config.window_seconds * 1_000_000_000)
        self._flow_threshold = config.flow_threshold
        self._flow_deque: deque[tuple[int, float]] = deque()
        self._net_flow = 0.0
        self._subscribed: set[str] = set()
        self._position_flat = True

    def on_start(self) -> None:
        self.log.info(f"ptg-f-l4 started (cap={self._position_cap}, window={self._window_ns/1e9:.1f}s, threshold={self._flow_threshold})")

    def on_reset(self) -> None:
        self._flow_deque.clear()
        self._net_flow = 0.0
        self._subscribed.clear()
        self._position_flat = True

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_trade_ticks(instrument_id)
            self._subscribed.add(key)

    def on_trade_tick(self, tick) -> None:
        s = tick.aggressor_side
        size = float(str(tick.size))
        sv = size if s == AggressorSide.BUYER else (-size if s == AggressorSide.SELLER else 0.0)
        self._flow_deque.append((tick.ts_event, sv))
        self._net_flow += sv

    def on_quote_tick(self, tick) -> None:
        pass

    def _prune(self, cutoff_ns: int) -> None:
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            _, v = self._flow_deque.popleft()
            self._net_flow -= v

    def _current_net_qty(self, instrument_id) -> float:
        pos = self.cache.positions_open(instrument_id=instrument_id)
        return sum(float(str(p.quantity)) for p in pos) if pos else 0.0

    def _flow_adverse(self, order) -> bool:
        self._prune(order.ts_init - self._window_ns)
        if not self._flow_deque:
            return False
        net = self._net_flow
        if order.side == OrderSide.BUY:
            return net <= -self._flow_threshold
        return net >= self._flow_threshold

    def on_order(self, order) -> None:
        self._ensure_subscribed(order.instrument_id)
        if order.is_reduce_only:
            self.submit_order(order)
            return
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty >= self._position_cap:
            return
        if self._position_flat:
            self._position_flat = False
            self.submit_order(order)
            return
        if self._flow_adverse(order):
            self._position_flat = True
            return
        self.submit_order(order)


def get_execution_algorithm(exec_id: str = "MY_GENERIC_ALGO", position_cap: int = 1,
                             window_seconds: float = 5.0, flow_threshold: float = 1.0):
    cfg = PositionTierGateL4Config(exec_algorithm_id=ExecAlgorithmId(exec_id),
                                    position_cap=position_cap, window_seconds=window_seconds,
                                    flow_threshold=flow_threshold)
    return PositionTierGateL4Algorithm(config=cfg)
