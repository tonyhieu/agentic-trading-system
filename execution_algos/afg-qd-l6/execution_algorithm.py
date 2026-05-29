"""Aggressor-flow-gate execution algorithm.

Conditions the OPEN leg of each oracle signal on a rolling signed net
aggressor-flow signal derived from recent trade prints (TradeTick data).

Algorithm:
  - Maintain a deque of (ts_event_ns, signed_volume) from trade ticks
    delivered via on_trade_tick().  signed_volume = +size for BUYER
    aggressor (crossed the ask), -size for SELLER aggressor (hit the bid),
    0 for NO_AGGRESSOR.
  - At each order event, prune entries older than `window_seconds` seconds.
  - Compute net_flow = sum of signed volumes in the window.
  - For BUY  orders: skip when net_flow <= -flow_threshold  (sell-dominated)
  - For SELL orders: skip when net_flow >=  flow_threshold  (buy-dominated)
  - No signal (empty window or |net_flow| < threshold): submit unconditionally.
  - Reduce-only / position-closing orders always execute.
  - After any skip: _position_flat = True so the NEXT open is unconditional
    (anti-cascade guarantee consistent with all passing algorithms).

Data requirement:
  `include_trades=True` in DatabentoDataLoader (already set in data_loader.py)
  ensures TradeTick objects are present in the backtest data feed.

No look-ahead bias: only trade ticks with ts_event <= order.ts_init are in
the deque at decision time (replay is strictly chronological; the window
prune uses the order's ts_init, not a future timestamp).
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class AggressorFlowGateConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the aggressor-flow-gate execution algorithm.

    Parameters
    ----------
    window_seconds : float
        Rolling look-back window for trade prints, in seconds.
        Default 10.0 seconds (short enough to be near-term but long enough
        for several trades to accumulate at typical futures cadence).
    flow_threshold : float
        Minimum absolute net signed flow (in contracts) to trigger a skip.
        For BUY  orders: skip when net_flow <= -flow_threshold.
        For SELL orders: skip when net_flow >=  flow_threshold.
        Default 2.0 contracts -- requires at least 2 net adverse contracts
        in the window before gating an entry.
    """

    window_seconds: float = 30.0
    flow_threshold: float = 0.5


class AggressorFlowGateAlgorithm(ExecAlgorithm):
    """Execution algorithm that gates open orders on rolling aggressor flow.

    Opening orders (is_reduce_only == False):
      - Evaluate net signed aggressor flow over the last `window_seconds`.
        BUY aggressor prints contribute +size; SELLER contributes -size.
      - Skip BUY  entries when net_flow <= -flow_threshold (sell pressure).
      - Skip SELL entries when net_flow >=  flow_threshold (buy pressure).
      - Submit unconditionally when no trade data is available (warm-up) or
        when |net_flow| < threshold (neutral/ambiguous period).
      - After any skip: _position_flat = True (next open unconditional).

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is ever modified. Quantity invariant always preserved.
    """

    def __init__(self, config: AggressorFlowGateConfig) -> None:
        super().__init__(config=config)
        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._flow_threshold: float = config.flow_threshold

        # Deque of (ts_event_ns: int, signed_vol: float)
        # signed_vol = +size (BUYER), -size (SELLER), 0 (NO_AGGRESSOR)
        self._flow_deque: deque[tuple[int, float]] = deque()

        # Running sum of signed volume in the deque (for O(1) updates)
        self._net_flow: float = 0.0

        # Safety: forced re-entry after any skip to prevent cascade
        self._position_flat: bool = True

        # Subscription tracking
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"AggressorFlowGateAlgorithm started "
            f"(window={self._window_ns / 1e9:.1f}s, "
            f"flow_threshold={self._flow_threshold:.1f} contracts)."
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
    # Trade tick handler — maintain rolling signed flow deque
    # ------------------------------------------------------------------

    def on_trade_tick(self, tick) -> None:
        """Receive a trade tick and update the rolling aggressor-flow deque."""
        aggressor = tick.aggressor_side
        size = float(str(tick.size))

        if aggressor == AggressorSide.BUYER:
            signed_vol = size
        elif aggressor == AggressorSide.SELLER:
            signed_vol = -size
        else:
            # NO_AGGRESSOR — treat as neutral; do not bias the flow signal
            signed_vol = 0.0

        self._flow_deque.append((tick.ts_event, signed_vol))
        self._net_flow += signed_vol

    # ------------------------------------------------------------------
    # Flow evaluation
    # ------------------------------------------------------------------

    def _prune_window(self, cutoff_ns: int) -> None:
        """Remove deque entries older than cutoff_ns, updating _net_flow."""
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            _, old_vol = self._flow_deque.popleft()
            self._net_flow -= old_vol

    def _flow_is_adverse(self, order) -> bool:
        """Return True if net aggressor flow is adverse for this order direction.

        BUY  order: adverse when net_flow <= -flow_threshold  (sellers dominate)
        SELL order: adverse when net_flow >=  flow_threshold  (buyers dominate)

        Returns False (do not skip) when:
          - Flow deque is empty (no trades seen yet — warm-up)
          - |net_flow| < flow_threshold (neutral / near-balanced window)
        """
        # Prune stale entries relative to order timestamp
        cutoff_ns = order.ts_init - self._window_ns
        self._prune_window(cutoff_ns)

        if not self._flow_deque:
            # No trade data in window — do not gate (warm-up / thin market)
            self.log.debug(
                f"No trade data in window; submitting {order.client_order_id} "
                f"unconditionally."
            )
            return False

        net = self._net_flow

        if order.side == OrderSide.BUY:
            if net <= -self._flow_threshold:
                self.log.debug(
                    f"BUY adverse flow: net_flow={net:.2f} <= "
                    f"-threshold={-self._flow_threshold:.2f}; SKIP."
                )
                return True
        else:  # SELL
            if net >= self._flow_threshold:
                self.log.debug(
                    f"SELL adverse flow: net_flow={net:.2f} >= "
                    f"threshold={self._flow_threshold:.2f}; SKIP."
                )
                return True

        return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on rolling aggressor flow."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Forced re-entry after a skip — always submit to prevent cascade.
        if self._position_flat:
            self.log.debug(
                f"Re-entry (first or post-skip); submitting "
                f"{order.client_order_id} unconditionally."
            )
            self._position_flat = False
            self.submit_order(order)
            return

        # Evaluate aggressor-flow gate.
        if self._flow_is_adverse(order):
            self.log.info(
                f"SKIP {order.client_order_id} — adverse aggressor flow "
                f"(net_flow={self._net_flow:.2f}, side="
                f"{'BUY' if order.side == OrderSide.BUY else 'SELL'})."
            )
            self._position_flat = True
            # Do NOT call submit_order — quantity invariant preserved.
        else:
            self.log.debug(
                f"SUBMIT {order.client_order_id} — flow neutral/favorable "
                f"(net_flow={self._net_flow:.2f})."
            )
            self._position_flat = False
            self.submit_order(order)

    def on_quote_tick(self, tick) -> None:
        """Passively receive quote ticks (kept for quote-cache side-effects)."""
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_seconds: float = 30.0,
    flow_threshold: float = 0.5,
) -> AggressorFlowGateAlgorithm:
    """Instantiate and return the AggressorFlowGateAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_seconds : float
        Rolling window for aggressor-flow accumulation, in seconds.
        Default 10.0s.
    flow_threshold : float
        Minimum absolute net aggressor flow (contracts) to trigger a skip.
        Default 2.0 contracts.
    """
    config = AggressorFlowGateConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        flow_threshold=flow_threshold,
    )
    return AggressorFlowGateAlgorithm(config=config)
