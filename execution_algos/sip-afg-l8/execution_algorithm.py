"""sip-afg-l8 — clipped-print aggressor-flow-gate.

Identical to ``aggressor-flow-gate`` (10s rolling signed aggressor-volume
window, symmetric ``flow_threshold = 2.0`` contracts, anti-cascade
``_position_flat`` flag forcing the post-skip order to submit
unconditionally) EXCEPT that each individual trade print's signed
contribution to the rolling sum is clipped in magnitude to
``max_print_size`` (default 3.0 contracts).

Rationale: with the base unclipped contribution, a single very large
trade print (e.g. a 100-lot sweep on a session open or macro release)
dominates ``net_flow`` for the entire 10-second window, even though
the directional impulse from that single sweep has typically been
absorbed almost immediately. Clipping each print's contribution to
``max_print_size`` makes the gate require a *broader-based*
directional pattern — multiple meaningfully-sized same-side prints
rather than a single big one — before skipping subsequent open
orders.

All execution constraints unchanged from base:
  - Quantity invariant: only submit/skip; never modify order.quantity.
  - top_of_book_only: no fill mechanics change.
  - participation_cap: no order sizing.
  - intraday_flat: reduce-only orders always submit.

No look-ahead bias: the deque pruning uses ``order.ts_init`` as the
reference time; only ticks with ``tick.ts_event <= order.ts_init`` are
considered (replay is strictly chronological). Clipping is a function
of ``tick.size`` only — known at ``on_trade_tick`` time.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class SipAfgL8Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the sip-afg-l8 execution algorithm.

    Parameters
    ----------
    window_seconds : float
        Rolling look-back window for trade prints, in seconds.
        Default 10.0 seconds (identical to base ``aggressor-flow-gate``).
    flow_threshold : float
        Minimum absolute net signed flow (in contracts) to trigger a
        skip. Default 2.0 contracts (identical to base).
    max_print_size : float
        Maximum magnitude of any single trade print's signed
        contribution to the rolling deque. A print with ``size``
        larger than ``max_print_size`` is clipped to
        ``±max_print_size`` before append. Default 3.0 contracts.
    """

    window_seconds: float = 10.0
    flow_threshold: float = 2.0
    max_print_size: float = 3.0


class SipAfgL8Algorithm(ExecAlgorithm):
    """Aggressor-flow-gate with per-print size clipping.

    Replaces the base algorithm's unclipped per-print signed contribution
    with a clipped one: each individual trade print contributes at most
    ``max_print_size`` in magnitude to the rolling ``net_flow``, so a
    single very large sweep cannot single-handedly trigger a skip.

    Everything else — the rolling window, the symmetric
    ``flow_threshold`` gate, the post-skip anti-cascade flag, the
    reduce-only short-circuit, the warm-up handling — is identical to
    ``aggressor-flow-gate``.
    """

    def __init__(self, config: SipAfgL8Config) -> None:
        super().__init__(config=config)
        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._flow_threshold: float = float(config.flow_threshold)
        self._max_print_size: float = float(config.max_print_size)

        # Deque of (ts_event_ns: int, signed_vol: float). The signed_vol
        # values are ALREADY CLIPPED at append time.
        self._flow_deque: deque[tuple[int, float]] = deque()
        self._net_flow: float = 0.0

        # Anti-cascade: forced re-entry after any skip — identical to base.
        self._position_flat: bool = True

        # Subscription tracking
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"SipAfgL8Algorithm started "
            f"(window={self._window_ns / 1e9:.1f}s, "
            f"flow_threshold={self._flow_threshold:.2f}, "
            f"max_print_size={self._max_print_size:.2f})."
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
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Trade tick handler — clip and append
    # ------------------------------------------------------------------

    def on_trade_tick(self, tick) -> None:
        """Receive a trade tick, clip its magnitude, and append to the deque."""
        aggressor = tick.aggressor_side
        size = float(str(tick.size))

        # Clip magnitude — single-print contribution capped.
        clipped = size if size < self._max_print_size else self._max_print_size

        if aggressor == AggressorSide.BUYER:
            signed_vol = clipped
        elif aggressor == AggressorSide.SELLER:
            signed_vol = -clipped
        else:
            # NO_AGGRESSOR — treat as neutral; do not bias the flow signal.
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
        """Return True if clipped net aggressor flow is adverse for this order.

        BUY  order: adverse when net_flow <= -flow_threshold.
        SELL order: adverse when net_flow >=  flow_threshold.

        Returns False (do not skip) when:
          - Flow deque is empty (warm-up).
          - |net_flow| < flow_threshold (neutral / sub-threshold).
        """
        cutoff_ns = order.ts_init - self._window_ns
        self._prune_window(cutoff_ns)

        if not self._flow_deque:
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
        """Route order: clipped aggressor-flow gate, anti-cascade flag."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat.
        if order.is_reduce_only:
            self.submit_order(order)
            return

        # Anti-cascade: forced re-entry after any skip.
        if self._position_flat:
            self._position_flat = False
            self.submit_order(order)
            return

        if self._flow_is_adverse(order):
            self.log.info(
                f"SKIP {order.client_order_id} — adverse clipped aggressor flow "
                f"(net_flow={self._net_flow:.2f}, side="
                f"{'BUY' if order.side == OrderSide.BUY else 'SELL'})."
            )
            self._position_flat = True
            # Do NOT call submit_order — quantity invariant preserved.
        else:
            self._position_flat = False
            self.submit_order(order)

    def on_quote_tick(self, tick) -> None:
        """Passively receive quote ticks (kept for quote-cache side-effects)."""
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_seconds: float = 10.0,
    flow_threshold: float = 2.0,
    max_print_size: float = 3.0,
) -> SipAfgL8Algorithm:
    """Instantiate and return the SipAfgL8Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_seconds : float
        Rolling window for aggressor-flow accumulation, in seconds.
        Default 10.0s (identical to base).
    flow_threshold : float
        Skip threshold in contracts. Default 2.0 (identical to base).
    max_print_size : float
        Per-print contribution magnitude cap, in contracts. Default 3.0.
    """
    config = SipAfgL8Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        flow_threshold=flow_threshold,
        max_print_size=max_print_size,
    )
    return SipAfgL8Algorithm(config=config)
