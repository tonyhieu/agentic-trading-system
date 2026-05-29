"""afg-pc-r5 — Time-decayed AFG with r2 directional-chain state machine.

Single-variable ablation of afg-pc-r2 (the empirical winner):
  - r2 used a rectangular 10s window: net_flow = sum(signed_vol_i) over prints
    in the window; skip when |net_flow| >= 2.0 in the adverse direction.
  - r5 replaces that with an EXPONENTIALLY-DECAYED weighted sum evaluated
    at order time:

        weighted_flow = sum( signed_vol_i * exp(-(t_order - t_i) / tau) )
        for prints with t_order - window <= t_i <= t_order

    with tau = 5s (half-life ~3.47s). All other r2 mechanics are preserved
    verbatim: max_consecutive_skips=3, direction-change force-submit, hard-cap
    force-submit, reduce-only short-circuit, first-signal warm-up, on_reset
    semantics. The skip threshold is held at 2.0 to isolate the decay change
    as the sole variable vs r2.

Look-ahead-free: only prints with ts_event <= order.ts_init are weighted (the
deque is built from chronologically-replayed trade ticks, and the weighted
sum loop explicitly skips any same-nanosecond edge case where a tick's
ts_event might equal or exceed the order's ts_init).

Quantity invariant: never modify order.quantity. Only submit or skip.
"""
from __future__ import annotations

import math
from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class AFGPCR5Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the afg-pc-r5 Time-Decayed AFG algorithm.

    Parameters
    ----------
    window_seconds : float
        Rolling look-back window for trade prints. Default 10.0s (matches r2).
        Prints older than this at decision time are dropped from the deque.
    flow_threshold : float
        Absolute weighted-flow magnitude required to trigger a skip. Default
        2.0 (matches r2). Held constant to isolate the decay variable.
    tau_seconds : float
        EWMA time constant. Per-print weight = exp(-(t_order - t_i)/tau).
        Default 5.0s (half-life ~3.47s; principled compromise between strong
        recency emphasis and meaningful older-half context).
    max_consecutive_skips : int
        Hard cap on chain length before force-submit. Default 3 (matches r2).
    """

    window_seconds: float = 10.0
    flow_threshold: float = 2.0
    tau_seconds: float = 5.0
    max_consecutive_skips: int = 3


class AFGPCR5Algorithm(ExecAlgorithm):
    """Time-decayed AFG with r2 directional-chain state machine."""

    def __init__(self, config: AFGPCR5Config) -> None:
        super().__init__(config=config)
        assert config.window_seconds > 0, "window_seconds must be > 0"
        assert config.flow_threshold > 0, "flow_threshold must be > 0"
        assert config.tau_seconds > 0, "tau_seconds must be > 0"
        assert config.max_consecutive_skips >= 1, (
            "max_consecutive_skips must be >= 1"
        )

        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._tau_ns: float = float(config.tau_seconds) * 1_000_000_000.0
        self._flow_threshold: float = float(config.flow_threshold)
        self._max_consecutive_skips: int = int(config.max_consecutive_skips)

        # Deque of (ts_event_ns: int, signed_vol: float)
        self._flow_deque: deque[tuple[int, float]] = deque()

        # First-signal / warm-up unconditional submit (matches r2)
        self._position_flat: bool = True

        # Directional-chain state (matches r2)
        self._consecutive_skips: int = 0
        self._last_skipped_side: OrderSide | None = None

        # Subscription tracking
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"AFGPCR5Algorithm started "
            f"(window={self._window_ns / 1e9:.1f}s, "
            f"tau={self._tau_ns / 1e9:.1f}s, "
            f"flow_threshold={self._flow_threshold:.2f}, "
            f"max_consecutive_skips={self._max_consecutive_skips})."
        )

    def on_reset(self) -> None:
        self._flow_deque.clear()
        self._position_flat = True
        self._consecutive_skips = 0
        self._last_skipped_side = None
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
    # Trade tick handler — append to flow deque
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

    # ------------------------------------------------------------------
    # Window pruning + EWMA-weighted gate evaluation
    # ------------------------------------------------------------------

    def _prune_window(self, cutoff_ns: int) -> None:
        """Remove deque entries older than cutoff_ns."""
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            self._flow_deque.popleft()

    def _weighted_flow(self, order_ts_ns: int) -> float:
        """Compute EWMA-weighted signed flow at order_ts_ns.

        weighted_flow = sum( signed_vol_i * exp(-(t_order - t_i) / tau) )
        over deque entries with t_i <= t_order.

        Returns 0.0 when the deque is empty.
        """
        if not self._flow_deque:
            return 0.0

        tau_ns = self._tau_ns
        total = 0.0
        for ts_ns, signed_vol in self._flow_deque:
            # Skip same-nanosecond edge case where a tick might equal the
            # order's ts_init (treat as not-yet-observed for safety).
            dt = order_ts_ns - ts_ns
            if dt < 0:
                continue
            total += signed_vol * math.exp(-dt / tau_ns)
        return total

    def _flow_is_adverse(self, order) -> bool:
        """Return True iff weighted aggressor flow is adverse to order side.

        BUY  order: adverse when weighted_flow <= -flow_threshold
        SELL order: adverse when weighted_flow >=  flow_threshold

        Returns False (do not skip) when:
          - Flow deque is empty (warm-up / thin market)
          - |weighted_flow| < flow_threshold (neutral / near-balanced)
        """
        cutoff_ns = order.ts_init - self._window_ns
        self._prune_window(cutoff_ns)

        if not self._flow_deque:
            return False

        wf = self._weighted_flow(order.ts_init)

        if order.side == OrderSide.BUY:
            return wf <= -self._flow_threshold
        else:  # SELL
            return wf >= self._flow_threshold

    # ------------------------------------------------------------------
    # State-machine helpers (identical to r2)
    # ------------------------------------------------------------------

    def _reset_chain(self) -> None:
        self._consecutive_skips = 0
        self._last_skipped_side = None

    def _record_skip(self, side: OrderSide) -> None:
        self._consecutive_skips += 1
        self._last_skipped_side = side

    # ------------------------------------------------------------------
    # Main order handler (chain state machine — identical to r2)
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only orders always submit (intraday_flat).
        if order.is_reduce_only:
            self.submit_order(order)
            return

        # First-signal / post-warm-up unconditional submit.
        if self._position_flat:
            self._position_flat = False
            self._reset_chain()
            self.submit_order(order)
            return

        # ----- Directional-chain state machine (r2 verbatim) -----
        if self._consecutive_skips == 0:
            if self._flow_is_adverse(order):
                self.log.info(
                    f"SKIP {order.client_order_id} — adverse weighted flow; "
                    f"starting chain (side="
                    f"{'BUY' if order.side == OrderSide.BUY else 'SELL'})."
                )
                self._record_skip(order.side)
                return
            else:
                self._reset_chain()
                self.submit_order(order)
                return

        # consecutive_skips >= 1: chain is active.

        # Direction change — force-submit and reset.
        if order.side != self._last_skipped_side:
            self.log.info(
                f"FORCE-SUBMIT {order.client_order_id} — direction change "
                f"(chain length was {self._consecutive_skips})."
            )
            self._reset_chain()
            self.submit_order(order)
            return

        # Hard cap — force-submit and reset.
        if self._consecutive_skips >= self._max_consecutive_skips:
            self.log.info(
                f"FORCE-SUBMIT {order.client_order_id} — hard cap reached "
                f"(consecutive_skips={self._consecutive_skips})."
            )
            self._reset_chain()
            self.submit_order(order)
            return

        # Gate re-evaluation on same-direction follow-up.
        if self._flow_is_adverse(order):
            self.log.info(
                f"SKIP {order.client_order_id} — chain extension "
                f"(consecutive_skips={self._consecutive_skips + 1})."
            )
            self._record_skip(order.side)
            return
        else:
            self._reset_chain()
            self.submit_order(order)
            return

    def on_quote_tick(self, tick) -> None:
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_seconds: float = 10.0,
    flow_threshold: float = 2.0,
    tau_seconds: float = 5.0,
    max_consecutive_skips: int = 3,
) -> AFGPCR5Algorithm:
    """Instantiate the afg-pc-r5 Time-Decayed AFG algorithm."""
    config = AFGPCR5Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        flow_threshold=flow_threshold,
        tau_seconds=tau_seconds,
        max_consecutive_skips=max_consecutive_skips,
    )
    return AFGPCR5Algorithm(config=config)
