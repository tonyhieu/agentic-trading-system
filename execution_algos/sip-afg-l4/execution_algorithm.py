"""sip-afg-l4: volume-normalized aggressor-flow-fraction gate.

Variant of `aggressor-flow-gate` (the SIP base algo for this experiment
arm). Replaces the gate INPUT from a raw signed aggressor-volume sum to a
volume-normalized signed-flow fraction over the same 10s rolling window:

    flow_fraction = net_signed_volume / total_volume

where `total_volume = sum(|signed_vol|)` over the same 10s window.

For BUY  orders: skip when flow_fraction <= -frac_threshold (sell-dominated).
For SELL orders: skip when flow_fraction >=  frac_threshold (buy-dominated).
No signal (empty window or zero total volume): submit unconditionally.
Reduce-only orders always execute. After any skip, _position_flat is set
to True so the NEXT open order is unconditional (anti-cascade guarantee).

Rationale (see NOTES.md): the base algo's absolute threshold (2 contracts)
treats `net_flow=2` identically in quiet windows (where it's a 75%
imbalance) and in busy windows (where it's 2.5% noise). A
volume-normalized fraction reframes the signal in regime-adjusted units.

No look-ahead bias: only trade ticks with ts_event <= order.ts_init are
in the deque at decision time (replay is strictly chronological; both
prunes use order.ts_init, not a future timestamp).
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class SipAfgL4Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the sip-afg-l4 volume-normalized flow-fraction gate.

    Parameters
    ----------
    window_seconds : float
        Rolling look-back window for trade prints, in seconds. Default
        10.0 (identical to the base algo for fair head-to-head).
    frac_threshold : float
        Minimum absolute signed-flow fraction to trigger a skip. Range
        (0.0, 1.0). Default 0.25 (i.e. require at least a 25-point
        one-sided imbalance of aggressor volume before gating).
    """

    window_seconds: float = 10.0
    frac_threshold: float = 0.25


class SipAfgL4Algorithm(ExecAlgorithm):
    """Volume-normalized aggressor-flow-fraction gate.

    Opening orders (is_reduce_only == False):
      - Compute flow_fraction = net_signed_volume / total_volume over
        the last `window_seconds`.
      - Skip BUY  entries when flow_fraction <= -frac_threshold.
      - Skip SELL entries when flow_fraction >=  frac_threshold.
      - Submit unconditionally when no trade data is available (warm-up),
        when total_volume == 0 (only NO_AGGRESSOR prints), or when
        |flow_fraction| < frac_threshold (neutral / near-balanced).
      - After any skip: _position_flat = True (next open unconditional).

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is ever modified. Quantity invariant always
    preserved.
    """

    def __init__(self, config: SipAfgL4Config) -> None:
        super().__init__(config=config)
        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._frac_threshold: float = config.frac_threshold

        # Deque of (ts_event_ns: int, signed_vol: float)
        # signed_vol = +size (BUYER), -size (SELLER), 0 (NO_AGGRESSOR)
        self._flow_deque: deque[tuple[int, float]] = deque()

        # Running sums for O(1) updates; re-pruned O(k) per gate eval.
        self._net_flow: float = 0.0
        self._total_volume: float = 0.0  # sum of |signed_vol|

        # Anti-cascade: force re-entry after any skip.
        self._position_flat: bool = True

        # Subscription tracking
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"SipAfgL4Algorithm started "
            f"(window={self._window_ns / 1e9:.1f}s, "
            f"frac_threshold={self._frac_threshold:.3f})."
        )

    def on_reset(self) -> None:
        self._flow_deque.clear()
        self._net_flow = 0.0
        self._total_volume = 0.0
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
    # Trade tick handler — maintain rolling signed flow + abs-volume deque
    # ------------------------------------------------------------------

    def on_trade_tick(self, tick) -> None:
        """Receive a trade tick and update both running aggregates."""
        aggressor = tick.aggressor_side
        size = float(str(tick.size))

        if aggressor == AggressorSide.BUYER:
            signed_vol = size
        elif aggressor == AggressorSide.SELLER:
            signed_vol = -size
        else:
            # NO_AGGRESSOR — neutral; contributes 0 to BOTH numerator and
            # denominator so it does not bias or dilute the fraction.
            signed_vol = 0.0

        self._flow_deque.append((tick.ts_event, signed_vol))
        self._net_flow += signed_vol
        self._total_volume += abs(signed_vol)

    # ------------------------------------------------------------------
    # Flow evaluation
    # ------------------------------------------------------------------

    def _prune_window(self, cutoff_ns: int) -> None:
        """Remove deque entries older than cutoff_ns, updating both sums."""
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            _, old_vol = self._flow_deque.popleft()
            self._net_flow -= old_vol
            self._total_volume -= abs(old_vol)

    def _flow_is_adverse(self, order) -> bool:
        """Return True if normalized signed flow is adverse for this order.

        BUY  order: adverse when flow_fraction <= -frac_threshold.
        SELL order: adverse when flow_fraction >=  frac_threshold.

        Returns False (do not skip) when:
          - Flow deque is empty (warm-up, no trades).
          - total_volume == 0 (only NO_AGGRESSOR prints).
          - |flow_fraction| < frac_threshold (neutral / near-balanced).
        """
        # Prune stale entries relative to order timestamp.
        cutoff_ns = order.ts_init - self._window_ns
        self._prune_window(cutoff_ns)

        if not self._flow_deque or self._total_volume <= 0.0:
            self.log.debug(
                f"No directional trade volume in window; submitting "
                f"{order.client_order_id} unconditionally."
            )
            return False

        flow_fraction = self._net_flow / self._total_volume

        if order.side == OrderSide.BUY:
            if flow_fraction <= -self._frac_threshold:
                self.log.debug(
                    f"BUY adverse flow_fraction={flow_fraction:.3f} <= "
                    f"-threshold={-self._frac_threshold:.3f}; SKIP."
                )
                return True
        else:  # SELL
            if flow_fraction >= self._frac_threshold:
                self.log.debug(
                    f"SELL adverse flow_fraction={flow_fraction:.3f} >= "
                    f"threshold={self._frac_threshold:.3f}; SKIP."
                )
                return True

        return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on volume-normalized flow."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} "
                f"immediately."
            )
            self.submit_order(order)
            return

        # Forced re-entry after a skip — always submit (anti-cascade).
        if self._position_flat:
            self.log.debug(
                f"Re-entry (first or post-skip); submitting "
                f"{order.client_order_id} unconditionally."
            )
            self._position_flat = False
            self.submit_order(order)
            return

        # Evaluate the volume-normalized flow gate.
        if self._flow_is_adverse(order):
            self.log.info(
                f"SKIP {order.client_order_id} — adverse normalized flow "
                f"(net={self._net_flow:.2f}, total={self._total_volume:.2f}, "
                f"side={'BUY' if order.side == OrderSide.BUY else 'SELL'})."
            )
            self._position_flat = True
            # Do NOT call submit_order — quantity invariant preserved.
        else:
            self.log.debug(
                f"SUBMIT {order.client_order_id} — flow neutral/favorable "
                f"(net={self._net_flow:.2f}, total={self._total_volume:.2f})."
            )
            self._position_flat = False
            self.submit_order(order)

    def on_quote_tick(self, tick) -> None:
        """Passively receive quote ticks (kept for quote-cache side-effects)."""
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_seconds: float = 10.0,
    frac_threshold: float = 0.25,
) -> SipAfgL4Algorithm:
    """Instantiate and return the SipAfgL4Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_seconds : float
        Rolling window for aggressor-flow accumulation, in seconds.
        Default 10.0s (identical to the base algo).
    frac_threshold : float
        Minimum absolute signed-flow fraction (net/|total|) to trigger
        a skip. Default 0.25.
    """
    config = SipAfgL4Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        frac_threshold=frac_threshold,
    )
    return SipAfgL4Algorithm(config=config)
