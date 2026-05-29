"""vrs-f-l8: vol-regime sizer + smooth signed-drift tightening + book-imbalance second signal.

Loop 8 (FINAL) of the per-iteration experiment, full-trace arm,
base = `vol-regime-sizer`.

Starting point: vrs-f-l6 (current best across L1-L7). L6's mechanism is the
L3-shape smooth sigmoid (k=3.0, max_tighten=0.9, full symmetric, defensive
z=0 tightening at 0.45) plus drift_halflife=60. L6 produced +91.97% pnl vs
base / sharpe 5.87.

L1-L7 trajectory:
  L1 -34.23% (alignment relaxation -- refuted)
  L2 +30.12% (binary adverse tightening -- supported)
  L3 +82.36% (smooth sigmoid k=3, max_tighten=0.9, symmetric)
  L4 +78.37% (sharper k=6 + saturated -- regress)
  L5 +59.67% (asymmetric clip -- regress)
  L6 +91.97% (drift_halflife 30 -> 60 -- NEW BEST)
  L7 +83.68% (drift_halflife 60 -> 90 -- regress, optimum at 60)

The (k, max_tighten, symmetry, drift_halflife) plane is well-explored and
every axis perturbed from L6 either regressed or tied. L4-L7 each flagged
"book imbalance or aggressor flow as second directional signal" as the
most promising orthogonal extension, deferred each time. L7's explicit
final prescription: "L8 should pivot to the orthogonal signal direction".

Change in this loop: add a SECOND directional signal -- top-of-book size
imbalance -- combined with the existing drift signal via weighted average,
then fed through the same proven sigmoid. The imbalance signal:

    imbal_raw = (bid_size - ask_size) / (bid_size + ask_size)   in [-1, 1]
    imbal_ewm = EWM(imbal_raw, halflife=60)
    z_imbal   = order_sign * imbal_ewm * imbal_scale            scale ~ 2.0

    z_combined = drift_weight * z_drift + imbal_weight * z_imbal
               (drift_weight=0.6, imbal_weight=0.4, sum=1.0)

    tighten = max_tighten * sigmoid(-k * z_combined)
    p_eff   = max(absolute_floor, p_vol * (1 - tighten))

Sign convention (mirrors L6's drift convention):
  - BUY + positive imbalance (deep bid, thin ask) -> z_imbal > 0 -> aligned ->
    NO tighten. Standard order-flow interpretation: deep bid signals upward
    pressure, so BUY into it is favorable.
  - SELL + positive imbalance -> z_imbal < 0 -> adverse -> tighten.
  - And vice versa for negative imbalance.

If signals disagree, z_combined moves toward 0 -> defensive tightening at
0.45 -- L3/L6 data show this is net-positive. If they reinforce on adverse,
tightening is sharper -- more of the worst-EV trades skipped.

Weight choice (0.6 drift, 0.4 imbal): drift is proven across L2-L7; imbal
is unproven, so it gets less initial weight. Sum to 1 preserves the
z_combined magnitude range comparable to z_drift alone, keeping the
L3/L6-tuned sigmoid shape (k=3) at its proven operating point.

All other parameters identical to L6: k=3.0, max_tighten=0.9,
drift_halflife=60, drift_noise_floor=1e-7, absolute_floor=0.01, no
aligned-side clip, slow_vol normalization (halflife=120), base vol-regime
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


class VrsFL8Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for vrs-f-l8.

    Identical to L6 except adds three new params for the book-imbalance
    second signal: `imbal_halflife`, `imbal_scale`, `drift_weight`,
    `imbal_weight`. All sigmoid-shape parameters and base vol-regime
    parameters are L3/L6's proven values.

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
        (L6 value, retained in L8).
    drift_noise_floor : float
        If |drift| < drift_noise_floor (raw mid-price units), the drift z
        coordinate is treated as zero. Default 1e-7.
    max_tighten : float
        Asymptotic max tightening at z << 0. Default 0.9 (L3/L6 value).
    tighten_steepness : float
        Sigmoid steepness `k`. Default 3.0 (L3/L6 value).
    drift_vol_eps : float
        Hard lower bound on the slow_vol denominator. Default 1e-12.
    absolute_floor : float
        Hard lower bound on p_eff after smooth tightening. Default 0.01.
    imbal_halflife : int
        Half-life (in ticks) of the top-of-book imbalance EWM. Default 60
        (matches drift_halflife for symmetry).
    imbal_scale : float
        Multiplier applied to side-signed imbal EWM to align magnitude
        with z_drift. Default 2.0 (raw imbal is in [-1, 1]; scaling to
        ~[-2, +2] matches the typical saturated tail of z_drift).
    drift_weight : float
        Weight on z_drift in the combined z. Default 0.6.
    imbal_weight : float
        Weight on z_imbal in the combined z. Default 0.4. Sum
        (drift_weight + imbal_weight) should equal 1.0 to keep the
        combined z magnitude comparable to z_drift alone.
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

    # New imbalance-signal parameters
    imbal_halflife: int = 60
    imbal_scale: float = 2.0
    drift_weight: float = 0.6
    imbal_weight: float = 0.4


class VrsFL8Algorithm(ExecAlgorithm):
    """vol-regime sizer + smooth signed-drift tightening + book-imbalance second signal."""

    def __init__(self, config: VrsFL8Config) -> None:
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
        self._drift_halflife_used: int = config.drift_halflife

        # Imbalance-EWM alpha + combination weights
        self._imbal_alpha: float = 1.0 - math.exp(-math.log(2) / config.imbal_halflife)
        self._imbal_scale: float = config.imbal_scale
        self._drift_weight: float = config.drift_weight
        self._imbal_weight: float = config.imbal_weight
        self._imbal_halflife_used: int = config.imbal_halflife

        # EWM state
        self._fast_vol: float | None = None    # EWM of |delta_mid|
        self._slow_vol: float | None = None    # EWM of |delta_mid|
        self._drift: float | None = None       # EWM of signed delta_mid
        self._imbal: float | None = None       # EWM of top-of-book imbalance in [-1, +1]
        self._prev_mid: float | None = None
        self._tick_count: int = 0

        # Subscription tracking
        self._subscribed: set[str] = set()

        # Diagnostic counters
        self._submitted: int = 0
        self._skipped: int = 0
        self._tighten_applied: int = 0
        self._tighten_zero_drift: int = 0    # z_drift below noise floor (signal off)
        self._imbal_undefined: int = 0       # imbal EWM not yet warm

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"VrsFL8Algorithm started "
            f"(fast_alpha={self._fast_alpha:.4f}, slow_alpha={self._slow_alpha:.4f}, "
            f"drift_alpha={self._drift_alpha:.4f}, "
            f"drift_halflife={self._drift_halflife_used}, "
            f"imbal_alpha={self._imbal_alpha:.4f}, "
            f"imbal_halflife={self._imbal_halflife_used}, "
            f"imbal_scale={self._imbal_scale}, "
            f"drift_weight={self._drift_weight}, imbal_weight={self._imbal_weight}, "
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
        self._imbal = None
        self._prev_mid = None
        self._tick_count = 0
        self._subscribed.clear()
        self._submitted = 0
        self._skipped = 0
        self._tighten_applied = 0
        self._tighten_zero_drift = 0
        self._imbal_undefined = 0

    # ------------------------------------------------------------------
    # Quote-tick handler -- update vol/drift/imbal EWMs
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

        # Update vol EWMs and drift EWM from mid-price delta
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

        # Update imbalance EWM from top-of-book sizes (independent of mid delta;
        # update every tick where bid_size + ask_size > 0).
        try:
            bid_size = float(str(tick.bid_size))
            ask_size = float(str(tick.ask_size))
        except Exception:
            bid_size = 0.0
            ask_size = 0.0

        denom = bid_size + ask_size
        if denom > 0.0:
            imbal_raw = (bid_size - ask_size) / denom
            if self._imbal is None:
                self._imbal = imbal_raw
            else:
                self._imbal = (
                    self._imbal_alpha * imbal_raw + (1.0 - self._imbal_alpha) * self._imbal
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
        warm), which yields tighten = max_tighten / 2 if imbal also 0.
        """
        if self._drift is None or self._slow_vol is None:
            return 0.0
        if abs(self._drift) < self._drift_noise_floor:
            return 0.0
        order_sign = 1.0 if order_side == OrderSide.BUY else -1.0
        s_drift = order_sign * self._drift
        denom = max(self._slow_vol, self._drift_vol_eps)
        return s_drift / denom

    def _signed_imbal_z(self, order_side) -> float:
        """Side-signed top-of-book imbalance coordinate.

        Returns 0.0 if imbal EWM not yet warm (no prior tick had
        bid_size + ask_size > 0).
        """
        if self._imbal is None:
            return 0.0
        order_sign = 1.0 if order_side == OrderSide.BUY else -1.0
        return order_sign * self._imbal * self._imbal_scale

    def _effective_prob(self, p_vol: float, order_side) -> float:
        """Smooth combined-signal tightening on top of p_vol.

        z_combined = drift_weight * z_drift + imbal_weight * z_imbal
        tighten    = max_tighten * sigmoid(-k * z_combined)
        p_eff      = max(absolute_floor, p_vol * (1 - tighten))
        """
        if p_vol >= 1.0 - 1e-9:
            # Calm regime -- vol skip is dormant, nothing to tighten.
            return 1.0

        z_drift = self._signed_drift_z(order_side)
        z_imbal = self._signed_imbal_z(order_side)

        # Track when each signal is unavailable
        if self._drift is None or abs(self._drift or 0.0) < self._drift_noise_floor:
            self._tighten_zero_drift += 1
        if self._imbal is None:
            self._imbal_undefined += 1

        z_combined = self._drift_weight * z_drift + self._imbal_weight * z_imbal

        tighten = self._max_tighten * self._sigmoid(
            -self._tighten_steepness * z_combined
        )
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
                f"imbal={self._imbal if self._imbal is not None else float('nan'):.4f}, "
                f"side={order.side}). "
                f"submitted={self._submitted} skipped={self._skipped} "
                f"tighten_applied={self._tighten_applied} "
                f"tighten_zero_drift={self._tighten_zero_drift} "
                f"imbal_undefined={self._imbal_undefined}."
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
    imbal_halflife: int = 60,
    imbal_scale: float = 2.0,
    drift_weight: float = 0.6,
    imbal_weight: float = 0.4,
) -> VrsFL8Algorithm:
    """Instantiate the vrs-f-l8 algorithm."""
    config = VrsFL8Config(
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
        imbal_halflife=imbal_halflife,
        imbal_scale=imbal_scale,
        drift_weight=drift_weight,
        imbal_weight=imbal_weight,
    )
    return VrsFL8Algorithm(config=config)
