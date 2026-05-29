"""Anchor-drift skip layered on top of vol-regime-sizer (sip-vrs-l8).

Hypothesis (Propose-Audit-Falsify-Commit method, prompt-l5.md):
---------------------------------------------------------------
The parent `vol-regime-sizer` measures only the ratio of fast vs slow
EWMs of |Δmid|; it is anchor-free and has no notion of how far the
current price has drifted from the session-open mid. Three candidate
weaknesses were enumerated:

  C1: signed local drift (into-the-move blindness)
  C2: price-level drift from session-open anchor
  C3: recent fill velocity (signal-burst regime)

All three were FALSIFIED on the 11 available train dates of the parent's
on-disk CSVs (per-date sign-consistency rule: need ≥ 8 of 11 dates with
delta < 0 between top-quartile-gated bucket and the rest; observed
2/11 for C1, 5/11 for C2, 1/11 for C3). Per Step 5 #3 of the method
(zero survived, pick smallest violation margin), candidate **C2** is
implemented as the weakest-falsification choice.

C2 falsification summary (per-date delta = mean pnl in top-quartile
abs_drift_from_open bucket − mean pnl in other bucket; gate hypothesis
predicted delta < 0):

  20260308: +0.0316   20260309: +0.0817   20260310: −0.1547
  20260311: −0.3106   20260312: −0.0105   20260313: −0.0206
  20260315: −0.0026   20260316: +0.0270   20260317: +0.0070
  20260318: +0.0102   20260320: +0.0380

5 negative-delta dates (skip helps); 6 positive-delta dates (skip
hurts). Magnitude is small (median |delta| ≈ $0.027/contract). Signs
mixed — this loop is not expected to beat the L5 champion.

Modification (single, layered on the parent):
---------------------------------------------
1. Compute `parent_p_submit` exactly as the parent does (unchanged).
2. Track `session_anchor_mid` = first observed mid on `on_quote_tick`,
   and update a running cumulative mean of `|mid − session_anchor_mid|`
   on every tick.
3. On each OPEN order arrival, compute
   `current_abs_drift = |latest_mid − session_anchor_mid|`. If
   `current_abs_drift > anchor_drift_k * running_mean_abs_drift`
   (default k=1.5, targeting ~25% of arrivals per the p75 audit
   bucket size), multiply `parent_p_submit` by
   `anchor_drift_suppress` (default 0.0 = hard skip).
4. Else: leave `parent_p_submit` unchanged.
5. Run the parent's deterministic SHA-256 accept/skip draw at the
   (possibly suppressed) probability.

Per Step 6 (regime-aware parameter rule): the candidate is
HETEROGENEOUS (per-session median abs_drift_from_open ranges 21 to 82
across the 11 train dates), so the threshold is specified as a
**regime-relative** quantity (`k × running_mean`) rather than an
absolute value. This guards against the loop-5-style failure where an
absolute threshold calibrated on dense-trade dates fires on essentially
no early-window thin-trade arrivals.

The reduce-only bypass, cold-start guard (`tick_count < min_ticks`),
`min_prob` floor, and quantity invariant are inherited unchanged from
the parent. Like the L5 wide-spread layer, this is a guard layered on
top of the parent — it only further suppresses; it never re-admits an
order the parent would skip.

Note: this targets the named parent `vol-regime-sizer`, not the L5
champion. The L5 wide-spread skip is intentionally NOT included
(method's parent is base_algo, not running champion). This may produce
strong overlap with the L5 wide-spread gate (both fire more on volatile
late-session windows) and result in no incremental edge vs L5 — that is
the documented honesty-flag risk for this loop.

Constraints (enforced):
- top_of_book_only: untouched.
- participation_cap: untouched (parent orders are 1 contract).
- intraday_flat: reduce-only orders always submit unconditionally.
- quantity invariant: skip → 0 child fills; submit → exactly parent
  quantity (1 contract). No inflation.

Expected effect vs `vol-regime-sizer`:
- realized_pnl: ambiguous (signs mixed across dates).
- mean_slippage: 0 (zero-slippage fill model).
- sharpe_ratio: ambiguous.
- trade_count: ↓ by roughly the gating rate (~12% nominal).
- win_rate: ≈ unchanged (small per-fill effect).
"""
from __future__ import annotations

import hashlib
import math
import struct

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class AnchorDriftSkipConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the anchor-drift skip layered on vol-regime-sizer.

    Parameters
    ----------
    fast_halflife : int
        Half-life (in ticks) of the fast EWM of |Δmid|. Inherited from
        parent. Default 20.
    slow_halflife : int
        Half-life (in ticks) of the slow EWM of |Δmid| (vol baseline).
        Inherited from parent. Default 120.
    sensitivity : float
        Decay rate from vol-excess to submission probability. Inherited
        from parent. Default 2.0.
    min_prob : float
        Floor on submission probability. Inherited from parent. Default 0.05.
    min_ticks : int
        Cold-start guard. Inherited from parent. Default 30.
    max_vol_ratio : float
        Clip vol_ratio. Inherited from parent. Default 5.0.
    anchor_drift_k : float
        Threshold multiplier. Gate fires when
        `|mid - session_anchor_mid| > anchor_drift_k * running_mean_abs_drift`.
        Default 1.5 (targets ~25% of arrivals per the p75 audit bucket).
    anchor_drift_suppress : float
        Multiplier applied to `parent_p_submit` when the anchor-drift
        gate fires. Default 0.0 (hard skip).
    """

    fast_halflife: int = 20
    slow_halflife: int = 120
    sensitivity: float = 2.0
    min_prob: float = 0.05
    min_ticks: int = 30
    max_vol_ratio: float = 5.0
    anchor_drift_k: float = 1.5
    anchor_drift_suppress: float = 0.0


class AnchorDriftSkipAlgorithm(ExecAlgorithm):
    """Parent vol-regime-sizer with a layered anchor-drift skip on OPENs.

    For each incoming OPEN order:
      1. Compute parent's vol-regime p_submit (unchanged formula).
      2. If |latest_mid - session_anchor_mid| > k * running_mean_abs_drift:
         p_submit *= anchor_drift_suppress.
      3. Else: leave p_submit unchanged.
      4. Run the deterministic SHA-256 accept/skip draw on the order.

    For reduce-only (CLOSE) orders: always submit unconditionally.

    Quantity invariant: child_qty = parent_qty = 1 for all submitted orders.
    """

    def __init__(self, config: AnchorDriftSkipConfig) -> None:
        super().__init__(config=config)

        # Parent EWM parameters
        self._fast_alpha: float = 1.0 - math.exp(-math.log(2) / config.fast_halflife)
        self._slow_alpha: float = 1.0 - math.exp(-math.log(2) / config.slow_halflife)
        self._sensitivity: float = config.sensitivity
        self._min_prob: float = config.min_prob
        self._min_ticks: int = config.min_ticks
        self._max_vol_ratio: float = config.max_vol_ratio

        # Anchor-drift layer
        self._anchor_drift_k: float = config.anchor_drift_k
        self._anchor_drift_suppress: float = config.anchor_drift_suppress

        # Parent EWM state
        self._fast_vol: float | None = None
        self._slow_vol: float | None = None
        self._prev_mid: float | None = None
        self._tick_count: int = 0

        # Latest top-of-book / mid (filled on each quote tick)
        self._last_mid: float | None = None

        # Anchor-drift session state
        self._session_anchor_mid: float | None = None
        self._cum_abs_drift: float = 0.0
        self._drift_count: int = 0

        # Subscription tracking
        self._subscribed: set[str] = set()

        # Diagnostic counters
        self._submitted: int = 0
        self._skipped_vol: int = 0      # skipped by parent's vol gate
        self._skipped_anchor: int = 0   # skipped by the anchor-drift layer

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"AnchorDriftSkipAlgorithm started "
            f"(fast_alpha={self._fast_alpha:.4f}, slow_alpha={self._slow_alpha:.4f}, "
            f"sensitivity={self._sensitivity}, min_prob={self._min_prob}, "
            f"min_ticks={self._min_ticks}, "
            f"anchor_drift_k={self._anchor_drift_k:.3f}, "
            f"anchor_drift_suppress={self._anchor_drift_suppress:.4f})."
        )

    def on_reset(self) -> None:
        self._fast_vol = None
        self._slow_vol = None
        self._prev_mid = None
        self._tick_count = 0
        self._last_mid = None
        self._session_anchor_mid = None
        self._cum_abs_drift = 0.0
        self._drift_count = 0
        self._subscribed.clear()
        self._submitted = 0
        self._skipped_vol = 0
        self._skipped_anchor = 0

    # ------------------------------------------------------------------
    # Quote tick handler — update EWM vol estimates + session anchor
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    def on_quote_tick(self, tick) -> None:
        """Update EWM vol estimates, latest mid, session anchor + running drift."""
        try:
            bid = float(str(tick.bid_price))
            ask = float(str(tick.ask_price))
            mid = (bid + ask) / 2.0
        except Exception:
            return

        # Cache the latest mid for the anchor-drift layer
        self._last_mid = mid

        # First-tick: anchor the session
        if self._session_anchor_mid is None:
            self._session_anchor_mid = mid

        # Update cumulative |drift from anchor|
        self._cum_abs_drift += abs(mid - self._session_anchor_mid)
        self._drift_count += 1

        # Parent EWM update
        if self._prev_mid is not None:
            abs_delta = abs(mid - self._prev_mid)
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

        self._prev_mid = mid
        self._tick_count += 1

    # ------------------------------------------------------------------
    # Parent vol-regime submission probability (unchanged formula)
    # ------------------------------------------------------------------

    def _compute_parent_prob(self) -> float:
        """Return parent's vol-regime probability in [min_prob, 1.0]."""
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
        return prob

    # ------------------------------------------------------------------
    # Deterministic pseudo-random draw (inherited unchanged from parent)
    # ------------------------------------------------------------------

    @staticmethod
    def _order_uniform(order_id_str: str) -> float:
        digest = hashlib.sha256(order_id_str.encode()).digest()
        val = struct.unpack(">Q", digest[:8])[0]
        return val / (2**64)

    # ------------------------------------------------------------------
    # Anchor-drift gate
    # ------------------------------------------------------------------

    def _is_anchor_drifted(self) -> bool:
        """True iff |latest_mid - anchor| > k * running_mean_abs_drift."""
        if self._last_mid is None or self._session_anchor_mid is None:
            # No quote yet — be conservative; treat as not drifted.
            return False
        if self._drift_count < self._min_ticks:
            # Cold start — running mean unreliable.
            return False

        running_mean = self._cum_abs_drift / max(1, self._drift_count)
        if running_mean < 1e-12:
            # Running mean essentially zero — treat as not drifted.
            return False

        current = abs(self._last_mid - self._session_anchor_mid)
        return current > self._anchor_drift_k * running_mean

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip, parent + anchor-drift layers combined."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders: always submit — intraday_flat compliance.
        if order.is_reduce_only:
            self.log.debug(
                f"Reduce-only {order.client_order_id}: submitting unconditionally."
            )
            self.submit_order(order)
            return

        # Parent vol-regime probability
        p = self._compute_parent_prob()

        # Anchor-drift layer
        if self._is_anchor_drifted():
            p_after = p * self._anchor_drift_suppress
        else:
            p_after = p

        # Fast path: p == 1.0 (calm regime, cold start, narrow drift)
        if p_after >= 1.0 - 1e-9:
            self._submitted += 1
            self.log.debug(
                f"SUBMIT {order.client_order_id} (p=1.0, calm/cold/anchored)."
            )
            self.submit_order(order)
            return

        # Hard-skip fast path: probability collapsed to zero by anchor layer
        if p_after <= 1e-12:
            self._skipped_anchor += 1
            self.log.info(
                f"SKIP {order.client_order_id} (anchor-drifted, p_after≈0). "
                f"submitted={self._submitted} "
                f"skipped_vol={self._skipped_vol} skipped_anchor={self._skipped_anchor}."
            )
            return

        # Deterministic draw from order ID
        u = self._order_uniform(str(order.client_order_id))

        if u < p_after:
            self._submitted += 1
            self.log.debug(
                f"SUBMIT {order.client_order_id} "
                f"(p_after={p_after:.4f}, u={u:.4f})."
            )
            self.submit_order(order)
        else:
            # Attribute skip to whichever layer was binding.
            if p_after < p - 1e-12:
                self._skipped_anchor += 1
                reason = "anchor"
            else:
                self._skipped_vol += 1
                reason = "vol"
            self.log.info(
                f"SKIP {order.client_order_id} "
                f"(p_after={p_after:.4f}, u={u:.4f}, reason={reason}). "
                f"submitted={self._submitted} "
                f"skipped_vol={self._skipped_vol} skipped_anchor={self._skipped_anchor}."
            )


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    fast_halflife: int = 20,
    slow_halflife: int = 120,
    sensitivity: float = 2.0,
    min_prob: float = 0.05,
    min_ticks: int = 30,
    max_vol_ratio: float = 5.0,
    anchor_drift_k: float = 1.5,
    anchor_drift_suppress: float = 0.0,
) -> AnchorDriftSkipAlgorithm:
    """Instantiate the anchor-drift skip layered on vol-regime-sizer (sip-vrs-l8)."""
    config = AnchorDriftSkipConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        fast_halflife=fast_halflife,
        slow_halflife=slow_halflife,
        sensitivity=sensitivity,
        min_prob=min_prob,
        min_ticks=min_ticks,
        max_vol_ratio=max_vol_ratio,
        anchor_drift_k=anchor_drift_k,
        anchor_drift_suppress=anchor_drift_suppress,
    )
    return AnchorDriftSkipAlgorithm(config=config)
