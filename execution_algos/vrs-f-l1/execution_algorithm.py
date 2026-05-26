"""vrs-f-l1: vol-regime sizer + directional-alignment skip relaxation.

Loop 1 of the per-iteration experiment, full-trace arm, base = `vol-regime-sizer`.

Starting point: the base `vol-regime-sizer` algorithm, which computes a
submission probability `p_vol = max(min_prob, exp(-sensitivity * max(0,
vol_ratio - 1)))` from fast/slow EWMs of |delta_mid| and routes each
open-leg order through a deterministic SHA-256 uniform draw on its
client_order_id.

Change in this loop: condition the skip on directional alignment between
the order side and the recent *signed* mid-price drift. A separate EWM of
signed mid-deltas (`drift`, halflife = `drift_halflife`) is maintained. On
each open-leg order:

  - Compute `p_vol` as in the base.
  - If `|drift|` exceeds `drift_noise_floor` AND `sign(drift)` matches the
    order side (BUY with drift > 0, or SELL with drift < 0), we are in an
    *aligned* trend-aligned high-vol burst. Soften the skip:
        p_eff = p_vol + align_boost * (1.0 - p_vol)
    so a base p_vol=0.05 becomes p_eff=0.715 at align_boost=0.7.
  - Otherwise (adverse drift, or drift below noise floor), use `p_vol`
    unchanged — preserving the base's loss-mitigation behavior.

In calm regimes (`p_vol = 1.0`) both branches collapse to full participation.
Reduce-only orders are always submitted unconditionally (intraday_flat
compliance, identical to base). Cold-start (tick_count < min_ticks) submits
at p=1.0 (identical to base). The accept/reject draw is the same
deterministic SHA-256 uniform on client_order_id.

Quantity invariant: child_qty = parent_qty = 1 — unchanged.
"""
from __future__ import annotations

import hashlib
import math
import struct

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class VrsFL1Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for vrs-f-l1.

    All vol-regime parameters are inherited semantically from the base
    `vol-regime-sizer`; three new parameters (`drift_halflife`,
    `drift_noise_floor`, `align_boost`) control the directional-alignment
    relaxation.

    Parameters
    ----------
    fast_halflife : int
        Half-life (in ticks) of the fast EWM of |delta_mid|. Default 20.
    slow_halflife : int
        Half-life (in ticks) of the slow EWM of |delta_mid|. Default 120.
    sensitivity : float
        Decay rate mapping vol excess to submission probability. Default 2.0.
    min_prob : float
        Floor on vol-only submission probability. Default 0.05.
    min_ticks : int
        Cold-start guard: full submission for first N ticks. Default 30.
    max_vol_ratio : float
        Clip vol_ratio to prevent outlier domination. Default 5.0.
    drift_halflife : int
        Half-life (in ticks) of the signed-mid-delta EWM used as the
        directional drift signal. Default 30.
    drift_noise_floor : float
        If |drift| < drift_noise_floor (raw mid-price units), alignment is
        undefined and the base p_vol is used unchanged. Default 1e-7.
    align_boost : float
        Blend factor for the aligned-drift case:
            p_eff = p_vol + align_boost * (1.0 - p_vol)
        In [0, 1]. 0.0 = no boost (degenerates to base); 1.0 = always full
        participation when aligned. Default 0.7.
    """

    fast_halflife: int = 20
    slow_halflife: int = 120
    sensitivity: float = 2.0
    min_prob: float = 0.05
    min_ticks: int = 30
    max_vol_ratio: float = 5.0

    drift_halflife: int = 30
    drift_noise_floor: float = 1e-7
    align_boost: float = 0.7


class VrsFL1Algorithm(ExecAlgorithm):
    """vol-regime sizer + directional-alignment relaxation."""

    def __init__(self, config: VrsFL1Config) -> None:
        super().__init__(config=config)

        # Vol-EWM alphas
        self._fast_alpha: float = 1.0 - math.exp(-math.log(2) / config.fast_halflife)
        self._slow_alpha: float = 1.0 - math.exp(-math.log(2) / config.slow_halflife)
        self._sensitivity: float = config.sensitivity
        self._min_prob: float = config.min_prob
        self._min_ticks: int = config.min_ticks
        self._max_vol_ratio: float = config.max_vol_ratio

        # Drift-EWM alpha + relaxation params
        self._drift_alpha: float = 1.0 - math.exp(-math.log(2) / config.drift_halflife)
        self._drift_noise_floor: float = config.drift_noise_floor
        self._align_boost: float = config.align_boost

        # EWM state
        self._fast_vol: float | None = None    # EWM of |delta_mid|
        self._slow_vol: float | None = None    # EWM of |delta_mid|
        self._drift: float | None = None       # EWM of signed delta_mid
        self._prev_mid: float | None = None
        self._tick_count: int = 0

        # Subscription tracking
        self._subscribed: set[str] = set()

        # Diagnostic counters
        self._submitted: int = 0
        self._skipped: int = 0
        self._aligned_boosted: int = 0
        self._adverse_kept: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"VrsFL1Algorithm started "
            f"(fast_alpha={self._fast_alpha:.4f}, slow_alpha={self._slow_alpha:.4f}, "
            f"drift_alpha={self._drift_alpha:.4f}, "
            f"sensitivity={self._sensitivity}, min_prob={self._min_prob}, "
            f"align_boost={self._align_boost}, "
            f"drift_noise_floor={self._drift_noise_floor})."
        )

    def on_reset(self) -> None:
        self._fast_vol = None
        self._slow_vol = None
        self._drift = None
        self._prev_mid = None
        self._tick_count = 0
        self._subscribed.clear()
        self._submitted = 0
        self._skipped = 0
        self._aligned_boosted = 0
        self._adverse_kept = 0

    # ------------------------------------------------------------------
    # Quote-tick handler — update vol EWMs and signed-drift EWM
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    def on_quote_tick(self, tick) -> None:
        try:
            bid = float(str(tick.bid_price))
            ask = float(str(tick.ask_price))
            mid = (bid + ask) / 2.0
        except Exception:
            return

        if self._prev_mid is not None:
            delta = mid - self._prev_mid
            abs_delta = abs(delta)

            # |delta_mid| EWMs (vol)
            if self._fast_vol is None:
                self._fast_vol = abs_delta
                self._slow_vol = abs_delta
            else:
                self._fast_vol = (
                    self._fast_alpha * abs_delta + (1.0 - self._fast_alpha) * self._fast_vol
                )
                self._slow_vol = (
                    self._slow_alpha * abs_delta + (1.0 - self._slow_alpha) * self._slow_vol
                )

            # Signed delta_mid EWM (drift)
            if self._drift is None:
                self._drift = delta
            else:
                self._drift = (
                    self._drift_alpha * delta + (1.0 - self._drift_alpha) * self._drift
                )

        self._prev_mid = mid
        self._tick_count += 1

    # ------------------------------------------------------------------
    # Probability computation
    # ------------------------------------------------------------------

    def _compute_vol_prob(self) -> float:
        """Base vol-regime submission probability — identical to base algo."""
        if self._tick_count < self._min_ticks:
            return 1.0

        if self._fast_vol is None or self._slow_vol is None:
            return 1.0

        if self._slow_vol < 1e-12:
            return 1.0

        vol_ratio = min(self._fast_vol / self._slow_vol, self._max_vol_ratio)
        excess = max(0.0, vol_ratio - 1.0)
        prob = math.exp(-self._sensitivity * excess)
        return max(self._min_prob, prob)

    def _is_aligned(self, order_side) -> bool | None:
        """Return True if order direction agrees with sign(drift), False if it
        opposes drift, None if drift is below the noise floor (undefined).
        """
        if self._drift is None:
            return None
        if abs(self._drift) < self._drift_noise_floor:
            return None
        if self._drift > 0.0:
            return order_side == OrderSide.BUY
        else:  # self._drift < 0.0
            return order_side == OrderSide.SELL

    def _effective_prob(self, p_vol: float, order_side) -> float:
        """Blend p_vol with the directional-alignment indicator."""
        if p_vol >= 1.0 - 1e-9:
            return 1.0  # calm regime — no boost needed

        aligned = self._is_aligned(order_side)
        if aligned is True:
            # Soften the skip toward full participation
            self._aligned_boosted += 1
            return p_vol + self._align_boost * (1.0 - p_vol)
        elif aligned is False:
            # Adverse drift — keep base p_vol (loss-mitigation preserved)
            self._adverse_kept += 1
            return p_vol
        else:  # None — drift undefined (below noise floor)
            return p_vol

    # ------------------------------------------------------------------
    # Deterministic pseudo-random draw — identical to base
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
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders: always submit unconditionally.
        if order.is_reduce_only:
            self.submit_order(order)
            return

        p_vol = self._compute_vol_prob()
        p_eff = self._effective_prob(p_vol, order.side)

        if p_eff >= 1.0 - 1e-9:
            self._submitted += 1
            self.submit_order(order)
            return

        u = self._order_uniform(str(order.client_order_id))

        if u < p_eff:
            self._submitted += 1
            self.submit_order(order)
        else:
            self._skipped += 1
            self.log.debug(
                f"SKIP {order.client_order_id} "
                f"(p_vol={p_vol:.4f}, p_eff={p_eff:.4f}, u={u:.4f}, "
                f"drift={self._drift if self._drift is not None else float('nan'):.2e}, "
                f"side={order.side}). "
                f"submitted={self._submitted} skipped={self._skipped} "
                f"aligned_boosted={self._aligned_boosted} adverse_kept={self._adverse_kept}."
            )


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    fast_halflife: int = 20,
    slow_halflife: int = 120,
    sensitivity: float = 2.0,
    min_prob: float = 0.05,
    min_ticks: int = 30,
    max_vol_ratio: float = 5.0,
    drift_halflife: int = 30,
    drift_noise_floor: float = 1e-7,
    align_boost: float = 0.7,
) -> VrsFL1Algorithm:
    """Instantiate the vrs-f-l1 algorithm."""
    config = VrsFL1Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        fast_halflife=fast_halflife,
        slow_halflife=slow_halflife,
        sensitivity=sensitivity,
        min_prob=min_prob,
        min_ticks=min_ticks,
        max_vol_ratio=max_vol_ratio,
        drift_halflife=drift_halflife,
        drift_noise_floor=drift_noise_floor,
        align_boost=align_boost,
    )
    return VrsFL1Algorithm(config=config)
