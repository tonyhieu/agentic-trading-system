"""vrs-f-l3: vol-regime sizer with smooth, vol-normalized signed-drift tightening.

Loop 3 of the per-iteration experiment, full-trace arm, base = `vol-regime-sizer`.

Starting point: vrs-f-l2 (the prior loop), which augmented the base
`vol-regime-sizer` with a binary adverse-drift tightening:
    `p_eff = max(absolute_floor, p_vol * (1 - adverse_tighten))` when
sign(drift) opposes order side. That worked strongly (+30.12% pnl vs base,
+1.06 Sharpe).

Change in this loop: replace the binary cut with a smooth, vol-normalized,
side-signed-drift-conditional tightening. Define
    `s_drift = order_sign * drift`
where `order_sign = +1` for BUY, `-1` for SELL. Normalize by `slow_vol`
(the existing slow EWM of |delta_mid|) to get a dimensionless coordinate
    `z = s_drift / max(slow_vol, eps_scale)`
Compute tightening factor as a sigmoid centred at z = 0:
    `tighten = max_tighten * sigmoid(-k * z)`
With `max_tighten = 0.9` and `k = 3.0`:
  - z >> 0 (strongly aligned): tighten -> 0 (no tightening).
  - z << 0 (strongly adverse): tighten -> 0.9 (more aggressive than L2's 0.5).
  - z = 0 (neutral or undefined drift): tighten = 0.45 (mild tightening).
Apply:
    `p_eff = max(absolute_floor, p_vol * (1 - tighten))`

Drift below noise floor (or not yet warm) -> s_drift = 0, so tighten = 0.45.
This is a deliberate behavior change vs L2 (which passed through unchanged
when drift was undefined). Reduce-only orders are always submitted. Cold-
start (tick_count < min_ticks) submits at p=1.0. Calm regimes (p_vol ~ 1.0)
short-circuit to p_eff = 1.0. The accept/reject draw is the same
deterministic SHA-256 uniform on client_order_id as in base/L1/L2.

Mechanism / inefficiency exploited: loop 2 showed direction matters within
the vol-skip region. The smooth function further encodes that drift
*magnitude* (relative to vol) matters too — strongly-adverse moments are
likely worse than marginally-adverse ones, in the same way large vol
excess is worse than small vol excess. The sigmoid concentrates additional
skipping in the strongly-adverse tail (where L2 was likely under-skipping)
while preserving L2's near-no-op on the strongly-aligned side.

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


class VrsFL3Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for vrs-f-l3.

    Inherits all base vol-regime parameters from L2 (and base) verbatim.
    Inherits the signed-drift EWM parameters (`drift_halflife`,
    `drift_noise_floor`) from L1/L2. Replaces L2's `adverse_tighten`
    with the smooth-tightening parameters `max_tighten` and
    `tighten_steepness`, plus `drift_vol_eps` to guard the vol
    normalization denominator.

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
        If |drift| < drift_noise_floor (raw mid-price units), the drift is
        treated as zero in the tightening function (sigmoid input -> 0,
        tighten -> max_tighten / 2). Default 1e-7.
    max_tighten : float
        Asymptotic max tightening at z << 0 (strongly adverse drift). The
        tightening factor t = max_tighten * sigmoid(-k * z) lies in
        [0, max_tighten]. Default 0.9.
    tighten_steepness : float
        Sigmoid steepness `k`. Higher k recovers the binary cut; lower k
        gives a softer ramp. Default 3.0.
    drift_vol_eps : float
        Hard lower bound on the slow_vol denominator in the vol
        normalization `z = s_drift / max(slow_vol, drift_vol_eps)`.
        Default 1e-12.
    absolute_floor : float
        Hard lower bound on p_eff after smooth tightening. Set strictly
        below `min_prob` so it only binds when the sigmoid pushes
        p_vol * (1 - tighten) below this. Default 0.01.
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


class VrsFL3Algorithm(ExecAlgorithm):
    """vol-regime sizer + smooth vol-normalized signed-drift tightening."""

    def __init__(self, config: VrsFL3Config) -> None:
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
        self._tighten_applied: int = 0       # any tightening (z != saturated aligned)
        self._tighten_zero_drift: int = 0    # |drift| below noise floor

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"VrsFL3Algorithm started "
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
        """Smooth vol-normalized signed-drift tightening on top of p_vol.

        tighten = max_tighten * sigmoid(-k * z)
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
    max_tighten: float = 0.9,
    tighten_steepness: float = 3.0,
    drift_vol_eps: float = 1e-12,
    absolute_floor: float = 0.01,
) -> VrsFL3Algorithm:
    """Instantiate the vrs-f-l3 algorithm."""
    config = VrsFL3Config(
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
    return VrsFL3Algorithm(config=config)
