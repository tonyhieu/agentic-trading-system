"""vrs-b-l2: vol-regime sizer + directional adverse-drift gate, threshold recalibrated.

Derived structurally from `vrs-b-l1` with a SINGLE targeted change:
the directional drift threshold is lowered from 0.05 to 0.008 (~6x
smaller). All other mechanics — fast/slow vol EWMs, sensitivity,
min_prob, drift_halflife, gate semantics (skip iff vol elevated AND
drift adverse; aligned drift forces p=1.0), reduce-only handling,
deterministic SHA256(client_order_id) draw — are preserved unchanged.

Rationale (informed by L1's brief-summary `next` text, the only L1
context this loop is permitted to read): L1 reported that the drift
gate fired on essentially 1 of 111,488 orders, so the directional
adverse-selection hypothesis was effectively UNTESTED. L1 recommended
dropping the threshold ~10x. We pick 0.008 — mid-range of the
suggested 0.005-0.01 band — to make the gate non-trivial on most
orders without saturating.

Quantity invariant: at most 1 contract submitted per parent 1-contract
order; same as L1 and base.
"""
from __future__ import annotations

import hashlib
import math
import struct

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class VrsBL2Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for vrs-b-l2.

    Identical to vrs-b-l1 except `drift_threshold` default is lowered
    from 0.05 to 0.008.

    Parameters
    ----------
    fast_halflife : int
        Half-life (in ticks) of the fast EWM. Default 20.
    slow_halflife : int
        Half-life (in ticks) of the slow EWM (vol baseline). Default 120.
    sensitivity : float
        p_vol = exp(-sensitivity * max(0, vol_ratio - 1)). Default 2.0.
    min_prob : float
        Floor on submission probability when vol-gated. Default 0.05.
    min_ticks : int
        Cold-start guard. Default 30.
    max_vol_ratio : float
        Clip vol_ratio. Default 5.0.
    drift_halflife : int
        Half-life (in ticks) of the signed-mid-increment drift EWM.
        Default 40.
    drift_threshold : float
        Magnitude of drift_ewm (price units, same as mid) above which
        the drift is treated as directional and adverse-selection
        becomes relevant. **Default 0.008** (was 0.05 in vrs-b-l1) —
        chosen mid-range of L1's recommended 0.005-0.01 band so the
        gate fires on a meaningful fraction of orders rather than
        ~1 in 111k.
    """

    fast_halflife: int = 20
    slow_halflife: int = 120
    sensitivity: float = 2.0
    min_prob: float = 0.05
    min_ticks: int = 30
    max_vol_ratio: float = 5.0
    drift_halflife: int = 40
    drift_threshold: float = 0.008


class VrsBL2Algorithm(ExecAlgorithm):
    """Vol-regime sizer with directional adverse-drift override, lower threshold.

    Logic identical to vrs-b-l1; only the drift_threshold default
    changes. See `VrsBL2Config` and the module docstring for
    rationale.

    For each incoming OPEN order:
      1. EWM vol (fast, slow) and EWM drift (signed delta_mid)
         are updated continuously in `on_quote_tick`.
      2. p_vol = max(min_prob, exp(-sensitivity * (vol_ratio - 1)+)).
      3. Drift adverse to order side?
            BUY  -> adverse if drift_ewm < -drift_threshold
            SELL -> adverse if drift_ewm > +drift_threshold
      4. If drift NOT adverse, force p = 1.0 (override vol skip).
         Otherwise apply p = p_vol.
      5. Deterministic SHA256(client_order_id) draw -> accept / skip.

    Reduce-only orders: always submitted unconditionally.
    """

    def __init__(self, config: VrsBL2Config) -> None:
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
            "VrsBL2Algorithm started "
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
    drift_threshold: float = 0.008,
) -> VrsBL2Algorithm:
    """Instantiate the vrs-b-l2 vol-regime sizer with lowered drift gate threshold."""
    config = VrsBL2Config(
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
    return VrsBL2Algorithm(config=config)
