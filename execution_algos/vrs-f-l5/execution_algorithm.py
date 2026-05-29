"""vrs-f-l5: vol-regime sizer with asymmetric (adverse-only) sigmoid tightening.

Loop 5 of the per-iteration experiment, full-trace arm, base = `vol-regime-sizer`.

Starting point: vrs-f-l4. L4 jointly pushed `max_tighten` 0.9->1.0 and
`tighten_steepness` k 3.0->6.0 vs L3. The full 12-date result is
$1,344.50 / sharpe 5.71 -- essentially flat-to-slightly-below L3
($1,374.50 / 5.80). This says the joint change of (sharper k + full
saturation) was a tiny step backward. L4's data is consistent with the
adverse-side gain from saturation being roughly canceled by the
aligned-side harm from reduced tightening.

Change in this loop -- the asymmetric clip L4 explicitly prescribed:
  1. Revert sigmoid shape parameters to L3's proven values:
     `max_tighten` = 0.9, `tighten_steepness` = 3.0.
  2. Clip the tightening to zero on the aligned side (z > 0). The
     z <= 0 branch (adverse drift and undefined/zero-drift) is
     identical to L3; the z > 0 branch is a full no-op (matches L2's
     aligned passthrough).

So L5 = L3 on the adverse half-line, L2 on the aligned half-line. This
isolates the aligned-side tightening from the adverse-side tightening
that L1-L3 conflated, and provides a clean A/B vs L3 on whether
aligned-side tightening was net-positive, net-neutral, or net-negative.

Numerical effect on the tightening curve (compare to L3 / L4):

| z       | L3 (k=3, mt=0.9) | L4 (k=6, mt=1.0) | L5 (k=3, mt=0.9, clipped) |
|---------|-------------------|--------------------|---------------------------|
| -2.0    | 0.897             | 1.000 -> floor    | 0.897                     |
| -1.0    | 0.857             | 0.998             | 0.857                     |
| -0.5    | 0.736             | 0.953             | 0.736                     |
| -0.25   | 0.611             | 0.818             | 0.611                     |
|  0.0    | 0.450             | 0.500             | 0.450                     |
| +0.25   | 0.289             | 0.182             | 0.000                     |
| +0.5    | 0.164             | 0.047             | 0.000                     |
| +1.0    | 0.043             | 0.002             | 0.000                     |
| +2.0    | 0.002             | ~0                | 0.000                     |

Mechanism / inefficiency exploited: L2 and L3 showed adverse-drift
tightening is the dominant gain driver. L4 showed that joint sharpening
+ saturation doesn't help. L5 tests whether the aligned-side tightening
(L3) was beneficial, neutral, or harmful in isolation -- by removing
it entirely and keeping everything else.

Quantity invariant: child_qty = parent_qty = 1.
"""
from __future__ import annotations

import hashlib
import math
import struct

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class VrsFL5Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for vrs-f-l5.

    Inherits L3's vol-regime + drift parameters and L3's sigmoid shape
    (max_tighten=0.9, tighten_steepness=3.0). The only behavioral change
    vs L3 is the aligned-side clip (z > 0 -> tighten = 0).

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
        Half-life (in ticks) of the signed-mid-delta EWM. Default 30.
    drift_noise_floor : float
        If |drift| < drift_noise_floor, drift is treated as zero in the
        tightening function (which puts it at the z=0 / undefined-drift
        defensive tightening of max_tighten/2 = 0.45). Default 1e-7.
    max_tighten : float
        Asymptotic max tightening at z << 0 (strongly adverse drift).
        Default 0.9 (reverted from L4's 1.0 back to L3's value).
    tighten_steepness : float
        Sigmoid steepness `k`. Default 3.0 (reverted from L4's 6.0).
    drift_vol_eps : float
        Hard lower bound on slow_vol denominator. Default 1e-12.
    absolute_floor : float
        Hard lower bound on p_eff after smooth tightening. Default 0.01.
    """

    fast_halflife: int = 20
    slow_halflife: int = 120
    sensitivity: float = 2.0
    min_prob: float = 0.05
    min_ticks: int = 30
    max_vol_ratio: float = 5.0

    drift_halflife: int = 30
    drift_noise_floor: float = 1e-7
    max_tighten: float = 0.9
    tighten_steepness: float = 3.0
    drift_vol_eps: float = 1e-12
    absolute_floor: float = 0.01


class VrsFL5Algorithm(ExecAlgorithm):
    """vol-regime sizer + asymmetric (adverse-only) smooth signed-drift tightening."""

    def __init__(self, config: VrsFL5Config) -> None:
        super().__init__(config=config)

        # Vol-EWM alphas
        self._fast_alpha: float = 1.0 - math.exp(-math.log(2) / config.fast_halflife)
        self._slow_alpha: float = 1.0 - math.exp(-math.log(2) / config.slow_halflife)
        self._sensitivity: float = config.sensitivity
        self._min_prob: float = config.min_prob
        self._min_ticks: int = config.min_ticks
        self._max_vol_ratio: float = config.max_vol_ratio

        # Drift-EWM alpha + smooth-tightening params
        self._drift_alpha: float = 1.0 - math.exp(-math.log(2) / config.drift_halflife)
        self._drift_noise_floor: float = config.drift_noise_floor
        self._max_tighten: float = config.max_tighten
        self._tighten_steepness: float = config.tighten_steepness
        self._drift_vol_eps: float = config.drift_vol_eps
        self._absolute_floor: float = config.absolute_floor

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
        self._tighten_applied: int = 0       # tighten > 1e-9 (i.e., z<=0 path)
        self._tighten_clipped_aligned: int = 0  # z > 0 path (clip active)
        self._tighten_zero_drift: int = 0    # |drift| < noise_floor path

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"VrsFL5Algorithm started "
            f"(fast_alpha={self._fast_alpha:.4f}, slow_alpha={self._slow_alpha:.4f}, "
            f"drift_alpha={self._drift_alpha:.4f}, "
            f"sensitivity={self._sensitivity}, min_prob={self._min_prob}, "
            f"max_tighten={self._max_tighten}, "
            f"tighten_steepness={self._tighten_steepness}, "
            f"absolute_floor={self._absolute_floor}, "
            f"drift_noise_floor={self._drift_noise_floor}, "
            f"aligned_clip=ON)."
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
        self._tighten_applied = 0
        self._tighten_clipped_aligned = 0
        self._tighten_zero_drift = 0

    # ------------------------------------------------------------------
    # Quote-tick handler -- update vol EWMs and signed-drift EWM
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
        """Base vol-regime submission probability -- identical to base algo."""
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

    @staticmethod
    def _sigmoid(x: float) -> float:
        """Numerically-stable logistic sigmoid."""
        if x >= 0.0:
            ez = math.exp(-x)
            return 1.0 / (1.0 + ez)
        else:
            ez = math.exp(x)
            return ez / (1.0 + ez)

    def _signed_drift_z(self, order_side) -> float:
        """Vol-normalized side-signed drift coordinate.

        Returns 0.0 if drift is below the noise floor (or state not yet
        warm). Caller distinguishes "z==0 because undefined" via the
        drift state directly; the clip then puts this case on the
        z<=0 (smooth tighten) branch with tighten=max_tighten/2.
        """
        if self._drift is None or self._slow_vol is None:
            return 0.0
        if abs(self._drift) < self._drift_noise_floor:
            return 0.0
        order_sign = 1.0 if order_side == OrderSide.BUY else -1.0
        s_drift = order_sign * self._drift
        denom = max(self._slow_vol, self._drift_vol_eps)
        return s_drift / denom

    def _effective_prob(self, p_vol: float, order_side) -> float:
        """Asymmetric smooth vol-normalized signed-drift tightening on top of p_vol.

        Three branches:
          - p_vol >= ~1.0       -> p_eff = 1.0 (calm regime, no tightening)
          - z > 0 (aligned)     -> tighten = 0, p_eff = p_vol (full no-op)
          - z <= 0 (adverse /
            undefined drift)   -> tighten = max_tighten * sigmoid(-k * z)
                                  p_eff = max(absolute_floor, p_vol * (1 - tighten))
        """
        if p_vol >= 1.0 - 1e-9:
            # Calm regime -- vol skip is dormant, nothing to tighten.
            return 1.0

        z = self._signed_drift_z(order_side)

        if z > 0.0:
            # Aligned-side clip: full no-op, identical to L2's aligned passthrough.
            self._tighten_clipped_aligned += 1
            return p_vol

        # z <= 0 path: smooth adverse tightening (identical to L3 on this half-line).
        if z == 0.0 and (
            self._drift is None
            or abs(self._drift) < self._drift_noise_floor
        ):
            self._tighten_zero_drift += 1

        tighten = self._max_tighten * self._sigmoid(-self._tighten_steepness * z)
        if tighten > 1e-9:
            self._tighten_applied += 1

        tightened = p_vol * (1.0 - tighten)
        return max(self._absolute_floor, tightened)

    # ------------------------------------------------------------------
    # Deterministic pseudo-random draw -- identical to base
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
                f"tighten_applied={self._tighten_applied} "
                f"tighten_clipped_aligned={self._tighten_clipped_aligned} "
                f"tighten_zero_drift={self._tighten_zero_drift}."
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
    max_tighten: float = 0.9,
    tighten_steepness: float = 3.0,
    drift_vol_eps: float = 1e-12,
    absolute_floor: float = 0.01,
) -> VrsFL5Algorithm:
    """Instantiate the vrs-f-l5 algorithm."""
    config = VrsFL5Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        fast_halflife=fast_halflife,
        slow_halflife=slow_halflife,
        sensitivity=sensitivity,
        min_prob=min_prob,
        min_ticks=min_ticks,
        max_vol_ratio=max_vol_ratio,
        drift_halflife=drift_halflife,
        drift_noise_floor=drift_noise_floor,
        max_tighten=max_tighten,
        tighten_steepness=tighten_steepness,
        drift_vol_eps=drift_vol_eps,
        absolute_floor=absolute_floor,
    )
    return VrsFL5Algorithm(config=config)
