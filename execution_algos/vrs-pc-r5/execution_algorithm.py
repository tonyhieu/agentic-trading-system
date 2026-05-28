"""vrs-pc-r5: sensitivity-2.5 variant of vrs-pc-r4 (compounds on min_prob=0.0).

Architecturally identical to vrs-pc-r4 in every respect except the default
`sensitivity` parameter (2.0 -> 2.5). With min_prob=0.0 inherited from run-4
(itself the only PASS in the proposer_criticizer_experiment over vol-regime-sizer
so far at +0.70%), the skip probability curve becomes:

    p = exp(-2.5 * max(0, vol_ratio - 1))    (no floor; clamped to 0.0 only on underflow)

Comparison at key vol_ratio values vs base (sensitivity=2.0, min_prob=0.05)
and vs run-4 (sensitivity=2.0, min_prob=0.0):

    vol_ratio=1.0 -> p=1.000  (base 1.000,  run-4 1.000)   identical, calm
    vol_ratio=1.2 -> p=0.607  (base 0.670,  run-4 0.670)   6pp compression
    vol_ratio=1.5 -> p=0.287  (base 0.368,  run-4 0.368)   8pp compression
    vol_ratio=2.0 -> p=0.082  (base 0.135,  run-4 0.135)   5pp compression
    vol_ratio=2.5 -> p=0.024  (base 0.05 floor, run-4 0.018)  past base floor
    vol_ratio=3.0 -> p=0.0067 (base 0.05 floor, run-4 0.0025) past base floor
    vol_ratio>=4.0 -> p<0.002 (base 0.05 floor, run-4 ~0)     past base floor

The sensitivity=2.5 calibration delivers ~5-10pp probability compression
across the moderate band (vol_ratio 1.2-2.0). This intermediate step
bounds the downside risk relative to a more aggressive sensitivity=3.0.

Hypothesis: prior runs in this experiment showed:
  - vrs-pc-r1 (signed-momentum overlay):   -88.23% vs base
  - vrs-pc-r2 (quote-staleness gate):      -41.39% vs base
  - vrs-pc-r3 (sensitivity 2.0 -> 1.0):    -30.18% vs base  (curve weakened: FAIL)
  - vrs-pc-r4 (min_prob 0.05 -> 0.0):      +0.70% vs base   (floor removed: PASS)

Joint reading of runs 3 + 4: the directional polarity 'tighter skipping
in the high-vol regime helps; looser skipping hurts.' sensitivity=2.5 + min_prob=0.0
extends this directional bet into the moderate-elevated band (vol_ratio 1.2-2.5)
while keeping the magnitude bounded.

Strict-subset property over run-4: For all vol_ratio > 1.0,
exp(-2.5 * excess) < exp(-2.0 * excess), so p_run5 < p_run4. Combined with
the deterministic SHA-256 draw on client_order_id, the submission set of
this variant is a STRICT SUBSET of run-4's. The vs-run-4 comparison
cleanly attributes the sensitivity-bump lever in isolation. The vs-base
comparison mixes the sensitivity-bump and run-4's already-validated
floor-removal.
"""
from __future__ import annotations

import hashlib
import math
import struct

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class VrsPcR5Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for vrs-pc-r5 (sensitivity-2.5 variant compounding on min_prob=0.0).

    Parameters
    ----------
    fast_halflife : int
        Half-life (in ticks) of the fast EWM used to estimate current
        short-term realized vol. Default 20 ticks (matches base and run-4).
    slow_halflife : int
        Half-life (in ticks) of the slow EWM used as the vol baseline.
        Default 120 ticks (matches base and run-4).
    sensitivity : float
        Controls how aggressively submission probability shrinks with vol.
        p = exp(-sensitivity * max(0, vol_ratio - 1))
        Default 2.5 (vs base/run-4 2.0) — the single structural change
        relative to run-4. Steepens the exponential decay so the compression
        region extends from the deep tail into the moderate-elevated band.
    min_prob : float
        Floor on submission probability. Default 0.0 (vs base 0.05; inherits
        from run-4 unchanged). Together with sensitivity=2.5 yields the
        unfloored curve p = exp(-2.5 * max(0, vol_ratio - 1)).
    min_ticks : int
        Minimum number of quote ticks before vol scaling activates.
        Default 30 (matches base and run-4).
    max_vol_ratio : float
        Clip vol_ratio before applying sensitivity. Default 5.0 (matches
        base and run-4).
    """

    fast_halflife: int = 20
    slow_halflife: int = 120
    sensitivity: float = 2.5
    min_prob: float = 0.0
    min_ticks: int = 30
    max_vol_ratio: float = 5.0


class VrsPcR5Algorithm(ExecAlgorithm):
    """Execution algorithm that scales open-leg submission probability with realized vol.

    Identical to VrsPcR4Algorithm in mechanism; only the default sensitivity
    differs (2.5 vs 2.0). With min_prob=0.0 inherited from run-4, the change
    extends compressed-skip behavior from the deep tail (vol_ratio>2.5 in
    run-4) into the moderate-elevated band (vol_ratio 1.2-2.5).

    For each incoming OPEN order:
      1. Read fast and slow EWM of |delta_mid| from recent quote ticks.
      2. Compute vol_ratio = fast_vol / slow_vol (clipped to max_vol_ratio).
      3. Map to p = max(min_prob, exp(-sensitivity * max(0, vol_ratio - 1))).
      4. Accept or skip the order using a deterministic pseudo-random draw
         keyed on the order's client_order_id.

    For reduce-only (CLOSE) orders: always submit unconditionally
    (intraday_flat compliance).

    Quantity invariant: child_qty = parent_qty = 1 for all submitted orders.

    Strict-subset property over run-4: For any order with vol_ratio > 1.0,
    p_run5 = exp(-2.5 * excess) < exp(-2.0 * excess) = p_run4. The SHA-256
    deterministic draw means the same u is computed for the same
    client_order_id. So the variant's submission set is a STRICT SUBSET of
    run-4's — the vs-run-4 P&L delta is attributable solely to the
    moderate-and-tail trades that run-4 submitted but this variant does not.
    """

    def __init__(self, config: VrsPcR5Config) -> None:
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
            f"VrsPcR5Algorithm started "
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
    fast_halflife: int = 20,
    slow_halflife: int = 120,
    sensitivity: float = 2.5,
    min_prob: float = 0.0,
    min_ticks: int = 30,
    max_vol_ratio: float = 5.0,
) -> VrsPcR5Algorithm:
    """Instantiate and return the VrsPcR5Algorithm.

    Defaults match base vol-regime-sizer except `sensitivity` (2.5 vs 2.0) and
    `min_prob` (0.0 vs 0.05; the min_prob change is inherited from vrs-pc-r4).
    """
    config = VrsPcR5Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        fast_halflife=fast_halflife,
        slow_halflife=slow_halflife,
        sensitivity=sensitivity,
        min_prob=min_prob,
        min_ticks=min_ticks,
        max_vol_ratio=max_vol_ratio,
    )
    return VrsPcR5Algorithm(config=config)
