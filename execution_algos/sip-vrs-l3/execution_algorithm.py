"""Transient-burst suppression layer (sip-vrs-l3).

Hypothesis (single, concrete modification of vol-regime-sizer):
-----------------------------------------------------------------
The parent algorithm `vol-regime-sizer` gates OPEN orders by an
instantaneous, unsigned vol-ratio probability. It treats a transient
spike (vol just rose, likely to mean-revert) identically to a sustained
high-vol regime. Per the loop-3 candidate-3 falsification test on
positions.csv across 20260313 and 20260317, position hold-duration is
strongly negatively correlated with mean realized_pnl among parent's
submitted orders:

   date       fast-bucket mean pnl   slow-bucket mean pnl   diff
   20260313   -0.121                  +0.005                +0.126
   20260317   -0.024                  +0.005                +0.029

Short-hold positions (closed early by oracle reversal) lose money;
long-hold positions break even or win. The oracle reverses position
direction during transient bursts that resolve quickly — exactly the
regime the parent's instantaneous gate cannot distinguish from a
sustained burst.

This algorithm layers a **transient-burst suppression** check on top of
the parent's gate. Compute the parent's `vol_ratio` exactly as the parent
does, then track a much slower EWM of the *vol_ratio itself* (halflife
600 ticks = 5x parent slow_halflife) — call this `vol_ratio_baseline`.
A transient burst is one where `vol_ratio > 1` AND
`vol_ratio - vol_ratio_baseline > burst_threshold` (default 0.3); the
ratio is meaningfully above its own sustained baseline.

When a transient burst is detected at order arrival, the parent's
`p_submit` is multiplied by `transient_factor` (default 0.5) — half the
parent's probability, meaning the algorithm skips roughly twice as often
during fresh bursts. When the burst is sustained
(`vol_ratio ≈ vol_ratio_baseline`), parent behavior is preserved exactly.
Calm regimes (`vol_ratio <= 1`) are also unchanged.

The deterministic SHA-256(client_order_id) draw and the
reduce-only-always-submit branch carry over unchanged from the parent.

Constraints (enforced by this algorithm):
- top_of_book_only: untouched — every submitted order is forwarded
  unchanged. The fill model handles top-of-book pricing.
- participation_cap: untouched — parent orders are 1 contract and we
  never inflate.
- intraday_flat: reduce-only orders always submit unconditionally.
- quantity invariant: skip means zero child fills (<= parent.quantity);
  submit means exactly the parent quantity. No inflation.

Expected effect vs `vol-regime-sizer` (the fixed comparison baseline):
- realized_pnl: up — suppressing fresh-burst submissions removes the
  short-hold adverse tail demonstrated by the C3 falsification test.
- mean_slippage: 0 (zero-slippage fill model; unchanged).
- sharpe_ratio: up — daily pnl tightens from removing the worst tail.
- trade_count: down slightly (additional 5-15% suppression vs parent
  during fresh bursts).
"""
from __future__ import annotations

import hashlib
import math
import struct

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class SipVrsL3Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for sip-vrs-l3 (transient-burst suppression).

    Parameters inherited unchanged from `vol-regime-sizer`:
      fast_halflife=20, slow_halflife=120, sensitivity=2.0,
      min_prob=0.05, min_ticks=30, max_vol_ratio=5.0.

    New parameters (added by this loop):
      regime_halflife=600   — EWM halflife (in ticks) of vol_ratio
                              itself. Principled rule: 5x parent
                              slow_halflife — captures regime-of-regimes
                              vs the parent's regime baseline.
      burst_threshold=0.3   — minimum (vol_ratio - vol_ratio_baseline)
                              for a "fresh burst." Principled rule:
                              aligns with parent's own "moderate excess"
                              decay scale (sensitivity × 0.3 ≈ 0.6 → p~0.55).
      transient_factor=0.5  — multiplicative reduction of parent p_submit
                              when in fresh burst. Principled rule: half.
    """

    fast_halflife: int = 20
    slow_halflife: int = 120
    sensitivity: float = 2.0
    min_prob: float = 0.05
    min_ticks: int = 30
    max_vol_ratio: float = 5.0
    # New layer parameters
    regime_halflife: int = 600
    burst_threshold: float = 0.3
    transient_factor: float = 0.5


class SipVrsL3Algorithm(ExecAlgorithm):
    """Parent vol-regime gate plus transient-burst suppression."""

    def __init__(self, config: SipVrsL3Config) -> None:
        super().__init__(config=config)

        # Parent EWM alphas (inherited)
        self._fast_alpha: float = 1.0 - math.exp(-math.log(2) / config.fast_halflife)
        self._slow_alpha: float = 1.0 - math.exp(-math.log(2) / config.slow_halflife)
        self._sensitivity: float = config.sensitivity
        self._min_prob: float = config.min_prob
        self._min_ticks: int = config.min_ticks
        self._max_vol_ratio: float = config.max_vol_ratio

        # New: even-slower EWM alpha for vol_ratio baseline
        self._regime_alpha: float = 1.0 - math.exp(
            -math.log(2) / config.regime_halflife
        )
        self._burst_threshold: float = config.burst_threshold
        self._transient_factor: float = config.transient_factor

        # EWM state
        self._fast_vol: float | None = None
        self._slow_vol: float | None = None
        self._vol_ratio_baseline: float | None = None  # slow EWM of vol_ratio
        self._prev_mid: float | None = None
        self._tick_count: int = 0

        # Subscription tracking
        self._subscribed: set[str] = set()

        # Diagnostic counters
        self._submitted: int = 0
        self._skipped: int = 0
        self._transient_suppressed: int = 0   # of submitted, how many hit transient layer
        self._fresh_burst_seen: int = 0       # how many parent calls observed fresh burst

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"SipVrsL3Algorithm started "
            f"(fast_alpha={self._fast_alpha:.4f}, slow_alpha={self._slow_alpha:.4f}, "
            f"regime_alpha={self._regime_alpha:.5f}, "
            f"sensitivity={self._sensitivity}, min_prob={self._min_prob}, "
            f"min_ticks={self._min_ticks}, "
            f"burst_threshold={self._burst_threshold}, "
            f"transient_factor={self._transient_factor})."
        )

    def on_reset(self) -> None:
        self._fast_vol = None
        self._slow_vol = None
        self._vol_ratio_baseline = None
        self._prev_mid = None
        self._tick_count = 0
        self._subscribed.clear()
        self._submitted = 0
        self._skipped = 0
        self._transient_suppressed = 0
        self._fresh_burst_seen = 0

    # ------------------------------------------------------------------
    # Quote tick handler — update EWM vol estimates + vol_ratio baseline
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    def on_quote_tick(self, tick) -> None:
        """Update EWM vol estimates and the slow EWM of vol_ratio."""
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
                self._fast_vol = (
                    self._fast_alpha * abs_delta
                    + (1.0 - self._fast_alpha) * self._fast_vol
                )
                self._slow_vol = (
                    self._slow_alpha * abs_delta
                    + (1.0 - self._slow_alpha) * self._slow_vol
                )

            # Update vol_ratio baseline with the current instantaneous vol_ratio
            if self._slow_vol is not None and self._slow_vol > 1e-12:
                inst_ratio = min(self._fast_vol / self._slow_vol, self._max_vol_ratio)
                if self._vol_ratio_baseline is None:
                    self._vol_ratio_baseline = inst_ratio
                else:
                    self._vol_ratio_baseline = (
                        self._regime_alpha * inst_ratio
                        + (1.0 - self._regime_alpha) * self._vol_ratio_baseline
                    )

        self._prev_mid = mid
        self._tick_count += 1

    # ------------------------------------------------------------------
    # Submission probability
    # ------------------------------------------------------------------

    def _compute_submit_prob(self) -> tuple[float, bool]:
        """Return (p_submit, fresh_burst_flag).

        Computes the parent's p_submit, then checks the transient-burst
        condition and applies the multiplicative suppression layer when
        a fresh burst is detected.

        Returns
        -------
        (p, fresh_burst) where p is the (possibly suppressed) probability
        in [min_prob, 1.0], and fresh_burst is True when the transient
        suppression layer fired.
        """
        if self._tick_count < self._min_ticks:
            return 1.0, False

        if self._fast_vol is None or self._slow_vol is None:
            return 1.0, False

        if self._slow_vol < 1e-12:
            return 1.0, False

        vol_ratio = min(self._fast_vol / self._slow_vol, self._max_vol_ratio)
        excess = max(0.0, vol_ratio - 1.0)
        parent_p = math.exp(-self._sensitivity * excess)
        parent_p = max(self._min_prob, parent_p)

        # Transient-burst layer
        fresh_burst = False
        if (
            vol_ratio > 1.0
            and self._vol_ratio_baseline is not None
            and (vol_ratio - self._vol_ratio_baseline) > self._burst_threshold
        ):
            fresh_burst = True
            p = max(self._min_prob, parent_p * self._transient_factor)
        else:
            p = parent_p

        self.log.debug(
            f"vol_ratio={vol_ratio:.4f} baseline={self._vol_ratio_baseline} "
            f"parent_p={parent_p:.4f} fresh_burst={fresh_burst} p={p:.4f}"
        )
        return p, fresh_burst

    # ------------------------------------------------------------------
    # Deterministic pseudo-random draw (inherited from parent unchanged)
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
        """Route order: parent vol gate plus transient-burst suppression."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders: always submit — intraday_flat compliance.
        if order.is_reduce_only:
            self.log.debug(
                f"Reduce-only {order.client_order_id}: submitting unconditionally."
            )
            self.submit_order(order)
            return

        p, fresh_burst = self._compute_submit_prob()
        if fresh_burst:
            self._fresh_burst_seen += 1

        if p >= 1.0 - 1e-9:
            self._submitted += 1
            self.log.debug(f"SUBMIT {order.client_order_id} (p=1.0, calm/cold).")
            self.submit_order(order)
            return

        u = self._order_uniform(str(order.client_order_id))

        if u < p:
            self._submitted += 1
            if fresh_burst:
                self._transient_suppressed += 0  # submitted despite suppression
            self.log.debug(
                f"SUBMIT {order.client_order_id} (p={p:.4f}, u={u:.4f}, "
                f"fresh_burst={fresh_burst})."
            )
            self.submit_order(order)
        else:
            self._skipped += 1
            if fresh_burst:
                self._transient_suppressed += 1
            self.log.info(
                f"SKIP {order.client_order_id} (p={p:.4f}, u={u:.4f}, "
                f"fresh_burst={fresh_burst}). "
                f"submitted={self._submitted} skipped={self._skipped} "
                f"transient_suppressed={self._transient_suppressed}."
            )


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    fast_halflife: int = 20,
    slow_halflife: int = 120,
    sensitivity: float = 2.0,
    min_prob: float = 0.05,
    min_ticks: int = 30,
    max_vol_ratio: float = 5.0,
    regime_halflife: int = 600,
    burst_threshold: float = 0.3,
    transient_factor: float = 0.5,
) -> SipVrsL3Algorithm:
    """Instantiate sip-vrs-l3 (transient-burst suppression on parent vol gate)."""
    config = SipVrsL3Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        fast_halflife=fast_halflife,
        slow_halflife=slow_halflife,
        sensitivity=sensitivity,
        min_prob=min_prob,
        min_ticks=min_ticks,
        max_vol_ratio=max_vol_ratio,
        regime_halflife=regime_halflife,
        burst_threshold=burst_threshold,
        transient_factor=transient_factor,
    )
    return SipVrsL3Algorithm(config=config)
