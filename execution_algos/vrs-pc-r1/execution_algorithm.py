"""Vol-regime sizer with signed-momentum directional conditioning (vrs-pc-r1).

Extends ``vol-regime-sizer`` by adding a signed-momentum factor that only
ATTENUATES participation when current mid-price momentum is adverse to the
order's direction AND we are already in an elevated-vol regime.

Construction guarantees the submission set is a strict subset of the base
``vol-regime-sizer`` algorithm's submission set:

  vol_excess     = max(0, min(vol_ratio, max_vol_ratio) - 1)
  vol_active     = min(1.0, vol_excess)        # 0 in calm, ramps to 1 by vol_ratio>=2
  adverse_excess = max(0, min(max_adverse_z,
                              side_sign * fast_signed_dm / max(fast_vol, eps)))
  effective_adv  = adverse_excess * vol_active
  p              = max(min_prob,
                       exp(-sens_vol * vol_excess) * exp(-sens_dir * effective_adv))

Properties:
  - In calm regimes (vol_excess=0): vol_active=0, p = 1.0 (identical to base).
  - With favorable momentum (adverse_excess=0): directional factor = 1.0; p
    equals the base's vol-only probability — no recovered "false-positive
    skips" relative to base.
  - With adverse momentum AND elevated vol: directional factor < 1; p is
    strictly less than base's vol-only probability — deeper skip on the
    adverse-direction-during-vol subset.
  - At every order, p_vrs-pc-r1 <= p_vol-regime-sizer. The submission set is
    a strict subset of base.

Reduce-only orders submit unconditionally at full quantity (intraday_flat
compliance, identical to base).

Submission decision uses a deterministic SHA-256 draw of ``client_order_id``
against ``p`` — reproducible without shared RNG state.
"""
from __future__ import annotations

import hashlib
import math
import struct

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class VrsPcR1Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the vrs-pc-r1 signed-momentum directional sizer.

    Parameters
    ----------
    fast_halflife : int
        Half-life (in ticks) of the fast EWM of |delta_mid|. Default 20.
    slow_halflife : int
        Half-life (in ticks) of the slow EWM of |delta_mid| (vol baseline).
        Default 120.
    sens_vol : float
        Sensitivity of the vol-only factor (matches base ``sensitivity``).
        Default 2.0.
    sens_dir : float
        Sensitivity of the directional factor. Conservative choice
        ``sens_dir < sens_vol`` keeps the directional term a perturbation
        rather than dominating signal. Default 1.5.
    min_prob : float
        Floor on submission probability. Default 0.05.
    min_ticks : int
        Cold-start guard: full submission for first N ticks. Default 30.
    max_vol_ratio : float
        Clip vol_ratio before applying sensitivity. Default 5.0.
    max_adverse_z : float
        Clip adverse_excess to prevent extreme outliers from dominating.
        Default 3.0 (at adverse_z=3 with sens_dir=1.5, directional factor
        is exp(-4.5)~0.011, below min_prob — so clipping rarely binds).
    """

    fast_halflife: int = 20
    slow_halflife: int = 120
    sens_vol: float = 2.0
    sens_dir: float = 1.5
    min_prob: float = 0.05
    min_ticks: int = 30
    max_vol_ratio: float = 5.0
    max_adverse_z: float = 3.0


class VrsPcR1Algorithm(ExecAlgorithm):
    """Vol-regime sizer with signed-momentum directional conditioning."""

    def __init__(self, config: VrsPcR1Config) -> None:
        super().__init__(config=config)

        # EWM decay coefficients
        self._fast_alpha: float = 1.0 - math.exp(-math.log(2) / config.fast_halflife)
        self._slow_alpha: float = 1.0 - math.exp(-math.log(2) / config.slow_halflife)

        # Config parameters
        self._sens_vol: float = config.sens_vol
        self._sens_dir: float = config.sens_dir
        self._min_prob: float = config.min_prob
        self._min_ticks: int = config.min_ticks
        self._max_vol_ratio: float = config.max_vol_ratio
        self._max_adverse_z: float = config.max_adverse_z

        # EWM state
        self._fast_vol: float | None = None         # EWM of |delta_mid|
        self._slow_vol: float | None = None         # EWM of |delta_mid| (slow)
        self._fast_signed_dm: float | None = None   # EWM of signed delta_mid (fast)
        self._prev_mid: float | None = None
        self._tick_count: int = 0

        # Subscription tracking
        self._subscribed: set[str] = set()

        # Diagnostic counters
        self._submitted: int = 0
        self._skipped: int = 0
        self._skipped_vol_only: int = 0
        self._skipped_with_adverse: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"VrsPcR1Algorithm started "
            f"(fast_alpha={self._fast_alpha:.4f}, slow_alpha={self._slow_alpha:.4f}, "
            f"sens_vol={self._sens_vol}, sens_dir={self._sens_dir}, "
            f"min_prob={self._min_prob}, min_ticks={self._min_ticks}, "
            f"max_vol_ratio={self._max_vol_ratio}, "
            f"max_adverse_z={self._max_adverse_z})."
        )

    def on_reset(self) -> None:
        self._fast_vol = None
        self._slow_vol = None
        self._fast_signed_dm = None
        self._prev_mid = None
        self._tick_count = 0
        self._subscribed.clear()
        self._submitted = 0
        self._skipped = 0
        self._skipped_vol_only = 0
        self._skipped_with_adverse = 0

    # ------------------------------------------------------------------
    # Quote tick handler — update EWM vol estimates and signed momentum
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    def on_quote_tick(self, tick) -> None:
        """Update EWM vol and signed-momentum estimates from each quote tick."""
        try:
            bid = float(str(tick.bid_price))
            ask = float(str(tick.ask_price))
            mid = (bid + ask) / 2.0
        except Exception:
            return

        if self._prev_mid is not None:
            delta = mid - self._prev_mid
            abs_delta = abs(delta)
            if self._fast_vol is None:
                self._fast_vol = abs_delta
                self._slow_vol = abs_delta
                self._fast_signed_dm = delta
            else:
                self._fast_vol = (
                    self._fast_alpha * abs_delta
                    + (1.0 - self._fast_alpha) * self._fast_vol
                )
                self._slow_vol = (
                    self._slow_alpha * abs_delta
                    + (1.0 - self._slow_alpha) * self._slow_vol
                )
                self._fast_signed_dm = (
                    self._fast_alpha * delta
                    + (1.0 - self._fast_alpha) * self._fast_signed_dm
                )

        self._prev_mid = mid
        self._tick_count += 1

    # ------------------------------------------------------------------
    # Submission probability
    # ------------------------------------------------------------------

    def _compute_submit_prob(self, side_sign: int) -> tuple[float, float, float]:
        """Compute submission probability and components.

        Returns
        -------
        tuple of (p, vol_excess, effective_adverse)
            p is the final submission probability in [min_prob, 1.0].
            vol_excess and effective_adverse are returned for diagnostics.
        """
        if self._tick_count < self._min_ticks:
            return 1.0, 0.0, 0.0

        if (
            self._fast_vol is None
            or self._slow_vol is None
            or self._fast_signed_dm is None
        ):
            return 1.0, 0.0, 0.0

        if self._slow_vol < 1e-12:
            return 1.0, 0.0, 0.0

        # Vol component (identical to base vol-regime-sizer)
        vol_ratio = min(self._fast_vol / self._slow_vol, self._max_vol_ratio)
        vol_excess = max(0.0, vol_ratio - 1.0)
        vol_active = min(1.0, vol_excess)

        # Directional component
        fast_vol_safe = max(self._fast_vol, 1e-12)
        # Adverse z is positive when momentum is against the order side
        adverse_raw = side_sign * self._fast_signed_dm / fast_vol_safe
        adverse_excess = max(0.0, min(self._max_adverse_z, adverse_raw))

        # Gate directional by vol_active: only deepen skips in elevated-vol regimes
        effective_adverse = adverse_excess * vol_active

        prob = math.exp(-self._sens_vol * vol_excess) * math.exp(
            -self._sens_dir * effective_adverse
        )
        prob = max(self._min_prob, prob)

        return prob, vol_excess, effective_adverse

    # ------------------------------------------------------------------
    # Deterministic pseudo-random draw
    # ------------------------------------------------------------------

    @staticmethod
    def _order_uniform(order_id_str: str) -> float:
        """Return a deterministic float in [0, 1) from the order's client ID."""
        digest = hashlib.sha256(order_id_str.encode()).digest()
        val = struct.unpack(">Q", digest[:8])[0]
        return val / (2**64)

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on vol + directional probability."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders: always submit — intraday_flat compliance.
        if order.is_reduce_only:
            self.log.debug(
                f"Reduce-only {order.client_order_id}: submitting unconditionally."
            )
            self.submit_order(order)
            return

        # Determine side sign: +1 for BUY, -1 for SELL.
        side_sign = 1 if order.side == OrderSide.BUY else -1

        p, vol_excess, effective_adverse = self._compute_submit_prob(side_sign)

        if p >= 1.0 - 1e-9:
            # Full participation (calm regime or cold start)
            self._submitted += 1
            self.log.debug(
                f"SUBMIT {order.client_order_id} (p=1.0, calm/cold)."
            )
            self.submit_order(order)
            return

        # Deterministic draw from order ID
        u = self._order_uniform(str(order.client_order_id))

        if u < p:
            self._submitted += 1
            self.log.debug(
                f"SUBMIT {order.client_order_id} "
                f"(p={p:.4f}, u={u:.4f}, vol_excess={vol_excess:.4f}, "
                f"eff_adv={effective_adverse:.4f})."
            )
            self.submit_order(order)
        else:
            self._skipped += 1
            if effective_adverse > 0.0:
                self._skipped_with_adverse += 1
            else:
                self._skipped_vol_only += 1
            self.log.info(
                f"SKIP {order.client_order_id} "
                f"(p={p:.4f}, u={u:.4f}, vol_excess={vol_excess:.4f}, "
                f"eff_adv={effective_adverse:.4f}). "
                f"submitted={self._submitted} skipped={self._skipped} "
                f"(vol_only={self._skipped_vol_only}, "
                f"with_adverse={self._skipped_with_adverse})."
            )
            # Do NOT call submit_order — quantity invariant preserved.


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    fast_halflife: int = 20,
    slow_halflife: int = 120,
    sens_vol: float = 2.0,
    sens_dir: float = 1.5,
    min_prob: float = 0.05,
    min_ticks: int = 30,
    max_vol_ratio: float = 5.0,
    max_adverse_z: float = 3.0,
) -> VrsPcR1Algorithm:
    """Instantiate and return the VrsPcR1Algorithm."""
    config = VrsPcR1Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        fast_halflife=fast_halflife,
        slow_halflife=slow_halflife,
        sens_vol=sens_vol,
        sens_dir=sens_dir,
        min_prob=min_prob,
        min_ticks=min_ticks,
        max_vol_ratio=max_vol_ratio,
        max_adverse_z=max_adverse_z,
    )
    return VrsPcR1Algorithm(config=config)
