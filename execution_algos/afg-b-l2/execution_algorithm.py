"""afg-b-l2: aggressor-flow-gate with COMBINED absolute + ratio gate.

Derived from afg-b-l1 (the prior loop), which itself was derived from the
base `aggressor-flow-gate`. The base gates on a flat absolute threshold
(|net_flow| >= 2.0); L1 gates on a pure volume-normalized ratio
(|net_flow|/max(min_abs_baseline, abs_vol_window) >= 0.35). L1's data showed
the absolute gate is the binding selectivity floor in busy windows and that
extra admitted orders systematically destroy pnl on this oracle.

This loop adds one targeted change relative to L1: replace the pure-ratio
gate with a CONJUNCTION -- require BOTH

    |net_flow| >= flow_threshold (=2.0)
  AND
    |net_flow| / max(min_abs_baseline, abs_vol_window) >= ratio_threshold (=0.35)

before triggering an adverse skip. The intersection cannot admit any order
that either the base or L1 would skip, so it is strictly more selective
than both prior gates. Per L1's per-1k arithmetic (every +1k admits ~=
-$47 pnl on this oracle), the conjunction should net pnl >= base with
trade_count <= base.

Other mechanics (window length, anti-cascade flat-flag semantics, reduce-
only-always-submit semantics, quantity invariant) preserved exactly from
L1 / base.

No look-ahead bias: only ticks with ts_event <= order.ts_init are in the
deque at decision time (replay is strictly chronological; the window prune
uses the order's ts_init, not a future timestamp).
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class AfgBL2Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for afg-b-l2.

    Parameters
    ----------
    window_seconds : float
        Rolling look-back window for trade prints, in seconds.
        Default 10.0 seconds (same as base + L1).
    flow_threshold : float
        Minimum absolute net signed flow (in contracts) to trigger a skip.
        Acts as the absolute selectivity floor (from base).
        Default 2.0.
    ratio_threshold : float
        Minimum |net_flow| / max(min_abs_baseline, abs_vol_window) to
        trigger a skip. Acts as the quiet-window denoising filter (from L1).
        Default 0.35.
    min_abs_baseline : float
        Floor on the ratio denominator (in contracts). Prevents divide-by-
        tiny on empty/sparse windows. Default 2.0.
    """

    window_seconds: float = 10.0
    flow_threshold: float = 2.0
    ratio_threshold: float = 0.35
    min_abs_baseline: float = 2.0


class AfgBL2Algorithm(ExecAlgorithm):
    """Aggressor-flow gate using a CONJUNCTION of absolute and ratio tests.

    Opening orders (is_reduce_only == False):
      - Compute signed net flow and total absolute volume over the same
        `window_seconds` window. Compute imbalance ratio
        r = net_flow / max(min_abs_baseline, abs_vol_window).
      - Skip BUY  entries when net_flow <= -flow_threshold AND r <= -ratio_threshold
        (BOTH adverse on the absolute and ratio axes).
      - Skip SELL entries when net_flow >=  flow_threshold AND r >=  ratio_threshold.
      - Submit unconditionally when either condition fails, or the deque
        is empty (warm-up).
      - After any skip: _position_flat = True (next open unconditional;
        anti-cascade guarantee preserved from base + L1).

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).
    """

    def __init__(self, config: AfgBL2Config) -> None:
        super().__init__(config=config)
        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._flow_threshold: float = config.flow_threshold
        self._ratio_threshold: float = config.ratio_threshold
        self._min_abs_baseline: float = config.min_abs_baseline

        # Deque of (ts_event_ns: int, signed_vol: float, abs_vol: float)
        # signed_vol = +size (BUYER), -size (SELLER), 0 (NO_AGGRESSOR)
        # abs_vol = size (always non-negative; NO_AGGRESSOR included)
        self._flow_deque: deque[tuple[int, float, float]] = deque()

        # Running sums for O(1) updates
        self._net_flow: float = 0.0
        self._abs_vol: float = 0.0

        # Safety: forced re-entry after any skip to prevent cascade
        self._position_flat: bool = True

        # Subscription tracking
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"AfgBL2Algorithm started "
            f"(window={self._window_ns / 1e9:.1f}s, "
            f"flow_threshold={self._flow_threshold:.2f} contracts, "
            f"ratio_threshold={self._ratio_threshold:.3f}, "
            f"min_abs_baseline={self._min_abs_baseline:.2f})."
        )

    def on_reset(self) -> None:
        self._flow_deque.clear()
        self._net_flow = 0.0
        self._abs_vol = 0.0
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
    # Trade tick handler — maintain rolling signed flow + abs volume deque
    # ------------------------------------------------------------------

    def on_trade_tick(self, tick) -> None:
        """Append the trade tick to the rolling deque and update both sums."""
        aggressor = tick.aggressor_side
        size = float(str(tick.size))

        if aggressor == AggressorSide.BUYER:
            signed_vol = size
        elif aggressor == AggressorSide.SELLER:
            signed_vol = -size
        else:
            # NO_AGGRESSOR — neutral; still contributes to abs_vol
            signed_vol = 0.0

        self._flow_deque.append((tick.ts_event, signed_vol, size))
        self._net_flow += signed_vol
        self._abs_vol += size

    # ------------------------------------------------------------------
    # Flow evaluation
    # ------------------------------------------------------------------

    def _prune_window(self, cutoff_ns: int) -> None:
        """Remove deque entries older than cutoff_ns, updating both sums."""
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            _, old_signed, old_abs = self._flow_deque.popleft()
            self._net_flow -= old_signed
            self._abs_vol -= old_abs

    def _flow_is_adverse(self, order) -> bool:
        """Return True iff BOTH absolute and ratio conditions are adverse.

        BUY  order: adverse when net_flow <= -flow_threshold AND r <= -ratio_threshold.
        SELL order: adverse when net_flow >=  flow_threshold AND r >=  ratio_threshold.

        Returns False (do not skip) when:
          - Flow deque is empty (no trades seen yet — warm-up).
          - Either the absolute test OR the ratio test is not adverse
            (the conjunction fails).
        """
        cutoff_ns = order.ts_init - self._window_ns
        self._prune_window(cutoff_ns)

        if not self._flow_deque:
            self.log.debug(
                f"No trade data in window; submitting {order.client_order_id} "
                f"unconditionally."
            )
            return False

        denom = max(self._min_abs_baseline, self._abs_vol)
        r = self._net_flow / denom
        net = self._net_flow

        if order.side == OrderSide.BUY:
            # Both adverse on the absolute and ratio axes.
            if net <= -self._flow_threshold and r <= -self._ratio_threshold:
                self.log.debug(
                    f"BUY adverse flow: net={net:.2f} <= -{self._flow_threshold:.2f} "
                    f"AND ratio={r:.3f} <= -{self._ratio_threshold:.3f} "
                    f"(abs_vol={self._abs_vol:.2f}); SKIP."
                )
                return True
        else:  # SELL
            if net >= self._flow_threshold and r >= self._ratio_threshold:
                self.log.debug(
                    f"SELL adverse flow: net={net:.2f} >= {self._flow_threshold:.2f} "
                    f"AND ratio={r:.3f} >= {self._ratio_threshold:.3f} "
                    f"(abs_vol={self._abs_vol:.2f}); SKIP."
                )
                return True

        return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on conjunction of absolute + ratio flow tests."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Forced re-entry after a skip — always submit to prevent cascade.
        if self._position_flat:
            self.log.debug(
                f"Re-entry (first or post-skip); submitting "
                f"{order.client_order_id} unconditionally."
            )
            self._position_flat = False
            self.submit_order(order)
            return

        # Evaluate combined (absolute AND ratio) aggressor-flow gate.
        if self._flow_is_adverse(order):
            self.log.info(
                f"SKIP {order.client_order_id} — combined adverse flow "
                f"(net_flow={self._net_flow:.2f}, abs_vol={self._abs_vol:.2f}, "
                f"side={'BUY' if order.side == OrderSide.BUY else 'SELL'})."
            )
            self._position_flat = True
            # Do NOT call submit_order — quantity invariant preserved.
        else:
            self.log.debug(
                f"SUBMIT {order.client_order_id} — conjunction not adverse "
                f"(net_flow={self._net_flow:.2f}, abs_vol={self._abs_vol:.2f})."
            )
            self._position_flat = False
            self.submit_order(order)

    def on_quote_tick(self, tick) -> None:
        """Passively receive quote ticks (kept for quote-cache side-effects)."""
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_seconds: float = 10.0,
    flow_threshold: float = 2.0,
    ratio_threshold: float = 0.35,
    min_abs_baseline: float = 2.0,
) -> AfgBL2Algorithm:
    """Instantiate and return the AfgBL2Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_seconds : float
        Rolling window for aggressor-flow accumulation, in seconds. Default 10.0s.
    flow_threshold : float
        Min |net_flow| (contracts) for the absolute leg of the conjunction. Default 2.0.
    ratio_threshold : float
        Min |net_flow|/max(min_abs_baseline, abs_vol) for the ratio leg. Default 0.35.
    min_abs_baseline : float
        Floor on the ratio denominator (contracts). Default 2.0.
    """
    config = AfgBL2Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        flow_threshold=flow_threshold,
        ratio_threshold=ratio_threshold,
        min_abs_baseline=min_abs_baseline,
    )
    return AfgBL2Algorithm(config=config)
