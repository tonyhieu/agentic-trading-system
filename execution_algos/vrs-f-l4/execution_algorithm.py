"""vrs-f-l4: vol-regime sizer with sharper smooth tightening + full-skip adverse tail.

Loop 4 of the per-iteration experiment, full-trace arm, base = `vol-regime-sizer`.

Starting point: vrs-f-l3 (the prior loop), which replaced L2's binary
adverse-drift cut with a smooth, vol-normalized signed-drift sigmoid:
    `tighten = max_tighten * sigmoid(-k * z)` with `max_tighten=0.9` and
    `k=3.0`, and `z = order_sign * drift / max(slow_vol, eps)`.
That worked strongly (+82.36% pnl vs base_algo, +40.15% vs L2, sharpe 5.80).

Change in this loop: sharpen the sigmoid and push the adverse asymptote to
the absolute floor.
  - `max_tighten`: 0.9 -> 1.0 (saturated adverse trades get
    `p_eff = p_vol * 0 = 0`, then clamped to `absolute_floor = 0.01`).
  - `tighten_steepness` (k): 3.0 -> 6.0 (transition zone narrows from
    `|z|<0.5` to `|z|<0.25`; saturation moves from `|z|~1.5` to `|z|~0.75`).
All other plumbing identical to L3:
  - drift EWM halflife = 30, noise floor = 1e-7
  - vol EWMs (fast=20, slow=120) and base p_vol formula
  - vol-normalized `z = order_sign * drift / max(slow_vol, drift_vol_eps)`
  - sigmoid centered at z=0 (z=0 still gives tighten = max_tighten/2 = 0.5
    with the new max_tighten=1.0, slightly above L3's 0.45)
  - absolute_floor = 0.01 safeguard
  - reduce-only orders always submit, cold-start submits at 1.0, calm
    regimes short-circuit to 1.0

Mechanism / inefficiency exploited: L3's data showed the
strongly-adverse tail (z << 0) was the dominant gain driver. The
sharper sigmoid concentrates more tightening in that tail while
*reducing* tightening on the marginally-adverse band (z slightly
negative) and the marginally-aligned band (z slightly positive). This
is a targeted hypothesis: the worst tail is uniformly bad and warrants
full skipping; the boundary regions are noisier and benefit from less
aggressive treatment.

Quantity invariant: child_qty = parent_qty = 1 -- unchanged.
"""
from __future__ import annotations

import hashlib
import math
import struct

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class VrsFL4Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for vrs-f-l4.

    Inherits all base vol-regime parameters from L3 verbatim. Only the
    two sigmoid shape parameters change:
      - max_tighten: 0.9 -> 1.0
      - tighten_steepness: 3.0 -> 6.0

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
        tightening function. Default 1e-7.
    max_tighten : float
        Asymptotic max tightening at z << 0 (strongly adverse drift).
        Default 1.0 (full skip in adverse tail, bounded by absolute_floor).
    tighten_steepness : float
        Sigmoid steepness `k`. Higher = sharper transition around z=0.
        Default 6.0.
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
    max_tighten: float = 1.0
    tighten_steepness: float = 6.0
    drift_vol_eps: float = 1e-12
    absolute_floor: float = 0.01


class VrsFL4Algorithm(ExecAlgorithm):
    """vol-regime sizer + sharper smooth signed-drift tightening with full-skip tail."""

    def __init__(self, config: VrsFL4Config) -> None:
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
        self._tighten_applied: int = 0
        self._tighten_zero_drift: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"VrsFL4Algorithm started "
            f"(fast_alpha={self._fast_alpha:.4f}, slow_alpha={self._slow_alpha:.4f}, "
            f"drift_alpha={self._drift_alpha:.4f}, "
            f"sensitivity={self._sensitivity}, min_prob={self._min_prob}, "
            f"max_tighten={self._max_tighten}, "
            f"tighten_steepness={self._tighten_steepness}, "
            f"absolute_floor={self._absolute_floor}, "
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
        self._tighten_applied = 0
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
        warm), which yields tighten = max_tighten / 2.
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
        """Sharper smooth vol-normalized signed-drift tightening on top of p_vol.

        tighten = max_tighten * sigmoid(-k * z)  with k=6.0, max_tighten=1.0
        p_eff = max(absolute_floor, p_vol * (1 - tighten))
        """
        if p_vol >= 1.0 - 1e-9:
            # Calm regime -- vol skip is dormant, nothing to tighten.
            return 1.0

        z = self._signed_drift_z(order_side)
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
    max_tighten: float = 1.0,
    tighten_steepness: float = 6.0,
    drift_vol_eps: float = 1e-12,
    absolute_floor: float = 0.01,
) -> VrsFL4Algorithm:
    """Instantiate the vrs-f-l4 algorithm."""
    config = VrsFL4Config(
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
    return VrsFL4Algorithm(config=config)
