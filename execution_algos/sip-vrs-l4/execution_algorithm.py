"""Trendiness-aware vol-regime sizer.

Extends `vol-regime-sizer` by recognizing that |delta_mid| volatility is
symmetric: it does not distinguish a *choppy / mean-reverting* regime from a
*trending* regime. The parent treats both identically (skips both), which is
suspected to forgo profitable participation when high vol is unidirectional.

Mechanism (parent submission probability `p_vol` is unchanged):

    p_vol = max(min_prob, exp(-sensitivity * max(0, vol_ratio - 1)))
    T     = |sum_window_delta_mid| / (sum_window_abs_delta_mid + eps)   # in [0, 1]
    p     = max(min_prob, T + (1 - T) * p_vol)

Where `T` is the *trendiness ratio* measured over a recent rolling window of
mid-changes. T=1 (pure trend, all deltas one-signed) re-admits the order at
full probability; T=0 (pure chop, signed deltas cancel) preserves the parent's
behavior. Mixed regimes interpolate linearly.

The rolling window for T is a fixed-length deque of the last `trend_window`
mid-changes (default 40 ticks — twice the fast EWM half-life). This is
independent of the EWM vol estimator so the trendiness signal is not
contaminated by the vol level.

Reduce-only orders are always submitted (intraday_flat compliance).
Quantity invariant: child_qty = parent_qty = 1, never inflated.

Cold-start: same as parent — full participation until `min_ticks` quote ticks
have been seen. The trend window is also still warming during this phase; in
the rare case it has < trend_window samples after min_ticks, T uses whatever
samples exist (no special-case branch needed — the ratio is well-defined
once any delta exists).
"""
from __future__ import annotations

import hashlib
import math
import struct
from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class SipVrsL4Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for sip-vrs-l4.

    Parameters
    ----------
    fast_halflife : int
        Fast EWM half-life (ticks) for vol estimation. Default 20.
    slow_halflife : int
        Slow EWM half-life (ticks) — vol baseline. Default 120.
    sensitivity : float
        Vol decay coefficient. p_vol = exp(-sensitivity * (vol_ratio - 1)).
        Default 2.0.
    min_prob : float
        Floor on final submission probability. Default 0.05.
    min_ticks : int
        Cold-start guard. Default 30.
    max_vol_ratio : float
        Clip vol_ratio to dampen outliers. Default 5.0.
    trend_window : int
        Number of recent mid-changes used to compute the trendiness ratio T.
        Default 40 (two parent fast half-lives).
    """

    fast_halflife: int = 20
    slow_halflife: int = 120
    sensitivity: float = 2.0
    min_prob: float = 0.05
    min_ticks: int = 30
    max_vol_ratio: float = 5.0
    trend_window: int = 40


class SipVrsL4Algorithm(ExecAlgorithm):
    """Vol-regime sizer with a trendiness multiplier."""

    def __init__(self, config: SipVrsL4Config) -> None:
        super().__init__(config=config)

        self._fast_alpha: float = 1.0 - math.exp(-math.log(2) / config.fast_halflife)
        self._slow_alpha: float = 1.0 - math.exp(-math.log(2) / config.slow_halflife)
        self._sensitivity: float = config.sensitivity
        self._min_prob: float = config.min_prob
        self._min_ticks: int = config.min_ticks
        self._max_vol_ratio: float = config.max_vol_ratio
        self._trend_window: int = config.trend_window

        # EWM vol state (parent mechanism preserved verbatim).
        self._fast_vol: float | None = None
        self._slow_vol: float | None = None
        self._prev_mid: float | None = None
        self._tick_count: int = 0

        # Trendiness window: signed mid-changes, plus running sums for O(1) update.
        self._delta_window: deque[float] = deque(maxlen=config.trend_window)
        self._sum_signed: float = 0.0   # sum of signed deltas in window
        self._sum_abs: float = 0.0      # sum of |deltas| in window

        # Subscription tracking
        self._subscribed: set[str] = set()

        # Diagnostic counters
        self._submitted: int = 0
        self._skipped: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"SipVrsL4Algorithm started "
            f"(fast_alpha={self._fast_alpha:.4f}, slow_alpha={self._slow_alpha:.4f}, "
            f"sensitivity={self._sensitivity}, min_prob={self._min_prob}, "
            f"min_ticks={self._min_ticks}, trend_window={self._trend_window})."
        )

    def on_reset(self) -> None:
        self._fast_vol = None
        self._slow_vol = None
        self._prev_mid = None
        self._tick_count = 0
        self._delta_window.clear()
        self._sum_signed = 0.0
        self._sum_abs = 0.0
        self._subscribed.clear()
        self._submitted = 0
        self._skipped = 0

    # ------------------------------------------------------------------
    # Quote tick handler
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    def on_quote_tick(self, tick) -> None:
        """Update EWMs and the rolling trendiness window."""
        try:
            bid = float(str(tick.bid_price))
            ask = float(str(tick.ask_price))
            mid = (bid + ask) / 2.0
        except Exception:
            return

        if self._prev_mid is not None:
            delta = mid - self._prev_mid
            abs_delta = abs(delta)

            # Parent EWM vol update (verbatim from vol-regime-sizer).
            if self._fast_vol is None:
                self._fast_vol = abs_delta
                self._slow_vol = abs_delta
            else:
                self._fast_vol = (
                    self._fast_alpha * abs_delta
                    + (1.0 - self._fast_alpha) * self._fast_vol
                )
                self._slow_vol = (
                    self._slow_alpha * abs_delta
                    + (1.0 - self._slow_alpha) * self._slow_vol
                )

            # Trendiness window: O(1) running-sum update via deque eviction.
            if len(self._delta_window) == self._trend_window:
                old = self._delta_window[0]
                self._sum_signed -= old
                self._sum_abs -= abs(old)
            self._delta_window.append(delta)
            self._sum_signed += delta
            self._sum_abs += abs_delta

        self._prev_mid = mid
        self._tick_count += 1

    # ------------------------------------------------------------------
    # Submission probability
    # ------------------------------------------------------------------

    def _compute_vol_prob(self) -> float:
        """Parent vol-regime probability (unchanged)."""
        if self._tick_count < self._min_ticks:
            return 1.0
        if self._fast_vol is None or self._slow_vol is None:
            return 1.0
        if self._slow_vol < 1e-12:
            return 1.0
        vol_ratio = min(self._fast_vol / self._slow_vol, self._max_vol_ratio)
        excess = max(0.0, vol_ratio - 1.0)
        return max(self._min_prob, math.exp(-self._sensitivity * excess))

    def _compute_trendiness(self) -> float:
        """Return T in [0, 1] — the directional ratio of recent mid-changes.

        T = |sum_signed_deltas| / (sum_abs_deltas + eps).

        With < 2 samples, returns 0.0 (parent behavior dominates).
        """
        if self._sum_abs < 1e-12:
            return 0.0
        return min(1.0, abs(self._sum_signed) / self._sum_abs)

    def _compute_submit_prob(self) -> float:
        """Blend parent vol probability with the trendiness multiplier.

        p = max(min_prob, T + (1 - T) * p_vol)
        """
        p_vol = self._compute_vol_prob()
        if p_vol >= 1.0 - 1e-9:
            return 1.0
        if self._tick_count < self._min_ticks:
            return 1.0
        T = self._compute_trendiness()
        p = T + (1.0 - T) * p_vol
        p = max(self._min_prob, min(1.0, p))
        return p

    # ------------------------------------------------------------------
    # Deterministic pseudo-random draw
    # ------------------------------------------------------------------

    @staticmethod
    def _order_uniform(order_id_str: str) -> float:
        digest = hashlib.sha256(order_id_str.encode()).digest()
        val = struct.unpack(">Q", digest[:8])[0]
        return val / (2**64)

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on blended vol/trend probability."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only orders: always submit — intraday_flat compliance.
        if order.is_reduce_only:
            self.submit_order(order)
            return

        p = self._compute_submit_prob()

        if p >= 1.0 - 1e-9:
            self._submitted += 1
            self.submit_order(order)
            return

        u = self._order_uniform(str(order.client_order_id))
        if u < p:
            self._submitted += 1
            self.submit_order(order)
        else:
            self._skipped += 1
            # Do NOT call submit_order — quantity invariant preserved.


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    fast_halflife: int = 20,
    slow_halflife: int = 120,
    sensitivity: float = 2.0,
    min_prob: float = 0.05,
    min_ticks: int = 30,
    max_vol_ratio: float = 5.0,
    trend_window: int = 40,
) -> SipVrsL4Algorithm:
    """Instantiate and return SipVrsL4Algorithm."""
    config = SipVrsL4Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        fast_halflife=fast_halflife,
        slow_halflife=slow_halflife,
        sensitivity=sensitivity,
        min_prob=min_prob,
        min_ticks=min_ticks,
        max_vol_ratio=max_vol_ratio,
        trend_window=trend_window,
    )
    return SipVrsL4Algorithm(config=config)
