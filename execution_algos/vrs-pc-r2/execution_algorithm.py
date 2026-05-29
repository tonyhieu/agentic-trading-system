"""Vol-regime sizer with quote-staleness gate (vrs-pc-r2).

Extends ``vol-regime-sizer`` by multiplying the base submission probability
by a quote-staleness factor that attenuates participation when the quote
stream has stalled (no MBP-1 updates for many multiples of the typical
inter-tick interval).

Submission probability:

  base_vol_prob   = exp(-sens_vol * max(0, vol_ratio - 1))         [identical to base]
  staleness_ratio = (now_ns - last_quote_ts_ns) / max(typical_gap_ns, 1)
  staleness_factor = exp(-sens_stale * max(0, staleness_ratio - stale_threshold))
  p               = max(min_prob, base_vol_prob * staleness_factor)

Properties:
  - In actively-streaming markets (staleness near typical_gap): staleness_factor = 1.0,
    behavior IDENTICAL to vol-regime-sizer.
  - In a stalled quote stream (staleness >> typical_gap * stale_threshold):
    staleness_factor < 1, deeper skip than base.
  - Submission set is a STRICT SUBSET of vol-regime-sizer's submission set
    at every order (multiplicative factor in (0, 1]).

Clock source: ``self.clock.timestamp_ns()`` (Nautilus simulated event time)
for both quote-tick arrivals and order-arrival staleness reference. NEVER
``time.time()`` — that would produce nonsense values in a backtest.

Cold-start guard: until ``stale_window`` (=200) inter-tick gaps have been
observed, staleness_factor = 1.0 (base behavior). Prevents early-session
skipping from an unstable median estimate.

Reduce-only orders: always submitted unconditionally (intraday_flat compliance,
identical to base).

Quantity invariant: child_qty == parent_qty == 1 for every submitted order.
"""
from __future__ import annotations

import hashlib
import math
import statistics
import struct
from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class VrsPcR2Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for vrs-pc-r2 (vol-regime sizer + quote-staleness gate).

    Parameters
    ----------
    fast_halflife : int
        Half-life (in ticks) of the fast EWM of |delta_mid|. Default 20.
    slow_halflife : int
        Half-life (in ticks) of the slow EWM of |delta_mid| (vol baseline).
        Default 120.
    sens_vol : float
        Sensitivity of the base vol factor. Default 2.0 (matches base).
    min_prob : float
        Floor on submission probability. Default 0.05.
    min_ticks : int
        Cold-start guard for vol estimator: full submission until N ticks observed.
        Default 30.
    max_vol_ratio : float
        Clip vol_ratio before applying sensitivity. Default 5.0.
    stale_window : int
        Number of recent inter-tick gaps to track for the typical-gap median.
        Default 200. Also serves as the cold-start guard for the staleness gate.
    stale_threshold : float
        Dimensionless threshold: staleness gate attenuates only when
        staleness_ratio > stale_threshold. Default 10.0 (10x median gap).
    sens_stale : float
        Sensitivity of the staleness factor. Default 0.5 (perturbation, not
        dominating signal — at ratio=12 → factor=0.37; at ratio=20 → factor=0.0067).
    """

    fast_halflife: int = 20
    slow_halflife: int = 120
    sens_vol: float = 2.0
    min_prob: float = 0.05
    min_ticks: int = 30
    max_vol_ratio: float = 5.0
    stale_window: int = 200
    stale_threshold: float = 10.0
    sens_stale: float = 0.5


class VrsPcR2Algorithm(ExecAlgorithm):
    """Vol-regime sizer + quote-staleness gate."""

    def __init__(self, config: VrsPcR2Config) -> None:
        super().__init__(config=config)

        # EWM decay coefficients
        self._fast_alpha: float = 1.0 - math.exp(-math.log(2) / config.fast_halflife)
        self._slow_alpha: float = 1.0 - math.exp(-math.log(2) / config.slow_halflife)

        # Config parameters
        self._sens_vol: float = config.sens_vol
        self._min_prob: float = config.min_prob
        self._min_ticks: int = config.min_ticks
        self._max_vol_ratio: float = config.max_vol_ratio
        self._stale_window: int = config.stale_window
        self._stale_threshold: float = config.stale_threshold
        self._sens_stale: float = config.sens_stale

        # Vol EWM state
        self._fast_vol: float | None = None
        self._slow_vol: float | None = None
        self._prev_mid: float | None = None
        self._tick_count: int = 0

        # Staleness state — uses Nautilus event-time ns timestamps
        self._last_quote_ts_ns: int | None = None
        self._gap_deque: deque[int] = deque(maxlen=self._stale_window)

        # Subscription tracking
        self._subscribed: set[str] = set()

        # Diagnostic counters
        self._submitted: int = 0
        self._skipped: int = 0
        self._skipped_vol_only: int = 0
        self._skipped_stale_active: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"VrsPcR2Algorithm started "
            f"(fast_alpha={self._fast_alpha:.4f}, slow_alpha={self._slow_alpha:.4f}, "
            f"sens_vol={self._sens_vol}, min_prob={self._min_prob}, "
            f"min_ticks={self._min_ticks}, max_vol_ratio={self._max_vol_ratio}, "
            f"stale_window={self._stale_window}, "
            f"stale_threshold={self._stale_threshold}, sens_stale={self._sens_stale})."
        )

    def on_reset(self) -> None:
        self._fast_vol = None
        self._slow_vol = None
        self._prev_mid = None
        self._tick_count = 0
        self._last_quote_ts_ns = None
        self._gap_deque.clear()
        self._subscribed.clear()
        self._submitted = 0
        self._skipped = 0
        self._skipped_vol_only = 0
        self._skipped_stale_active = 0

    # ------------------------------------------------------------------
    # Quote tick handler — vol EWM + staleness gap tracking
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    def on_quote_tick(self, tick) -> None:
        """Update vol EWMs and staleness gap tracking from each quote tick."""
        try:
            bid = float(str(tick.bid_price))
            ask = float(str(tick.ask_price))
            mid = (bid + ask) / 2.0
        except Exception:
            return

        # ---- Vol estimator (matches base vol-regime-sizer) ----
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

        # ---- Staleness tracking (Nautilus event-time ns) ----
        now_ns = self.clock.timestamp_ns()
        if self._last_quote_ts_ns is not None:
            gap_ns = now_ns - self._last_quote_ts_ns
            if gap_ns > 0:
                self._gap_deque.append(gap_ns)
        self._last_quote_ts_ns = now_ns

    # ------------------------------------------------------------------
    # Submission probability
    # ------------------------------------------------------------------

    def _compute_base_vol_prob(self) -> float:
        """Return the vol-regime-sizer probability factor (identical to base)."""
        if self._tick_count < self._min_ticks:
            return 1.0
        if self._fast_vol is None or self._slow_vol is None:
            return 1.0
        if self._slow_vol < 1e-12:
            return 1.0

        vol_ratio = min(self._fast_vol / self._slow_vol, self._max_vol_ratio)
        excess = max(0.0, vol_ratio - 1.0)
        return math.exp(-self._sens_vol * excess)

    def _compute_staleness_factor(self) -> tuple[float, float]:
        """Return (staleness_factor, staleness_ratio).

        staleness_factor = 1.0 (no attenuation) if:
          - cold-start (fewer than stale_window gaps observed), or
          - no quote has been seen yet.

        Otherwise: staleness_factor = exp(-sens_stale * max(0, ratio - threshold)).
        """
        if self._last_quote_ts_ns is None:
            return 1.0, 0.0
        if len(self._gap_deque) < self._stale_window:
            return 1.0, 0.0

        now_ns = self.clock.timestamp_ns()
        staleness_ns = now_ns - self._last_quote_ts_ns
        if staleness_ns < 0:
            staleness_ns = 0

        typical_gap_ns = statistics.median(self._gap_deque)
        if typical_gap_ns <= 0:
            return 1.0, 0.0

        ratio = staleness_ns / typical_gap_ns
        excess = max(0.0, ratio - self._stale_threshold)
        factor = math.exp(-self._sens_stale * excess)
        return factor, ratio

    # ------------------------------------------------------------------
    # Deterministic pseudo-random draw
    # ------------------------------------------------------------------

    @staticmethod
    def _order_uniform(order_id_str: str) -> float:
        """Return a deterministic float in [0, 1) from the order's client ID."""
        digest = hashlib.sha256(order_id_str.encode()).digest()
        val = struct.unpack(">Q", digest[:8])[0]
        return val / (2**64)

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on vol AND staleness factors."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders: always submit — intraday_flat compliance.
        if order.is_reduce_only:
            self.log.debug(
                f"Reduce-only {order.client_order_id}: submitting unconditionally."
            )
            self.submit_order(order)
            return

        base_prob = self._compute_base_vol_prob()
        stale_factor, stale_ratio = self._compute_staleness_factor()

        prob = max(self._min_prob, base_prob * stale_factor)

        if prob >= 1.0 - 1e-9:
            # Full participation
            self._submitted += 1
            self.log.debug(
                f"SUBMIT {order.client_order_id} (p=1.0, calm/cold/active)."
            )
            self.submit_order(order)
            return

        # Deterministic draw from order ID
        u = self._order_uniform(str(order.client_order_id))

        if u < prob:
            self._submitted += 1
            self.log.debug(
                f"SUBMIT {order.client_order_id} "
                f"(p={prob:.4f}, u={u:.4f}, base={base_prob:.4f}, "
                f"stale_factor={stale_factor:.4f}, stale_ratio={stale_ratio:.2f})."
            )
            self.submit_order(order)
        else:
            self._skipped += 1
            if stale_factor < 1.0 - 1e-9:
                self._skipped_stale_active += 1
            else:
                self._skipped_vol_only += 1
            self.log.info(
                f"SKIP {order.client_order_id} "
                f"(p={prob:.4f}, u={u:.4f}, base={base_prob:.4f}, "
                f"stale_factor={stale_factor:.4f}, stale_ratio={stale_ratio:.2f}). "
                f"submitted={self._submitted} skipped={self._skipped} "
                f"(vol_only={self._skipped_vol_only}, "
                f"stale_active={self._skipped_stale_active})."
            )
            # Do NOT call submit_order — quantity invariant preserved.


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    fast_halflife: int = 20,
    slow_halflife: int = 120,
    sens_vol: float = 2.0,
    min_prob: float = 0.05,
    min_ticks: int = 30,
    max_vol_ratio: float = 5.0,
    stale_window: int = 200,
    stale_threshold: float = 10.0,
    sens_stale: float = 0.5,
) -> VrsPcR2Algorithm:
    """Instantiate and return the VrsPcR2Algorithm."""
    config = VrsPcR2Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        fast_halflife=fast_halflife,
        slow_halflife=slow_halflife,
        sens_vol=sens_vol,
        min_prob=min_prob,
        min_ticks=min_ticks,
        max_vol_ratio=max_vol_ratio,
        stale_window=stale_window,
        stale_threshold=stale_threshold,
        sens_stale=sens_stale,
    )
    return VrsPcR2Algorithm(config=config)
