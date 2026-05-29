"""vrs-b-l8: vol-regime sizer + further-WIDENED adverse-drift subset (threshold 0.003 -> 0.002).

Derived structurally from `vrs-b-l7` with a SINGLE targeted change:
`drift_threshold` default is lowered from 0.003 to 0.002 (a 33% reduction,
the same proportional step as 0.005 -> 0.003 was relative to L6's 0.005).
All other mechanics -- `adverse_multiplier` (0.025, held since L6), fast/slow
vol EWMs, sensitivity, min_prob (0.05 floor on base_p only; p_final may dip
below), min_ticks, drift_halflife (40), reduce-only path,
SHA256(client_order_id) deterministic draw, "always apply base vol-skip
with additional multiplicative skip on adverse-drift" gate topology -- are
preserved verbatim.

Rationale (informed by L7's brief-summary `next` text, the only L7
context this loop is permitted to read): L7 reported the single-knob
WIDENING 0.005 -> 0.003 (first edit on the threshold dimension since L3)
paid off with the LARGEST pnl/sharpe jump in the breakthrough lineage
since L3 -> L4: +$182.50 pnl vs L6 (+14.95%), +1.01 sharpe vs L6
(L5 -> L6 was only +0.24, L4 -> L5 only +0.38). Per-borderline-skip EV
landed at $0.0746/skip (mid-weak-subset band $0.04-0.08/skip as L6's
`next` predicted), but the borderline subset turned out ~10x LARGER
than L6's marginal mult-deepening subset (2,446 vs 242 marginal skips),
so total contribution exceeded L6's best-case band ($1,230-1,310) by
~$93. L7 explicitly prescribed: continue widening the same fresh
dimension (drift_threshold 0.003 -> 0.002), AVOID further mult deepening
(saturated at L6) AND vol-conditional multipliers (adds complexity,
no prior signal). The threshold dimension is fresh (only one data
point so far), productive (largest single-step in the lineage), and
the choice gives a sharper signal on where the threshold dimension's
productive region ends.

Mechanism: with drift_threshold=0.002 instead of 0.003:
* The adverse-drift set is DEFINED by |drift_ewm| > drift_threshold
  AND opposing the order side. Lowering the threshold ENLARGES the
  adverse set: orders with drift_ewm magnitude in [0.002, 0.003] that
  oppose order side were previously treated as non-adverse (p_final =
  base_p, no extra skip pressure); they are now treated as adverse
  (p_final = base_p * 0.025).
* For BUY orders this catches new admits where drift_ewm in [-0.003,
  -0.002] (mild negative drift opposing a BUY); for SELL orders new
  admits where drift_ewm in [+0.002, +0.003] (mild positive drift
  opposing a SELL).
* The L8 admit set is a STRICT SUBSET of L7's admit set on
  orders with |drift_ewm| in [0.002, 0.003] (newly adverse, now
  multiplier-skipped). Outside that band the admit decision is
  unchanged (already adverse with |drift_ewm| > 0.003, or non-adverse
  with |drift_ewm| < 0.002 -- both unchanged in behavior).

Expected outcome (per L7's `next`):
* Best case: per-skip EV holds at ~$0.07/skip on a subset of similar
  relative width (~50% of L7's borderline, so ~1,200 new skips) ->
  incremental pnl $80-110 -> total ~$1,480-1,520.
* Weaker-subset case: per-skip EV drops further toward $0.04-0.05/skip
  as the drift signal weakens at smaller magnitudes -> incremental
  pnl $50-80 -> total ~$1,450-1,490.
* Failure case: per-skip EV inverts on the new tail at |drift_ewm| in
  [0.002, 0.003] -- newly skipped admits are net-positive-EV; pnl
  regresses toward L7's $1,403 or modestly below. Strict-subset
  architecture caps the downside ON THE NEW BORDERLINE SUBSET ONLY
  (orders with |drift_ewm| <= 0.002 or > 0.003 behave identically to L7).

Quantity invariant: at most 1 contract submitted per parent
1-contract order; same as L7, L6, L5, L4, L3, base.
"""
from __future__ import annotations

import hashlib
import math
import struct

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class VrsBL8Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for vrs-b-l8.

    Identical to vrs-b-l7 except `drift_threshold` default is lowered
    from 0.003 to 0.002.

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
        intentional and continues the L3/L4/L5/L6/L7 design choice.
    min_ticks : int
        Cold-start guard. Default 30.
    max_vol_ratio : float
        Clip vol_ratio. Default 5.0.
    drift_halflife : int
        Half-life (in ticks) of the signed-mid-increment drift EWM.
        Default 40.
    drift_threshold : float
        Magnitude of drift_ewm above which the drift is treated as
        directional/adverse. **Default 0.002** (was 0.003 in vrs-b-l7,
        0.005 in vrs-b-l3/l4/l5/l6) -- the single-knob WIDENING per
        L7's `next` text, extending the fresh-and-productive threshold
        dimension (L7 delivered the largest single-step pnl/sharpe gain
        in the lineage on this dimension).
    adverse_multiplier : float
        Multiplicative reduction applied to p_vol on adverse-drift orders.
        Must be in (0, 1]. Default 0.025 (unchanged from vrs-b-l6/l7 per
        L7's `next` text: hold the multiplier fixed; widen the subset
        further on the same dimension).
    """

    fast_halflife: int = 20
    slow_halflife: int = 120
    sensitivity: float = 2.0
    min_prob: float = 0.05
    min_ticks: int = 30
    max_vol_ratio: float = 5.0
    drift_halflife: int = 40
    drift_threshold: float = 0.002
    adverse_multiplier: float = 0.025


class VrsBL8Algorithm(ExecAlgorithm):
    """Vol-regime sizer with further-WIDENED adverse-drift subset.

    Logic identical to vrs-b-l7; only the drift_threshold default
    changes (0.003 -> 0.002). See `VrsBL8Config` and the module
    docstring for rationale.

    For each incoming OPEN order:
      1. EWM vol (fast, slow) and EWM drift (signed delta_mid) updated
         continuously in `on_quote_tick` (same as L7).
      2. base_p = max(min_prob, exp(-sensitivity * max(0, vol_ratio-1))).
      3. adverse = drift_ewm < -drift_threshold (BUY) or
                   drift_ewm > +drift_threshold (SELL).
                   (L8: threshold FURTHER WIDENED to 0.002.)
      4. p_final = base_p * adverse_multiplier  if adverse
                   base_p                       otherwise.
      5. Deterministic SHA256(client_order_id) draw -> accept / skip.

    Reduce-only (CLOSE) orders: always submitted unconditionally.
    """

    def __init__(self, config: VrsBL8Config) -> None:
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
            "VrsBL8Algorithm started "
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
    drift_threshold: float = 0.002,
    adverse_multiplier: float = 0.025,
) -> VrsBL8Algorithm:
    """Instantiate the vrs-b-l8 vol-regime sizer with further-WIDENED adverse-drift subset."""
    config = VrsBL8Config(
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
    return VrsBL8Algorithm(config=config)
