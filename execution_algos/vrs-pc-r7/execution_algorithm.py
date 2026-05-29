"""vrs-pc-r7: sensor-axis pivot — fast EWM halflife 20 -> 10 ticks.

Architecturally identical to vrs-pc-r5 in every respect except the default
`fast_halflife` parameter (20 -> 10). All other parameters retained from
run-5: sensitivity=2.5, min_prob=0.0, slow_halflife=120, min_ticks=30,
max_vol_ratio=5.0. The skip-probability formula is unchanged:

    p = exp(-2.5 * max(0, vol_ratio - 1))    (no floor; clamped to 0.0 only on underflow)

The change is in the SENSOR, not the curve. At fast_halflife=10, the fast EWM
alpha doubles (~0.0670 vs ~0.0341 at halflife=20), so it reaches 50% response
to a new |delta_mid| in ~10 ticks instead of ~20. The slow EWM is unchanged
(slow_halflife=120, alpha ~0.00578), so the baseline is identical to base
and runs 4-6 — only the SPEED of fast_vol response to new bursts differs.

Sensor-axis hypothesis: empirically observed plateau on the sensitivity axis:

  - vrs-pc-r3 (sensitivity 2.0 -> 1.0, min_prob=0.05):  -30.18% vs base  (FAIL)
  - vrs-pc-r4 (sensitivity 2.0,        min_prob=0.0):    +0.70% vs base
  - vrs-pc-r5 (sensitivity 2.5,        min_prob=0.0):   +17.88% vs base  (large gain)
  - vrs-pc-r6 (sensitivity 3.0,        min_prob=0.0):   +19.50% vs base  (small gain; +$12 vs r5)

Per-pruned-trade marginal P&L dropped 10x from the r4 -> r5 step (~$0.10/trade)
to the r5 -> r6 step (~$0.01/trade). Two interpretations of the plateau:
(1) the residual addressable adverse-EV set is small (sensitivity axis is
exhausted at the current sensor); (2) the sensor is too slow — bursts that
should trigger skipping are detected only AFTER the trade has already been
submitted, so steepening the curve can't reduce participation in those trades.
Interpretation (2) predicts that a faster sensor re-opens the addressable set.

NO strict-subset property over run-5: this is a sensor change, not a curve
change. At the same order, r7 may compute a higher vol_ratio than r5 (faster
burst capture) or a lower vol_ratio than r5 (faster recovery from a passing
burst). The SHA-256 deterministic draw u is identical, but p differs in both
direction and magnitude. The vs-r5 P&L delta cleanly attributes the
sensor-axis change in isolation since sensitivity, min_prob, slow_halflife,
min_ticks, and max_vol_ratio are constant.
"""
from __future__ import annotations

import hashlib
import math
import struct

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class VrsPcR7Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for vrs-pc-r7 (fast_halflife=10 variant compounding on run-5).

    Parameters
    ----------
    fast_halflife : int
        Half-life (in ticks) of the fast EWM used to estimate current
        short-term realized vol. Default 10 ticks — the single structural
        change relative to run-5 (which used 20 ticks). At halflife=10, the
        fast EWM responds ~2x faster to new |delta_mid| observations.
    slow_halflife : int
        Half-life (in ticks) of the slow EWM used as the vol baseline.
        Default 120 ticks (matches base and runs 4-6).
    sensitivity : float
        Controls how aggressively submission probability shrinks with vol.
        p = exp(-sensitivity * max(0, vol_ratio - 1))
        Default 2.5 (matches run-5; vs run-6 3.0, base 2.0). Inherited from
        run-5 — the cleaner baseline since the r5 -> r6 sensitivity step
        added only ~$12 P&L.
    min_prob : float
        Floor on submission probability. Default 0.0 (inherited from runs 4-6;
        vs base 0.05).
    min_ticks : int
        Minimum number of quote ticks before vol scaling activates.
        Default 30 (matches base and runs 4-6).
    max_vol_ratio : float
        Clip vol_ratio before applying sensitivity. Default 5.0 (matches
        base and runs 4-6).
    """

    fast_halflife: int = 10
    slow_halflife: int = 120
    sensitivity: float = 2.5
    min_prob: float = 0.0
    min_ticks: int = 30
    max_vol_ratio: float = 5.0


class VrsPcR7Algorithm(ExecAlgorithm):
    """Execution algorithm that scales open-leg submission probability with realized vol.

    Identical to VrsPcR5Algorithm in mechanism; only the default fast_halflife
    differs (10 vs 20). All other parameters and code paths are bitwise-identical
    to run-5. The change affects the SPEED of fast_vol response to new bursts,
    not the curve mapping vol_ratio -> submit probability.

    For each incoming OPEN order:
      1. Read fast and slow EWM of |delta_mid| from recent quote ticks.
      2. Compute vol_ratio = fast_vol / slow_vol (clipped to max_vol_ratio).
      3. Map to p = max(min_prob, exp(-sensitivity * max(0, vol_ratio - 1))).
      4. Accept or skip the order using a deterministic pseudo-random draw
         keyed on the order's client_order_id.

    For reduce-only (CLOSE) orders: always submit unconditionally
    (intraday_flat compliance).

    Quantity invariant: child_qty = parent_qty = 1 for all submitted orders.

    NO strict-subset over run-5: at the same order, r7's vol_ratio may be
    higher (faster burst capture, more skips) or lower (faster post-burst
    recovery, more submissions) than r5's. The vs-r5 P&L delta cleanly
    attributes the sensor-axis change in isolation.
    """

    def __init__(self, config: VrsPcR7Config) -> None:
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
            f"VrsPcR7Algorithm started "
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
    # Quote tick handler — update EWM vol estimates
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

        # Reduce-only (close) orders: always submit — intraday_flat compliance.
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
            # Do NOT call submit_order — quantity invariant preserved.


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    fast_halflife: int = 10,
    slow_halflife: int = 120,
    sensitivity: float = 2.5,
    min_prob: float = 0.0,
    min_ticks: int = 30,
    max_vol_ratio: float = 5.0,
) -> VrsPcR7Algorithm:
    """Instantiate and return the VrsPcR7Algorithm.

    Defaults match run-5 except `fast_halflife` (10 vs 20). All other
    parameters inherited from run-5: sensitivity=2.5, min_prob=0.0,
    slow_halflife=120, min_ticks=30, max_vol_ratio=5.0. Vs base
    vol-regime-sizer this variant differs in three parameters
    (fast_halflife 10 vs 20, sensitivity 2.5 vs 2.0, min_prob 0.0 vs 0.05).
    """
    config = VrsPcR7Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        fast_halflife=fast_halflife,
        slow_halflife=slow_halflife,
        sensitivity=sensitivity,
        min_prob=min_prob,
        min_ticks=min_ticks,
        max_vol_ratio=max_vol_ratio,
    )
    return VrsPcR7Algorithm(config=config)
