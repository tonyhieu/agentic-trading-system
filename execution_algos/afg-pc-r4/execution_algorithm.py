"""afg-pc-r4 — Extended-Chain AFG (max_consecutive_skips=5).

Verbatim re-implementation of afg-pc-r2's directional-chain state machine,
with a single parameter change: the hard cap on consecutive same-direction
skips is raised from 3 to 5. All other mechanics — signed 10s rolling
window of aggressor flow, 2.0 flow threshold, direction-change reset,
first-signal warm-up unconditional submit, reduce-only short-circuit,
on_reset state clear — are preserved exactly.

Hypothesis: r2's cap=3 may be cutting persistent-regime suppression too
short on heavy-volume days; raising the cap to 5 directly tests whether
the cap is currently the binding constraint. r2's suggested-next-attempt
#1 verbatim.

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


class AFGPCR4Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the afg-pc-r4 Extended-Chain AFG algorithm.

    Parameters
    ----------
    window_seconds : float
        Rolling look-back window for trade prints, in seconds. Default 10.0s.
    flow_threshold : float
        Minimum absolute net signed flow (in contracts) to trigger a skip.
        Default 2.0 contracts (matches base AFG and r2).
    max_consecutive_skips : int
        Hard cap on the number of consecutive same-direction skips before
        the algorithm force-submits unconditionally. Default 5 (raised from
        r2's default of 3).
    """

    window_seconds: float = 10.0
    flow_threshold: float = 2.0
    max_consecutive_skips: int = 5


class AFGPCR4Algorithm(ExecAlgorithm):
    """Extended-Chain AFG execution algorithm — see module docstring."""

    def __init__(self, config: AFGPCR4Config) -> None:
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
        self._flow_deque: deque[tuple[int, float]] = deque()
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
            f"AFGPCR4Algorithm started "
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

        # Reduce-only orders always execute (intraday_flat compliance).
        if order.is_reduce_only:
            self.submit_order(order)
            return

        # First-signal / post-warm-up unconditional submit (matches base AFG).
        if self._position_flat:
            self._position_flat = False
            self._reset_chain()
            self.submit_order(order)
            return

        # ----- Directional-chain state machine -----
        if self._consecutive_skips == 0:
            if self._flow_is_adverse(order):
                self._record_skip(order.side)
                return
            else:
                self._reset_chain()
                self.submit_order(order)
                return

        # consecutive_skips >= 1: chain is active.

        # Direction change — force-submit and reset.
        if order.side != self._last_skipped_side:
            self._reset_chain()
            self.submit_order(order)
            return

        # Hard cap — force-submit and reset.
        if self._consecutive_skips >= self._max_consecutive_skips:
            self._reset_chain()
            self.submit_order(order)
            return

        # Gate re-evaluation on same-direction follow-up.
        if self._flow_is_adverse(order):
            self._record_skip(order.side)
            return
        else:
            self._reset_chain()
            self.submit_order(order)
            return


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_seconds: float = 10.0,
    flow_threshold: float = 2.0,
    max_consecutive_skips: int = 5,
) -> AFGPCR4Algorithm:
    """Instantiate and return the AFGPCR4Algorithm (Extended-Chain AFG)."""
    config = AFGPCR4Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        flow_threshold=flow_threshold,
        max_consecutive_skips=max_consecutive_skips,
    )
    return AFGPCR4Algorithm(config=config)
