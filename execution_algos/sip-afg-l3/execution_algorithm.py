"""sip-afg-l3 execution algorithm.

Two-window confirmation variant of `aggressor-flow-gate`.

Mechanism:
  - Maintain TWO rolling signed-volume deques over trade ticks:
      * a 10-second outer deque (same as base algo)
      * a 3-second inner deque (NEW — confirmation window)
    signed_volume = +size for BUYER aggressor, -size for SELLER
    aggressor, 0 for NO_AGGRESSOR.
  - At each open-order event, prune both deques by their respective
    cutoffs (10s and 3s before order.ts_init).
  - Compute net_flow_10s and net_flow_3s.
  - For BUY  orders: skip when net_flow_10s <= -outer_threshold (2.0)
                          AND net_flow_3s  <= -inner_threshold (1.0).
  - For SELL orders: skip when net_flow_10s >=  outer_threshold (2.0)
                          AND net_flow_3s  >=  inner_threshold (1.0).
  - If EITHER deque is empty (warm-up) or the AND condition fails,
    submit unconditionally.
  - Reduce-only / position-closing orders always execute.
  - After any skip: _position_flat = True so the NEXT open is
    unconditional (anti-cascade, preserved verbatim from base).

Rationale (vs base aggressor-flow-gate):
  The base algo's 10s single-window gate fires on the TAIL of a
  transient flow burst even after the pressure has dissipated. A
  10-contract sweep at t=-9s leaves net_flow_10s = +10 for nearly 10
  more seconds, but if no further buying continues in t = [-3s, 0],
  the buying pressure is over. The 3s confirmation requirement ensures
  the gate fires only when adverse flow is *currently active*, not
  when it is a stale-but-still-windowed legacy of a finished burst.
  This addresses the IS regression the base's NOTES.md flags
  ("the filter holds back entries during adverse-flow periods, but
  those exact moments sometimes offer the best fill prices").

No look-ahead bias: only trade ticks with ts_event <= order.ts_init
are in either deque at decision time (replay is strictly chronological;
the window prune uses the order's ts_init, not a future timestamp).

Constraint compliance:
  - Quantity invariant: never modify order.quantity (only submit/skip).
  - top_of_book_only / participation_cap: untouched — gate-only algo.
  - intraday_flat: reduce-only orders always submit.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class SipAfgL3Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the sip-afg-l3 execution algorithm.

    Parameters
    ----------
    outer_window_seconds : float
        Outer rolling window, in seconds. Default 10.0 (same as base).
    inner_window_seconds : float
        Inner (confirmation) rolling window, in seconds. Default 3.0.
    outer_threshold : float
        Minimum absolute net signed flow over the outer window to flag
        adverse. Default 2.0 contracts (same as base).
    inner_threshold : float
        Minimum absolute net signed flow over the inner window to
        CONFIRM adverse. Default 1.0 contract. Both outer AND inner
        must exceed their threshold for a skip.
    """

    outer_window_seconds: float = 10.0
    inner_window_seconds: float = 3.0
    outer_threshold: float = 2.0
    inner_threshold: float = 1.0


class SipAfgL3Algorithm(ExecAlgorithm):
    """Two-window confirmation aggressor-flow gate.

    Opening orders (is_reduce_only == False):
      - Evaluate signed aggressor flow over BOTH the 10s outer window
        and the 3s inner (confirmation) window.
      - BUY: skip iff net_10s <= -outer_threshold AND
                       net_3s  <= -inner_threshold.
      - SELL: skip iff net_10s >=  outer_threshold AND
                        net_3s  >=  inner_threshold.
      - Otherwise (warm-up, or only one condition triggered, or
        neutral/favorable): submit unconditionally.
      - After any skip: _position_flat = True (next open unconditional).

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is ever modified.
    """

    def __init__(self, config: SipAfgL3Config) -> None:
        super().__init__(config=config)
        self._outer_window_ns: int = int(config.outer_window_seconds * 1_000_000_000)
        self._inner_window_ns: int = int(config.inner_window_seconds * 1_000_000_000)
        self._outer_threshold: float = config.outer_threshold
        self._inner_threshold: float = config.inner_threshold

        # Two parallel deques of (ts_event_ns, signed_vol).
        # The 3s deque is a strict subset of the 10s deque, but kept
        # separate for O(1) running-sum maintenance.
        self._outer_deque: deque[tuple[int, float]] = deque()
        self._inner_deque: deque[tuple[int, float]] = deque()

        self._net_flow_outer: float = 0.0
        self._net_flow_inner: float = 0.0

        self._position_flat: bool = True
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"SipAfgL3Algorithm started "
            f"(outer={self._outer_window_ns / 1e9:.1f}s "
            f"threshold={self._outer_threshold:.1f}, "
            f"inner={self._inner_window_ns / 1e9:.1f}s "
            f"threshold={self._inner_threshold:.1f})."
        )

    def on_reset(self) -> None:
        self._outer_deque.clear()
        self._inner_deque.clear()
        self._net_flow_outer = 0.0
        self._net_flow_inner = 0.0
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
    # Trade tick handler — maintain BOTH rolling deques
    # ------------------------------------------------------------------

    def on_trade_tick(self, tick) -> None:
        """Update both signed-flow deques with the incoming trade tick."""
        aggressor = tick.aggressor_side
        size = float(str(tick.size))

        if aggressor == AggressorSide.BUYER:
            signed_vol = size
        elif aggressor == AggressorSide.SELLER:
            signed_vol = -size
        else:
            # NO_AGGRESSOR — neutral; do not bias either window.
            signed_vol = 0.0

        ts = tick.ts_event
        self._outer_deque.append((ts, signed_vol))
        self._net_flow_outer += signed_vol
        self._inner_deque.append((ts, signed_vol))
        self._net_flow_inner += signed_vol

    # ------------------------------------------------------------------
    # Window pruning helpers
    # ------------------------------------------------------------------

    def _prune_outer(self, cutoff_ns: int) -> None:
        while self._outer_deque and self._outer_deque[0][0] < cutoff_ns:
            _, old_vol = self._outer_deque.popleft()
            self._net_flow_outer -= old_vol

    def _prune_inner(self, cutoff_ns: int) -> None:
        while self._inner_deque and self._inner_deque[0][0] < cutoff_ns:
            _, old_vol = self._inner_deque.popleft()
            self._net_flow_inner -= old_vol

    # ------------------------------------------------------------------
    # Two-window gate
    # ------------------------------------------------------------------

    def _flow_is_adverse_confirmed(self, order) -> bool:
        """Return True iff BOTH the outer 10s and inner 3s flows are
        adverse for this order direction.

        Warm-up: if either deque is empty after pruning, return False
        (submit unconditionally) — matches base algo's empty-window
        behavior.
        """
        ts_init = order.ts_init
        self._prune_outer(ts_init - self._outer_window_ns)
        self._prune_inner(ts_init - self._inner_window_ns)

        if not self._outer_deque or not self._inner_deque:
            # Warm-up / thin market — do not gate.
            return False

        net_outer = self._net_flow_outer
        net_inner = self._net_flow_inner

        if order.side == OrderSide.BUY:
            if (
                net_outer <= -self._outer_threshold
                and net_inner <= -self._inner_threshold
            ):
                self.log.debug(
                    f"BUY adverse-confirmed: net_10s={net_outer:.2f} <= "
                    f"-outer={-self._outer_threshold:.2f}, "
                    f"net_3s={net_inner:.2f} <= "
                    f"-inner={-self._inner_threshold:.2f}; SKIP."
                )
                return True
        else:  # SELL
            if (
                net_outer >= self._outer_threshold
                and net_inner >= self._inner_threshold
            ):
                self.log.debug(
                    f"SELL adverse-confirmed: net_10s={net_outer:.2f} >= "
                    f"outer={self._outer_threshold:.2f}, "
                    f"net_3s={net_inner:.2f} >= "
                    f"inner={self._inner_threshold:.2f}; SKIP."
                )
                return True

        return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on confirmed adverse flow."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} "
                f"immediately."
            )
            self.submit_order(order)
            return

        # Anti-cascade: forced re-entry after any skip.
        if self._position_flat:
            self.log.debug(
                f"Re-entry (first or post-skip); submitting "
                f"{order.client_order_id} unconditionally."
            )
            self._position_flat = False
            self.submit_order(order)
            return

        if self._flow_is_adverse_confirmed(order):
            self.log.info(
                f"SKIP {order.client_order_id} — confirmed adverse flow "
                f"(net_10s={self._net_flow_outer:.2f}, "
                f"net_3s={self._net_flow_inner:.2f}, side="
                f"{'BUY' if order.side == OrderSide.BUY else 'SELL'})."
            )
            self._position_flat = True
            # No submit_order call — quantity invariant preserved.
        else:
            self.log.debug(
                f"SUBMIT {order.client_order_id} — flow not confirmed "
                f"adverse (net_10s={self._net_flow_outer:.2f}, "
                f"net_3s={self._net_flow_inner:.2f})."
            )
            self._position_flat = False
            self.submit_order(order)

    def on_quote_tick(self, tick) -> None:
        """Passively receive quote ticks (kept for quote-cache side-effects)."""
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    outer_window_seconds: float = 10.0,
    inner_window_seconds: float = 3.0,
    outer_threshold: float = 2.0,
    inner_threshold: float = 1.0,
) -> SipAfgL3Algorithm:
    """Instantiate the SipAfgL3Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    outer_window_seconds : float
        Outer rolling window for aggressor-flow, in seconds.
        Default 10.0 (matches base aggressor-flow-gate).
    inner_window_seconds : float
        Inner (confirmation) rolling window, in seconds. Default 3.0.
    outer_threshold : float
        Outer-window adverse threshold (contracts). Default 2.0
        (matches base aggressor-flow-gate).
    inner_threshold : float
        Inner-window confirmation threshold (contracts). Default 1.0.
    """
    config = SipAfgL3Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        outer_window_seconds=outer_window_seconds,
        inner_window_seconds=inner_window_seconds,
        outer_threshold=outer_threshold,
        inner_threshold=inner_threshold,
    )
    return SipAfgL3Algorithm(config=config)
