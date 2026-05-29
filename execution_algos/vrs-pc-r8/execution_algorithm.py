"""vrs-pc-r8: cross-axis compound — fast_halflife=10 (from r7) + sensitivity=3.0 (from r6).

Architecturally identical to vrs-pc-r7 in every respect except the default
`sensitivity` parameter (2.5 -> 3.0). All other parameters retained from r7:
fast_halflife=10, min_prob=0.0, slow_halflife=120, min_ticks=30,
max_vol_ratio=5.0. The skip-probability formula becomes:

    p = exp(-3.0 * max(0, vol_ratio - 1))    (no floor; clamped to 0.0 only on underflow)

The change is on the CURVE, not the sensor. Vs r7, the curve is steeper:

    vol_ratio   r7 p            r8 p
    1.0         1.000           1.000
    1.5         0.287           0.223
    2.0         0.082           0.050
    3.0         0.007           0.002
    5.0 (cap)   0.000045        0.0000061

At the same vol_ratio, r8's p <= r7's p uniformly for vol_ratio > 1 -- so
r8 is a strict subset of r7's submitted orders. Combined with r7's faster
sensor (fast_alpha ~0.0670 vs base ~0.0341), r8 tests the COMPOUND
hypothesis: does the sensitivity axis re-acquire leverage at the faster
sensor speed?

Empirical motivation (cross-axis compound):
  - At fast_halflife=20 (r5/r6 sensor), the marginal sensitivity step
    2.5 -> 3.0 added only ~$12/12days. Sensitivity axis appeared plateaued.
  - At fast_halflife=10 (r7 sensor), the sensitivity step from base 2.0
    delivered $700 in compound. Sensor axis has documented leverage.
  - Hypothesis: the r5->r6 plateau was caused by the slower sensor missing
    most of the addressable adverse-EV bursts. With a faster sensor catching
    more bursts (richer addressable population), a steeper curve should
    re-acquire leverage by skipping a higher FRACTION of detected adverse
    orders.

The two axes act on independent gates: the sensor determines WHICH orders
enter the elevated-vol slice; the sensitivity determines WHAT FRACTION of
those orders is skipped. r8 tests whether these compose linearly.

Builds on vrs-pc-r7 (PASS, +92.94% vs base, sharpe=6.19, realized_pnl=$1454.25).
Single-parameter delta vs r7: sensitivity 2.5 -> 3.0.
"""
from __future__ import annotations

import hashlib
import math
import struct

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class VrsPcR8Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for vrs-pc-r8 (sensitivity=3.0 variant compounding on r7).

    Parameters
    ----------
    fast_halflife : int
        Half-life (in ticks) of the fast EWM. Default 10 ticks (inherited
        from r7). At halflife=10, fast_alpha = 1 - exp(-ln(2)/10) ~= 0.0670,
        about 2x faster response than base's halflife=20.
    slow_halflife : int
        Half-life (in ticks) of the slow EWM. Default 120 ticks (matches
        base and runs 4-7). slow_alpha ~= 0.00578.
    sensitivity : float
        Controls how aggressively submission probability shrinks with vol.
        p = exp(-sensitivity * max(0, vol_ratio - 1))
        Default 3.0 -- the single structural change relative to r7
        (which used 2.5). Adopts r6's sensitivity setting at r7's sensor
        speed.
    min_prob : float
        Floor on submission probability. Default 0.0 (inherited from r4-r7).
    min_ticks : int
        Minimum number of quote ticks before vol scaling activates.
        Default 30 (matches base and runs 4-7).
    max_vol_ratio : float
        Clip vol_ratio before applying sensitivity. Default 5.0 (matches
        base and runs 4-7).
    """

    fast_halflife: int = 10
    slow_halflife: int = 120
    sensitivity: float = 3.0
    min_prob: float = 0.0
    min_ticks: int = 30
    max_vol_ratio: float = 5.0


class VrsPcR8Algorithm(ExecAlgorithm):
    """Execution algorithm that scales open-leg submission probability with realized vol.

    Identical to VrsPcR7Algorithm in mechanism; only the default sensitivity
    differs (3.0 vs 2.5). All other parameters and code paths are
    bitwise-identical to r7. The change affects the STEEPNESS of the skip
    probability curve, not the sensor.

    For each incoming OPEN order:
      1. Read fast and slow EWM of |delta_mid| from recent quote ticks.
      2. Compute vol_ratio = fast_vol / slow_vol (clipped to max_vol_ratio).
      3. Map to p = max(min_prob, exp(-sensitivity * max(0, vol_ratio - 1))).
      4. Accept or skip the order using a deterministic pseudo-random draw
         keyed on the order's client_order_id.

    For reduce-only (CLOSE) orders: always submit unconditionally
    (intraday_flat compliance).

    Quantity invariant: child_qty = parent_qty = 1 for all submitted orders.

    STRICT subset over run-7: at the same order, r8's vol_ratio is identical
    to r7's (fast_halflife and slow_halflife unchanged) but r8's p is
    uniformly <= r7's p for vol_ratio > 1. The SHA-256 deterministic draw u
    is identical. Therefore every order skipped by r7 is also skipped by r8,
    plus additional orders from the [exp(-3*excess), exp(-2.5*excess)] band.
    """

    def __init__(self, config: VrsPcR8Config) -> None:
        super().__init__(config=config)

        # Config parameters
        self._fast_alpha: float = 1.0 - math.exp(-math.log(2) / config.fast_halflife)
        self._slow_alpha: float = 1.0 - math.exp(-math.log(2) / config.slow_halflife)
        self._sensitivity: float = config.sensitivity
        self._min_prob: float = config.min_prob
        self._min_ticks: int = config.min_ticks
        self._max_vol_ratio: float = config.max_vol_ratio

        # EWM state
        self._fast_vol: float | None = None
        self._slow_vol: float | None = None
        self._prev_mid: float | None = None
        self._tick_count: int = 0

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
            f"VrsPcR8Algorithm started "
            f"(fast_alpha={self._fast_alpha:.4f}, slow_alpha={self._slow_alpha:.4f}, "
            f"sensitivity={self._sensitivity}, min_prob={self._min_prob}, "
            f"min_ticks={self._min_ticks})."
        )

    def on_reset(self) -> None:
        self._fast_vol = None
        self._slow_vol = None
        self._prev_mid = None
        self._tick_count = 0
        self._subscribed.clear()
        self._submitted = 0
        self._skipped = 0

    # ------------------------------------------------------------------
    # Quote tick handler -- update EWM vol estimates
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    def on_quote_tick(self, tick) -> None:
        """Update EWM vol estimates from each incoming quote tick."""
        try:
            bid = float(str(tick.bid_price))
            ask = float(str(tick.ask_price))
            mid = (bid + ask) / 2.0
        except Exception:
            return

        if self._prev_mid is not None:
            abs_delta = abs(mid - self._prev_mid)
            if self._fast_vol is None:
                self._fast_vol = abs_delta
                self._slow_vol = abs_delta
            else:
                self._fast_vol = self._fast_alpha * abs_delta + (1.0 - self._fast_alpha) * self._fast_vol
                self._slow_vol = self._slow_alpha * abs_delta + (1.0 - self._slow_alpha) * self._slow_vol

        self._prev_mid = mid
        self._tick_count += 1

    # ------------------------------------------------------------------
    # Submission probability
    # ------------------------------------------------------------------

    def _compute_submit_prob(self) -> float:
        """Return submission probability in [min_prob, 1.0].

        Returns 1.0 (full participation) on cold start or undefined baseline.
        """
        if self._tick_count < self._min_ticks:
            return 1.0

        if self._fast_vol is None or self._slow_vol is None:
            return 1.0

        if self._slow_vol < 1e-12:
            return 1.0

        vol_ratio = min(self._fast_vol / self._slow_vol, self._max_vol_ratio)
        excess = max(0.0, vol_ratio - 1.0)
        prob = math.exp(-self._sensitivity * excess)
        prob = max(self._min_prob, prob)

        self.log.debug(
            f"vol_ratio={vol_ratio:.4f} excess={excess:.4f} "
            f"fast={self._fast_vol:.8f} slow={self._slow_vol:.8f} "
            f"p_submit={prob:.4f}"
        )
        return prob

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
        """Route order: submit or skip based on vol-regime probability."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders: always submit -- intraday_flat compliance.
        if order.is_reduce_only:
            self.log.debug(
                f"Reduce-only {order.client_order_id}: submitting unconditionally."
            )
            self.submit_order(order)
            return

        # Compute submission probability
        p = self._compute_submit_prob()

        if p >= 1.0 - 1e-9:
            # Full participation (calm regime or cold start)
            self._submitted += 1
            self.log.debug(f"SUBMIT {order.client_order_id} (p=1.0, calm/cold).")
            self.submit_order(order)
            return

        # Deterministic draw from order ID
        u = self._order_uniform(str(order.client_order_id))

        if u < p:
            self._submitted += 1
            self.log.debug(
                f"SUBMIT {order.client_order_id} (p={p:.4f}, u={u:.4f})."
            )
            self.submit_order(order)
        else:
            self._skipped += 1
            self.log.info(
                f"SKIP {order.client_order_id} (p={p:.4f}, u={u:.4f}). "
                f"submitted={self._submitted} skipped={self._skipped}."
            )
            # Do NOT call submit_order -- quantity invariant preserved.


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    fast_halflife: int = 10,
    slow_halflife: int = 120,
    sensitivity: float = 3.0,
    min_prob: float = 0.0,
    min_ticks: int = 30,
    max_vol_ratio: float = 5.0,
) -> VrsPcR8Algorithm:
    """Instantiate and return the VrsPcR8Algorithm.

    Defaults match r7 except `sensitivity` (3.0 vs 2.5). All other
    parameters inherited from r7: fast_halflife=10, min_prob=0.0,
    slow_halflife=120, min_ticks=30, max_vol_ratio=5.0. Vs base
    vol-regime-sizer this variant differs in three parameters
    (fast_halflife 10 vs 20, sensitivity 3.0 vs 2.0, min_prob 0.0 vs 0.05).
    """
    config = VrsPcR8Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        fast_halflife=fast_halflife,
        slow_halflife=slow_halflife,
        sensitivity=sensitivity,
        min_prob=min_prob,
        min_ticks=min_ticks,
        max_vol_ratio=max_vol_ratio,
    )
    return VrsPcR8Algorithm(config=config)
