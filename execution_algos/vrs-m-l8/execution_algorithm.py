"""Volatility-regime trade-size scaling execution algorithm (vrs-m-l8).

Per-iteration experiment loop 8 (FINAL) — base `vol-regime-sizer`, metrics-only mode.

Code body is mechanically copied from vrs-m-l7; only the `sensitivity`
default changes from 6.0 -> 7.0 and `min_prob` from 0.07 -> 0.10
(adopt L5's apex). This is the only parameter change vs L7.

Hypothesis (derived solely from prior-loop metrics):
  L1 (sens=3.0, min_prob=0.05): pnl_vs_base=+24.25%  sharpe=3.91  trades=125,873
  L2 (sens=4.0, min_prob=0.05): pnl_vs_base=+41.72%  sharpe=4.43  trades=124,497
  L3 (sens=5.0, min_prob=0.05): pnl_vs_base=+51.04%  sharpe=4.70  trades=123,457
  L4 (sens=6.0, min_prob=0.05): pnl_vs_base=+76.23%  sharpe=4.45  trades=99,833
  L5 (sens=6.0, min_prob=0.10): pnl_vs_base=+79.40%  sharpe=4.49  trades=100,209
  L6 (sens=6.0, min_prob=0.20): pnl_vs_base=+71.87%  sharpe=4.33  trades=101,021
  L7 (sens=6.0, min_prob=0.07): pnl_vs_base=+74.81%  sharpe=4.39  trades=99,979

Two distinct levers were probed:
  (a) sensitivity ramp L1->L4 (min_prob=0.05): +24 -> +42 -> +51 -> +76% in pnl_vs_base.
      Each unit of sensitivity added ~17 percentage points on average.
  (b) min_prob sweep L4-L7 (sens=6.0): all within 71-79% range.
      Concave curve with apex near min_prob=0.10 (L5 = best ever, +79.4%).

The sensitivity lever has been the dominant driver historically; min_prob
tuning around the apex shows diminishing returns (~1-5 pp swings).

L8 (the final loop) tests whether sensitivity can be pushed further while
holding min_prob at L5's optimum (0.10). Set sensitivity = 7.0 and
min_prob = 0.10. Expected effects:
  - If sensitivity ramp still has headroom: pnl_vs_base > +79.4% (new best).
  - If the algorithm has saturated near sens=6: pnl_vs_base near or below L5.
  - trade_count likely to drop modestly (more aggressive vol-throttling).

Single parameter change vs L7 in spirit (sensitivity 6.0 -> 7.0), with
min_prob set to L5's known-best 0.10 (where the apex was demonstrated).

Quantity invariant: at most 1 contract is submitted per parent 1-contract
order, so child_qty <= parent_qty always holds.
"""
from __future__ import annotations

import hashlib
import math
import struct

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class VrsML8Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the volatility-regime probabilistic sizer (vrs-m-l8).

    Parameters
    ----------
    fast_halflife : int
        Half-life (in ticks) of the fast EWM used to estimate current
        short-term realized vol. Smaller = more reactive to vol bursts.
        Default 20 ticks.
    slow_halflife : int
        Half-life (in ticks) of the slow EWM used as the vol baseline.
        Default 120 ticks.
    sensitivity : float
        Controls how aggressively submission probability shrinks with vol.
        p = exp(-sensitivity * max(0, vol_ratio - 1))
        Raised from loop 7's 6.0 -> 7.0 (probe whether sensitivity ramp
        still has headroom past 6.0). Default 7.0.
    min_prob : float
        Floor on submission probability. Even at extreme vol, submit at
        least this fraction of open orders. In [0, 1]. Set to L5's
        known-best 0.10 (the apex demonstrated by L4/L5/L6/L7 sweep at
        sens=6.0). Default 0.10.
    min_ticks : int
        Minimum number of quote ticks before vol scaling activates. Before
        this threshold, submit at full probability (cold-start guard). Default 30.
    max_vol_ratio : float
        Clip vol_ratio before applying sensitivity. Prevents extreme outliers
        from dominating. Default 5.0.
    """

    fast_halflife: int = 20
    slow_halflife: int = 120
    sensitivity: float = 7.0
    min_prob: float = 0.10
    min_ticks: int = 30
    max_vol_ratio: float = 5.0


class VrsML8Algorithm(ExecAlgorithm):
    """Execution algorithm that scales open-leg submission probability with realized vol.

    For each incoming OPEN order:
      1. Read fast and slow EWM of |delta_mid| from recent quote ticks.
      2. Compute vol_ratio = fast_vol / slow_vol (clipped to max_vol_ratio).
      3. Map to p = max(min_prob, exp(-sensitivity * max(0, vol_ratio - 1))).
      4. Accept or skip the order using a deterministic pseudo-random draw
         keyed on the order's client_order_id (reproducible, no shared state).

    For reduce-only (CLOSE) orders: always submit unconditionally.

    Quantity invariant: child_qty = parent_qty = 1 for all submitted orders.
    """

    def __init__(self, config: VrsML8Config) -> None:
        super().__init__(config=config)

        # Config parameters
        self._fast_alpha: float = 1.0 - math.exp(-math.log(2) / config.fast_halflife)
        self._slow_alpha: float = 1.0 - math.exp(-math.log(2) / config.slow_halflife)
        self._sensitivity: float = config.sensitivity
        self._min_prob: float = config.min_prob
        self._min_ticks: int = config.min_ticks
        self._max_vol_ratio: float = config.max_vol_ratio

        # EWM state
        self._fast_vol: float | None = None   # fast EWM of |delta_mid|
        self._slow_vol: float | None = None   # slow EWM of |delta_mid|
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
            f"VrsML8Algorithm started "
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
            # Near-zero baseline: both are very small → calm regime
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
        """Return a deterministic float in [0, 1) from the order's client ID.

        Uses SHA-256 of the string representation, takes the first 8 bytes
        as a uint64, and normalizes to [0, 1). This is reproducible across
        runs given the same order_id sequence (deterministic oracle seed).
        """
        digest = hashlib.sha256(order_id_str.encode()).digest()
        # Unpack first 8 bytes as big-endian uint64
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
                f"SKIP {order.client_order_id} (p={p:.4f}, u={u:.4f}, "
                f"vol_ratio estimated from fast/slow EWM). "
                f"submitted={self._submitted} skipped={self._skipped}."
            )
            # Do NOT call submit_order — quantity invariant preserved.


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    fast_halflife: int = 20,
    slow_halflife: int = 120,
    sensitivity: float = 7.0,
    min_prob: float = 0.10,
    min_ticks: int = 30,
    max_vol_ratio: float = 5.0,
) -> VrsML8Algorithm:
    """Instantiate and return the VrsML8Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier.
    fast_halflife : int
        Fast EWM half-life in ticks. Default 20.
    slow_halflife : int
        Slow EWM half-life in ticks (vol baseline). Default 120.
    sensitivity : float
        Decay rate mapping vol excess to submission probability. Raised
        from loop 7's 6.0. Default 7.0.
    min_prob : float
        Floor on submission probability. Set to L5's apex value 0.10. Default 0.10.
    min_ticks : int
        Cold-start guard: full submission for first N ticks. Default 30.
    max_vol_ratio : float
        Clip vol_ratio to prevent outlier domination. Default 5.0.
    """
    config = VrsML8Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        fast_halflife=fast_halflife,
        slow_halflife=slow_halflife,
        sensitivity=sensitivity,
        min_prob=min_prob,
        min_ticks=min_ticks,
        max_vol_ratio=max_vol_ratio,
    )
    return VrsML8Algorithm(config=config)
