"""Wide-spread skip layered on top of vol-regime-sizer (sip-vrs-l5).

Hypothesis (Propose-Falsify-Commit method, prompt-l1.md):
---------------------------------------------------------
The parent `vol-regime-sizer` gates OPEN orders by an unsigned vol_ratio
(fast EWM(|Δmid|) / slow EWM(|Δmid|)) and has no visibility into the
bid-ask spread at order-arrival time. The step-4 falsification test on
parent CSVs for 20260316 and 20260318 found Pearson corr(is_bps,
realized_pnl) = −0.153 and −0.171 respectively (same-sign on both
dates, both ≤ −0.10), and per-bucket mean pnl by half-spread:

  20260316: 1-tick spread (half_spread ≤ 0.125, n=17,590): mean pnl −$0.010
            wider spread (half_spread > 0.125, n=1,618):   mean pnl −$0.131
  20260318: 1-tick spread (n=19,944): mean pnl +$0.012
            wider spread (n=969):     mean pnl −$0.053

Wide-spread opens are 5−8% of submitted orders but carry 5−10× more
negative mean pnl than 1-tick opens. The post-fill `is_bps` cannot be
known at order arrival; the proxy is the live top-of-book spread
captured from the same quote-tick stream the parent already consumes.

Modification (single, layered):
-------------------------------
1. Compute `parent_p_submit` exactly as the parent does (unchanged).
2. Read the most recent cached (bid, ask) from on_quote_tick.
   If `ask − bid > wide_spread_threshold * tick_size`:
       multiply `parent_p_submit` by `wide_spread_suppress` (default 0.0).
3. Else: leave `parent_p_submit` unchanged.
4. Run the parent's deterministic SHA-256 accept/skip draw at the
   (possibly suppressed) probability.

This is a guard *layered on top of* the parent — it only further
suppresses; it never re-admits an order the parent would skip. The
reduce-only bypass, cold-start guard, `min_prob` floor, and the
quantity invariant are inherited unchanged from the parent.

Constraints (enforced by this algorithm):
- top_of_book_only: untouched — every submitted order routes through
  the same path as the parent.
- participation_cap: untouched — parent orders are 1 contract.
- intraday_flat: reduce-only orders always submit unconditionally.
- quantity invariant: skip → 0 child fills; submit → exactly parent
  quantity (1 contract). No inflation.

Expected effect vs `vol-regime-sizer`:
- realized_pnl: ↑ — removes wide-spread loss tail (~5−8% of opens
  carrying −$0.05 to −$0.16 mean pnl).
- mean_slippage: 0 (zero-slippage fill model).
- sharpe_ratio: ↑ (tighter daily pnl distribution).
- trade_count: ↓ slightly (5−8% additional skips on top of parent).
- win_rate: ↑ slightly (removed fills are loss-heavy).
"""
from __future__ import annotations

import hashlib
import math
import struct

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


# MES tick size in price units (quarter-point). Constant of the futures
# contract; not a free parameter.
MES_TICK_SIZE: float = 0.25


class WideSpreadSkipConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the wide-spread skip layered on vol-regime-sizer.

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
    wide_spread_threshold : float
        Multiple of `tick_size`. If the cached top-of-book spread
        `ask − bid` exceeds `wide_spread_threshold * tick_size`, the
        wide-spread suppress kicks in. Default 1.5 (i.e., trigger when
        the spread is strictly wider than 1 tick). Derived from step-4
        bucket statistic: 1-tick spreads are near break-even on both
        test dates; 2-tick spreads have strongly negative mean pnl.
    wide_spread_suppress : float
        Multiplier applied to `parent_p_submit` when the spread is wide.
        Default 0.0 (hard skip). Derived from step-4 statistic: in the
        wide-spread regime, expected pnl per fill is negative on both
        test dates, so rational participation rate is 0.
    tick_size : float
        MES tick size in price units. Default 0.25 (constant).
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


class WideSpreadSkipAlgorithm(ExecAlgorithm):
    """Parent vol-regime-sizer with a layered wide-spread skip on OPENs.

    For each incoming OPEN order:
      1. Compute parent's vol-regime p_submit (unchanged formula).
      2. If cached top-of-book spread > wide_spread_threshold * tick_size:
         p_submit *= wide_spread_suppress.
      3. Else: leave p_submit unchanged.
      4. Run the deterministic SHA-256 accept/skip draw on the order.

    For reduce-only (CLOSE) orders: always submit unconditionally.

    Quantity invariant: child_qty = parent_qty = 1 for all submitted orders.
    """

    def __init__(self, config: WideSpreadSkipConfig) -> None:
        super().__init__(config=config)

        # Parent EWM parameters
        self._fast_alpha: float = 1.0 - math.exp(-math.log(2) / config.fast_halflife)
        self._slow_alpha: float = 1.0 - math.exp(-math.log(2) / config.slow_halflife)
        self._sensitivity: float = config.sensitivity
        self._min_prob: float = config.min_prob
        self._min_ticks: int = config.min_ticks
        self._max_vol_ratio: float = config.max_vol_ratio

        # Wide-spread layer
        self._wide_spread_abs_threshold: float = (
            config.wide_spread_threshold * config.tick_size
        )
        self._wide_spread_suppress: float = config.wide_spread_suppress

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
        self._skipped_spread: int = 0   # skipped by the wide-spread layer

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"WideSpreadSkipAlgorithm started "
            f"(fast_alpha={self._fast_alpha:.4f}, slow_alpha={self._slow_alpha:.4f}, "
            f"sensitivity={self._sensitivity}, min_prob={self._min_prob}, "
            f"min_ticks={self._min_ticks}, "
            f"wide_spread_abs_threshold={self._wide_spread_abs_threshold:.4f}, "
            f"wide_spread_suppress={self._wide_spread_suppress:.4f})."
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
        self._skipped_spread = 0

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

        # Cache the latest top-of-book for the wide-spread layer
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
        """Return parent's vol-regime probability in [min_prob, 1.0].

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
    # Wide-spread guard
    # ------------------------------------------------------------------

    def _is_wide_spread(self) -> bool:
        """True iff the cached top-of-book spread exceeds the threshold."""
        if self._last_bid is None or self._last_ask is None:
            # No quote observed yet — be conservative and treat as narrow.
            # (Cold-start orders should still flow under the parent's gate.)
            return False
        spread = self._last_ask - self._last_bid
        return spread > self._wide_spread_abs_threshold

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip, parent + wide-spread layers combined."""
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

        # Wide-spread layer: multiply probability when the cached spread is wide
        if self._is_wide_spread():
            p_after_spread = p * self._wide_spread_suppress
        else:
            p_after_spread = p

        # Fast path: p == 1.0 (calm regime, cold start, narrow spread)
        if p_after_spread >= 1.0 - 1e-9:
            self._submitted += 1
            self.log.debug(
                f"SUBMIT {order.client_order_id} (p=1.0, narrow/calm/cold)."
            )
            self.submit_order(order)
            return

        # Hard-skip fast path: probability collapsed to zero by spread layer
        if p_after_spread <= 1e-12:
            self._skipped_spread += 1
            self.log.info(
                f"SKIP {order.client_order_id} (wide spread, p_after_spread≈0). "
                f"submitted={self._submitted} "
                f"skipped_vol={self._skipped_vol} skipped_spread={self._skipped_spread}."
            )
            return

        # Deterministic draw from order ID
        u = self._order_uniform(str(order.client_order_id))

        if u < p_after_spread:
            self._submitted += 1
            self.log.debug(
                f"SUBMIT {order.client_order_id} "
                f"(p_after_spread={p_after_spread:.4f}, u={u:.4f})."
            )
            self.submit_order(order)
        else:
            # Attribute the skip to whichever layer was binding. If the
            # spread layer reduced p (p_after_spread < p), call it a
            # spread skip; otherwise it's a vol skip.
            if p_after_spread < p - 1e-12:
                self._skipped_spread += 1
                reason = "spread"
            else:
                self._skipped_vol += 1
                reason = "vol"
            self.log.info(
                f"SKIP {order.client_order_id} "
                f"(p_after_spread={p_after_spread:.4f}, u={u:.4f}, reason={reason}). "
                f"submitted={self._submitted} "
                f"skipped_vol={self._skipped_vol} skipped_spread={self._skipped_spread}."
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
) -> WideSpreadSkipAlgorithm:
    """Instantiate the wide-spread skip layered on vol-regime-sizer (sip-vrs-l5)."""
    config = WideSpreadSkipConfig(
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
    )
    return WideSpreadSkipAlgorithm(config=config)
