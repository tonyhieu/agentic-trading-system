"""vrs-f-l2: vol-regime sizer + adverse-drift skip tightening.

Loop 2 of the per-iteration experiment, full-trace arm, base = `vol-regime-sizer`.

Starting point: the prior loop's algorithm (vrs-f-l1), which added a signed
drift EWM and *relaxed* the vol-skip when sign(drift) matched the order side.
That relaxation was decisively refuted (-34.23% pnl vs base). Loop 1's
full-trace context explicitly identified the symmetric inversion as the
most promising next direction.

Change in this loop: invert the alignment branch from loop 1. Instead of
relaxing the skip when drift is aligned with the order side, *tighten* the
skip when drift is adverse (opposite to the order side). The aligned branch
becomes a no-op vs base, and the adverse branch shrinks p_vol by a
multiplicative factor:

  - aligned (sign(drift) == sign(order_side), |drift| > noise_floor):
        p_eff = p_vol             # no boost -- pure inversion of loop 1
  - undefined (|drift| <= noise_floor or drift state not yet warm):
        p_eff = p_vol             # fall back to base behavior
  - adverse (sign(drift) != sign(order_side), |drift| > noise_floor):
        p_eff = max(absolute_floor, p_vol * (1 - adverse_tighten))

with `adverse_tighten = 0.5` and `absolute_floor = 0.01` (strictly less than
the base's `min_prob = 0.05` so the floor only binds in the adverse branch).

In calm regimes (p_vol >= 1 - eps), p_eff = 1.0 -- the tightening only
applies inside the base's existing skip region. Reduce-only orders are
always submitted unconditionally. Cold-start (tick_count < min_ticks)
submits at p=1.0. The accept/reject draw is the same deterministic
SHA-256 uniform on client_order_id as base and loop 1.

Mechanism / inefficiency exploited: the base vol-skip is direction-blind.
Loop 1 showed that aligned-drift trades inside the vol-skip region have
worse per-trade economics than the average skipped trade. By symmetry,
adverse-drift trades are likely even worse, since the trader is
participating against recent price momentum during a vol burst -- a
textbook adverse-selection setup. Tightening participation in that subset
should remove the worst trades while preserving the base's behavior
elsewhere.

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


class VrsFL2Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for vrs-f-l2.

    All vol-regime parameters are inherited semantically from the base
    `vol-regime-sizer`. The signed-drift EWM parameters (`drift_halflife`,
    `drift_noise_floor`) are inherited from vrs-f-l1. The new parameter is
    `adverse_tighten`, replacing loop 1's `align_boost`.

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
        If |drift| < drift_noise_floor (raw mid-price units), the drift sign
        is treated as undefined and the base p_vol is used unchanged.
        Default 1e-7.
    adverse_tighten : float
        Multiplicative tightening factor for adverse-drift trades:
            p_eff = max(absolute_floor, p_vol * (1 - adverse_tighten))
        In [0, 1]. 0.0 = no tightening (degenerates to base); 1.0 = always
        skip adverse-drift trades (subject to absolute_floor). Default 0.5.
    absolute_floor : float
        Hard lower bound on p_eff after adverse-tightening. Set strictly
        below `min_prob` so it only binds when the adverse branch fires.
        Default 0.01.
    """

    fast_halflife: int = 20
    slow_halflife: int = 120
    sensitivity: float = 2.0
    min_prob: float = 0.05
    min_ticks: int = 30
    max_vol_ratio: float = 5.0

    drift_halflife: int = 30
    drift_noise_floor: float = 1e-7
    adverse_tighten: float = 0.5
    absolute_floor: float = 0.01


class VrsFL2Algorithm(ExecAlgorithm):
    """vol-regime sizer + adverse-drift skip tightening."""

    def __init__(self, config: VrsFL2Config) -> None:
        super().__init__(config=config)

        # Vol-EWM alphas
        self._fast_alpha: float = 1.0 - math.exp(-math.log(2) / config.fast_halflife)
        self._slow_alpha: float = 1.0 - math.exp(-math.log(2) / config.slow_halflife)
        self._sensitivity: float = config.sensitivity
        self._min_prob: float = config.min_prob
        self._min_ticks: int = config.min_ticks
        self._max_vol_ratio: float = config.max_vol_ratio

        # Drift-EWM alpha + tightening params
        self._drift_alpha: float = 1.0 - math.exp(-math.log(2) / config.drift_halflife)
        self._drift_noise_floor: float = config.drift_noise_floor
        self._adverse_tighten: float = config.adverse_tighten
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
        self._adverse_tightened: int = 0
        self._aligned_passthrough: int = 0
        self._undefined_passthrough: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"VrsFL2Algorithm started "
            f"(fast_alpha={self._fast_alpha:.4f}, slow_alpha={self._slow_alpha:.4f}, "
            f"drift_alpha={self._drift_alpha:.4f}, "
            f"sensitivity={self._sensitivity}, min_prob={self._min_prob}, "
            f"adverse_tighten={self._adverse_tighten}, "
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
        self._adverse_tightened = 0
        self._aligned_passthrough = 0
        self._undefined_passthrough = 0

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
        """Adverse-drift tightening on top of the base vol-skip.

        Inverts loop 1's aligned-boost: aligned-drift trades pass through
        unchanged, undefined-drift trades pass through unchanged, and
        adverse-drift trades are tightened by `(1 - adverse_tighten)` with
        an absolute_floor safeguard.
        """
        if p_vol >= 1.0 - 1e-9:
            # Calm regime -- vol skip is dormant, nothing to tighten.
            return 1.0

        aligned = self._is_aligned(order_side)
        if aligned is True:
            # Aligned-drift inside the vol-skip region: no-op vs base.
            self._aligned_passthrough += 1
            return p_vol
        elif aligned is False:
            # Adverse-drift inside the vol-skip region: tighten further.
            self._adverse_tightened += 1
            tightened = p_vol * (1.0 - self._adverse_tighten)
            return max(self._absolute_floor, tightened)
        else:
            # Drift undefined (below noise floor or not yet warm).
            self._undefined_passthrough += 1
            return p_vol

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
                f"adverse_tightened={self._adverse_tightened} "
                f"aligned_passthrough={self._aligned_passthrough} "
                f"undefined_passthrough={self._undefined_passthrough}."
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
    adverse_tighten: float = 0.5,
    absolute_floor: float = 0.01,
) -> VrsFL2Algorithm:
    """Instantiate the vrs-f-l2 algorithm."""
    config = VrsFL2Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        fast_halflife=fast_halflife,
        slow_halflife=slow_halflife,
        sensitivity=sensitivity,
        min_prob=min_prob,
        min_ticks=min_ticks,
        max_vol_ratio=max_vol_ratio,
        drift_halflife=drift_halflife,
        drift_noise_floor=drift_noise_floor,
        adverse_tighten=adverse_tighten,
        absolute_floor=absolute_floor,
    )
    return VrsFL2Algorithm(config=config)
