"""afg-pc-r3 — Magnitude-Conditional Chained Gate (MCCG v2).

Refinement of aggressor-flow-gate (base) and afg-pc-r2 (persistent-flow chain).

Same gate primitive (single 10s rolling window of signed aggressor flow;
trade-tick subscription; look-ahead-free deque prune by ts_event), with a
THREE-REGIME tier dispatch on |net_flow|:

  - NEUTRAL: |net_flow| < weak_threshold (default 2.0)
    -> submit unconditionally (no signal).

  - WEAK ADVERSE: weak_threshold <= |net_flow| < strong_threshold
    AND direction is adverse to order side
    -> base AFG one-shot: skip + _position_flat=True (next open
       unconditional, no chaining).

  - STRONG ADVERSE: |net_flow| >= strong_threshold (default 50.0,
    empirical p70 of fired magnitudes from EDA on 20260308 + 20260316)
    AND direction is adverse to order side
    -> r2-style directional chain with hard cap (default 3):
       skip + record(consecutive_skips, last_skipped_side).

Chain re-evaluation (when _consecutive_skips >= 1):
  (a) order.side != _last_skipped_side  -> direction change ->
      force-submit + reset.
  (b) _consecutive_skips >= max_consecutive_skips  -> hard cap ->
      force-submit + reset.
  (c) else: re-evaluate using the STRONG threshold ONLY (not the weak):
      - still strong-adverse -> skip + increment.
      - decayed below strong  -> force-submit + reset.

  The chain ONLY persists while the magnitude justifies it. We do NOT
  fall back to the weak gate during chain re-eval; doing so would defeat
  the magnitude-condition's purpose by extending chains on decayed signals.

Reduce-only orders always submit, never modify chain state.

No look-ahead: deque is pruned by `order.ts_init`; trade-tick processing
is chronological.

Quantity invariant: never modify order.quantity. Only submit or skip.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class AFGPCR3Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for afg-pc-r3 MCCG v2.

    Parameters
    ----------
    window_seconds : float
        Rolling look-back window for trade prints, in seconds. Default 10.0s
        (matches base AFG and r2).
    weak_threshold : float
        Lower bound of the gate-firing zone (|net_flow| >= weak_threshold).
        Default 2.0 contracts (matches base AFG).
    strong_threshold : float
        Magnitude at which the directional chain engages. Empirical p70 of
        fired |net_flow| from EDA on 20260308 + 20260316. Default 50.0.
    max_consecutive_skips : int
        Hard cap on strong-tier chain length. Default 3 (matches r2).
    """

    window_seconds: float = 10.0
    weak_threshold: float = 2.0
    strong_threshold: float = 50.0
    max_consecutive_skips: int = 3


class AFGPCR3Algorithm(ExecAlgorithm):
    """Magnitude-Conditional Chained Gate execution algorithm — see module docstring."""

    def __init__(self, config: AFGPCR3Config) -> None:
        super().__init__(config=config)
        assert config.window_seconds > 0, "window_seconds must be > 0"
        assert config.weak_threshold > 0, "weak_threshold must be > 0"
        assert config.strong_threshold > config.weak_threshold, (
            "strong_threshold must be > weak_threshold"
        )
        assert config.max_consecutive_skips >= 1, (
            "max_consecutive_skips must be >= 1"
        )

        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._weak_threshold: float = float(config.weak_threshold)
        self._strong_threshold: float = float(config.strong_threshold)
        self._max_consecutive_skips: int = int(config.max_consecutive_skips)

        # Deque of (ts_event_ns, signed_vol). signed_vol = +size (BUYER),
        # -size (SELLER), 0 (NO_AGGRESSOR).
        self._flow_deque: deque[tuple[int, float]] = deque()

        # Running sum of signed volume in the deque (O(1) updates).
        self._net_flow: float = 0.0

        # First-signal / warm-up unconditional submit (matches base AFG / r2).
        self._position_flat: bool = True

        # Directional-chain state (strong-tier only).
        self._consecutive_skips: int = 0
        self._last_skipped_side: OrderSide | None = None

        # Subscription tracking.
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"AFGPCR3Algorithm started "
            f"(window={self._window_ns / 1e9:.1f}s, "
            f"weak_threshold={self._weak_threshold:.2f}, "
            f"strong_threshold={self._strong_threshold:.2f}, "
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
            signed_vol = 0.0  # NO_AGGRESSOR -> neutral

        self._flow_deque.append((tick.ts_event, signed_vol))
        self._net_flow += signed_vol

    # ------------------------------------------------------------------
    # Window pruning + flow inspection
    # ------------------------------------------------------------------

    def _prune_window(self, cutoff_ns: int) -> None:
        """Remove deque entries older than cutoff_ns, updating _net_flow."""
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            _, old_vol = self._flow_deque.popleft()
            self._net_flow -= old_vol

    def _current_net_flow(self, order) -> float:
        """Return net signed flow over the window ending at order.ts_init.

        Empty deque returns 0.0 (warm-up / thin market).
        """
        cutoff_ns = order.ts_init - self._window_ns
        self._prune_window(cutoff_ns)
        if not self._flow_deque:
            return 0.0
        return self._net_flow

    @staticmethod
    def _is_adverse(net: float, side: OrderSide) -> bool:
        """Direction sign check (independent of magnitude tier).

        BUY  is adverse when net < 0 (sellers dominate).
        SELL is adverse when net > 0 (buyers dominate).
        """
        if side == OrderSide.BUY:
            return net < 0.0
        else:  # SELL
            return net > 0.0

    # ------------------------------------------------------------------
    # State-machine helpers
    # ------------------------------------------------------------------

    def _reset_chain(self) -> None:
        self._consecutive_skips = 0
        self._last_skipped_side = None

    def _record_strong_skip(self, side: OrderSide) -> None:
        self._consecutive_skips += 1
        self._last_skipped_side = side

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        # Closing orders are orthogonal to the entry-gating chain state.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # First-signal / post-warm-up unconditional submit (matches base AFG / r2).
        if self._position_flat:
            self.log.debug(
                f"First open (warm-up); submitting "
                f"{order.client_order_id} unconditionally."
            )
            self._position_flat = False
            self._reset_chain()
            self.submit_order(order)
            return

        net = self._current_net_flow(order)
        abs_net = abs(net)

        # ----- Active chain branch (strong-tier persistence) -----
        if self._consecutive_skips >= 1:
            # (a) Direction change — force-submit + reset.
            if order.side != self._last_skipped_side:
                self.log.info(
                    f"FORCE-SUBMIT {order.client_order_id} — direction change "
                    f"(chain side={self._last_skipped_side}, "
                    f"new side={order.side}); resetting chain "
                    f"(length was {self._consecutive_skips})."
                )
                self._reset_chain()
                self.submit_order(order)
                return

            # (b) Hard cap — force-submit + reset.
            if self._consecutive_skips >= self._max_consecutive_skips:
                self.log.info(
                    f"FORCE-SUBMIT {order.client_order_id} — hard cap reached "
                    f"(consecutive_skips={self._consecutive_skips} >= "
                    f"max={self._max_consecutive_skips}); resetting chain."
                )
                self._reset_chain()
                self.submit_order(order)
                return

            # (c) Chain re-eval uses STRONG threshold ONLY (not weak).
            if abs_net >= self._strong_threshold and self._is_adverse(net, order.side):
                self.log.info(
                    f"SKIP {order.client_order_id} — chain extension "
                    f"(consecutive_skips={self._consecutive_skips + 1}, "
                    f"|net_flow|={abs_net:.2f} >= "
                    f"strong={self._strong_threshold:.2f}, "
                    f"side={'BUY' if order.side == OrderSide.BUY else 'SELL'})."
                )
                self._record_strong_skip(order.side)
                # Quantity invariant: no submit_order call.
                return
            else:
                # Decayed below strong threshold (regime weakened) or
                # direction sign flipped on the deque — release the chain.
                self.log.info(
                    f"FORCE-SUBMIT {order.client_order_id} — chain decayed "
                    f"(|net_flow|={abs_net:.2f} < strong="
                    f"{self._strong_threshold:.2f} or no longer adverse); "
                    f"resetting chain (length was {self._consecutive_skips})."
                )
                self._reset_chain()
                self.submit_order(order)
                return

        # ----- No active chain: tier dispatch on |net_flow| -----

        # NEUTRAL: insufficient signal — submit.
        if abs_net < self._weak_threshold:
            self.log.debug(
                f"SUBMIT {order.client_order_id} — neutral "
                f"(|net_flow|={abs_net:.2f} < weak="
                f"{self._weak_threshold:.2f})."
            )
            self.submit_order(order)
            return

        # Direction check (regardless of tier).
        if not self._is_adverse(net, order.side):
            self.log.debug(
                f"SUBMIT {order.client_order_id} — flow favorable "
                f"(net_flow={net:.2f}, side="
                f"{'BUY' if order.side == OrderSide.BUY else 'SELL'})."
            )
            self.submit_order(order)
            return

        # Adverse direction — dispatch on magnitude tier.
        if abs_net < self._strong_threshold:
            # WEAK ADVERSE: base AFG one-shot.
            self.log.info(
                f"SKIP {order.client_order_id} — weak-tier adverse "
                f"(|net_flow|={abs_net:.2f} in "
                f"[{self._weak_threshold:.2f}, {self._strong_threshold:.2f}), "
                f"side={'BUY' if order.side == OrderSide.BUY else 'SELL'}); "
                f"one-shot, no chain."
            )
            self._position_flat = True
            # Quantity invariant: no submit_order call.
            return
        else:
            # STRONG ADVERSE: start a chain.
            self.log.info(
                f"SKIP {order.client_order_id} — strong-tier adverse "
                f"(|net_flow|={abs_net:.2f} >= strong="
                f"{self._strong_threshold:.2f}, "
                f"side={'BUY' if order.side == OrderSide.BUY else 'SELL'}); "
                f"starting chain."
            )
            self._record_strong_skip(order.side)
            # Quantity invariant: no submit_order call.
            return

    def on_quote_tick(self, tick) -> None:
        """Passively receive quote ticks (kept for quote-cache side-effects)."""
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_seconds: float = 10.0,
    weak_threshold: float = 2.0,
    strong_threshold: float = 50.0,
    max_consecutive_skips: int = 3,
) -> AFGPCR3Algorithm:
    """Instantiate and return the AFGPCR3Algorithm (MCCG v2).

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_seconds : float
        Rolling window for aggressor-flow accumulation, in seconds. Default 10.0s.
    weak_threshold : float
        Lower bound of the gate-firing zone. Default 2.0 contracts.
    strong_threshold : float
        Chain-engagement threshold. Default 50.0 (EDA-derived p70).
    max_consecutive_skips : int
        Hard cap on strong-tier chain length. Default 3 (matches r2).
    """
    config = AFGPCR3Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        weak_threshold=weak_threshold,
        strong_threshold=strong_threshold,
        max_consecutive_skips=max_consecutive_skips,
    )
    return AFGPCR3Algorithm(config=config)
