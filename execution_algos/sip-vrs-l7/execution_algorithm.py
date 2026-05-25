"""Streak-PnL skip layered on sip-vrs-l5 (sip-vrs-l7).

Hypothesis (Propose-Audit-Falsify-Commit, prompt-l5.md):
--------------------------------------------------------
The running-best `sip-vrs-l5` gates OPEN orders by
`p_submit = vol_p × wide_spread_suppress`. Neither layer has
visibility into recent realized pnl. Tier-A audit across all 11
available train dates finds that orders fired during an adverse pnl
streak (rolling mean of last M=10 closed positions < 0) carry a
mean pnl that is, on every one of 11 train dates, lower than orders
fired during a non-negative streak. The pre-stated threshold
δ ≤ -$0.03/contract is met on 5/11 dates (not the rule's 8/11), so
C2 is FALSIFIED at the SURVIVED bar. The same-sign-across-all-11
evidence is the strongest of the three Tier-A candidates and is
selected per step-5 "weakest violation" branch.

Modification (single, layered):
-------------------------------
1. Compute `vol_p` exactly as the parent (vol-regime-sizer) does.
2. Apply the L5 wide-spread layer: if cached top-of-book spread
   exceeds `wide_spread_threshold * tick_size`, multiply by
   `wide_spread_suppress` (default 0.0 = hard skip).
3. **NEW**: maintain a deque of the last M=10 closed-position
   realized pnls (this algorithm's own closes). If the deque is
   full (size = M) AND mean(deque) < `streak_threshold`, multiply
   `p_submit` further by `streak_suppress` (default 0.0 = hard skip).
4. Run the parent's deterministic SHA-256 accept/skip draw at the
   final probability.

Reduce-only orders always submit unconditionally (intraday_flat).
Cold-start (vol-regime), narrow-spread, deque-not-full short-circuit
all return parent behaviour unchanged.

Constraints:
- top_of_book_only: untouched — every submitted order routes through
  the same path as the parent.
- participation_cap: untouched — parent orders are 1 contract.
- intraday_flat: reduce-only orders always submit unconditionally.
- quantity invariant: skip → 0 child fills; submit → exactly parent
  quantity (1 contract). No inflation.

Expected effect vs `vol-regime-sizer`:
- realized_pnl: ↑ — removes adverse-streak orders (~$0.04/contract
  expected loss reduction on the gated arrivals).
- mean_slippage: 0 (zero-slippage fill model).
- sharpe_ratio: ↑ (narrower daily distribution).
- trade_count: ↓ moderately.

Expected effect vs `sip-vrs-l5` (running-best, gate comparison):
ambiguous. The streak gate may overlap with the wide-spread gate
(both fire in similar adverse-cost regimes). The honesty notes in
NOTES.md flag this as the dominant mechanism risk.
"""
from __future__ import annotations

import hashlib
import math
import struct
from collections import deque
from decimal import Decimal

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


# MES tick size in price units (quarter-point).
MES_TICK_SIZE: float = 0.25


class StreakPnlSkipConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the streak-pnl skip layered on sip-vrs-l5.

    Parameters
    ----------
    fast_halflife : int
        Half-life of fast EWM in ticks. Inherited from parent. Default 20.
    slow_halflife : int
        Half-life of slow EWM in ticks. Inherited from parent. Default 120.
    sensitivity : float
        Decay rate. Inherited from parent. Default 2.0.
    min_prob : float
        Floor on submission probability. Inherited from parent. Default 0.05.
    min_ticks : int
        Cold-start guard. Inherited from parent. Default 30.
    max_vol_ratio : float
        Clip vol_ratio. Inherited from parent. Default 5.0.
    wide_spread_threshold : float
        Multiple of `tick_size`. Inherited unchanged from L5. Default 1.5.
    wide_spread_suppress : float
        Multiplier on `p_submit` in wide-spread regime. Inherited from L5.
        Default 0.0 (hard skip).
    tick_size : float
        MES tick size. Default 0.25.
    streak_M : int
        Number of last closed positions to average for the streak signal.
        Default 10 (the falsification window).
    streak_threshold : float
        Sign threshold on the rolling mean. If mean < this, the streak
        layer fires. Default 0.0 (regime-relative by construction —
        a sign test on a centered rolling mean).
    streak_suppress : float
        Multiplier on `p_submit` when the streak layer fires. Default
        0.0 (hard skip). Derived from step-4 statistic: average per-date
        delta ≈ -$0.042/contract (negative ⇒ adverse). Principled rule:
        rational participation in a negative-EV regime is 0.
    """

    fast_halflife: int = 20
    slow_halflife: int = 120
    sensitivity: float = 2.0
    min_prob: float = 0.05
    min_ticks: int = 30
    max_vol_ratio: float = 5.0
    wide_spread_threshold: float = 1.5
    wide_spread_suppress: float = 0.0
    tick_size: float = MES_TICK_SIZE
    streak_M: int = 10
    streak_threshold: float = 0.0
    streak_suppress: float = 0.0


class StreakPnlSkipAlgorithm(ExecAlgorithm):
    """Parent vol-regime + L5 wide-spread skip + rolling-pnl streak gate.

    For each incoming OPEN order:
      1. Compute parent's vol-regime p_submit (unchanged formula).
      2. If cached spread > wide_spread_threshold * tick_size:
         p *= wide_spread_suppress.
      3. NEW: if streak deque is full (M closes) AND its mean <
         streak_threshold: p *= streak_suppress.
      4. Deterministic SHA-256 accept/skip draw.

    Reduce-only orders: always submit unconditionally.
    Quantity invariant: child_qty = parent_qty = 1.
    """

    def __init__(self, config: StreakPnlSkipConfig) -> None:
        super().__init__(config=config)

        # Parent EWM parameters
        self._fast_alpha: float = 1.0 - math.exp(-math.log(2) / config.fast_halflife)
        self._slow_alpha: float = 1.0 - math.exp(-math.log(2) / config.slow_halflife)
        self._sensitivity: float = config.sensitivity
        self._min_prob: float = config.min_prob
        self._min_ticks: int = config.min_ticks
        self._max_vol_ratio: float = config.max_vol_ratio

        # L5 wide-spread layer
        self._wide_spread_abs_threshold: float = (
            config.wide_spread_threshold * config.tick_size
        )
        self._wide_spread_suppress: float = config.wide_spread_suppress

        # L7 streak-pnl layer
        self._streak_M: int = config.streak_M
        self._streak_threshold: float = config.streak_threshold
        self._streak_suppress: float = config.streak_suppress
        self._pnl_deque: deque[float] = deque(maxlen=self._streak_M)
        self._seen_position_ids: set[str] = set()

        # Parent EWM state
        self._fast_vol: float | None = None
        self._slow_vol: float | None = None
        self._prev_mid: float | None = None
        self._tick_count: int = 0

        # Top-of-book cache
        self._last_bid: float | None = None
        self._last_ask: float | None = None

        # Subscription tracking
        self._subscribed: set[str] = set()

        # Diagnostics
        self._submitted: int = 0
        self._skipped_vol: int = 0
        self._skipped_spread: int = 0
        self._skipped_streak: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"StreakPnlSkipAlgorithm started "
            f"(fast_alpha={self._fast_alpha:.4f}, slow_alpha={self._slow_alpha:.4f}, "
            f"sensitivity={self._sensitivity}, min_prob={self._min_prob}, "
            f"min_ticks={self._min_ticks}, "
            f"wide_spread_abs_threshold={self._wide_spread_abs_threshold:.4f}, "
            f"wide_spread_suppress={self._wide_spread_suppress:.4f}, "
            f"streak_M={self._streak_M}, streak_threshold={self._streak_threshold}, "
            f"streak_suppress={self._streak_suppress:.4f})."
        )

    def on_reset(self) -> None:
        self._fast_vol = None
        self._slow_vol = None
        self._prev_mid = None
        self._tick_count = 0
        self._last_bid = None
        self._last_ask = None
        self._subscribed.clear()
        self._pnl_deque.clear()
        self._seen_position_ids.clear()
        self._submitted = 0
        self._skipped_vol = 0
        self._skipped_spread = 0
        self._skipped_streak = 0

    # ------------------------------------------------------------------
    # Quote tick handler — update EWMs + cache top-of-book
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

        self._last_bid = bid
        self._last_ask = ask

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
    # Position close handler — update streak deque
    # ------------------------------------------------------------------

    def on_position_closed(self, event) -> None:
        """Track this algorithm's own closed-position realized pnl.

        Nautilus's PositionClosed event carries `realized_pnl` (a Money).
        We append the float value to the deque. We deduplicate via
        `position_id` because Nautilus can republish events in the
        backtester.
        """
        try:
            pos_id = str(event.position_id)
        except Exception:
            return
        if pos_id in self._seen_position_ids:
            return
        self._seen_position_ids.add(pos_id)

        try:
            pnl = float(str(event.realized_pnl).split()[0])
        except Exception:
            return

        self._pnl_deque.append(pnl)

    # ------------------------------------------------------------------
    # Parent vol-regime probability (unchanged)
    # ------------------------------------------------------------------

    def _compute_parent_prob(self) -> float:
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
    # Wide-spread guard (L5)
    # ------------------------------------------------------------------

    def _is_wide_spread(self) -> bool:
        if self._last_bid is None or self._last_ask is None:
            return False
        spread = self._last_ask - self._last_bid
        return spread > self._wide_spread_abs_threshold

    # ------------------------------------------------------------------
    # Streak guard (L7)
    # ------------------------------------------------------------------

    def _is_adverse_streak(self) -> bool:
        """True iff the deque is full AND its mean is below threshold.

        Before M closes have been observed, the gate does not fire
        (cold-start equivalent for this layer).
        """
        if len(self._pnl_deque) < self._streak_M:
            return False
        mean_pnl = sum(self._pnl_deque) / self._streak_M
        return mean_pnl < self._streak_threshold

    # ------------------------------------------------------------------
    # Deterministic pseudo-random draw (inherited unchanged)
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

        # Reduce-only orders: always submit (intraday_flat)
        if order.is_reduce_only:
            self.submit_order(order)
            return

        # Layer 1: parent vol-regime probability
        p = self._compute_parent_prob()

        # Layer 2: wide-spread skip (L5)
        if self._is_wide_spread():
            p = p * self._wide_spread_suppress

        # Layer 3: streak-pnl skip (L7, NEW)
        if self._is_adverse_streak():
            p_before = p
            p = p * self._streak_suppress
            # Track if streak was the binding skip layer
            self._streak_was_binding = (p_before > p + 1e-12)
        else:
            self._streak_was_binding = False

        # Fast path: full submission
        if p >= 1.0 - 1e-9:
            self._submitted += 1
            self.submit_order(order)
            return

        # Hard-skip fast path
        if p <= 1e-12:
            if self._streak_was_binding:
                self._skipped_streak += 1
                reason = "streak"
            elif self._is_wide_spread():
                self._skipped_spread += 1
                reason = "spread"
            else:
                self._skipped_vol += 1
                reason = "vol"
            self.log.info(
                f"SKIP {order.client_order_id} (p=0, reason={reason}). "
                f"submitted={self._submitted} skipped_vol={self._skipped_vol} "
                f"skipped_spread={self._skipped_spread} "
                f"skipped_streak={self._skipped_streak}."
            )
            return

        # Deterministic draw
        u = self._order_uniform(str(order.client_order_id))
        if u < p:
            self._submitted += 1
            self.submit_order(order)
        else:
            # Attribution: streak > spread > vol (in reverse order of
            # being newest layer)
            if self._streak_was_binding:
                self._skipped_streak += 1
                reason = "streak"
            elif self._is_wide_spread():
                self._skipped_spread += 1
                reason = "spread"
            else:
                self._skipped_vol += 1
                reason = "vol"
            self.log.info(
                f"SKIP {order.client_order_id} "
                f"(p={p:.4f}, u={u:.4f}, reason={reason}). "
                f"submitted={self._submitted} skipped_vol={self._skipped_vol} "
                f"skipped_spread={self._skipped_spread} "
                f"skipped_streak={self._skipped_streak}."
            )


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    fast_halflife: int = 20,
    slow_halflife: int = 120,
    sensitivity: float = 2.0,
    min_prob: float = 0.05,
    min_ticks: int = 30,
    max_vol_ratio: float = 5.0,
    wide_spread_threshold: float = 1.5,
    wide_spread_suppress: float = 0.0,
    tick_size: float = MES_TICK_SIZE,
    streak_M: int = 10,
    streak_threshold: float = 0.0,
    streak_suppress: float = 0.0,
) -> StreakPnlSkipAlgorithm:
    """Instantiate the streak-pnl skip layered on sip-vrs-l5 (sip-vrs-l7)."""
    config = StreakPnlSkipConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        fast_halflife=fast_halflife,
        slow_halflife=slow_halflife,
        sensitivity=sensitivity,
        min_prob=min_prob,
        min_ticks=min_ticks,
        max_vol_ratio=max_vol_ratio,
        wide_spread_threshold=wide_spread_threshold,
        wide_spread_suppress=wide_spread_suppress,
        tick_size=tick_size,
        streak_M=streak_M,
        streak_threshold=streak_threshold,
        streak_suppress=streak_suppress,
    )
    return StreakPnlSkipAlgorithm(config=config)
