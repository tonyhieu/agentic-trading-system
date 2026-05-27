"""afg-pc-r6 — Two-Path Additive AFG with conservative acute-burst threshold.

Refinement of afg-pc-r2 (empirical winner). Preserves r2's directional-chain
state machine, max_consecutive_skips=3, and 10s "long" gate (Path A) verbatim.
ADDS Path B: an acute-burst gate over a 2s short window with a high threshold
(burst_threshold=5.0). The OVERALL gate fires when Path A OR Path B fires.

  Mechanism at each open-order decision:
    long_net  = sum signed_vol over (t_order - 10s, t_order]
    short_net = sum signed_vol over (t_order -  2s, t_order]

    Path A (BUY)  : long_net  <= -long_threshold   (default 2.0)
    Path A (SELL) : long_net  >= +long_threshold
    Path B (BUY)  : short_net <= -burst_threshold  (default 5.0)
    Path B (SELL) : short_net >= +burst_threshold

    Overall gate fires iff Path A OR Path B fires.

  Chain state machine (from afg-pc-r2 verbatim):
    State: _consecutive_skips (int), _last_skipped_side (OrderSide | None)
    Reduce-only orders always submit (intraday_flat compliance).
    First-signal warm-up (_position_flat == True): submit unconditionally.

    If consecutive_skips == 0:
      adverse -> skip and start chain;
      not adverse -> submit and ensure chain reset.

    If consecutive_skips >= 1:
      side != last_skipped_side (direction change) -> force-submit, reset.
      consecutive_skips >= max_consecutive_skips    -> force-submit, reset.
      adverse (same direction, under cap)           -> skip, increment.
      not adverse                                   -> submit, reset.

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


class AFGPCR6Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for afg-pc-r6 Two-Path Additive AFG.

    Parameters
    ----------
    long_window_seconds : float
        Long-window rolling look-back (Path A). Default 10.0s (matches r2/base AFG).
    long_threshold : float
        Path A skip threshold on long-window signed flow. Default 2.0 contracts.
    short_window_seconds : float
        Short-window rolling look-back (Path B). Default 2.0s.
    burst_threshold : float
        Path B skip threshold on short-window signed flow. Default 5.0 contracts
        (conservative — fires only on genuinely acute concentrated bursts).
    max_consecutive_skips : int
        Hard cap on consecutive same-direction skips before force-submit. Default 3.
    """

    long_window_seconds: float = 10.0
    long_threshold: float = 2.0
    short_window_seconds: float = 2.0
    burst_threshold: float = 5.0
    max_consecutive_skips: int = 3


class AFGPCR6Algorithm(ExecAlgorithm):
    """Two-Path Additive AFG — see module docstring."""

    def __init__(self, config: AFGPCR6Config) -> None:
        super().__init__(config=config)
        assert config.long_window_seconds > 0, "long_window_seconds must be > 0"
        assert config.short_window_seconds > 0, "short_window_seconds must be > 0"
        assert config.short_window_seconds < config.long_window_seconds, (
            "short_window_seconds must be < long_window_seconds"
        )
        assert config.long_threshold > 0, "long_threshold must be > 0"
        assert config.burst_threshold > 0, "burst_threshold must be > 0"
        assert config.max_consecutive_skips >= 1, (
            "max_consecutive_skips must be >= 1"
        )

        self._long_window_ns: int = int(config.long_window_seconds * 1_000_000_000)
        self._short_window_ns: int = int(config.short_window_seconds * 1_000_000_000)
        self._long_threshold: float = float(config.long_threshold)
        self._burst_threshold: float = float(config.burst_threshold)
        self._max_consecutive_skips: int = int(config.max_consecutive_skips)

        # Single deque of (ts_event_ns: int, signed_vol: float)
        # Pruned to the LONG window; short_net computed by scanning tail at
        # each decision (entries with ts >= t_order - short_window_ns).
        self._flow_deque: deque[tuple[int, float]] = deque()

        # Running sum of signed volume over the LONG window (O(1) updates).
        self._long_net: float = 0.0

        # First-signal / warm-up unconditional submit.
        self._position_flat: bool = True

        # Directional-chain state.
        self._consecutive_skips: int = 0
        self._last_skipped_side: OrderSide | None = None

        # Subscription tracking.
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"AFGPCR6Algorithm started "
            f"(long_window={self._long_window_ns / 1e9:.1f}s, "
            f"long_threshold={self._long_threshold:.2f}, "
            f"short_window={self._short_window_ns / 1e9:.1f}s, "
            f"burst_threshold={self._burst_threshold:.2f}, "
            f"max_consecutive_skips={self._max_consecutive_skips})."
        )

    def on_reset(self) -> None:
        self._flow_deque.clear()
        self._long_net = 0.0
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
    # Trade tick handler — append to deque, update long_net
    # ------------------------------------------------------------------

    def on_trade_tick(self, tick) -> None:
        aggressor = tick.aggressor_side
        size = float(str(tick.size))

        if aggressor == AggressorSide.BUYER:
            signed_vol = size
        elif aggressor == AggressorSide.SELLER:
            signed_vol = -size
        else:
            # NO_AGGRESSOR — neutral
            signed_vol = 0.0

        self._flow_deque.append((tick.ts_event, signed_vol))
        self._long_net += signed_vol

    # ------------------------------------------------------------------
    # Window pruning + dual-window gate evaluation
    # ------------------------------------------------------------------

    def _prune_long_window(self, cutoff_ns: int) -> None:
        """Remove deque entries older than cutoff_ns, updating _long_net."""
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            _, old_vol = self._flow_deque.popleft()
            self._long_net -= old_vol

    def _compute_short_net(self, short_cutoff_ns: int) -> float:
        """Sum signed_vol over entries with ts_event >= short_cutoff_ns.

        Walks the deque tail from newest to oldest, stopping once an older
        entry is encountered. Deque entries are in chronological order
        (oldest at index 0, newest at the right), so iterating reversed()
        terminates as soon as ts < short_cutoff_ns.
        """
        short_net = 0.0
        # reversed() on a deque is O(N) over entries seen; we break early.
        for ts, vol in reversed(self._flow_deque):
            if ts < short_cutoff_ns:
                break
            short_net += vol
        return short_net

    def _gate_fires(self, order) -> bool:
        """Return True iff Path A OR Path B fires (skip the order)."""
        long_cutoff_ns = order.ts_init - self._long_window_ns
        self._prune_long_window(long_cutoff_ns)

        if not self._flow_deque:
            return False  # Warm-up — no data, no skip.

        # Path A (long window).
        if order.side == OrderSide.BUY:
            path_a = self._long_net <= -self._long_threshold
        else:  # SELL
            path_a = self._long_net >= self._long_threshold

        if path_a:
            return True

        # Path B (short window, computed on demand).
        short_cutoff_ns = order.ts_init - self._short_window_ns
        short_net = self._compute_short_net(short_cutoff_ns)

        if order.side == OrderSide.BUY:
            return short_net <= -self._burst_threshold
        else:  # SELL
            return short_net >= self._burst_threshold

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
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # First-signal / post-warm-up unconditional submit.
        if self._position_flat:
            self.log.debug(
                f"First open (warm-up); submitting {order.client_order_id} "
                f"unconditionally."
            )
            self._position_flat = False
            self._reset_chain()
            self.submit_order(order)
            return

        # ----- Directional-chain state machine -----
        if self._consecutive_skips == 0:
            if self._gate_fires(order):
                self.log.info(
                    f"SKIP {order.client_order_id} — adverse flow "
                    f"(long_net={self._long_net:.2f}, side="
                    f"{'BUY' if order.side == OrderSide.BUY else 'SELL'}); "
                    f"starting chain."
                )
                self._record_skip(order.side)
                return
            else:
                self._reset_chain()
                self.submit_order(order)
                return

        # consecutive_skips >= 1: chain active.

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
        if self._gate_fires(order):
            self.log.info(
                f"SKIP {order.client_order_id} — chain extension "
                f"(consecutive_skips={self._consecutive_skips + 1}, "
                f"long_net={self._long_net:.2f}, side="
                f"{'BUY' if order.side == OrderSide.BUY else 'SELL'})."
            )
            self._record_skip(order.side)
            return
        else:
            self._reset_chain()
            self.submit_order(order)
            return

    def on_quote_tick(self, tick) -> None:
        """Passively receive quote ticks (quote-cache side-effects only)."""
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    long_window_seconds: float = 10.0,
    long_threshold: float = 2.0,
    short_window_seconds: float = 2.0,
    burst_threshold: float = 5.0,
    max_consecutive_skips: int = 3,
) -> AFGPCR6Algorithm:
    """Instantiate and return the AFGPCR6Algorithm (Two-Path Additive AFG).

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    long_window_seconds : float
        Path A long-window (default 10.0s, matches r2/base AFG).
    long_threshold : float
        Path A threshold (default 2.0 contracts, matches r2/base AFG).
    short_window_seconds : float
        Path B short-window (default 2.0s).
    burst_threshold : float
        Path B acute-burst threshold (default 5.0 contracts; conservative).
    max_consecutive_skips : int
        Hard cap on consecutive same-direction skips (default 3).
    """
    config = AFGPCR6Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        long_window_seconds=long_window_seconds,
        long_threshold=long_threshold,
        short_window_seconds=short_window_seconds,
        burst_threshold=burst_threshold,
        max_consecutive_skips=max_consecutive_skips,
    )
    return AFGPCR6Algorithm(config=config)
