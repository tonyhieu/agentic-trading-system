"""QD-AFG structural template — aggressor-flow gate with two behavior dials.

This is the variation surface for the quality_diversity_experiment afg arm.
It extends the base aggressor-flow-gate with two STRUCTURAL controls chosen so
that the two MAP-Elites behavior descriptors can each be driven across their
full range independently:

  Axis 1 — selectivity (trade_count / simple_trade_count):
      `submit_fraction` ∈ (0,1].  After the flow gate decides to submit, only a
      deterministic 1-in-N subset of opens is actually sent (N = round(1/frac)).
      Deterministic counter (no RNG) so the realized selectivity is reproducible
      and the descriptor↔result link is stable.

  Axis 2 — timing concentration (Gini of open-fills across the session):
      `windows` = list of (start_hour, end_hour) in UTC.  Opens outside every
      window are skipped.  An empty list means "all day" (low Gini); one narrow
      window concentrates fills into a burst (high Gini).

Both dials only ever SKIP opens — never add quantity, never modify size — so the
quantity invariant (sum(child_fills) <= parent.quantity) is preserved by
construction.  Reduce-only (close) orders are always submitted (intraday_flat).

The base flow gate (window_seconds, flow_threshold) is retained underneath so a
candidate is still a real aggressor-flow executor, not a pure throttle.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class QDAFGConfig(ExecAlgorithmConfig, frozen=True):
    window_seconds: float = 10.0
    flow_threshold: float = 2.0
    submit_fraction: float = 1.0          # axis 1: fraction of gated opens to submit
    windows: tuple = ()                    # axis 2: ((start_h,end_h),...) UTC; () = all day
    cascade_reentry: bool = True           # base anti-cascade behavior


class QDAFGAlgorithm(ExecAlgorithm):
    def __init__(self, config: QDAFGConfig) -> None:
        super().__init__(config=config)
        self._window_ns = int(config.window_seconds * 1_000_000_000)
        self._flow_threshold = config.flow_threshold
        self._submit_fraction = max(1e-9, min(1.0, config.submit_fraction))
        self._stride = max(1, round(1.0 / self._submit_fraction))  # submit 1-in-stride
        self._windows = [(float(a), float(b)) for (a, b) in config.windows]
        self._cascade_reentry = config.cascade_reentry

        self._flow_deque: deque[tuple[int, float]] = deque()
        self._net_flow = 0.0
        self._position_flat = True
        self._subscribed: set[str] = set()
        self._open_counter = 0  # deterministic subsample counter

    def on_start(self) -> None:
        self.log.info(
            f"QDAFG started (window={self._window_ns/1e9:.1f}s, "
            f"thr={self._flow_threshold:.2f}, frac={self._submit_fraction:.3f}"
            f"(1-in-{self._stride}), windows={self._windows}, "
            f"cascade_reentry={self._cascade_reentry})."
        )

    def on_reset(self) -> None:
        self._flow_deque.clear()
        self._net_flow = 0.0
        self._position_flat = True
        self._subscribed.clear()
        self._open_counter = 0

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_trade_ticks(instrument_id)
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    def on_trade_tick(self, tick) -> None:
        aggressor = tick.aggressor_side
        size = float(str(tick.size))
        if aggressor == AggressorSide.BUYER:
            signed = size
        elif aggressor == AggressorSide.SELLER:
            signed = -size
        else:
            signed = 0.0
        self._flow_deque.append((tick.ts_event, signed))
        self._net_flow += signed

    def _prune_window(self, cutoff_ns: int) -> None:
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            _, old = self._flow_deque.popleft()
            self._net_flow -= old

    def _flow_is_adverse(self, order) -> bool:
        cutoff = order.ts_init - self._window_ns
        self._prune_window(cutoff)
        if not self._flow_deque:
            return False
        net = self._net_flow
        if order.side == OrderSide.BUY:
            return net <= -self._flow_threshold
        return net >= self._flow_threshold

    def _in_window(self, order) -> bool:
        if not self._windows:
            return True
        # ts_init is ns since epoch UTC; derive hour-of-day in UTC.
        secs = (order.ts_init // 1_000_000_000) % 86400
        hour = secs / 3600.0
        return any(a <= hour < b for (a, b) in self._windows)

    def on_order(self, order) -> None:
        self._ensure_subscribed(order.instrument_id)

        if order.is_reduce_only:
            self.submit_order(order)
            return

        # Axis 2 — schedule gate (timing concentration).
        if not self._in_window(order):
            if self._cascade_reentry:
                self._position_flat = True
            return

        # Base anti-cascade re-entry: first open after a skip is unconditional.
        if self._cascade_reentry and self._position_flat:
            self._position_flat = False
            self._submit_subsampled(order)
            return

        # Base flow gate.
        if self._flow_is_adverse(order):
            self._position_flat = True
            return

        self._position_flat = False
        self._submit_subsampled(order)

    def _submit_subsampled(self, order) -> None:
        """Axis 1 — deterministic 1-in-stride submission (selectivity dial)."""
        self._open_counter += 1
        if self._stride <= 1 or (self._open_counter % self._stride) == 0:
            self.submit_order(order)
        # else: dropped — quantity invariant preserved (we only skip).

    def on_quote_tick(self, tick) -> None:
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_seconds: float = 10.0,
    flow_threshold: float = 2.0,
    submit_fraction: float = 1.0,
    windows: tuple = (),
    cascade_reentry: bool = True,
) -> QDAFGAlgorithm:
    config = QDAFGConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        flow_threshold=flow_threshold,
        submit_fraction=submit_fraction,
        windows=tuple(tuple(w) for w in windows),
        cascade_reentry=cascade_reentry,
    )
    return QDAFGAlgorithm(config=config)
