"""vrs-b-l3: vol-regime sizer + DISJUNCTIVE adverse-drift skip pressure.

Built on the L1/L2 lineage by INVERTING the gate semantics in line with
L2's brief-summary `next`:

  L1/L2 architecture (asymmetric override, REJECTED by L2 outcome):
      if drift NOT adverse: force p = 1.0   (override base vol-skip)
      else:                 p = p_vol        (apply base vol-skip)
   -> admitted set = (drift_aligned OR drift_neutral) UNION
                     (drift_adverse AND vol-draw passes)
      This is a SUPERSET of base's admit set on aligned-drift orders;
      it re-admits ~half of base's correctly-skipped negative-EV orders.

  L3 architecture (disjunctive, additive skip pressure):
      base_p = p_vol                          (always apply base vol-skip)
      if drift adverse:  p_final = base_p * adverse_multiplier  (< 1)
      else:              p_final = base_p                       (unchanged)
   -> admitted set = (vol-draw passes at p_final). Because
      p_final <= base_p for every order, the admitted set is a strict
      SUBSET of base's admitted set. We skip everything base skips,
      plus an additional fraction on adverse-drift orders.

Why this should help: base's symmetric vol-skip is provably useful
($579 vs simple $43 over 11 dates ~= $50/1k extra PnL from base's
~7k skips). The directional information was hypothesized in L1 to be
real -- adverse-drift high-vol orders ARE worse than aligned-drift
high-vol orders. The L1/L2 architecture lost because it traded base's
~$540 of skip-EV for a ~$50 directional refinement; the L3 architecture
KEEPS base's $540 and adds the directional refinement on top, so the
worst-case outcome is matching the base (if drift signal is uninformative,
adverse_multiplier=0.5 just skips ~half the adverse subset for zero
expected value change; could shave a small EV) and the best-case
outcome is beating the base by the directional refinement's value.

Rationale informed by L2's brief-summary cross-reference: this is
structurally analogous to afg-b-l3 in the aggressor-flow-gate arm,
which broke the asymmetric-gate trap by using a DISJUNCTIVE
(skip-OR) structure that yielded a strict superset of base's skips.
That move was the inflection point of the afg-b arm: L3 = base
parity, L4 = +12% vs base. We aim for the same dynamic here.

Specific parameter choices vs L2:
  * adverse_multiplier = 0.5: cuts admission probability in half on
    adverse-drift orders (e.g. p_vol=0.3 in elevated vol becomes
    p_final=0.15; p_vol=0.05 floor becomes 0.025). NOT floored by
    min_prob -- the multiplier should be allowed to push below the
    base floor since the directional signal justifies extra
    selectivity.
  * drift_threshold = 0.005: lowered from L2's 0.008 per L2's `next`
    hint ("could go to 0.005 to further increase adverse coverage").
    L2 with 0.008 fired the gate on ~72 extra orders; we want
    materially more adverse-drift coverage so the directional pressure
    actually engages.
  * Override semantics REMOVED: there is no aligned-drift path that
    forces p=1.0. Aligned (and neutral) drift falls through to base
    p_vol unchanged.
  * All other base mechanics preserved (fast/slow halflives 20/120,
    sensitivity 2.0, min_prob 0.05, min_ticks 30, drift_halflife 40,
    reduce-only always submit, SHA256 deterministic draw).

Quantity invariant: at most 1 contract submitted per parent 1-contract
order; same as base/L1/L2.
"""
from __future__ import annotations

import hashlib
import math
import struct

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class VrsBL3Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for vrs-b-l3.

    Vs vrs-b-l2: gate semantics INVERTED from `override on aligned drift,
    apply skip only on adverse` to `always apply base skip, with an
    ADDITIONAL multiplicative skip on adverse drift`. Drift threshold
    lowered 0.008 -> 0.005. New parameter `adverse_multiplier` = 0.5.

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
        floor, so p_final may go below min_prob on adverse-drift orders.
        This is intentional -- the directional signal justifies extra
        selectivity below the base floor.
    min_ticks : int
        Cold-start guard. Default 30.
    max_vol_ratio : float
        Clip vol_ratio. Default 5.0.
    drift_halflife : int
        Half-life (in ticks) of the signed-mid-increment drift EWM.
        Default 40.
    drift_threshold : float
        Magnitude of drift_ewm above which the drift is treated as
        directional/adverse. **Default 0.005** (was 0.008 in vrs-b-l2)
        per L2's brief-summary `next` hint, to widen adverse coverage.
    adverse_multiplier : float
        Multiplicative reduction applied to p_vol on adverse-drift orders.
        Must be in (0, 1]. Default **0.5** (cut admit probability in half
        on adverse drift).
    """

    fast_halflife: int = 20
    slow_halflife: int = 120
    sensitivity: float = 2.0
    min_prob: float = 0.05
    min_ticks: int = 30
    max_vol_ratio: float = 5.0
    drift_halflife: int = 40
    drift_threshold: float = 0.005
    adverse_multiplier: float = 0.5


class VrsBL3Algorithm(ExecAlgorithm):
    """Vol-regime sizer with disjunctive adverse-drift skip pressure.

    For each incoming OPEN order:
      1. EWM vol (fast, slow) and EWM drift (signed delta_mid) updated
         continuously in `on_quote_tick` (same as L1/L2).
      2. base_p = max(min_prob, exp(-sensitivity * max(0, vol_ratio-1))).
      3. adverse = drift_ewm < -drift_threshold (BUY) or
                   drift_ewm > +drift_threshold (SELL).
      4. p_final = base_p * adverse_multiplier  if adverse
                   base_p                       otherwise.
      5. Deterministic SHA256(client_order_id) draw -> accept / skip.

    Reduce-only (CLOSE) orders: always submitted unconditionally.
    """

    def __init__(self, config: VrsBL3Config) -> None:
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
            "VrsBL3Algorithm started "
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
    adverse_multiplier: float = 0.5,
) -> VrsBL3Algorithm:
    """Instantiate the vrs-b-l3 vol-regime sizer with disjunctive adverse-drift pressure."""
    config = VrsBL3Config(
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
    return VrsBL3Algorithm(config=config)
