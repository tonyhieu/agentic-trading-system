"""afg-f-l1 execution algorithm.

Per-iteration experiment, base_algo `aggressor-flow-gate`, context mode
`full-trace`, loop 1.

Variant of `aggressor-flow-gate`. The base algo gates the OPEN leg of each
oracle signal on a 10 s rolling net signed aggressor-flow signal, skipping
whenever `|net_flow| >= flow_threshold` and the sign is adverse to the
order. This variant adds a single new pre-condition:

    The flow-direction gate may only fire when in-window gross trade
    volume (sum of |size|) >= `min_gross_volume`.

Below that floor the algorithm submits unconditionally (gate stands
down — too few trades in the window for the directional signal to be
reliable). Above the floor, behaviour is identical to the base algo.

Algorithm:
  - Maintain a deque of (ts_event_ns, signed_volume) from trade ticks
    via on_trade_tick().  signed_volume = +size for BUYER aggressor
    (crossed the ask), -size for SELLER (hit the bid), 0 for
    NO_AGGRESSOR.
  - Maintain O(1) running sums alongside the deque:
        _net_flow      = sum(signed_volume)
        _gross_volume  = sum(|signed_volume|)
  - At each order event, prune entries older than `window_seconds`,
    updating both running sums in O(1) per pruned entry.
  - Decision logic for opening orders:
        if _gross_volume < min_gross_volume:
            submit (gate disabled — thin tape, low confidence)
        elif side == BUY  and _net_flow <= -flow_threshold:
            SKIP (sell-dominated)
        elif side == SELL and _net_flow >=  flow_threshold:
            SKIP (buy-dominated)
        else:
            submit
  - Reduce-only / position-closing orders always execute.
  - After any skip: _position_flat = True so the NEXT open is
    unconditional (anti-cascade guarantee consistent with all passing
    algorithms).

No look-ahead bias: only trade ticks with ts_event <= order.ts_init are
in the deque at decision time (replay is strictly chronological; the
window prune uses the order's ts_init, never a future timestamp). The
_gross_volume running sum is derived from the same deque and inherits
the same property.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class AggressorFlowVolumeGateConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the afg-f-l1 execution algorithm.

    Parameters
    ----------
    window_seconds : float
        Rolling look-back window for trade prints, in seconds. Prints older
        than this are pruned and contribute nothing. Default 10.0 seconds
        (unchanged from base `aggressor-flow-gate`).
    flow_threshold : float
        Minimum absolute net signed flow (in contracts) to trigger a skip.
        For BUY  orders: skip when net_flow <= -flow_threshold.
        For SELL orders: skip when net_flow >= +flow_threshold.
        Default 2.0 contracts (unchanged from base).
    min_gross_volume : float
        Minimum gross in-window trade volume (sum of |size| across all
        aggressor types) required before the flow-direction gate is
        allowed to fire. Below this floor the algo submits orders
        unconditionally (gate disabled — too thin / too noisy to be a
        reliable directional signal). Default 8.0 contracts -- 4x
        `flow_threshold`, which at the floor enforces a minimum 25%
        signed/gross imbalance ratio before any skip can occur.
    """

    window_seconds: float = 10.0
    flow_threshold: float = 2.0
    min_gross_volume: float = 8.0


class AggressorFlowVolumeGateAlgorithm(ExecAlgorithm):
    """Aggressor-flow gate with a gross-volume floor on gate activation.

    Opening orders (is_reduce_only == False):
      - Maintain a 10 s deque of signed-volume trade prints with O(1)
        running sums for net flow and gross volume.
      - If gross_volume < min_gross_volume in the window: submit
        unconditionally (gate stands down — thin tape).
      - Otherwise: skip BUY when net_flow <= -flow_threshold (sell pressure)
        or skip SELL when net_flow >= flow_threshold (buy pressure).
      - Submit unconditionally when no trade data is available (warm-up).
      - After any skip: _position_flat = True (next open unconditional).

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is ever modified. Quantity invariant always preserved.
    """

    def __init__(self, config: AggressorFlowVolumeGateConfig) -> None:
        super().__init__(config=config)
        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._flow_threshold: float = config.flow_threshold
        self._min_gross_volume: float = config.min_gross_volume

        # Deque of (ts_event_ns: int, signed_vol: float)
        # signed_vol = +size (BUYER), -size (SELLER), 0 (NO_AGGRESSOR)
        self._flow_deque: deque[tuple[int, float]] = deque()

        # O(1) running aggregates over the deque
        self._net_flow: float = 0.0
        self._gross_volume: float = 0.0

        # Safety: forced re-entry after any skip to prevent cascade
        self._position_flat: bool = True

        # Subscription tracking
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"AggressorFlowVolumeGateAlgorithm started "
            f"(window={self._window_ns / 1e9:.1f}s, "
            f"flow_threshold={self._flow_threshold:.2f} contracts, "
            f"min_gross_volume={self._min_gross_volume:.2f} contracts)."
        )

    def on_reset(self) -> None:
        self._flow_deque.clear()
        self._net_flow = 0.0
        self._gross_volume = 0.0
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
    # Trade tick handler — maintain rolling signed + gross aggregates
    # ------------------------------------------------------------------

    def on_trade_tick(self, tick) -> None:
        """Receive a trade tick and update the rolling deque + aggregates."""
        aggressor = tick.aggressor_side
        size = float(str(tick.size))

        if aggressor == AggressorSide.BUYER:
            signed_vol = size
        elif aggressor == AggressorSide.SELLER:
            signed_vol = -size
        else:
            # NO_AGGRESSOR — treat as neutral; do not bias the flow signal
            # OR the gross-volume count (consistent with base algo).
            signed_vol = 0.0

        self._flow_deque.append((tick.ts_event, signed_vol))
        self._net_flow += signed_vol
        self._gross_volume += abs(signed_vol)

    # ------------------------------------------------------------------
    # Flow + volume evaluation
    # ------------------------------------------------------------------

    def _prune_window(self, cutoff_ns: int) -> None:
        """Remove deque entries older than cutoff_ns, updating both sums."""
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            _, old_vol = self._flow_deque.popleft()
            self._net_flow -= old_vol
            self._gross_volume -= abs(old_vol)

    def _flow_is_adverse(self, order) -> bool:
        """Return True if the gate should SKIP this order.

        Skip rules (only evaluated when gross_volume >= min_gross_volume):
          BUY  order: skip when net_flow <= -flow_threshold (sellers dominate)
          SELL order: skip when net_flow >=  flow_threshold (buyers dominate)

        Returns False (do not skip) when:
          - Flow deque is empty (warm-up).
          - Gross in-window volume below `min_gross_volume` (gate stands down
            — tape too thin for the directional signal to be reliable).
          - |net_flow| < flow_threshold (neutral / near-balanced).
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

        # NEW: gross-volume floor. If the tape is thin, the directional
        # signal is unreliable -- stand the gate down rather than skip on
        # noise. This is the only change vs the base algo's on-order logic.
        if self._gross_volume < self._min_gross_volume:
            self.log.debug(
                f"Gross volume below floor (gross={self._gross_volume:.2f} "
                f"< min={self._min_gross_volume:.2f}); gate disabled, "
                f"submitting {order.client_order_id}."
            )
            return False

        net = self._net_flow

        if order.side == OrderSide.BUY:
            if net <= -self._flow_threshold:
                self.log.debug(
                    f"BUY adverse flow: net_flow={net:.2f} <= "
                    f"-threshold={-self._flow_threshold:.2f} "
                    f"(gross={self._gross_volume:.2f}); SKIP."
                )
                return True
        else:  # SELL
            if net >= self._flow_threshold:
                self.log.debug(
                    f"SELL adverse flow: net_flow={net:.2f} >= "
                    f"threshold={self._flow_threshold:.2f} "
                    f"(gross={self._gross_volume:.2f}); SKIP."
                )
                return True

        return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on flow + volume gate."""
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

        # Evaluate the flow + volume gate.
        if self._flow_is_adverse(order):
            self.log.info(
                f"SKIP {order.client_order_id} — adverse aggressor flow "
                f"(net_flow={self._net_flow:.2f}, "
                f"gross={self._gross_volume:.2f}, side="
                f"{'BUY' if order.side == OrderSide.BUY else 'SELL'})."
            )
            self._position_flat = True
            # Do NOT call submit_order — quantity invariant preserved.
        else:
            self.log.debug(
                f"SUBMIT {order.client_order_id} — flow neutral/favorable or "
                f"tape thin (net_flow={self._net_flow:.2f}, "
                f"gross={self._gross_volume:.2f})."
            )
            self._position_flat = False
            self.submit_order(order)

    def on_quote_tick(self, tick) -> None:
        """Passively receive quote ticks (kept for quote-cache side-effects)."""
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_seconds: float = 10.0,
    flow_threshold: float = 2.0,
    min_gross_volume: float = 8.0,
) -> AggressorFlowVolumeGateAlgorithm:
    """Instantiate and return the AggressorFlowVolumeGateAlgorithm.

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
    min_gross_volume : float
        Minimum in-window gross trade volume (contracts) required before
        the gate is allowed to fire. Default 8.0 contracts.
    """
    config = AggressorFlowVolumeGateConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        flow_threshold=flow_threshold,
        min_gross_volume=min_gross_volume,
    )
    return AggressorFlowVolumeGateAlgorithm(config=config)
