"""afg-pc-r8 — Raised-Threshold AFG (single-variable ablation vs base).

Identical to base aggressor-flow-gate in every respect EXCEPT:
  - flow_threshold default raised from 2.0 to 5.0 contracts.

Mechanism: rolling 10s signed aggressor-flow deque from trade ticks.
  signed_vol = +size (BUYER aggressor) / -size (SELLER aggressor) / 0 (NO_AGGRESSOR)
  long_net = sum signed_vol over (t_order - 10s, t_order].

  Skip BUY  when long_net <= -flow_threshold (default 5.0)
  Skip SELL when long_net >= +flow_threshold (default 5.0)

  Reduce-only orders always submit (intraday_flat compliance).
  Warm-up: submit unconditionally if deque empty.
  Anti-cascade: after any skip, _position_flat=True so the next open is
  unconditional (matches base AFG semantics verbatim).

No look-ahead: deque pruned by ts_event < cutoff = order.ts_init - window_ns.
Quantity invariant: never modify order.quantity. Only submit or skip.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class AFGPCR8Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for afg-pc-r8 Raised-Threshold AFG.

    Parameters
    ----------
    window_seconds : float
        Rolling look-back window for trade prints, in seconds. Default 10.0s
        (matches base aggressor-flow-gate).
    flow_threshold : float
        Minimum absolute net signed flow (contracts) to trigger a skip.
        Default 5.0 contracts (2.5x the base AFG threshold of 2.0). This is
        the single variable changed vs base AFG.
    """

    window_seconds: float = 10.0
    flow_threshold: float = 5.0


class AFGPCR8Algorithm(ExecAlgorithm):
    """Raised-Threshold AFG — see module docstring."""

    def __init__(self, config: AFGPCR8Config) -> None:
        super().__init__(config=config)
        assert config.window_seconds > 0, "window_seconds must be > 0"
        assert config.flow_threshold > 0, "flow_threshold must be > 0"

        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._flow_threshold: float = float(config.flow_threshold)

        # Deque of (ts_event_ns: int, signed_vol: float)
        self._flow_deque: deque[tuple[int, float]] = deque()

        # Running sum of signed volume in the deque (O(1) updates)
        self._net_flow: float = 0.0

        # Anti-cascade: forced unconditional re-entry after any skip
        self._position_flat: bool = True

        # Subscription tracking
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"AFGPCR8Algorithm started "
            f"(window={self._window_ns / 1e9:.1f}s, "
            f"flow_threshold={self._flow_threshold:.2f} contracts)."
        )

    def on_reset(self) -> None:
        self._flow_deque.clear()
        self._net_flow = 0.0
        self._position_flat = True
        self._subscribed.clear()

    # ------------------------------------------------------------------
    # Subscription helper
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_trade_ticks(instrument_id)
            self.subscribe_quote_ticks(instrument_id)  # keep quote cache warm
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
            signed_vol = 0.0  # NO_AGGRESSOR — neutral

        self._flow_deque.append((tick.ts_event, signed_vol))
        self._net_flow += signed_vol

    # ------------------------------------------------------------------
    # Window pruning + gate evaluation
    # ------------------------------------------------------------------

    def _prune_window(self, cutoff_ns: int) -> None:
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            _, old_vol = self._flow_deque.popleft()
            self._net_flow -= old_vol

    def _flow_is_adverse(self, order) -> bool:
        cutoff_ns = order.ts_init - self._window_ns
        self._prune_window(cutoff_ns)

        if not self._flow_deque:
            return False  # Warm-up — submit unconditionally

        net = self._net_flow
        if order.side == OrderSide.BUY:
            return net <= -self._flow_threshold
        else:  # SELL
            return net >= self._flow_threshold

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        if order.is_reduce_only:
            self.submit_order(order)
            return

        # Anti-cascade: first signal or post-skip — submit unconditionally.
        if self._position_flat:
            self._position_flat = False
            self.submit_order(order)
            return

        if self._flow_is_adverse(order):
            self.log.info(
                f"SKIP {order.client_order_id} — adverse aggressor flow "
                f"(net_flow={self._net_flow:.2f}, threshold={self._flow_threshold:.2f}, "
                f"side={'BUY' if order.side == OrderSide.BUY else 'SELL'})."
            )
            self._position_flat = True
            # Do NOT call submit_order — quantity invariant preserved.
        else:
            self._position_flat = False
            self.submit_order(order)

    def on_quote_tick(self, tick) -> None:
        """Passively receive quote ticks (quote-cache side-effects only)."""
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_seconds: float = 10.0,
    flow_threshold: float = 5.0,
) -> AFGPCR8Algorithm:
    """Instantiate and return the AFGPCR8Algorithm (Raised-Threshold AFG).

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_seconds : float
        Rolling window for aggressor-flow accumulation, in seconds. Default 10.0s.
    flow_threshold : float
        Minimum absolute net adverse flow (contracts) to trigger a skip.
        Default 5.0 (2.5x base AFG; single-variable change under test).
    """
    config = AFGPCR8Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        flow_threshold=flow_threshold,
    )
    return AFGPCR8Algorithm(config=config)
