"""vrs-f-l6: vol-regime sizer with smooth signed-drift tightening, drift_halflife=60.

Loop 6 of the per-iteration experiment, full-trace arm, base = `vol-regime-sizer`.

Starting point: vrs-f-l3 in shape (k=3.0, max_tighten=0.9, full symmetric
sigmoid -- the proven best shape across L1-L5). The asymmetric clip tested
in L5 underperformed L3 by ~12% pnl, confirming L3's mild aligned-side
tightening was net-positive. L4's sharpened/saturated joint variant was
essentially flat vs L3. So shape is locked at L3's defaults.

Change in this loop: perturb `drift_halflife` from 30 (inherited from L1
through L5, never tested) to 60 ticks. This is a one-knob ablation isolated
from any sigmoid-shape change. The signed-drift EWM at halflife=30 ticks
weights the most recent ~30 ticks of |delta_mid| at ~50% per halflife; at
halflife=60 the same effective weight is given to the most recent ~60 ticks
-- roughly twice the smoothing horizon.

Hypothesis: the drift signal carries information about persistent
adverse-selection regimes that operate on a longer timescale than the
30-tick window captures. A slower EWM should:
  (a) reduce noise-driven sign flips of drift in low-information windows
      (fewer spurious "adverse" labels when the local price is
      direction-less);
  (b) hold a stronger adverse signal across the duration of a genuine
      adverse-selection burst, so trades arriving mid-burst still get
      tightened;
  (c) potentially miss the very-fast-onset adverse moments that the
      30-tick window catches but a 60-tick window dilutes.

If (a) and (b) dominate, pnl improves vs L3. If (c) dominates, pnl
regresses. The clean A/B isolates the timescale question that L1-L5
never settled.

All other parameters remain at L3 defaults: k=3.0, max_tighten=0.9,
drift_noise_floor=1e-7, absolute_floor=0.01, no aligned-side clip,
slow_vol normalization (halflife=120) unchanged, base vol-regime
parameters unchanged.

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


class VrsFL6Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for vrs-f-l6.

    Identical to L3 except `drift_halflife` defaults to 60 (was 30 in
    L1-L5). All sigmoid-shape parameters and base vol-regime parameters
    are L3's proven values.

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
        Half-life (in ticks) of the signed-mid-delta EWM. Default 60
        (the L6 change; L1-L5 used 30).
    drift_noise_floor : float
        If |drift| < drift_noise_floor (raw mid-price units), the drift is
        treated as zero in the tightening function (sigmoid input -> 0,
        tighten -> max_tighten / 2). Default 1e-7.
    max_tighten : float
        Asymptotic max tightening at z << 0 (strongly adverse drift).
        Default 0.9 (L3 value).
    tighten_steepness : float
        Sigmoid steepness `k`. Default 3.0 (L3 value).
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

    drift_halflife: int = 60
    drift_noise_floor: float = 1e-7
    max_tighten: float = 0.9
    tighten_steepness: float = 3.0
    drift_vol_eps: float = 1e-12
    absolute_floor: float = 0.01


class VrsFL6Algorithm(ExecAlgorithm):
    """vol-regime sizer + smooth signed-drift tightening, drift_halflife=60."""

    def __init__(self, config: VrsFL6Config) -> None:
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
        self._drift_halflife_used: int = config.drift_halflife  # for logging

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
            f"VrsFL6Algorithm started "
            f"(fast_alpha={self._fast_alpha:.4f}, slow_alpha={self._slow_alpha:.4f}, "
            f"drift_alpha={self._drift_alpha:.4f}, "
            f"drift_halflife={self._drift_halflife_used}, "
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

        Identical to L3:
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
    drift_halflife: int = 60,
    drift_noise_floor: float = 1e-7,
    max_tighten: float = 0.9,
    tighten_steepness: float = 3.0,
    drift_vol_eps: float = 1e-12,
    absolute_floor: float = 0.01,
) -> VrsFL6Algorithm:
    """Instantiate the vrs-f-l6 algorithm."""
    config = VrsFL6Config(
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
    return VrsFL6Algorithm(config=config)
