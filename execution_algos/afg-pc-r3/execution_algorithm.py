"""afg-pc-r3: Threshold-Lowered AFG with thin-market floor.

Refinement of base aggressor-flow-gate (AFG). Identical mechanics to AFG
except:
  (a) flow_threshold lowered from 2.0 to 1.0 -- skip BUY when net_flow <= -1.0
      and SELL when net_flow >= +1.0 (more skips at lower magnitudes).
  (b) thin-market noise floor: gate requires at least min_prints=3 trade
      prints in the 10s window before it can fire. If len(deque) < min_prints,
      submit unconditionally (graceful degradation in thin periods).

Anti-cascade preserved: _position_flat=True after any skip so the next open
is unconditional. Reduce-only always submits immediately.

Hypothesis: AFG's existing skip set is precision-positive (broad 10/12-date
wins, +704.8% vs simple in cached results). The marginal value of additional
skips at lower flow magnitudes should also be positive provided we filter out
thin-window noise where a single small print could gate.

No look-ahead bias: deque pruned by ts_event <= order.ts_init at decision time.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class AFGPCR3Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for afg-pc-r3.

    Parameters
    ----------
    window_seconds : float
        Rolling look-back window for trade prints, in seconds. Default 10.0
        (matches base AFG for direct comparability).
    flow_threshold : float
        Minimum absolute net signed flow (in contracts) to trigger a skip.
        Default 1.0 (down from base AFG's 2.0).
    min_prints : int
        Minimum number of trade prints required in the window before the
        gate may fire. Default 3 -- prevents the lower threshold from
        firing on near-empty windows where a single small print would gate.
    """

    window_seconds: float = 10.0
    flow_threshold: float = 1.0
    min_prints: int = 3


class AFGPCR3Algorithm(ExecAlgorithm):
    """Threshold-Lowered AFG with thin-market floor."""

    def __init__(self, config: AFGPCR3Config) -> None:
        super().__init__(config=config)
        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._flow_threshold: float = config.flow_threshold
        self._min_prints: int = config.min_prints

        # Deque of (ts_event_ns: int, signed_vol: float)
        self._flow_deque: deque[tuple[int, float]] = deque()
        self._net_flow: float = 0.0

        # Anti-cascade: forced re-entry after any skip
        self._position_flat: bool = True

        # Subscription tracking
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"AFGPCR3Algorithm started "
            f"(window={self._window_ns / 1e9:.1f}s, "
            f"flow_threshold={self._flow_threshold:.2f}, "
            f"min_prints={self._min_prints})."
        )

    def on_reset(self) -> None:
        self._flow_deque.clear()
        self._net_flow = 0.0
        self._position_flat = True
        self._subscribed.clear()

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_trade_ticks(instrument_id)
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Trade tick handler
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Flow evaluation
    # ------------------------------------------------------------------

    def _prune_window(self, cutoff_ns: int) -> None:
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            _, old_vol = self._flow_deque.popleft()
            self._net_flow -= old_vol

    def _flow_is_adverse(self, order) -> bool:
        cutoff_ns = order.ts_init - self._window_ns
        self._prune_window(cutoff_ns)

        # Thin-market floor: require minimum prints before gating
        if len(self._flow_deque) < self._min_prints:
            return False

        net = self._net_flow

        if order.side == OrderSide.BUY:
            if net <= -self._flow_threshold:
                return True
        else:  # SELL
            if net >= self._flow_threshold:
                return True

        return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only always submits (intraday_flat compliance)
        if order.is_reduce_only:
            self.submit_order(order)
            return

        # Anti-cascade re-entry after skip
        if self._position_flat:
            self._position_flat = False
            self.submit_order(order)
            return

        if self._flow_is_adverse(order):
            self._position_flat = True
            # Skip -- do NOT call submit_order. Quantity invariant preserved.
        else:
            self._position_flat = False
            self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_seconds: float = 10.0,
    flow_threshold: float = 1.0,
    min_prints: int = 3,
) -> AFGPCR3Algorithm:
    """Instantiate the afg-pc-r3 algorithm."""
    config = AFGPCR3Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        flow_threshold=flow_threshold,
        min_prints=min_prints,
    )
    return AFGPCR3Algorithm(config=config)
