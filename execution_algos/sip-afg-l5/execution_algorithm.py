"""sip-afg-l5 — graduated post-skip cascade policy.

Identical to ``aggressor-flow-gate`` (10s rolling signed aggressor-volume
window, symmetric ``flow_threshold = 2.0`` contracts, BUY/SELL gating on
adverse net flow) EXCEPT for the post-skip cascade policy.

Base behavior: after any skip, ``_position_flat = True`` forces the next
opening order to submit unconditionally (no gate evaluation).

This algorithm: replaces the binary ``_position_flat`` flag with a
graduated ``_skip_streak`` counter and applies threshold relaxation
rather than a hard bypass:

  - streak=0 (fresh):     evaluate with ``flow_threshold`` (base).
  - streak=1 (one skip):  evaluate with ``flow_threshold * relaxation``
                          (default 1.5x). Most orders pass; only strongly-
                          adverse flow gates a second time.
  - streak>=2 (two skips): force-submit unconditionally and reset to 0
                           (safety bound — never gate indefinitely).
  - any submit:           reset streak to 0.

Reduce-only orders always submit (intraday_flat) and never touch the
counter. Warm-up (empty deque) submits unconditionally.

All constraint compliance is identical to base:
  - Quantity invariant: only submit/skip; never modify order.quantity.
  - top_of_book_only: no fill mechanics change.
  - participation_cap: no order sizing.
  - intraday_flat: reduce-only orders always submit.

No look-ahead bias: trade-tick deque pruning uses ``order.ts_init`` as the
reference time; only ticks with ``tick.ts_event <= order.ts_init`` are
considered (replay is strictly chronological).
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class SipAfgL5Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the sip-afg-l5 execution algorithm.

    Parameters
    ----------
    window_seconds : float
        Rolling look-back window for trade prints, in seconds.
        Default 10.0 seconds (identical to base ``aggressor-flow-gate``).
    flow_threshold : float
        Base absolute net signed flow (in contracts) to trigger a skip
        when the skip streak is 0. Default 2.0 contracts (identical to
        base).
    relaxation_factor : float
        Multiplier applied to ``flow_threshold`` when evaluating the
        order immediately following a skip (skip_streak == 1). Default
        1.5 — the gate must see notably stronger adverse flow to fire a
        second time consecutively.
    max_consecutive_skips : int
        Cap on consecutive skips. After this many skips in a row, the
        next order is force-submitted unconditionally (matching the
        base algo's anti-cascade safety behavior). Default 2.
    """

    window_seconds: float = 10.0
    flow_threshold: float = 2.0
    relaxation_factor: float = 1.5
    max_consecutive_skips: int = 2


class SipAfgL5Algorithm(ExecAlgorithm):
    """Aggressor-flow-gate with a graduated post-skip cascade policy.

    Replaces the base algorithm's binary ``_position_flat`` flag (after
    any skip the next opening order submits unconditionally) with a
    ``_skip_streak`` counter that relaxes the threshold on the
    immediately-following order rather than disabling the gate.
    """

    def __init__(self, config: SipAfgL5Config) -> None:
        super().__init__(config=config)
        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._flow_threshold: float = float(config.flow_threshold)
        self._relaxation_factor: float = float(config.relaxation_factor)
        self._max_consecutive_skips: int = int(config.max_consecutive_skips)

        # Deque of (ts_event_ns: int, signed_vol: float)
        self._flow_deque: deque[tuple[int, float]] = deque()
        self._net_flow: float = 0.0

        # Graduated cascade state. Counts consecutive skips. Resets to 0
        # on any submission. At streak == max_consecutive_skips the next
        # order force-submits.
        self._skip_streak: int = 0

        # Subscription tracking
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"SipAfgL5Algorithm started "
            f"(window={self._window_ns / 1e9:.1f}s, "
            f"flow_threshold={self._flow_threshold:.2f}, "
            f"relaxation_factor={self._relaxation_factor:.2f}, "
            f"max_consecutive_skips={self._max_consecutive_skips})."
        )

    def on_reset(self) -> None:
        self._flow_deque.clear()
        self._net_flow = 0.0
        self._skip_streak = 0
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

    def _flow_is_adverse(self, order, threshold: float) -> bool:
        """Return True if net aggressor flow exceeds ``threshold`` adversely.

        BUY  order: adverse when net_flow <= -threshold.
        SELL order: adverse when net_flow >=  threshold.

        Returns False (do not skip) when:
          - Flow deque is empty (warm-up).
          - |net_flow| < threshold (neutral / sub-threshold).
        """
        cutoff_ns = order.ts_init - self._window_ns
        self._prune_window(cutoff_ns)

        if not self._flow_deque:
            self.log.debug(
                f"No trade data in window; submitting {order.client_order_id} "
                f"unconditionally."
            )
            return False

        net = self._net_flow

        if order.side == OrderSide.BUY:
            if net <= -threshold:
                self.log.debug(
                    f"BUY adverse flow: net_flow={net:.2f} <= "
                    f"-threshold={-threshold:.2f}; SKIP."
                )
                return True
        else:  # SELL
            if net >= threshold:
                self.log.debug(
                    f"SELL adverse flow: net_flow={net:.2f} >= "
                    f"threshold={threshold:.2f}; SKIP."
                )
                return True

        return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: graduated cascade-policy gate on aggressor flow."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute. They do NOT touch
        # the skip streak counter.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Cap on consecutive skips — force a submit and reset the streak.
        if self._skip_streak >= self._max_consecutive_skips:
            self.log.debug(
                f"Skip streak cap reached ({self._skip_streak}); force-submit "
                f"{order.client_order_id} and reset streak."
            )
            self._skip_streak = 0
            self.submit_order(order)
            return

        # Pick the threshold for this evaluation. At streak == 1 use the
        # relaxed (looser) threshold; at streak == 0 use the base
        # threshold.
        if self._skip_streak == 0:
            threshold = self._flow_threshold
        else:
            threshold = self._flow_threshold * self._relaxation_factor

        if self._flow_is_adverse(order, threshold):
            self.log.info(
                f"SKIP {order.client_order_id} — adverse aggressor flow "
                f"(net_flow={self._net_flow:.2f}, side="
                f"{'BUY' if order.side == OrderSide.BUY else 'SELL'}, "
                f"streak={self._skip_streak} -> {self._skip_streak + 1}, "
                f"threshold={threshold:.2f})."
            )
            self._skip_streak += 1
            # Do NOT call submit_order — quantity invariant preserved.
        else:
            self.log.debug(
                f"SUBMIT {order.client_order_id} — flow neutral/favorable "
                f"(net_flow={self._net_flow:.2f}, "
                f"streak={self._skip_streak} -> 0, "
                f"threshold={threshold:.2f})."
            )
            self._skip_streak = 0
            self.submit_order(order)

    def on_quote_tick(self, tick) -> None:
        """Passively receive quote ticks (kept for quote-cache side-effects)."""
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_seconds: float = 10.0,
    flow_threshold: float = 2.0,
    relaxation_factor: float = 1.5,
    max_consecutive_skips: int = 2,
) -> SipAfgL5Algorithm:
    """Instantiate and return the SipAfgL5Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_seconds : float
        Rolling window for aggressor-flow accumulation, in seconds.
        Default 10.0s (identical to base).
    flow_threshold : float
        Base skip threshold in contracts. Default 2.0 (identical to base).
    relaxation_factor : float
        Multiplier for ``flow_threshold`` when evaluating the order
        immediately following a skip (skip_streak == 1). Default 1.5.
    max_consecutive_skips : int
        Maximum allowed consecutive skips. After this many in a row, the
        next order is force-submitted unconditionally. Default 2.
    """
    config = SipAfgL5Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        flow_threshold=flow_threshold,
        relaxation_factor=relaxation_factor,
        max_consecutive_skips=max_consecutive_skips,
    )
    return SipAfgL5Algorithm(config=config)
