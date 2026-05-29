"""Volatility-regime trade-size scaling execution algorithm (vrs-m-l5).

Per-iteration experiment loop 5 — base `vol-regime-sizer`, metrics-only mode.

Code body is mechanically copied from vrs-m-l4; only the `min_prob`
default is bumped from 0.05 -> 0.10. This is the only parameter change.

Hypothesis (derived solely from prior-loop metrics):
  L1 (sens=3.0, min_prob=0.05): pnl_vs_base=+27.39%  sharpe=3.91  trades=125,873
  L2 (sens=4.0, min_prob=0.05): pnl_vs_base=+50.47%  sharpe=4.43  trades=124,497
  L3 (sens=5.0, min_prob=0.05): pnl_vs_base=+60.31%  sharpe=4.70  trades=123,457
  L4 (sens=6.0, min_prob=0.05): pnl_vs_base=+76.23%  sharpe=4.45  trades= 99,833

Per-step deltas: L1→L2 (+23.08pp PnL, +0.52 Sharpe, −1,376 trades);
L2→L3 (+9.84pp, +0.27, −1,040); L3→L4 (+15.92pp, −0.25, −23,624).

L3→L4 is the first step where Sharpe DROPPED while PnL still rose, and
trade-count shrank ~23× more than every prior step. That signals
sensitivity=6.0 is now filtering mid-vol-ratio mass rather than just the
extreme tail — PnL growth is being purchased with higher per-day variance.
Continuing to push `sensitivity` is a 50/50 bet at this point.

The next single-parameter lever is `min_prob`, the floor of the
submission probability curve `p = max(min_prob, exp(-sens * excess))`.
Raising it from 0.05 → 0.10 forces the algorithm to keep participating
at a higher minimum rate even when the vol-regime decay would otherwise
collapse `p` toward zero. Since the L3→L4 Sharpe loss came with a
massive trade-count drop, restoring some of those filtered submissions
(at the tail end of the vol distribution) should reduce per-day variance
and recover Sharpe. The trade-off: PnL may give back some of L4's +15.92pp
gain because we'll re-admit some of the high-vol-regime orders L4
filtered out. The test isolates whether L4's Sharpe inversion is
recoverable via the floor without touching the decay rate.

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


class VrsML5Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the volatility-regime probabilistic sizer (vrs-m-l5).

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
        Held at loop 4's 6.0. Default 6.0.
    min_prob : float
        Floor on submission probability. Even at extreme vol, submit at
        least this fraction of open orders. In [0, 1]. Raised from loop 4's
        0.05 -> 0.10. Default 0.10.
    min_ticks : int
        Minimum number of quote ticks before vol scaling activates. Before
        this threshold, submit at full probability (cold-start guard). Default 30.
    max_vol_ratio : float
        Clip vol_ratio before applying sensitivity. Prevents extreme outliers
        from dominating. Default 5.0.
    """

    fast_halflife: int = 20
    slow_halflife: int = 120
    sensitivity: float = 6.0
    min_prob: float = 0.10
    min_ticks: int = 30
    max_vol_ratio: float = 5.0


class VrsML5Algorithm(ExecAlgorithm):
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

    def __init__(self, config: VrsML5Config) -> None:
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
            f"VrsML5Algorithm started "
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
    sensitivity: float = 6.0,
    min_prob: float = 0.10,
    min_ticks: int = 30,
    max_vol_ratio: float = 5.0,
) -> VrsML5Algorithm:
    """Instantiate and return the VrsML5Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier.
    fast_halflife : int
        Fast EWM half-life in ticks. Default 20.
    slow_halflife : int
        Slow EWM half-life in ticks (vol baseline). Default 120.
    sensitivity : float
        Decay rate mapping vol excess to submission probability. Default 6.0.
    min_prob : float
        Floor on submission probability. Raised from loop 4's 0.05. Default 0.10.
    min_ticks : int
        Cold-start guard: full submission for first N ticks. Default 30.
    max_vol_ratio : float
        Clip vol_ratio to prevent outlier domination. Default 5.0.
    """
    config = VrsML5Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        fast_halflife=fast_halflife,
        slow_halflife=slow_halflife,
        sensitivity=sensitivity,
        min_prob=min_prob,
        min_ticks=min_ticks,
        max_vol_ratio=max_vol_ratio,
    )
    return VrsML5Algorithm(config=config)
