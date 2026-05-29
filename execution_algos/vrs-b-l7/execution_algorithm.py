"""vrs-b-l7: vol-regime sizer + WIDENED adverse-drift subset (threshold 0.005 -> 0.003).

Derived structurally from `vrs-b-l6` with a SINGLE targeted change:
`drift_threshold` default is lowered from 0.005 to 0.003. All other
mechanics -- `adverse_multiplier` (0.025, the L6 value), fast/slow vol
EWMs, sensitivity, min_prob (0.05 floor on base_p only; p_final may dip
below), min_ticks, drift_halflife (40), reduce-only path,
SHA256(client_order_id) deterministic draw, "always apply base
vol-skip with additional multiplicative skip on adverse-drift" gate
topology -- are preserved verbatim.

Rationale (informed by L6's brief-summary `next` text, the only L6
context this loop is permitted to read): L6 reported the single-knob
deepening 0.10 -> 0.025 paid off (+2.37% pnl vs L5, +110.66% vs base
on 11 dates) with marginal per-skip EV ~$0.117/skip -- BELOW L5's
marginal $0.21/skip and BELOW L4's marginal $0.18/skip, indicating the
diminishing-returns slope L4 originally predicted has finally bent. L6
explicitly prescribed: STOP deepening the multiplier (further halving
0.025 -> ~0.006 risks crossing into negative marginal EV and the
strict-subset cap doesn't help vs L6) and instead WIDEN the adverse
subset by lowering drift_threshold 0.005 -> 0.003. This brings NEW
borderline-drift orders into the multiplier zone -- a different subset
of admits than the saturated mult-deepening dimension.

Mechanism: with drift_threshold=0.003 instead of 0.005:
* The adverse-drift set is DEFINED by |drift_ewm| > drift_threshold
  AND opposing the order side. Lowering the threshold ENLARGES the
  adverse set: orders with drift_ewm magnitude in [0.003, 0.005] that
  oppose order side were previously treated as non-adverse (p_final =
  base_p, no extra skip pressure); they are now treated as adverse
  (p_final = base_p * 0.025).
* For BUY orders this catches new admits where drift_ewm in [-0.005,
  -0.003] (mild negative drift opposing a BUY); for SELL orders new
  admits where drift_ewm in [+0.003, +0.005] (mild positive drift
  opposing a SELL).
* The L7 admit set is a STRICT SUBSET of L6's admit set on
  orders with |drift_ewm| in [0.003, 0.005] (newly adverse, now
  multiplier-skipped). Outside that band the admit decision is
  unchanged (already adverse with |drift_ewm| > 0.005, or non-adverse
  with |drift_ewm| < 0.003 -- both unchanged in behavior).

Expected outcome (per L6's `next`):
* Best case: marginal per-borderline-skip EV ~$0.117/skip (comparable
  to L6's recent marginal) -> incremental pnl $40-90 -> total
  ~$1,260-1,310.
* Weak-subset case: borderline drift (magnitude in [0.003, 0.005])
  carries less directional information than [>0.005]; per-skip EV
  drops to ~$0.04-0.08/skip -> incremental pnl $20-60 -> total
  ~$1,240-1,280, OR per-skip EV inverts -> pnl regresses toward
  L6 $1,220 or modestly below (strict-subset architecture caps the
  downside on the borderline subset only; non-borderline behavior is
  identical to L6).

Quantity invariant: at most 1 contract submitted per parent
1-contract order; same as L6, L5, L4, L3, base.
"""
from __future__ import annotations

import hashlib
import math
import struct

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class VrsBL7Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for vrs-b-l7.

    Identical to vrs-b-l6 except `drift_threshold` default is lowered
    from 0.005 to 0.003.

    Parameters
    ----------
    fast_halflife : int
        Half-life (in ticks) of the fast EWM. Default 20.
    slow_halflife : int
        Half-life (in ticks) of the slow EWM (vol baseline). Default 120.
    sensitivity : float
        p_vol = exp(-sensitivity * max(0, vol_ratio - 1)). Default 2.0.
    min_prob : float
        Floor on the base vol probability p_vol when vol-gated. Default
        0.05. Note: the adverse-drift multiplier is applied AFTER this
        floor, so p_final may go below min_prob on adverse-drift orders
        (e.g. base_p=0.05 floor * mult=0.025 = p_final=0.00125). This is
        intentional and continues the L3/L4/L5/L6 design choice.
    min_ticks : int
        Cold-start guard. Default 30.
    max_vol_ratio : float
        Clip vol_ratio. Default 5.0.
    drift_halflife : int
        Half-life (in ticks) of the signed-mid-increment drift EWM.
        Default 40.
    drift_threshold : float
        Magnitude of drift_ewm above which the drift is treated as
        directional/adverse. **Default 0.003** (was 0.005 in
        vrs-b-l3/l4/l5/l6) -- the single-knob WIDENING L6's `next`
        prescribed in lieu of further mult-deepening (which has reached
        saturation: marginal per-skip EV dropped from L5 $0.21/skip to
        L6 $0.117/skip; further deepening would risk negative marginal).
    adverse_multiplier : float
        Multiplicative reduction applied to p_vol on adverse-drift orders.
        Must be in (0, 1]. Default 0.025 (unchanged from vrs-b-l6 per
        L6's `next` text: hold the multiplier fixed; widen the subset
        instead).
    """

    fast_halflife: int = 20
    slow_halflife: int = 120
    sensitivity: float = 2.0
    min_prob: float = 0.05
    min_ticks: int = 30
    max_vol_ratio: float = 5.0
    drift_halflife: int = 40
    drift_threshold: float = 0.003
    adverse_multiplier: float = 0.025


class VrsBL7Algorithm(ExecAlgorithm):
    """Vol-regime sizer with WIDENED adverse-drift subset.

    Logic identical to vrs-b-l6; only the drift_threshold default
    changes (0.005 -> 0.003). See `VrsBL7Config` and the module
    docstring for rationale.

    For each incoming OPEN order:
      1. EWM vol (fast, slow) and EWM drift (signed delta_mid) updated
         continuously in `on_quote_tick` (same as L6).
      2. base_p = max(min_prob, exp(-sensitivity * max(0, vol_ratio-1))).
      3. adverse = drift_ewm < -drift_threshold (BUY) or
                   drift_ewm > +drift_threshold (SELL).
                   (L7: threshold WIDENED to 0.003.)
      4. p_final = base_p * adverse_multiplier  if adverse
                   base_p                       otherwise.
      5. Deterministic SHA256(client_order_id) draw -> accept / skip.

    Reduce-only (CLOSE) orders: always submitted unconditionally.
    """

    def __init__(self, config: VrsBL7Config) -> None:
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
        self._adverse_multiplier: float = config.adverse_multiplier

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
        self._skipped_base: int = 0
        self._skipped_adverse_extra: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            "VrsBL7Algorithm started "
            f"(fast_alpha={self._fast_alpha:.4f}, slow_alpha={self._slow_alpha:.4f}, "
            f"drift_alpha={self._drift_alpha:.4f}, sensitivity={self._sensitivity}, "
            f"min_prob={self._min_prob}, min_ticks={self._min_ticks}, "
            f"drift_threshold={self._drift_threshold}, "
            f"adverse_multiplier={self._adverse_multiplier})."
        )

    def on_reset(self) -> None:
        self._fast_vol = None
        self._slow_vol = None
        self._drift_ewm = 0.0
        self._prev_mid = None
        self._tick_count = 0
        self._subscribed.clear()
        self._submitted = 0
        self._skipped_base = 0
        self._skipped_adverse_extra = 0

    # ------------------------------------------------------------------
    # Quote tick handler -- update EWMs
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

        # Reduce-only (close) orders: always submit -- intraday_flat compliance.
        if order.is_reduce_only:
            self.submit_order(order)
            return

        # Base vol-regime probability (ALWAYS applied -- no override path).
        base_p = self._compute_p_vol()

        # Apply additional adverse-drift skip pressure (disjunctive structure).
        adverse = self._drift_is_adverse(order.side)
        if adverse:
            p_final = base_p * self._adverse_multiplier
        else:
            p_final = base_p

        # Fast path: full participation (cold start / calm regime, no adverse).
        if p_final >= 1.0 - 1e-9:
            self._submitted += 1
            self.submit_order(order)
            return

        u = self._order_uniform(str(order.client_order_id))
        if u < p_final:
            self._submitted += 1
            self.submit_order(order)
        else:
            # Skipped. Bucket the skip into "base would have skipped too"
            # vs "additional skip due to adverse-drift multiplier" for
            # diagnostic visibility (no behavioral effect).
            if adverse and u < base_p:
                # base would have ADMITTED at u, but we tightened to
                # base_p * mult and now skip -- this is the directional
                # refinement at work.
                self._skipped_adverse_extra += 1
            else:
                self._skipped_base += 1
            self.log.info(
                f"SKIP {order.client_order_id} (base_p={base_p:.4f}, "
                f"p_final={p_final:.4f}, u={u:.4f}, adverse={adverse}, "
                f"drift_ewm={self._drift_ewm:.4f}, "
                f"submitted={self._submitted} "
                f"skipped_base={self._skipped_base} "
                f"skipped_adverse_extra={self._skipped_adverse_extra})."
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
    drift_threshold: float = 0.003,
    adverse_multiplier: float = 0.025,
) -> VrsBL7Algorithm:
    """Instantiate the vrs-b-l7 vol-regime sizer with WIDENED adverse-drift subset."""
    config = VrsBL7Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        fast_halflife=fast_halflife,
        slow_halflife=slow_halflife,
        sensitivity=sensitivity,
        min_prob=min_prob,
        min_ticks=min_ticks,
        max_vol_ratio=max_vol_ratio,
        drift_halflife=drift_halflife,
        drift_threshold=drift_threshold,
        adverse_multiplier=adverse_multiplier,
    )
    return VrsBL7Algorithm(config=config)
