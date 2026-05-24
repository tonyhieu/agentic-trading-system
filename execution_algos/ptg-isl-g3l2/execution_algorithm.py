"""ptg-isl-g3l2: Operating-point retune of g1l1's spread-quantile gate.

Lineage
-------
Direct fork of ``ptg-isl-g1l1`` (island-0's chop-free best, +26.55% vs base
position-tier-gate, sharpe 23.17). g1l2/g2l1/g2l2/g3l1 each added a third
orthogonal skip axis (queue-imbalance, boolean chop, probabilistic chop,
aggressor-flow) on top of g1l1's position-cap + rolling-spread-p75 stack;
ALL four regressed vs g1l1 -- the cleanest negative result being g3l1 at
-40.75% vs g1l1 even after re-tuning the third-axis threshold +50%. This
is now FOUR independent third-axis approaches that have failed on ptg's
base => strong evidence for THREE-AXIS-SATURATION on this base (see
g3l1 NOTES Implementation Decisions §"third-axis-saturation").

The g3l1 ``summary_out.next`` and the gen-2 migration's `base_specific`
finding for island-0 ("gate-stacking plateaued; the operating point is
base-specific because each base presents a different surviving-population
distribution") converge on the same recommendation: stop adding axes,
RE-TUNE the one axis with empirical EV-positivity on ptg's base -- the
rolling-spread-quantile gate from g1l1.

Single-knob choice: ``spread_quantile``
---------------------------------------
The g3l1 ``next`` block offered two sweep directions:
  (a) quantile q in {0.70, 0.80, 0.85}
  (b) window in {30s, 90s, 120s}

We choose (a) -- quantile is the direct cut-depth dial; window controls
how much history is averaged into the threshold (an indirect knob that
shifts the threshold up/down asymmetrically depending on spread
autocorrelation). Quantile is a clean monotonic dial on the
EV-cost vs entry-recall tradeoff.

Direction within {0.70, 0.80, 0.85}: we move TIGHTER (q=0.80, skip only
the top 20% of spreads) rather than LOOSER (q=0.70, skip the top 30%).
Rationale:
  * g1l1 already had a SHALLOW cut: trade_count only fell 3.4%
    (87319 vs base 90433) because the spread gate fires AFTER the
    position-cap has already removed most candidates. The currently-skipped
    population is small.
  * The recurring failure mode across g1l2/g2l1/g2l2/g3l1 is gates that
    cut into EV-POSITIVE trades. The prior should therefore be that ANY
    cut deeper than necessary risks the same failure mode. Moving to
    q=0.80 tests whether g1l1's q=0.75 was already over-cutting; if so,
    re-admitting the [0.75, 0.80] band's worth of spread tails should
    capture marginal EV-positive trades that were paying a small adverse-
    selection premium but were net-positive.
  * Falsification is symmetric: if q=0.80 underperforms g1l1's 5394.25,
    we have evidence that q=0.75 was already at-or-past the EV peak and
    g4 should try q=0.70 (the other direction). If q=0.80 outperforms,
    g4 should sweep q=0.85 to find the peak.

This is the lower-risk, higher-prior-evidence option from g3l1.next; the
alternative (quantity modulation: probabilistic sizing instead of skip)
remains reserved for g4 if this single-knob retune fails.

Algorithm
---------
Identical to ptg-isl-g1l1 except spread_quantile changes from 0.75 -> 0.80.
All other parameters preserved: position_cap=1, spread_window_seconds=60.0,
min_samples=50. No new gate axes, no quantity modification, no change to
reduce-only handling. Both gates (position-cap + spread-quantile) must
pass for an OPEN to be submitted; reduce-only / closing orders always
execute (intraday_flat compliance).
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PtgIslG3L2Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for ptg-isl-g3l2.

    Parameters
    ----------
    position_cap : int
        Inherited from position-tier-gate. Skip OPEN if absolute net
        position >= position_cap. Default 1 (proven by base).
    spread_window_seconds : float
        Rolling window for spread samples (seconds). Default 60.0 --
        unchanged from g1l1.
    spread_quantile : float
        Quantile threshold for the spread gate (0 < q < 1). Skip OPEN
        when the latest spread is strictly greater than the q-th
        quantile of the rolling window. Default 0.80 -- TIGHTER than
        g1l1's 0.75 (this is the single tuned knob for g3l2).
    min_samples : int
        Minimum samples required before the spread gate fires. Below
        this, the gate is a no-op (warm-up). Default 50 -- unchanged.
    """

    position_cap: int = 1
    spread_window_seconds: float = 60.0
    spread_quantile: float = 0.80
    min_samples: int = 50


class PtgIslG3L2Algorithm(ExecAlgorithm):
    """ExecAlgorithm: position-cap + retuned rolling-spread-quantile gate."""

    def __init__(self, config: PtgIslG3L2Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        self._spread_window_ns: int = int(config.spread_window_seconds * 1_000_000_000)
        self._spread_quantile: float = config.spread_quantile
        self._min_samples: int = config.min_samples

        # Rolling spread samples: (ts_event_ns, spread).
        self._spread_deque: deque[tuple[int, float]] = deque()
        # Most recent observed spread (used as the comparison point).
        self._latest_spread: float | None = None

        # Subscription tracking (we need quote ticks).
        self._subscribed: set[str] = set()

        # Instrumentation counters (carry-forward from gen-1 migration's
        # "every gate ships with counters" generalizable rule).
        self._evaluated_count: int = 0
        self._position_skip_count: int = 0
        self._spread_skip_count: int = 0
        self._submitted_count: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"PtgIslG3L2Algorithm started "
            f"(position_cap={self._position_cap}, "
            f"spread_window={self._spread_window_ns / 1e9:.1f}s, "
            f"spread_quantile={self._spread_quantile:.2f}, "
            f"min_samples={self._min_samples})."
        )

    def on_reset(self) -> None:
        self._spread_deque.clear()
        self._latest_spread = None
        self._subscribed.clear()
        self._evaluated_count = 0
        self._position_skip_count = 0
        self._spread_skip_count = 0
        self._submitted_count = 0

    # ------------------------------------------------------------------
    # Subscription helper
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Quote tick handler -- maintain rolling spread samples
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        try:
            bid = float(str(tick.bid_price))
            ask = float(str(tick.ask_price))
        except Exception:
            return
        spread = ask - bid
        if spread < 0.0:
            # Defensive: crossed book -- skip the sample.
            return
        self._spread_deque.append((tick.ts_event, spread))
        self._latest_spread = spread

    # ------------------------------------------------------------------
    # Gate helpers
    # ------------------------------------------------------------------

    def _current_net_qty(self, instrument_id) -> float:
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        return sum(float(str(p.quantity)) for p in open_positions)

    def _prune_spread_window(self, cutoff_ns: int) -> None:
        while self._spread_deque and self._spread_deque[0][0] < cutoff_ns:
            self._spread_deque.popleft()

    def _spread_gate_skip(self, order) -> bool:
        """Return True if the latest spread sits above the rolling quantile."""
        cutoff_ns = order.ts_init - self._spread_window_ns
        self._prune_spread_window(cutoff_ns)

        n = len(self._spread_deque)
        if n < self._min_samples or self._latest_spread is None:
            return False  # warm-up: do not gate

        # Quantile via sorted copy. n is bounded by window (seconds-scale).
        sorted_spreads = sorted(s for _, s in self._spread_deque)
        # Linear interpolation: index = q * (n - 1)
        idx_f = self._spread_quantile * (n - 1)
        lo = int(idx_f)
        hi = min(lo + 1, n - 1)
        frac = idx_f - lo
        threshold = sorted_spreads[lo] * (1.0 - frac) + sorted_spreads[hi] * frac

        if self._latest_spread > threshold:
            self.log.debug(
                f"SPREAD SKIP {order.client_order_id} -- "
                f"latest_spread={self._latest_spread:.5f} > "
                f"q{self._spread_quantile:.2f}={threshold:.5f} "
                f"(n={n})."
            )
            return True
        return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute -- intraday_flat compliance.
        if order.is_reduce_only:
            self.submit_order(order)
            return

        self._evaluated_count += 1

        # Gate 1: position-tier-gate (inherited base behavior).
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty >= self._position_cap:
            self._position_skip_count += 1
            self.log.debug(
                f"POSITION SKIP {order.client_order_id} -- net_qty={net_qty:.1f} "
                f">= cap={self._position_cap}."
            )
            return

        # Gate 2: spread gate (retuned quantile = 0.80 vs g1l1's 0.75).
        if self._spread_gate_skip(order):
            self._spread_skip_count += 1
            return

        self._submitted_count += 1
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    spread_window_seconds: float = 60.0,
    spread_quantile: float = 0.80,
    min_samples: int = 50,
) -> PtgIslG3L2Algorithm:
    config = PtgIslG3L2Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        spread_window_seconds=spread_window_seconds,
        spread_quantile=spread_quantile,
        min_samples=min_samples,
    )
    return PtgIslG3L2Algorithm(config=config)
