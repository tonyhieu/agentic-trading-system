"""afg-b-l1: aggressor-flow-gate with volume-normalized adaptive threshold.

Derived from `aggressor-flow-gate` (the base). The base gates OPEN orders when
the absolute signed aggressor net flow over the last `window_seconds`
exceeds a flat `flow_threshold` (default 2.0 contracts) adverse to the order
side.

This loop adds one targeted change: replace the absolute contract threshold
with a *volume-normalized ratio threshold*. The gate fires when

    |net_flow| / max(min_abs_baseline, abs_vol_window) >= ratio_threshold

so the gate adapts to local trade intensity: during a quiet stretch a 2-
contract net dominates a small denominator and triggers; during a busy
stretch 2 contracts is noise relative to a large denominator and does not.

Rationale (informed only by inspecting the base algo; this is loop 1 of the
brief-summary arm and prior-loop context is empty):

The base's flat absolute threshold of 2 contracts is a single value applied
uniformly across the whole session and across all days. But realized trade
intensity in MES varies dramatically -- opening minutes, news prints, and
the close all see far higher tick rates than quiet midday periods. Under a
flat threshold:
  * In quiet windows, a couple of one-sided trades hit the threshold even
    when they carry essentially no information -- we skip orders we
    shouldn't.
  * In busy windows, 2 contracts of net imbalance against 200 contracts of
    total flow is statistical noise that wouldn't tilt the next 30 seconds
    of mid-price one way or the other -- we submit orders we should skip.

A volume-normalized signal -- the ratio of *signed* flow to *total* absolute
flow in the same window -- is the standard imbalance estimator in
microstructure work and is unit-free across intensity regimes. By gating on
the ratio rather than the absolute count, the same threshold should mean
the same thing whether the window contains 5 or 500 contracts.

Mechanism additions over base:
  * In addition to the signed-flow deque, maintain a parallel running sum of
    *absolute* trade sizes in the same window (`abs_vol_window`). Both are
    pruned together when entries age out.
  * Replace the absolute test `|net_flow| >= flow_threshold` with the ratio
    test `|net_flow| / max(min_abs_baseline, abs_vol_window) >= ratio_threshold`.
    `min_abs_baseline` (default 2.0 contracts) is a floor on the denominator
    so a single one-sided trade in an empty window doesn't divide-by-near-
    zero and force a skip.
  * Default `ratio_threshold = 0.35` -- net flow must constitute at least
    35% of total absolute volume in the window before gating. This is a
    standard "moderately one-sided" cutoff in trade-flow imbalance work.
  * All anti-cascade and reduce-only semantics preserved exactly from base.

Quantity invariant: orders are skipped or submitted unchanged -- never
modified, split, or duplicated. Same as base.

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


class AfgBL1Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for afg-b-l1.

    Parameters
    ----------
    window_seconds : float
        Rolling look-back window for trade prints, in seconds.
        Default 10.0 seconds (same as base).
    ratio_threshold : float
        Minimum |net_flow| / max(min_abs_baseline, abs_vol_window) to trigger
        a skip. 0.0 disables the gate; 1.0 requires a fully one-sided window.
        Default 0.35.
    min_abs_baseline : float
        Floor on the denominator (in contracts). Prevents divide-by-tiny
        on empty/sparse windows. Default 2.0.
    """

    window_seconds: float = 10.0
    ratio_threshold: float = 0.35
    min_abs_baseline: float = 2.0


class AfgBL1Algorithm(ExecAlgorithm):
    """Aggressor-flow gate with volume-normalized ratio threshold.

    Opening orders (is_reduce_only == False):
      - Compute signed net flow and total absolute volume over the same
        `window_seconds` window. Compute imbalance ratio
        r = net_flow / max(min_abs_baseline, abs_vol_window).
      - Skip BUY  entries when r <= -ratio_threshold (sell pressure dominates).
      - Skip SELL entries when r >=  ratio_threshold (buy pressure dominates).
      - Submit unconditionally when the deque is empty (warm-up) or |r| <
        ratio_threshold (neutral / mixed window).
      - After any skip: _position_flat = True (next open unconditional;
        anti-cascade guarantee preserved from base).

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).
    """

    def __init__(self, config: AfgBL1Config) -> None:
        super().__init__(config=config)
        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
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
            f"AfgBL1Algorithm started "
            f"(window={self._window_ns / 1e9:.1f}s, "
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
        """Return True if the volume-normalized flow ratio is adverse.

        ratio r = net_flow / max(min_abs_baseline, abs_vol_window)
        BUY:  skip when r <= -ratio_threshold
        SELL: skip when r >=  ratio_threshold

        Returns False (do not skip) when:
          - Flow deque is empty (no trades seen yet — warm-up)
          - |r| < ratio_threshold (neutral / mixed window)
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

        if order.side == OrderSide.BUY:
            if r <= -self._ratio_threshold:
                self.log.debug(
                    f"BUY adverse flow: ratio={r:.3f} <= "
                    f"-threshold={-self._ratio_threshold:.3f} "
                    f"(net={self._net_flow:.2f}, abs_vol={self._abs_vol:.2f}); "
                    f"SKIP."
                )
                return True
        else:  # SELL
            if r >= self._ratio_threshold:
                self.log.debug(
                    f"SELL adverse flow: ratio={r:.3f} >= "
                    f"threshold={self._ratio_threshold:.3f} "
                    f"(net={self._net_flow:.2f}, abs_vol={self._abs_vol:.2f}); "
                    f"SKIP."
                )
                return True

        return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on volume-normalized aggressor flow."""
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

        # Evaluate volume-normalized aggressor-flow gate.
        if self._flow_is_adverse(order):
            self.log.info(
                f"SKIP {order.client_order_id} — adverse normalized flow "
                f"(net_flow={self._net_flow:.2f}, abs_vol={self._abs_vol:.2f}, "
                f"side={'BUY' if order.side == OrderSide.BUY else 'SELL'})."
            )
            self._position_flat = True
            # Do NOT call submit_order — quantity invariant preserved.
        else:
            self.log.debug(
                f"SUBMIT {order.client_order_id} — normalized flow neutral/favorable "
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
    ratio_threshold: float = 0.35,
    min_abs_baseline: float = 2.0,
) -> AfgBL1Algorithm:
    """Instantiate and return the AfgBL1Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_seconds : float
        Rolling window for aggressor-flow accumulation, in seconds. Default 10.0s.
    ratio_threshold : float
        Min |net_flow|/max(min_abs_baseline, abs_vol) to trigger a skip. Default 0.35.
    min_abs_baseline : float
        Floor on the denominator (contracts). Default 2.0.
    """
    config = AfgBL1Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        ratio_threshold=ratio_threshold,
        min_abs_baseline=min_abs_baseline,
    )
    return AfgBL1Algorithm(config=config)
