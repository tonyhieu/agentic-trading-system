"""sip-afg-l1 execution algorithm.

Variant of ``aggressor-flow-gate`` that replaces the uniform 10-second
sum of signed aggressor volumes with an exponentially-weighted sum
(half-life tau = 3.0s). Threshold rescaled to 0.6 so steady-state skip
pressure approximately matches the base algo while bursts of fresh
aggressor activity trip the gate more readily and stale flow near the
10s tail contributes only marginally.

All other mechanics are preserved verbatim from the base algo:
  - Reduce-only / position-closing orders always execute.
  - After any skip: _position_flat = True so the NEXT open is
    unconditional (anti-cascade guarantee).
  - Quantity never modified; only skip or submit.
  - top_of_book_only and participation_cap are not affected
    (parent-order gating only).
"""
from __future__ import annotations

import math
from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class SipAfgL1Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the sip-afg-l1 execution algorithm.

    Parameters
    ----------
    window_seconds : float
        Outer rolling window for trade prints, in seconds. Default 10.0s
        (matches base algo). Beyond this the exponential weight is <0.04
        so trades are pruned for cheapness.
    tau_seconds : float
        Exponential decay time constant, in seconds. Default 3.0s
        (roughly a half-life of ~2.1s). Recent prints carry weight
        exp(-(t_order - t_trade) / tau).
    flow_threshold : float
        Minimum absolute EWMA-signed flow (in weighted contracts) to
        trigger a skip. Default 0.6, chosen so that for a uniform
        arrival of unit-signed prints across the 10s window the
        equivalent uniform-sum threshold is ~2.0 (matching the base
        algo's default skip pressure under that assumption).
    """

    window_seconds: float = 10.0
    tau_seconds: float = 3.0
    flow_threshold: float = 0.6


class SipAfgL1Algorithm(ExecAlgorithm):
    """Exponentially-weighted aggressor-flow gate.

    Opening orders (is_reduce_only == False):
      - Compute ewma_flow = sum over deque of
            signed_vol * exp(-(order.ts_init - tick.ts_event) / tau_ns)
      - Skip BUY  entries when ewma_flow <= -flow_threshold
      - Skip SELL entries when ewma_flow >=  flow_threshold
      - Empty deque or |ewma_flow| < threshold → submit.
      - After any skip: _position_flat = True (next open unconditional).

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).
    """

    def __init__(self, config: SipAfgL1Config) -> None:
        super().__init__(config=config)
        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._tau_ns: float = float(config.tau_seconds * 1_000_000_000)
        self._flow_threshold: float = float(config.flow_threshold)

        # Deque of (ts_event_ns: int, signed_vol: float)
        self._flow_deque: deque[tuple[int, float]] = deque()

        # Safety: forced re-entry after any skip to prevent cascade
        self._position_flat: bool = True

        # Subscription tracking
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"SipAfgL1Algorithm started "
            f"(window={self._window_ns / 1e9:.1f}s, "
            f"tau={self._tau_ns / 1e9:.1f}s, "
            f"flow_threshold={self._flow_threshold:.2f})."
        )

    def on_reset(self) -> None:
        self._flow_deque.clear()
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
    # Trade tick handler
    # ------------------------------------------------------------------

    def on_trade_tick(self, tick) -> None:
        """Append a signed-volume entry for this trade print."""
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
    # Flow evaluation
    # ------------------------------------------------------------------

    def _prune_window(self, cutoff_ns: int) -> None:
        """Remove deque entries older than cutoff_ns."""
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            self._flow_deque.popleft()

    def _compute_ewma_flow(self, ref_ts_ns: int) -> float:
        """Compute exponentially-weighted signed flow at ref_ts_ns.

        Each deque entry (ts_event_ns, signed_vol) contributes
            signed_vol * exp(-(ref_ts_ns - ts_event_ns) / tau_ns).
        Entries with ts_event_ns > ref_ts_ns (shouldn't happen given
        chronological replay) are clamped to weight 1.0.
        """
        total = 0.0
        tau = self._tau_ns
        for ts_event_ns, signed_vol in self._flow_deque:
            dt = ref_ts_ns - ts_event_ns
            if dt <= 0:
                weight = 1.0
            else:
                weight = math.exp(-dt / tau)
            total += signed_vol * weight
        return total

    def _flow_is_adverse(self, order) -> bool:
        """Return True if EWMA aggressor flow is adverse for this order."""
        cutoff_ns = order.ts_init - self._window_ns
        self._prune_window(cutoff_ns)

        if not self._flow_deque:
            self.log.debug(
                f"No trade data in window; submitting {order.client_order_id} "
                f"unconditionally."
            )
            return False

        ewma = self._compute_ewma_flow(order.ts_init)

        if order.side == OrderSide.BUY:
            if ewma <= -self._flow_threshold:
                self.log.debug(
                    f"BUY adverse EWMA flow: ewma={ewma:.3f} <= "
                    f"-threshold={-self._flow_threshold:.3f}; SKIP."
                )
                return True
        else:  # SELL
            if ewma >= self._flow_threshold:
                self.log.debug(
                    f"SELL adverse EWMA flow: ewma={ewma:.3f} >= "
                    f"threshold={self._flow_threshold:.3f}; SKIP."
                )
                return True

        return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on EWMA aggressor flow."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id}."
            )
            self.submit_order(order)
            return

        # Forced re-entry after a skip — always submit to prevent cascade.
        if self._position_flat:
            self.log.debug(
                f"Re-entry; submitting {order.client_order_id} "
                f"unconditionally."
            )
            self._position_flat = False
            self.submit_order(order)
            return

        if self._flow_is_adverse(order):
            self.log.info(
                f"SKIP {order.client_order_id} — adverse EWMA aggressor flow "
                f"(side={'BUY' if order.side == OrderSide.BUY else 'SELL'})."
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
    tau_seconds: float = 3.0,
    flow_threshold: float = 0.6,
) -> SipAfgL1Algorithm:
    """Instantiate and return the SipAfgL1Algorithm."""
    config = SipAfgL1Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        tau_seconds=tau_seconds,
        flow_threshold=flow_threshold,
    )
    return SipAfgL1Algorithm(config=config)
