"""vrs-b-l5: vol-regime sizer + adverse-drift multiplier deepened 0.25 -> 0.1.

Derived structurally from `vrs-b-l4` with a SINGLE targeted change:
`adverse_multiplier` default is lowered from 0.25 to 0.10. All other
mechanics — fast/slow vol EWMs, sensitivity, min_prob (0.05 floor on
base_p only; p_final may dip below), min_ticks, drift_halflife (40),
drift_threshold (0.005), reduce-only path, SHA256(client_order_id)
deterministic draw, "always apply base vol-skip with additional
multiplicative skip on adverse-drift" gate topology — are preserved
verbatim.

Rationale (informed by L4's brief-summary `next` text, the only L4
context this loop is permitted to read): L4 reported the single-knob
deepening 0.5 -> 0.25 paid off (+15.18% pnl vs L3, +87.53% vs base on
11 dates) with marginal per-skip EV ~$0.18/skip, mildly below L3's
~$0.27/skip extras-vs-base. The diminishing-returns slope was
~$0.09/skip per multiplier halving. L4 explicitly prescribed the next
move: single-knob push 0.25 -> 0.1 at fixed drift_threshold=0.005, do
NOT touch other levers, AVOID the corner case mult=0.0 (save that for
L6 if L5 confirms the diminishing-returns slope shape).

Expected outcome (per L4's `next`):
* Best case: marginal EV ~$0.09/skip * additional skips ~$70-100
  incremental pnl -> total ~$1,150-1,200 over 11 dates.
* Failure case: per-skip EV inverts on the new tail -- the adverse
  admits at u in `(0.1*base_p, 0.25*base_p)` are actually neutral or
  positive-EV, so newly skipping them costs pnl. Pnl regresses
  toward L3's $943 but the strict-subset architecture caps the
  downside.

Quantity invariant: at most 1 contract submitted per parent
1-contract order; same as L4, L3 and base.
"""
from __future__ import annotations

import hashlib
import math
import struct

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class VrsBL5Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for vrs-b-l5.

    Identical to vrs-b-l4 except `adverse_multiplier` default is
    lowered from 0.25 to 0.10.

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
        (e.g. base_p=0.05 floor * mult=0.10 = p_final=0.005). This is
        intentional -- the directional signal justifies extra selectivity
        below the base floor; L3/L4 already operated this way at mult
        0.5/0.25.
    min_ticks : int
        Cold-start guard. Default 30.
    max_vol_ratio : float
        Clip vol_ratio. Default 5.0.
    drift_halflife : int
        Half-life (in ticks) of the signed-mid-increment drift EWM.
        Default 40.
    drift_threshold : float
        Magnitude of drift_ewm above which the drift is treated as
        directional/adverse. Default 0.005 (unchanged from vrs-b-l3/l4 per
        L4's `next` text: hold the subset definition fixed; deepen the
        multiplier instead).
    adverse_multiplier : float
        Multiplicative reduction applied to p_vol on adverse-drift orders.
        Must be in (0, 1]. **Default 0.10** (was 0.25 in vrs-b-l4) — the
        single-knob deepening L4's `next` prescribed.
    """

    fast_halflife: int = 20
    slow_halflife: int = 120
    sensitivity: float = 2.0
    min_prob: float = 0.05
    min_ticks: int = 30
    max_vol_ratio: float = 5.0
    drift_halflife: int = 40
    drift_threshold: float = 0.005
    adverse_multiplier: float = 0.10


class VrsBL5Algorithm(ExecAlgorithm):
    """Vol-regime sizer with further-deepened adverse-drift skip pressure.

    Logic identical to vrs-b-l4; only the adverse_multiplier default
    changes. See `VrsBL5Config` and the module docstring for rationale.

    For each incoming OPEN order:
      1. EWM vol (fast, slow) and EWM drift (signed delta_mid) updated
         continuously in `on_quote_tick` (same as L4).
      2. base_p = max(min_prob, exp(-sensitivity * max(0, vol_ratio-1))).
      3. adverse = drift_ewm < -drift_threshold (BUY) or
                   drift_ewm > +drift_threshold (SELL).
      4. p_final = base_p * adverse_multiplier  if adverse
                   base_p                       otherwise.
      5. Deterministic SHA256(client_order_id) draw -> accept / skip.

    Reduce-only (CLOSE) orders: always submitted unconditionally.
    """

    def __init__(self, config: VrsBL5Config) -> None:
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
            "VrsBL5Algorithm started "
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

        # Base vol-regime probability (ALWAYS applied — no override path).
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
    drift_threshold: float = 0.005,
    adverse_multiplier: float = 0.10,
) -> VrsBL5Algorithm:
    """Instantiate the vrs-b-l5 vol-regime sizer with deepened adverse-drift multiplier."""
    config = VrsBL5Config(
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
    return VrsBL5Algorithm(config=config)
