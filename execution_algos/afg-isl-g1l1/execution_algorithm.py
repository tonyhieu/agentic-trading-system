"""afg-isl-g1l1 — island-1, generation 1, loop 1.

Two-window persistence + reversal aggressor-flow gate.

Structural extension of the base aggressor-flow-gate:
  - Computes signed aggressor flow over BOTH a short sub-window
    (`short_window_seconds`, default 3.0s) and the full window
    (`window_seconds`, default 10.0s, matching base).
  - Skips an opening order only when the adverse flow is persistent
    across BOTH timescales (full_flow and short_flow both adverse beyond
    their respective thresholds).
  - Adds a reversal-exception: even if the full window is adverse, submit
    when the short window has flipped favorable by at least
    `reversal_threshold` — the adverse pressure has measurably exhausted
    and the moment is often a favorable arrival price.
  - Reduce-only / closing orders always submit.
  - After any skip: `_position_flat = True` (anti-cascade contract preserved).
  - Quantity invariant: never modify `order.quantity`.

Hypothesis (see NOTES.md): the base's single-window gate is too coarse —
it cannot distinguish "adverse and worsening" from "was adverse but
already reversing." The two-window structure should preserve the wins
from the base (skip persistent adverse periods) while recapturing the
favorable-arrival-price entries the base's NOTES.md flags as the source
of the +21.9% IS regression.

No look-ahead: the deque is fed strictly by `on_trade_tick` callbacks in
replay-chronological order; pruning uses `order.ts_init` as the cutoff.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class AfgIslG1L1Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the afg-isl-g1l1 two-window persistence+reversal gate.

    Parameters
    ----------
    window_seconds : float
        Full rolling look-back window for trade prints, in seconds. Default 10.0.
        Matches the base aggressor-flow-gate window.
    short_window_seconds : float
        Inner sub-window for short-horizon flow, in seconds. Default 3.0.
        Must be < window_seconds.
    full_threshold : float
        Minimum absolute net signed flow over the FULL window (in contracts)
        for the persistent-adverse condition. Default 2.0 (matches base).
    short_threshold : float
        Minimum absolute net signed flow over the SHORT window (in contracts)
        for the persistent-adverse condition. Default 1.0 (lower because the
        short window naturally carries less volume).
    reversal_threshold : float
        Minimum absolute net signed flow over the short window in the
        FAVORABLE direction needed to override an otherwise-adverse full
        window (the "reversal exception"). Default 1.0.
    """

    window_seconds: float = 10.0
    short_window_seconds: float = 3.0
    full_threshold: float = 2.0
    short_threshold: float = 1.0
    reversal_threshold: float = 1.0


class AfgIslG1L1Algorithm(ExecAlgorithm):
    """Two-window persistence + reversal aggressor-flow gate.

    Opening orders (is_reduce_only == False):
      Compute `full_flow` over the full window and `short_flow` over the
      most recent short window from a single trade-tick deque.

      - **Skip BUY**  iff `full_flow <= -full_threshold` AND
                          `short_flow <= -short_threshold`.
      - **Skip SELL** iff `full_flow >=  full_threshold` AND
                          `short_flow >=  short_threshold`.
      - **Reversal exception (override skip → submit)**:
          BUY:  `full_flow <= -full_threshold` AND
                `short_flow >=  reversal_threshold`  → submit.
          SELL: `full_flow >=  full_threshold` AND
                `short_flow <= -reversal_threshold`  → submit.
      - Otherwise (warm-up, neutral, partial adversity, favorable):
        submit.
      - After any skip: `_position_flat = True` (next open submits
        unconditionally).

    Closing orders (is_reduce_only == True): always submit immediately
    (intraday_flat compliance).

    No order quantity is ever modified.
    """

    def __init__(self, config: AfgIslG1L1Config) -> None:
        super().__init__(config=config)
        if config.short_window_seconds >= config.window_seconds:
            raise ValueError(
                "short_window_seconds must be strictly less than window_seconds "
                f"(got {config.short_window_seconds} >= {config.window_seconds})."
            )

        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._short_window_ns: int = int(config.short_window_seconds * 1_000_000_000)
        self._full_threshold: float = config.full_threshold
        self._short_threshold: float = config.short_threshold
        self._reversal_threshold: float = config.reversal_threshold

        # Deque of (ts_event_ns: int, signed_vol: float).
        # signed_vol = +size (BUYER), -size (SELLER), 0 (NO_AGGRESSOR).
        self._flow_deque: deque[tuple[int, float]] = deque()

        # Running sum of signed volume in the (full-window) deque (O(1) updates).
        self._net_flow: float = 0.0

        # Safety: forced re-entry after any skip to prevent cascade.
        self._position_flat: bool = True

        # Subscription tracking.
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            "AfgIslG1L1Algorithm started "
            f"(window={self._window_ns / 1e9:.1f}s, "
            f"short_window={self._short_window_ns / 1e9:.1f}s, "
            f"full_threshold={self._full_threshold:.2f}, "
            f"short_threshold={self._short_threshold:.2f}, "
            f"reversal_threshold={self._reversal_threshold:.2f})."
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
            # NO_AGGRESSOR — treat as neutral.
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

    def _short_flow(self, short_cutoff_ns: int) -> float:
        """Compute the net signed flow over the SHORT sub-window.

        Iterates from the newest entry backward, summing while
        `ts_event_ns >= short_cutoff_ns`. Stops as soon as it crosses the
        cutoff. The full deque has already been pruned to the FULL window,
        so this loop is bounded by the deque length (typically tens to a
        few hundred entries for 3-10s windows in MES futures).
        """
        total = 0.0
        # Iterate newest-first via reversed() on the deque.
        for ts_event_ns, vol in reversed(self._flow_deque):
            if ts_event_ns < short_cutoff_ns:
                break
            total += vol
        return total

    def _should_skip(self, order) -> bool:
        """Two-window persistence + reversal gate decision.

        Returns True iff the order should be skipped. False otherwise (submit).
        """
        # Prune the full-window deque relative to this order's timestamp.
        full_cutoff_ns = order.ts_init - self._window_ns
        self._prune_window(full_cutoff_ns)

        if not self._flow_deque:
            # Warm-up / thin market — do not gate.
            return False

        full_flow = self._net_flow
        short_cutoff_ns = order.ts_init - self._short_window_ns
        short_flow = self._short_flow(short_cutoff_ns)

        if order.side == OrderSide.BUY:
            full_adverse = full_flow <= -self._full_threshold
            if not full_adverse:
                return False  # full window not adverse → submit
            # Reversal exception: short window has flipped favorably.
            if short_flow >= self._reversal_threshold:
                self.log.debug(
                    f"BUY reversal: full_flow={full_flow:.2f} "
                    f"<= -full_thr={-self._full_threshold:.2f} BUT "
                    f"short_flow={short_flow:.2f} >= "
                    f"reversal_thr={self._reversal_threshold:.2f}; SUBMIT."
                )
                return False
            # Persistent adverse: both windows adverse beyond their thresholds.
            if short_flow <= -self._short_threshold:
                self.log.debug(
                    f"BUY persistent adverse: full_flow={full_flow:.2f}, "
                    f"short_flow={short_flow:.2f}; SKIP."
                )
                return True
            # Full adverse but short neutral — submit (no confirmation).
            return False
        else:  # SELL
            full_adverse = full_flow >= self._full_threshold
            if not full_adverse:
                return False
            if short_flow <= -self._reversal_threshold:
                self.log.debug(
                    f"SELL reversal: full_flow={full_flow:.2f} "
                    f">= full_thr={self._full_threshold:.2f} BUT "
                    f"short_flow={short_flow:.2f} <= "
                    f"-reversal_thr={-self._reversal_threshold:.2f}; SUBMIT."
                )
                return False
            if short_flow >= self._short_threshold:
                self.log.debug(
                    f"SELL persistent adverse: full_flow={full_flow:.2f}, "
                    f"short_flow={short_flow:.2f}; SKIP."
                )
                return True
            return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on two-window flow gate."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        if order.is_reduce_only:
            self.submit_order(order)
            return

        # Forced re-entry after a skip — always submit to prevent cascade.
        if self._position_flat:
            self._position_flat = False
            self.submit_order(order)
            return

        if self._should_skip(order):
            self.log.info(
                f"SKIP {order.client_order_id} — persistent adverse aggressor flow "
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
    short_window_seconds: float = 3.0,
    full_threshold: float = 2.0,
    short_threshold: float = 1.0,
    reversal_threshold: float = 1.0,
) -> AfgIslG1L1Algorithm:
    """Instantiate and return the afg-isl-g1l1 algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_seconds : float
        Full rolling window for aggressor flow, in seconds. Default 10.0s.
    short_window_seconds : float
        Short sub-window for reversal/persistence detection. Default 3.0s.
    full_threshold : float
        Adverse-flow threshold for the full window (contracts). Default 2.0.
    short_threshold : float
        Adverse-flow confirmation threshold for the short window. Default 1.0.
    reversal_threshold : float
        Favorable-flow threshold in the short window that overrides an
        adverse full-window verdict. Default 1.0.
    """
    config = AfgIslG1L1Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        short_window_seconds=short_window_seconds,
        full_threshold=full_threshold,
        short_threshold=short_threshold,
        reversal_threshold=reversal_threshold,
    )
    return AfgIslG1L1Algorithm(config=config)
