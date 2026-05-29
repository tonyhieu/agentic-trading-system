"""vrs-b-l1: vol-regime sizer + directional adverse-drift gate.

Derived from `vol-regime-sizer` (the base). The base computes a submission
probability that decays smoothly with the fast/slow EWM vol ratio and uses
that probability to skip a fraction of OPEN orders. This loop adds a single
targeted change:

    The probabilistic skip only fires when both
       (a) vol_ratio is elevated  AND
       (b) the recent mid-price drift is moving AGAINST the order's side
    are true. If the drift aligns with the order side, the order is always
    submitted at p = 1.0, regardless of the vol regime.

Rationale (informed only by my own backtest design — no prior loop context
available in this arm; this is loop 1):

The base algo treats all high-vol regimes as equally hostile and skips
proportionally to vol magnitude. But adverse selection at high vol is
asymmetric: when fast vol is up AND the mid is drifting opposite to our
trade side, we are more likely buying a tick that already moved away from
us (or selling into a falling book). When the drift aligns with our side,
the high vol is "with us" and skipping forfeits good fills.

By gating skips on (vol_high) AND (drift_adverse), we preserve participation
on directionally-favorable high-vol moments while still cutting losses on
true adverse-selection bursts. Trade count should drop less than in the base
(skips are now conditional on two signals, not one) but skip selectivity
should be higher.

Mechanism additions over base:
  * Track a short-EWM `drift` of signed mid-price increments
        drift_ewm = alpha_drift * (mid - prev_mid)
                  + (1 - alpha_drift) * drift_ewm_prev
    drift_ewm > 0 means mid trending up; drift_ewm < 0 trending down.
  * In `on_order`, compute the base vol_ratio submission probability p_vol.
    Determine order side: BUY -> adverse if drift_ewm < -drift_threshold,
                          SELL -> adverse if drift_ewm > +drift_threshold.
  * Final p:
        if drift not adverse:   p = 1.0  (always submit, override vol skip)
        else:                   p = p_vol (apply base vol-regime skip)

All other base mechanics (reduce-only always submits, deterministic
SHA256(client_order_id) draw, cold-start guard, EWM vol estimator) are
preserved unchanged.

Quantity invariant: at most 1 contract submitted per parent 1-contract
order; same as the base.
"""
from __future__ import annotations

import hashlib
import math
import struct

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class VrsBL1Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for vrs-b-l1: base vol-regime sizer + directional drift gate.

    Parameters
    ----------
    fast_halflife : int
        Half-life (in ticks) of the fast EWM used to estimate current
        short-term realized vol. Default 20.
    slow_halflife : int
        Half-life (in ticks) of the slow EWM used as the vol baseline.
        Default 120.
    sensitivity : float
        p_vol = exp(-sensitivity * max(0, vol_ratio - 1)). Default 2.0.
    min_prob : float
        Floor on submission probability when vol-gated. Default 0.05.
    min_ticks : int
        Cold-start guard. Default 30.
    max_vol_ratio : float
        Clip vol_ratio. Default 5.0.
    drift_halflife : int
        Half-life (in ticks) of the signed-mid-increment EWM that tracks
        short-term directional drift. Default 40 ticks (between fast and
        slow vol windows).
    drift_threshold : float
        Magnitude of drift_ewm (in price units, same units as mid) above
        which the drift is considered directional and adverse-selection
        becomes relevant. Default 0.05 (5 cents on MES; ~2 ticks).
    """

    fast_halflife: int = 20
    slow_halflife: int = 120
    sensitivity: float = 2.0
    min_prob: float = 0.05
    min_ticks: int = 30
    max_vol_ratio: float = 5.0
    drift_halflife: int = 40
    drift_threshold: float = 0.05


class VrsBL1Algorithm(ExecAlgorithm):
    """Vol-regime sizer with a directional adverse-drift override.

    For each incoming OPEN order:
      1. Update EWM vol (fast, slow) and EWM drift (signed delta_mid) from
         the most recent quote ticks. (Updates happen continuously in
         `on_quote_tick`.)
      2. Compute p_vol = max(min_prob, exp(-sensitivity * (vol_ratio - 1)+))
         per the base.
      3. Determine whether the recent drift is adverse to the order side:
            BUY  -> adverse if drift_ewm < -drift_threshold (mid falling)
            SELL -> adverse if drift_ewm > +drift_threshold (mid rising)
      4. If drift is NOT adverse, force p = 1.0 (override the vol skip).
         Otherwise, apply p = p_vol.
      5. Use deterministic SHA256(client_order_id) draw to accept/skip.

    Reduce-only orders: always submitted unconditionally.
    """

    def __init__(self, config: VrsBL1Config) -> None:
        super().__init__(config=config)

        # Pre-compute EWM alphas
        self._fast_alpha: float = 1.0 - math.exp(-math.log(2) / config.fast_halflife)
        self._slow_alpha: float = 1.0 - math.exp(-math.log(2) / config.slow_halflife)
        self._drift_alpha: float = 1.0 - math.exp(-math.log(2) / config.drift_halflife)

        self._sensitivity: float = config.sensitivity
        self._min_prob: float = config.min_prob
        self._min_ticks: int = config.min_ticks
        self._max_vol_ratio: float = config.max_vol_ratio
        self._drift_threshold: float = config.drift_threshold

        # EWM state
        self._fast_vol: float | None = None
        self._slow_vol: float | None = None
        self._drift_ewm: float = 0.0
        self._prev_mid: float | None = None
        self._tick_count: int = 0

        # Subscription tracking
        self._subscribed: set[str] = set()

        # Diagnostic counters
        self._submitted: int = 0
        self._skipped_vol_adverse: int = 0
        self._submitted_aligned_override: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            "VrsBL1Algorithm started "
            f"(fast_alpha={self._fast_alpha:.4f}, slow_alpha={self._slow_alpha:.4f}, "
            f"drift_alpha={self._drift_alpha:.4f}, sensitivity={self._sensitivity}, "
            f"min_prob={self._min_prob}, min_ticks={self._min_ticks}, "
            f"drift_threshold={self._drift_threshold})."
        )

    def on_reset(self) -> None:
        self._fast_vol = None
        self._slow_vol = None
        self._drift_ewm = 0.0
        self._prev_mid = None
        self._tick_count = 0
        self._subscribed.clear()
        self._submitted = 0
        self._skipped_vol_adverse = 0
        self._submitted_aligned_override = 0

    # ------------------------------------------------------------------
    # Quote tick handler — update EWMs
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

            # Signed-drift EWM (preserves direction of price moves)
            self._drift_ewm = (
                self._drift_alpha * delta
                + (1.0 - self._drift_alpha) * self._drift_ewm
            )

        self._prev_mid = mid
        self._tick_count += 1

    # ------------------------------------------------------------------
    # Submission probability (base vol path)
    # ------------------------------------------------------------------

    def _compute_p_vol(self) -> float:
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

    # ------------------------------------------------------------------
    # Directional drift check
    # ------------------------------------------------------------------

    def _drift_is_adverse(self, order_side) -> bool:
        """Return True if recent drift opposes the order's side."""
        if self._tick_count < self._min_ticks:
            return False
        if order_side == OrderSide.BUY:
            return self._drift_ewm < -self._drift_threshold
        if order_side == OrderSide.SELL:
            return self._drift_ewm > self._drift_threshold
        return False

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
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders: always submit — intraday_flat compliance.
        if order.is_reduce_only:
            self.submit_order(order)
            return

        # Determine if drift is adverse to this order's side.
        adverse = self._drift_is_adverse(order.side)

        if not adverse:
            # Drift aligns with order side (or undefined): override vol skip.
            self._submitted += 1
            self._submitted_aligned_override += 1
            self.log.debug(
                f"SUBMIT {order.client_order_id} (drift aligned/neutral, "
                f"drift_ewm={self._drift_ewm:.4f}, override=True)."
            )
            self.submit_order(order)
            return

        # Drift IS adverse — apply the base vol-regime probabilistic skip.
        p = self._compute_p_vol()

        if p >= 1.0 - 1e-9:
            self._submitted += 1
            self.submit_order(order)
            return

        u = self._order_uniform(str(order.client_order_id))
        if u < p:
            self._submitted += 1
            self.submit_order(order)
        else:
            self._skipped_vol_adverse += 1
            self.log.info(
                f"SKIP {order.client_order_id} (adverse drift + vol gate, "
                f"p={p:.4f}, u={u:.4f}, drift_ewm={self._drift_ewm:.4f}, "
                f"submitted={self._submitted} "
                f"skipped_vol_adverse={self._skipped_vol_adverse})."
            )


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    fast_halflife: int = 20,
    slow_halflife: int = 120,
    sensitivity: float = 2.0,
    min_prob: float = 0.05,
    min_ticks: int = 30,
    max_vol_ratio: float = 5.0,
    drift_halflife: int = 40,
    drift_threshold: float = 0.05,
) -> VrsBL1Algorithm:
    """Instantiate the vrs-b-l1 vol-regime sizer with directional drift gate."""
    config = VrsBL1Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        fast_halflife=fast_halflife,
        slow_halflife=slow_halflife,
        sensitivity=sensitivity,
        min_prob=min_prob,
        min_ticks=min_ticks,
        max_vol_ratio=max_vol_ratio,
        drift_halflife=drift_halflife,
        drift_threshold=drift_threshold,
    )
    return VrsBL1Algorithm(config=config)
