"""ptg-f-l3 execution algorithm.

Per-iteration experiment, base_algo `position-tier-gate`, context mode
`full-trace`, loop 3.

Combination of:
1. Position-tier gate (cap=1): blocks concurrent opens (base mechanism).
2. Aggressor-flow gate (window=30s, threshold=1.0): blocks open-leg orders
   when the 30s rolling aggressor flow is adverse to the order direction.

The position gate prevents concurrent entries (stack control).
The flow gate filters between-oracle openings where market microstructure
disagrees with the oracle signal (adverse-selection filter).

This combines the best mechanisms from both the ptg and afg arms:
- cap=1 is the proven operating point for the position-tier-gate mechanism.
- window=30s, threshold=1.0 is the proven operating point for the afg arm
  (afg-f-l7: +32.59% vs afg base).
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PositionTierGateL3Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for ptg-f-l3.

    Parameters
    ----------
    position_cap : int
        Maximum net position before gating opens. Default 1 (preserved from base).
    window_seconds : float
        Rolling window for aggressor-flow accumulation. Default 30.0s.
    flow_threshold : float
        Minimum |net_flow| to trigger adverse-flow skip. Default 1.0.
    """

    position_cap: int = 1
    window_seconds: float = 30.0
    flow_threshold: float = 1.0


class PositionTierGateL3Algorithm(ExecAlgorithm):
    """Position-tier gate (cap=1) + aggressor-flow gate (window=30s, threshold=1).

    Opening orders (is_reduce_only == False):
      1. If net_qty >= position_cap: SKIP (position gate).
      2. If adverse flow in 30s window: SKIP (flow gate); set _position_flat.
      3. Else: SUBMIT.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately.

    After any flow-gate skip: _position_flat = True (next open unconditional
    on the position gate, mimicking afg's anti-cascade). But position gate
    still applies independently.
    """

    def __init__(self, config: PositionTierGateL3Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._flow_threshold: float = config.flow_threshold

        self._flow_deque: deque[tuple[int, float]] = deque()
        self._net_flow: float = 0.0
        self._subscribed: set[str] = set()
        self._position_flat: bool = True  # anti-cascade for flow gate

    def on_start(self) -> None:
        self.log.info(
            f"PositionTierGateL3Algorithm started "
            f"(position_cap={self._position_cap}, "
            f"window={self._window_ns/1e9:.1f}s, "
            f"flow_threshold={self._flow_threshold})."
        )

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
        aggressor = tick.aggressor_side
        size = float(str(tick.size))
        if aggressor == AggressorSide.BUYER:
            signed_vol = size
        elif aggressor == AggressorSide.SELLER:
            signed_vol = -size
        else:
            signed_vol = 0.0
        self._flow_deque.append((tick.ts_event, signed_vol))
        self._net_flow += signed_vol

    def on_quote_tick(self, tick) -> None:
        pass

    def _prune_window(self, cutoff_ns: int) -> None:
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            _, old_vol = self._flow_deque.popleft()
            self._net_flow -= old_vol

    def _current_net_qty(self, instrument_id) -> float:
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        return sum(float(str(p.quantity)) for p in open_positions)

    def _flow_is_adverse(self, order) -> bool:
        cutoff_ns = order.ts_init - self._window_ns
        self._prune_window(cutoff_ns)
        if not self._flow_deque:
            return False
        net = self._net_flow
        if order.side == OrderSide.BUY:
            return net <= -self._flow_threshold
        else:
            return net >= self._flow_threshold

    def on_order(self, order) -> None:
        self._ensure_subscribed(order.instrument_id)

        if order.is_reduce_only:
            self.submit_order(order)
            return

        # Position cap gate
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty >= self._position_cap:
            self.log.debug(
                f"SKIP {order.client_order_id} — position cap "
                f"(net_qty={net_qty:.1f} >= cap={self._position_cap})."
            )
            return

        # Anti-cascade: re-entry after flow-gate skip
        if self._position_flat:
            self._position_flat = False
            self.submit_order(order)
            return

        # Flow gate
        if self._flow_is_adverse(order):
            self.log.info(
                f"SKIP {order.client_order_id} — adverse flow "
                f"(net_flow={self._net_flow:.2f})."
            )
            self._position_flat = True
            return

        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    window_seconds: float = 30.0,
    flow_threshold: float = 1.0,
) -> PositionTierGateL3Algorithm:
    """Instantiate and return the PositionTierGateL3Algorithm."""
    config = PositionTierGateL3Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        window_seconds=window_seconds,
        flow_threshold=flow_threshold,
    )
    return PositionTierGateL3Algorithm(config=config)
