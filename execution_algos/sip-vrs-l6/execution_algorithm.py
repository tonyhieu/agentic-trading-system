"""Round-number proximity skip layered on vol-regime-sizer (sip-vrs-l6).

Hypothesis (Propose-Audit-Falsify-Commit method, prompt-l5.md):
---------------------------------------------------------------
The parent `vol-regime-sizer` gates OPEN orders on an unsigned vol_ratio
and is otherwise price-agnostic. The step-4 falsification test across all
11 available train dates (20260319 OOM'd in the parent re-run) found:

  per-date `mean_pnl(round_dist >= 1 tick) - mean_pnl(round_dist < 1 tick)`
  on parent's submitted opens:

    20260308: +0.165 (n_near=18)
    20260309: +0.118 (n_near=197)
    20260310: +0.171 (n_near=162)
    20260311: -0.367 (n_near=157)
    20260312: +0.005 (n_near=425)
    20260313: +0.001 (n_near=749)
    20260315: +0.054 (n_near=191)
    20260316: -0.002 (n_near=1948)
    20260317:  0.000 (n_near=2059)
    20260318: +0.005 (n_near=2004)
    20260320: -0.005 (n_near=1879)

  Mean = +0.013, n_pos=7/11. Threshold mean>=0.04 AND n_pos>=9 FAILED.

All three candidate weaknesses tested in loop 6 (side asymmetry, range-
position, round-number) were FALSIFIED. Per method step 5 #3 (zero
survived, pick smallest violation), C3 (round-number) was selected as
weakest-violation. The expected lift is small to near-zero.

Modification (single, layered, honest about being a weakest-pick):
------------------------------------------------------------------
1. Compute `parent_p_submit` exactly as the parent does (unchanged).
2. Read the most recent cached top-of-book quote and compute mid.
   If `|mid - round(mid / 5) * 5| < 1 tick (= 0.25 points)`:
       multiply `parent_p_submit` by `round_suppress` (default 0.0).
3. Else: leave `parent_p_submit` unchanged.
4. Run the parent's deterministic SHA-256 accept/skip draw at the
   (possibly suppressed) probability.

Reduce-only bypass, cold-start guard, `min_prob` floor, and the quantity
invariant are inherited unchanged from the parent.

Constraints (enforced by this algorithm):
- top_of_book_only: untouched — every submitted order routes through
  the same path as the parent.
- participation_cap: untouched — parent orders are 1 contract.
- intraday_flat: reduce-only orders always submit unconditionally.
- quantity invariant: skip -> 0 child fills; submit -> exactly parent
  quantity (1 contract). No inflation.

Expected effect vs `vol-regime-sizer`:
- realized_pnl: ~0 to slightly positive (falsification mean +0.013).
- mean_slippage: 0 (zero-slippage fill model).
- trade_count: down ~7-10% (binding feature fires on 5-10% of arrivals
  on every train date — HOMOGENEOUS audit verdict).
- sharpe_ratio: ambiguous; small effect either way.
"""
from __future__ import annotations

import hashlib
import math
import struct

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


# MES tick size in price units. Constant of the futures contract; not a free
# parameter.
MES_TICK_SIZE: float = 0.25


class RoundNumberSkipConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the round-number skip layered on vol-regime-sizer.

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
    round_level_points : float
        Spacing of the round-number grid in price points. MES is quoted
        in 0.25 ticks; the natural round-number grid is 5 points (e.g.
        5800.00, 5805.00 — every 20 ticks). Default 5.0.
    round_threshold_ticks : float
        If the most-recent mid is strictly within this many ticks of the
        nearest round level (`|mid - nearest_round| < threshold * tick_size`),
        the round-number skip layer applies. Default 1.0 (skip when mid is
        within 1 tick of a 5-point round level). Derived from the step-4
        bucket boundary; matches the binding-feature distribution from
        the step-3 audit (5-10% activation per date).
    round_suppress : float
        Multiplier applied to parent's `p_submit` when the round-number
        layer triggers. Default 0.0 (hard skip). Principled choice: the
        falsification verdict was directionally positive (mean +0.013)
        but below threshold; a partial-suppress value is a free parameter.
        Hard skip removes the regime entirely, mirroring the parent L5's
        wide-spread layer.
    tick_size : float
        MES tick size in price units. Default 0.25 (constant).
    """

    fast_halflife: int = 20
    slow_halflife: int = 120
    sensitivity: float = 2.0
    min_prob: float = 0.05
    min_ticks: int = 30
    max_vol_ratio: float = 5.0
    round_level_points: float = 5.0
    round_threshold_ticks: float = 1.0
    round_suppress: float = 0.0
    tick_size: float = MES_TICK_SIZE


class RoundNumberSkipAlgorithm(ExecAlgorithm):
    """Parent vol-regime-sizer with a layered round-number skip on OPENs.

    For each incoming OPEN order:
      1. Compute parent's vol-regime p_submit (unchanged formula).
      2. If cached mid sits within `round_threshold_ticks * tick_size` of
         the nearest `round_level_points` multiple:
             p_submit *= round_suppress.
      3. Else: leave p_submit unchanged.
      4. Run the deterministic SHA-256 accept/skip draw on the order.

    For reduce-only (CLOSE) orders: always submit unconditionally.

    Quantity invariant: child_qty = parent_qty = 1 for all submitted orders.
    """

    def __init__(self, config: RoundNumberSkipConfig) -> None:
        super().__init__(config=config)

        # Parent EWM parameters
        self._fast_alpha: float = 1.0 - math.exp(-math.log(2) / config.fast_halflife)
        self._slow_alpha: float = 1.0 - math.exp(-math.log(2) / config.slow_halflife)
        self._sensitivity: float = config.sensitivity
        self._min_prob: float = config.min_prob
        self._min_ticks: int = config.min_ticks
        self._max_vol_ratio: float = config.max_vol_ratio

        # Round-number layer
        self._round_level_points: float = config.round_level_points
        self._round_abs_threshold: float = (
            config.round_threshold_ticks * config.tick_size
        )
        self._round_suppress: float = config.round_suppress

        # Parent EWM state
        self._fast_vol: float | None = None
        self._slow_vol: float | None = None
        self._prev_mid: float | None = None
        self._tick_count: int = 0

        # Top-of-book cache (filled on every quote tick)
        self._last_bid: float | None = None
        self._last_ask: float | None = None

        # Subscription tracking
        self._subscribed: set[str] = set()

        # Diagnostic counters
        self._submitted: int = 0
        self._skipped_vol: int = 0      # skipped by parent's vol gate
        self._skipped_round: int = 0    # skipped by the round-number layer

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"RoundNumberSkipAlgorithm started "
            f"(fast_alpha={self._fast_alpha:.4f}, slow_alpha={self._slow_alpha:.4f}, "
            f"sensitivity={self._sensitivity}, min_prob={self._min_prob}, "
            f"min_ticks={self._min_ticks}, "
            f"round_level_points={self._round_level_points}, "
            f"round_abs_threshold={self._round_abs_threshold:.4f}, "
            f"round_suppress={self._round_suppress:.4f})."
        )

    def on_reset(self) -> None:
        self._fast_vol = None
        self._slow_vol = None
        self._prev_mid = None
        self._tick_count = 0
        self._last_bid = None
        self._last_ask = None
        self._subscribed.clear()
        self._submitted = 0
        self._skipped_vol = 0
        self._skipped_round = 0

    # ------------------------------------------------------------------
    # Quote tick handler — update EWM vol estimates + cache top-of-book
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    def on_quote_tick(self, tick) -> None:
        """Update EWM vol estimates and cache the latest top-of-book quote."""
        try:
            bid = float(str(tick.bid_price))
            ask = float(str(tick.ask_price))
            mid = (bid + ask) / 2.0
        except Exception:
            return

        # Cache the latest top-of-book for the round-number layer.
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
    # Round-number guard
    # ------------------------------------------------------------------

    def _is_near_round(self) -> bool:
        """True iff the cached mid is within `round_abs_threshold` of the
        nearest `round_level_points` multiple."""
        if self._last_bid is None or self._last_ask is None:
            # No quote observed yet — be conservative and treat as not-near.
            return False
        mid = (self._last_bid + self._last_ask) / 2.0
        nearest_round = round(mid / self._round_level_points) * self._round_level_points
        return abs(mid - nearest_round) < self._round_abs_threshold

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip, parent + round-number layers combined."""
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

        # Round-number layer: multiply probability when mid is near a round level.
        if self._is_near_round():
            p_after_round = p * self._round_suppress
        else:
            p_after_round = p

        # Fast path: p == 1.0 (calm regime, cold start, not near round)
        if p_after_round >= 1.0 - 1e-9:
            self._submitted += 1
            self.log.debug(
                f"SUBMIT {order.client_order_id} (p=1.0, no-round/calm/cold)."
            )
            self.submit_order(order)
            return

        # Hard-skip fast path: probability collapsed to zero by round layer
        if p_after_round <= 1e-12:
            self._skipped_round += 1
            self.log.info(
                f"SKIP {order.client_order_id} (near round, p_after_round≈0). "
                f"submitted={self._submitted} "
                f"skipped_vol={self._skipped_vol} skipped_round={self._skipped_round}."
            )
            return

        # Deterministic draw from order ID
        u = self._order_uniform(str(order.client_order_id))

        if u < p_after_round:
            self._submitted += 1
            self.log.debug(
                f"SUBMIT {order.client_order_id} "
                f"(p_after_round={p_after_round:.4f}, u={u:.4f})."
            )
            self.submit_order(order)
        else:
            # Attribute the skip to whichever layer was binding.
            if p_after_round < p - 1e-12:
                self._skipped_round += 1
                reason = "round"
            else:
                self._skipped_vol += 1
                reason = "vol"
            self.log.info(
                f"SKIP {order.client_order_id} "
                f"(p_after_round={p_after_round:.4f}, u={u:.4f}, reason={reason}). "
                f"submitted={self._submitted} "
                f"skipped_vol={self._skipped_vol} skipped_round={self._skipped_round}."
            )


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    fast_halflife: int = 20,
    slow_halflife: int = 120,
    sensitivity: float = 2.0,
    min_prob: float = 0.05,
    min_ticks: int = 30,
    max_vol_ratio: float = 5.0,
    round_level_points: float = 5.0,
    round_threshold_ticks: float = 1.0,
    round_suppress: float = 0.0,
    tick_size: float = MES_TICK_SIZE,
) -> RoundNumberSkipAlgorithm:
    """Instantiate the round-number skip layered on vol-regime-sizer (sip-vrs-l6)."""
    config = RoundNumberSkipConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        fast_halflife=fast_halflife,
        slow_halflife=slow_halflife,
        sensitivity=sensitivity,
        min_prob=min_prob,
        min_ticks=min_ticks,
        max_vol_ratio=max_vol_ratio,
        round_level_points=round_level_points,
        round_threshold_ticks=round_threshold_ticks,
        round_suppress=round_suppress,
        tick_size=tick_size,
    )
    return RoundNumberSkipAlgorithm(config=config)
