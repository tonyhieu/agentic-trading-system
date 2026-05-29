"""afg-pc-r2 — Persistent-Flow AFG with directional-chain condition.

Refinement of aggressor-flow-gate (base). Same gate criterion (single 10s
rolling window of signed aggressor flow; skip BUY when net_flow<=-2.0,
skip SELL when net_flow>=+2.0; reduce-only always submits), EXCEPT the
post-skip anti-cascade is replaced with a directional conditional re-entry:

  State variables:
    _consecutive_skips : int = 0
    _last_skipped_side : OrderSide | None = None

  After a skip, do NOT set _position_flat=True. On the next open order
  with side S:

    (i)  if _consecutive_skips == 0
         (first signal or post-reset):
         apply AFG's normal gate — skip on adverse and update chain state;
         else submit and ensure chain state is reset.

    (ii) if _consecutive_skips >= 1:
         (a) if S != _last_skipped_side (DIRECTION CHANGE — possible
             legitimate reversal): force-submit unconditionally, reset state.
         (b) elif _consecutive_skips >= max_consecutive_skips (hard cap,
             default 3): force-submit unconditionally, reset state.
         (c) else evaluate AFG's gate:
             - if it fires (still adverse in same direction): skip, increment.
             - if it does NOT fire (regime has cleared): submit, reset state.

  Reduce-only orders always submit (intraday_flat compliance) and never
  participate in the chain state.

  First-signal handling: on the very first open order after warm-up
  (_position_flat == True), submit unconditionally and clear _position_flat,
  matching base AFG semantics.

No look-ahead: only trade ticks with ts_event <= order.ts_init are in
the deque at decision time.

Quantity invariant: never modify order.quantity. Only submit or skip.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class AFGPCR2Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the afg-pc-r2 Persistent-Flow AFG algorithm.

    Parameters
    ----------
    window_seconds : float
        Rolling look-back window for trade prints, in seconds. Default 10.0s
        (matches base AFG).
    flow_threshold : float
        Minimum absolute net signed flow (in contracts) to trigger a skip.
        Default 2.0 contracts (matches base AFG).
    max_consecutive_skips : int
        Hard cap on the number of consecutive same-direction skips before
        the algorithm force-submits unconditionally. Bounds deferred-entry
        risk during very long persistent regimes. Default 3 (~3 oracle
        signals at the configured signal_interval_seconds=1.0).
    """

    window_seconds: float = 10.0
    flow_threshold: float = 2.0
    max_consecutive_skips: int = 3


class AFGPCR2Algorithm(ExecAlgorithm):
    """Persistent-Flow AFG execution algorithm — see module docstring."""

    def __init__(self, config: AFGPCR2Config) -> None:
        super().__init__(config=config)
        assert config.window_seconds > 0, "window_seconds must be > 0"
        assert config.flow_threshold > 0, "flow_threshold must be > 0"
        assert config.max_consecutive_skips >= 1, (
            "max_consecutive_skips must be >= 1"
        )

        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._flow_threshold: float = float(config.flow_threshold)
        self._max_consecutive_skips: int = int(config.max_consecutive_skips)

        # Deque of (ts_event_ns: int, signed_vol: float)
        # signed_vol = +size (BUYER), -size (SELLER), 0 (NO_AGGRESSOR)
        self._flow_deque: deque[tuple[int, float]] = deque()

        # Running sum of signed volume in the deque (for O(1) updates)
        self._net_flow: float = 0.0

        # First-signal / warm-up unconditional submit (matches base AFG)
        self._position_flat: bool = True

        # Directional-chain state
        self._consecutive_skips: int = 0
        self._last_skipped_side: OrderSide | None = None

        # Subscription tracking
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"AFGPCR2Algorithm started "
            f"(window={self._window_ns / 1e9:.1f}s, "
            f"flow_threshold={self._flow_threshold:.2f}, "
            f"max_consecutive_skips={self._max_consecutive_skips})."
        )

    def on_reset(self) -> None:
        self._flow_deque.clear()
        self._net_flow = 0.0
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
            self.subscribe_quote_ticks(instrument_id)  # keep quote cache warm
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Trade tick handler — maintain rolling signed flow deque
    # ------------------------------------------------------------------

    def on_trade_tick(self, tick) -> None:
        aggressor = tick.aggressor_side
        size = float(str(tick.size))

        if aggressor == AggressorSide.BUYER:
            signed_vol = size
        elif aggressor == AggressorSide.SELLER:
            signed_vol = -size
        else:
            # NO_AGGRESSOR: neutral
            signed_vol = 0.0

        self._flow_deque.append((tick.ts_event, signed_vol))
        self._net_flow += signed_vol

    # ------------------------------------------------------------------
    # Window pruning + gate evaluation
    # ------------------------------------------------------------------

    def _prune_window(self, cutoff_ns: int) -> None:
        """Remove deque entries older than cutoff_ns, updating _net_flow."""
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            _, old_vol = self._flow_deque.popleft()
            self._net_flow -= old_vol

    def _flow_is_adverse(self, order) -> bool:
        """Return True iff net aggressor flow is adverse to order direction.

        Identical gate criterion to base AFG. Returns False (do not skip)
        when:
          - Flow deque is empty (warm-up / thin market)
          - |net_flow| < flow_threshold (neutral / near-balanced)
        """
        cutoff_ns = order.ts_init - self._window_ns
        self._prune_window(cutoff_ns)

        if not self._flow_deque:
            return False

        net = self._net_flow

        if order.side == OrderSide.BUY:
            return net <= -self._flow_threshold
        else:  # SELL
            return net >= self._flow_threshold

    # ------------------------------------------------------------------
    # State-machine helpers
    # ------------------------------------------------------------------

    def _reset_chain(self) -> None:
        self._consecutive_skips = 0
        self._last_skipped_side = None

    def _record_skip(self, side: OrderSide) -> None:
        self._consecutive_skips += 1
        self._last_skipped_side = side

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        # Do not modify chain state — closing orders are orthogonal to the
        # entry-gating logic.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # First-signal / post-warm-up unconditional submit (matches base AFG).
        if self._position_flat:
            self.log.debug(
                f"First open (warm-up); submitting "
                f"{order.client_order_id} unconditionally."
            )
            self._position_flat = False
            self._reset_chain()
            self.submit_order(order)
            return

        # ----- Directional-chain state machine -----
        if self._consecutive_skips == 0:
            # No active chain: behave like base AFG's gate, but DO NOT
            # set _position_flat after a skip — start the chain instead.
            if self._flow_is_adverse(order):
                self.log.info(
                    f"SKIP {order.client_order_id} — adverse flow "
                    f"(net_flow={self._net_flow:.2f}, side="
                    f"{'BUY' if order.side == OrderSide.BUY else 'SELL'}); "
                    f"starting chain."
                )
                self._record_skip(order.side)
                # Quantity invariant: no submit_order call.
                return
            else:
                self.log.debug(
                    f"SUBMIT {order.client_order_id} — flow neutral/favorable "
                    f"(net_flow={self._net_flow:.2f})."
                )
                # Chain already inactive; ensure state is clean.
                self._reset_chain()
                self.submit_order(order)
                return

        # consecutive_skips >= 1: chain is active.

        # (ii.a) Direction change — force-submit and reset.
        if order.side != self._last_skipped_side:
            self.log.info(
                f"FORCE-SUBMIT {order.client_order_id} — direction change "
                f"(chain side={self._last_skipped_side}, new side={order.side}); "
                f"resetting chain (length was {self._consecutive_skips})."
            )
            self._reset_chain()
            self.submit_order(order)
            return

        # (ii.b) Hard cap — force-submit and reset.
        if self._consecutive_skips >= self._max_consecutive_skips:
            self.log.info(
                f"FORCE-SUBMIT {order.client_order_id} — hard cap reached "
                f"(consecutive_skips={self._consecutive_skips} >= "
                f"max={self._max_consecutive_skips}); resetting chain."
            )
            self._reset_chain()
            self.submit_order(order)
            return

        # (ii.c) Gate re-evaluation on same-direction follow-up.
        if self._flow_is_adverse(order):
            self.log.info(
                f"SKIP {order.client_order_id} — chain extension "
                f"(consecutive_skips={self._consecutive_skips + 1}, "
                f"net_flow={self._net_flow:.2f}, side="
                f"{'BUY' if order.side == OrderSide.BUY else 'SELL'})."
            )
            self._record_skip(order.side)
            # Quantity invariant: no submit_order call.
            return
        else:
            self.log.debug(
                f"SUBMIT {order.client_order_id} — chain cleared "
                f"(net_flow={self._net_flow:.2f}); resetting chain."
            )
            self._reset_chain()
            self.submit_order(order)
            return

    def on_quote_tick(self, tick) -> None:
        """Passively receive quote ticks (kept for quote-cache side-effects)."""
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_seconds: float = 10.0,
    flow_threshold: float = 2.0,
    max_consecutive_skips: int = 3,
) -> AFGPCR2Algorithm:
    """Instantiate and return the AFGPCR2Algorithm (Persistent-Flow AFG).

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_seconds : float
        Rolling window for aggressor-flow accumulation, in seconds.
        Default 10.0s (matches base AFG).
    flow_threshold : float
        Minimum absolute net aggressor flow (contracts) to trigger a skip.
        Default 2.0 contracts (matches base AFG).
    max_consecutive_skips : int
        Hard cap on the number of consecutive same-direction skips before
        the algorithm force-submits unconditionally. Default 3.
    """
    config = AFGPCR2Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        flow_threshold=flow_threshold,
        max_consecutive_skips=max_consecutive_skips,
    )
    return AFGPCR2Algorithm(config=config)
