"""afg-pc-r1 — Flow-Burst Gate execution algorithm.

Refinement of aggressor-flow-gate (base). Replaces base AFG's single-window
LEVEL-based threshold with a ratio-based ACCELERATION (burst) test:

  Maintain a deque of (ts_event_ns, signed_volume) trade-tick entries.
  For each open order, prune entries older than 10s. Then compute:
    long_flow  = sum(signed_vol)  over the trailing 10s
    short_flow = sum(signed_vol)  over the trailing 3s
    older_flow = long_flow - short_flow         # signed older-7s
    burst_ratio = |short_flow| / max(|older_flow|, eps)

  Skip an open order when ALL hold:
    (1) short_flow is adverse to order direction
        (BUY:  short_flow < 0;
         SELL: short_flow > 0)
    (2) |short_flow| >= min_burst_flow  (default 2.0)
    (3) burst_ratio >= burst_ratio_threshold  (default 1.5)

  Reduce-only (closing) orders always submit. After any skip,
  _position_flat = True so the next open is unconditional (anti-cascade,
  identical to base AFG semantics).

No look-ahead: only trade ticks with ts_event <= order.ts_init are in
the deque at decision time (chronological replay; prune uses order.ts_init).

Quantity invariant: never modify order.quantity. Only submit or skip.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class AFGPCR1Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the afg-pc-r1 Flow-Burst Gate algorithm.

    Parameters
    ----------
    short_window_seconds : float
        Short trailing window over which the recent ('burst') signed
        aggressor flow is computed. Default 3.0 seconds.
    long_window_seconds : float
        Long trailing window over which baseline signed aggressor flow
        is computed. Default 10.0 seconds. Must be > short_window_seconds.
    min_burst_flow : float
        Minimum absolute short-window signed flow (in contracts) required
        before the gate can fire. Filters tiny-print noise in thin
        markets. Default 2.0 contracts.
    burst_ratio_threshold : float
        Minimum ratio |short_flow| / max(|older_flow|, eps) required to
        fire the gate (where older_flow = long_flow - short_flow).
        Default 1.5 — the recent short-window flow must be at least 1.5x
        the (scaled-equivalent) older interval's flow magnitude.
    """

    short_window_seconds: float = 3.0
    long_window_seconds: float = 10.0
    min_burst_flow: float = 2.0
    burst_ratio_threshold: float = 1.5


_EPS: float = 1e-6


class AFGPCR1Algorithm(ExecAlgorithm):
    """Flow-Burst Gate execution algorithm — see module docstring."""

    def __init__(self, config: AFGPCR1Config) -> None:
        super().__init__(config=config)
        assert config.long_window_seconds > config.short_window_seconds > 0, (
            "long_window_seconds must be > short_window_seconds > 0"
        )

        self._short_ns: int = int(config.short_window_seconds * 1_000_000_000)
        self._long_ns: int = int(config.long_window_seconds * 1_000_000_000)
        self._min_burst_flow: float = float(config.min_burst_flow)
        self._burst_ratio_threshold: float = float(config.burst_ratio_threshold)

        # Single deque of (ts_event_ns, signed_volume).
        # signed_volume = +size (BUYER), -size (SELLER), 0 (NO_AGGRESSOR)
        self._flow_deque: deque[tuple[int, float]] = deque()

        # Running signed sum over the FULL long window (for O(1) updates on
        # prune / append). The short-window sum is recomputed at each order
        # by scanning from the deque tail backward — typically O(few) entries.
        self._long_sum: float = 0.0

        # Anti-cascade: after any skip, the next open is unconditional.
        self._position_flat: bool = True

        # Subscription tracking.
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"AFGPCR1Algorithm started (short_window="
            f"{self._short_ns / 1e9:.1f}s, long_window="
            f"{self._long_ns / 1e9:.1f}s, min_burst_flow="
            f"{self._min_burst_flow:.2f}, burst_ratio="
            f"{self._burst_ratio_threshold:.2f})."
        )

    def on_reset(self) -> None:
        self._flow_deque.clear()
        self._long_sum = 0.0
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
        aggressor = tick.aggressor_side
        size = float(str(tick.size))

        if aggressor == AggressorSide.BUYER:
            signed_vol = size
        elif aggressor == AggressorSide.SELLER:
            signed_vol = -size
        else:
            # NO_AGGRESSOR: neutral contribution
            signed_vol = 0.0

        self._flow_deque.append((tick.ts_event, signed_vol))
        self._long_sum += signed_vol

    # ------------------------------------------------------------------
    # Window pruning + short-window sum
    # ------------------------------------------------------------------

    def _prune_long_window(self, cutoff_ns: int) -> None:
        """Remove deque entries older than cutoff_ns, updating _long_sum."""
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            _, old_vol = self._flow_deque.popleft()
            self._long_sum -= old_vol

    def _compute_short_sum(self, short_cutoff_ns: int) -> float:
        """Sum signed volumes for entries with ts_event >= short_cutoff_ns.

        Scans from the deque's right (newest) end backward, stopping once an
        entry older than the short-window cutoff is encountered. Typically
        O(few) entries since trade cadence on MES is modest.
        """
        s = 0.0
        # Iterate from the right (newest first) — collections.deque supports
        # reversed iteration in O(1) per step.
        for ts_ns, signed_vol in reversed(self._flow_deque):
            if ts_ns < short_cutoff_ns:
                break
            s += signed_vol
        return s

    # ------------------------------------------------------------------
    # Gate evaluation
    # ------------------------------------------------------------------

    def _is_adverse_burst(self, order) -> bool:
        """Return True if a flow burst is adverse to the order direction."""
        long_cutoff_ns = order.ts_init - self._long_ns
        short_cutoff_ns = order.ts_init - self._short_ns

        # Prune the long window (also bounds the deque for the short scan).
        self._prune_long_window(long_cutoff_ns)

        if not self._flow_deque:
            # No trade data in window: warm-up / thin market — do not gate.
            self.log.debug(
                f"No trade data in long window; submitting "
                f"{order.client_order_id} unconditionally."
            )
            return False

        short_flow = self._compute_short_sum(short_cutoff_ns)
        long_flow = self._long_sum
        older_flow = long_flow - short_flow  # signed older-window flow

        # Condition (1): short_flow adverse to order direction
        if order.side == OrderSide.BUY:
            if short_flow >= 0.0:
                return False
        else:  # SELL
            if short_flow <= 0.0:
                return False

        # Condition (2): |short_flow| meets min_burst_flow noise floor
        abs_short = abs(short_flow)
        if abs_short < self._min_burst_flow:
            return False

        # Condition (3): burst ratio threshold
        denom = max(abs(older_flow), _EPS)
        burst_ratio = abs_short / denom
        if burst_ratio < self._burst_ratio_threshold:
            return False

        self.log.debug(
            f"Adverse burst detected for {order.side}: short_flow="
            f"{short_flow:.2f}, older_flow={older_flow:.2f}, "
            f"burst_ratio={burst_ratio:.2f} >= "
            f"{self._burst_ratio_threshold:.2f}; SKIP."
        )
        return True

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} "
                f"immediately."
            )
            self.submit_order(order)
            return

        # Anti-cascade: first open and post-skip opens are unconditional.
        if self._position_flat:
            self.log.debug(
                f"Re-entry (first or post-skip); submitting "
                f"{order.client_order_id} unconditionally."
            )
            self._position_flat = False
            self.submit_order(order)
            return

        if self._is_adverse_burst(order):
            self.log.info(
                f"SKIP {order.client_order_id} — adverse flow burst "
                f"(side={'BUY' if order.side == OrderSide.BUY else 'SELL'})."
            )
            self._position_flat = True
            # No submit_order call: quantity invariant preserved.
        else:
            self.log.debug(
                f"SUBMIT {order.client_order_id} — no adverse burst."
            )
            self._position_flat = False
            self.submit_order(order)

    def on_quote_tick(self, tick) -> None:
        """Passively receive quote ticks (kept for quote-cache side-effects)."""
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    short_window_seconds: float = 3.0,
    long_window_seconds: float = 10.0,
    min_burst_flow: float = 2.0,
    burst_ratio_threshold: float = 1.5,
) -> AFGPCR1Algorithm:
    """Instantiate and return the AFGPCR1Algorithm (Flow-Burst Gate)."""
    config = AFGPCR1Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        short_window_seconds=short_window_seconds,
        long_window_seconds=long_window_seconds,
        min_burst_flow=min_burst_flow,
        burst_ratio_threshold=burst_ratio_threshold,
    )
    return AFGPCR1Algorithm(config=config)
