"""Directional-headwind probabilistic gate (sip-vrs-l1).

Hypothesis (single, concrete modification of vol-regime-sizer):
-----------------------------------------------------------------
The parent algorithm `vol-regime-sizer` gates OPEN orders by an
*absolute* short-term volatility ratio (fast EWM |Δmid| / slow EWM |Δmid|).
This signal is direction-blind: it treats a 5-tick rip *up* the same as
a 5-tick crash *down*. But the oracle strategy has a *directional* signal.
A BUY order issued into recent downward drift is the dangerous regime
(fading the burst — likely to print a loss). A BUY order issued into
recent upward drift is riding momentum and is more likely to print a win.
The parent algorithm currently skips both regimes at the same probability,
discarding wins as well as losses during vol bursts.

This algorithm replaces the *unsigned* vol-ratio gate with a *signed*
**directional-headwind** gate:

    ewm_drift  = EWM(Δmid)              # signed, fast halflife
    slow_vol   = EWM(|Δmid|)            # unsigned baseline, slow halflife
    headwind   = -side_sign × ewm_drift / max(slow_vol, eps)
                  (positive ⇔ recent mid drift opposes the order side)
    p_submit   = max(min_prob, exp(-sensitivity × max(0, headwind)))

When `headwind ≤ 0` (recent drift agrees with or is neutral to the order
side), `p_submit = 1.0`. The skip is concentrated on the entries where
recent micro-momentum is *against* the side — the regime where oracle
losses cluster within the parent algorithm's own logic.

The deterministic SHA-256(client_order_id) draw and the
reduce-only-always-submit branch carry over unchanged from the parent.

Constraints (enforced by this algorithm):
- top_of_book_only: untouched — every submitted order is forwarded
  unchanged. The fill model handles top-of-book pricing.
- participation_cap: untouched — parent orders are 1 contract and we
  never inflate.
- intraday_flat: reduce-only orders always submit unconditionally.
- quantity invariant: skip means zero child fills (≤ parent.quantity);
  submit means exactly the parent quantity (1 contract). No inflation.

Expected effect vs `vol-regime-sizer` (the comparison baseline):
- realized_pnl: ↑ — we stop discarding winning momentum-aligned entries.
- mean_slippage: 0 (zero-slippage fill model; no regression).
- trade_count: between `simple` (more) and `vol-regime-sizer` (fewer).
"""
from __future__ import annotations

import hashlib
import math
import struct

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class DirectionalHeadwindGateConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the directional-headwind probabilistic gate.

    Parameters
    ----------
    drift_halflife : int
        Half-life (ticks) of the signed-drift EWM used to estimate the
        direction of recent mid-price motion. Smaller = more reactive.
        Default 20 ticks.
    slow_halflife : int
        Half-life (ticks) of the |Δmid| EWM used as a unit-scale baseline
        for the headwind ratio. Default 120 ticks.
    sensitivity : float
        Decay rate from headwind to submission probability.
        p = max(min_prob, exp(-sensitivity * max(0, headwind))).
        Default 2.0 (matches parent's parameter scale).
    min_prob : float
        Floor on submission probability. Default 0.05.
    min_ticks : int
        Cold-start guard: submit at p=1.0 until this many quote ticks
        have been observed. Default 30.
    max_headwind : float
        Clip headwind before exponentiation to avoid outlier domination.
        Default 5.0.
    eps : float
        Small constant guarding the slow-vol denominator. Default 1e-12.
    """

    drift_halflife: int = 20
    slow_halflife: int = 120
    sensitivity: float = 2.0
    min_prob: float = 0.05
    min_ticks: int = 30
    max_headwind: float = 5.0
    eps: float = 1e-12


class DirectionalHeadwindGateAlgorithm(ExecAlgorithm):
    """Probabilistic OPEN gate keyed on signed micro-drift against order side."""

    def __init__(self, config: DirectionalHeadwindGateConfig) -> None:
        super().__init__(config=config)

        self._drift_alpha: float = 1.0 - math.exp(-math.log(2) / config.drift_halflife)
        self._slow_alpha: float = 1.0 - math.exp(-math.log(2) / config.slow_halflife)
        self._sensitivity: float = config.sensitivity
        self._min_prob: float = config.min_prob
        self._min_ticks: int = config.min_ticks
        self._max_headwind: float = config.max_headwind
        self._eps: float = config.eps

        # EWM state
        self._ewm_drift: float | None = None   # signed EWM of Δmid
        self._slow_vol: float | None = None    # EWM of |Δmid| (unsigned)
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
            f"DirectionalHeadwindGateAlgorithm started "
            f"(drift_alpha={self._drift_alpha:.4f}, slow_alpha={self._slow_alpha:.4f}, "
            f"sensitivity={self._sensitivity}, min_prob={self._min_prob}, "
            f"min_ticks={self._min_ticks})."
        )

    def on_reset(self) -> None:
        self._ewm_drift = None
        self._slow_vol = None
        self._prev_mid = None
        self._tick_count = 0
        self._subscribed.clear()
        self._submitted = 0
        self._skipped = 0

    # ------------------------------------------------------------------
    # Quote tick handler — update signed-drift + unsigned-vol estimators
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
            if self._ewm_drift is None:
                self._ewm_drift = delta
                self._slow_vol = abs_delta
            else:
                self._ewm_drift = (
                    self._drift_alpha * delta
                    + (1.0 - self._drift_alpha) * self._ewm_drift
                )
                self._slow_vol = (
                    self._slow_alpha * abs_delta
                    + (1.0 - self._slow_alpha) * self._slow_vol
                )

        self._prev_mid = mid
        self._tick_count += 1

    # ------------------------------------------------------------------
    # Submission probability
    # ------------------------------------------------------------------

    def _side_sign(self, order) -> int:
        """+1 for BUY, -1 for SELL. 0 if the side cannot be resolved."""
        try:
            if order.side == OrderSide.BUY:
                return 1
            if order.side == OrderSide.SELL:
                return -1
        except Exception:
            return 0
        return 0

    def _compute_submit_prob(self, side_sign: int) -> float:
        """Return submission probability in [min_prob, 1.0] for the given side."""
        if self._tick_count < self._min_ticks:
            return 1.0
        if self._ewm_drift is None or self._slow_vol is None:
            return 1.0
        if side_sign == 0:
            # Unknown side: be conservative and submit (preserves baseline behavior).
            return 1.0
        if self._slow_vol < self._eps:
            return 1.0

        # headwind > 0 ⇔ recent mid drift is against the order side.
        headwind = -side_sign * self._ewm_drift / self._slow_vol
        headwind = min(self._max_headwind, max(0.0, headwind))
        prob = math.exp(-self._sensitivity * headwind)
        prob = max(self._min_prob, prob)

        self.log.debug(
            f"side_sign={side_sign} drift={self._ewm_drift:.8f} "
            f"slow_vol={self._slow_vol:.8f} headwind={headwind:.4f} "
            f"p_submit={prob:.4f}"
        )
        return prob

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
            self.log.debug(
                f"Reduce-only {order.client_order_id}: submitting unconditionally."
            )
            self.submit_order(order)
            return

        side_sign = self._side_sign(order)
        p = self._compute_submit_prob(side_sign)

        if p >= 1.0 - 1e-9:
            self._submitted += 1
            self.log.debug(f"SUBMIT {order.client_order_id} (p=1.0, with-wind/cold).")
            self.submit_order(order)
            return

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
                f"SKIP {order.client_order_id} (p={p:.4f}, u={u:.4f}, "
                f"side_sign={side_sign}, headwind regime). "
                f"submitted={self._submitted} skipped={self._skipped}."
            )
            # Do NOT call submit_order — quantity invariant preserved.


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    drift_halflife: int = 20,
    slow_halflife: int = 120,
    sensitivity: float = 2.0,
    min_prob: float = 0.05,
    min_ticks: int = 30,
    max_headwind: float = 5.0,
    eps: float = 1e-12,
) -> DirectionalHeadwindGateAlgorithm:
    """Instantiate the directional-headwind probabilistic gate (sip-vrs-l1)."""
    config = DirectionalHeadwindGateConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        drift_halflife=drift_halflife,
        slow_halflife=slow_halflife,
        sensitivity=sensitivity,
        min_prob=min_prob,
        min_ticks=min_ticks,
        max_headwind=max_headwind,
        eps=eps,
    )
    return DirectionalHeadwindGateAlgorithm(config=config)
