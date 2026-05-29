"""afg-b-l3: aggressor-flow-gate with DISJUNCTIVE absolute OR (ratio AND busyness) gate.

Derived from afg-b-l2 (the prior loop). L2 was derived from afg-b-l1, which
was derived from the base `aggressor-flow-gate`. Brief-summary context only:
L1 replaced base's absolute gate with a pure-ratio gate and LOST (-53% vs
base, +13.5k extra admits). L2 conjoined base + ratio and LOST again
(-52% vs base, +14.2k extra admits) because ANDing the ratio leg onto
base's absolute leg admits the UNION of each operand's admits.

This loop makes ONE targeted change vs L2: flip the joiner from AND to OR
and gate the ratio leg by a minimum absolute-volume floor:

    skip iff (|net_flow| >= flow_threshold)                                  # base leg
          OR (|r| >= ratio_threshold AND abs_vol >= min_busy_abs_vol)        # ratio leg gated by busyness

The disjunction makes the skip set a strict SUPERSET of base's skip set
(every base skip remains a skip), so admitted-trade count is strictly
<= base. The busyness floor on the ratio leg avoids the L1 failure mode
where a near-empty window with a single 2-contract trade trivially yields
r = 1.0 -- those are no-information windows that should not be filtered
on ratio. With min_busy_abs_vol = 5.0 the ratio leg only fires when at
least ~3 trades have hit in the window.

Hypothesis (informed only by L1 + L2 brief_summary + L2's "next" text
plus mechanical inspection of afg-b-l1 and afg-b-l2 source for the
class structure / parameter shape):

  - vs base: admitted-trades strictly <= base (disjunctive skip is
    superset of base's skip). On this oracle, L1 established the
    monotone "extra admits map to ~$47/1k pnl destruction"; therefore
    skipping additional orders should net positive pnl provided those
    extra skips are not systematically informative (the ratio leg is
    a microstructure-standard imbalance signal, so they should be
    weakly anti-informative).
  - vs L2 / L1: trade_count strictly lower (we are now tightening
    where L1 + L2 both loosened).

Expected direction: pnl > base, trade_count < base, win_rate roughly
similar to base. If pnl improves materially over base, this is the new
high-water mark for the arm. If it matches base within noise, the ratio
information content is small relative to the absolute threshold and
future loops should target a different axis entirely (window length,
asymmetric per-side thresholds, regime-conditional thresholds).

Quantity invariant: orders are skipped or submitted unchanged -- never
modified, split, or duplicated. Same as base + L1 + L2.

No look-ahead bias: only ticks with ts_event <= order.ts_init are in the
deque at decision time (replay is strictly chronological; the window
prune uses the order's ts_init, not a future timestamp).
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class AfgBL3Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for afg-b-l3.

    Parameters
    ----------
    window_seconds : float
        Rolling look-back window for trade prints, in seconds.
        Default 10.0 seconds (same as base + L1 + L2).
    flow_threshold : float
        Minimum absolute net signed flow (in contracts) for the absolute
        leg of the disjunction. Default 2.0 (same as base + L2).
    ratio_threshold : float
        Minimum |net_flow| / max(min_abs_baseline, abs_vol_window) for the
        ratio leg of the disjunction. Default 0.35 (same as L1 + L2).
    min_abs_baseline : float
        Floor on the ratio denominator (in contracts). Prevents
        divide-by-tiny on empty/sparse windows. Default 2.0.
    min_busy_abs_vol : float
        Minimum absolute volume in the window before the ratio leg of
        the disjunction is allowed to fire. Disqualifies near-empty
        warm-up windows where a single trade trivially gives r=1.0.
        Default 5.0 contracts.
    """

    window_seconds: float = 10.0
    flow_threshold: float = 2.0
    ratio_threshold: float = 0.35
    min_abs_baseline: float = 2.0
    min_busy_abs_vol: float = 5.0


class AfgBL3Algorithm(ExecAlgorithm):
    """Aggressor-flow gate using a DISJUNCTION of absolute OR (ratio AND busyness) tests.

    Opening orders (is_reduce_only == False):
      - Compute signed net flow and total absolute volume over the same
        `window_seconds` window. Compute imbalance ratio
        r = net_flow / max(min_abs_baseline, abs_vol_window).
      - Skip BUY  entries when (net_flow <= -flow_threshold)
                            OR (r <= -ratio_threshold AND abs_vol >= min_busy_abs_vol).
      - Skip SELL entries when (net_flow >=  flow_threshold)
                            OR (r >=  ratio_threshold AND abs_vol >= min_busy_abs_vol).
      - Submit unconditionally when the deque is empty (warm-up) or
        neither leg of the disjunction is adverse.
      - After any skip: _position_flat = True (next open unconditional;
        anti-cascade guarantee preserved from base + L1 + L2).

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).
    """

    def __init__(self, config: AfgBL3Config) -> None:
        super().__init__(config=config)
        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._flow_threshold: float = config.flow_threshold
        self._ratio_threshold: float = config.ratio_threshold
        self._min_abs_baseline: float = config.min_abs_baseline
        self._min_busy_abs_vol: float = config.min_busy_abs_vol

        # Deque of (ts_event_ns: int, signed_vol: float, abs_vol: float)
        # signed_vol = +size (BUYER), -size (SELLER), 0 (NO_AGGRESSOR)
        # abs_vol = size (always non-negative; NO_AGGRESSOR included)
        self._flow_deque: deque[tuple[int, float, float]] = deque()

        # Running sums for O(1) updates
        self._net_flow: float = 0.0
        self._abs_vol: float = 0.0

        # Safety: forced re-entry after any skip to prevent cascade
        self._position_flat: bool = True

        # Subscription tracking
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"AfgBL3Algorithm started "
            f"(window={self._window_ns / 1e9:.1f}s, "
            f"flow_threshold={self._flow_threshold:.2f} contracts, "
            f"ratio_threshold={self._ratio_threshold:.3f}, "
            f"min_abs_baseline={self._min_abs_baseline:.2f}, "
            f"min_busy_abs_vol={self._min_busy_abs_vol:.2f})."
        )

    def on_reset(self) -> None:
        self._flow_deque.clear()
        self._net_flow = 0.0
        self._abs_vol = 0.0
        self._position_flat = True
        self._subscribed.clear()

    # ------------------------------------------------------------------
    # Subscription helper
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_trade_ticks(instrument_id)
            self.subscribe_quote_ticks(instrument_id)  # keep quote cache warm
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Trade tick handler — maintain rolling signed flow + abs volume deque
    # ------------------------------------------------------------------

    def on_trade_tick(self, tick) -> None:
        """Append the trade tick to the rolling deque and update both sums."""
        aggressor = tick.aggressor_side
        size = float(str(tick.size))

        if aggressor == AggressorSide.BUYER:
            signed_vol = size
        elif aggressor == AggressorSide.SELLER:
            signed_vol = -size
        else:
            # NO_AGGRESSOR — neutral; still contributes to abs_vol
            signed_vol = 0.0

        self._flow_deque.append((tick.ts_event, signed_vol, size))
        self._net_flow += signed_vol
        self._abs_vol += size

    # ------------------------------------------------------------------
    # Flow evaluation
    # ------------------------------------------------------------------

    def _prune_window(self, cutoff_ns: int) -> None:
        """Remove deque entries older than cutoff_ns, updating both sums."""
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            _, old_signed, old_abs = self._flow_deque.popleft()
            self._net_flow -= old_signed
            self._abs_vol -= old_abs

    def _flow_is_adverse(self, order) -> bool:
        """Return True iff EITHER the absolute leg OR the (ratio AND busy) leg is adverse.

        BUY  order: adverse when (net_flow <= -flow_threshold)
                              OR (r <= -ratio_threshold AND abs_vol >= min_busy_abs_vol).
        SELL order: adverse when (net_flow >=  flow_threshold)
                              OR (r >=  ratio_threshold AND abs_vol >= min_busy_abs_vol).

        Returns False (do not skip) when:
          - Flow deque is empty (no trades seen yet — warm-up).
          - Neither leg of the disjunction is adverse.
        """
        cutoff_ns = order.ts_init - self._window_ns
        self._prune_window(cutoff_ns)

        if not self._flow_deque:
            self.log.debug(
                f"No trade data in window; submitting {order.client_order_id} "
                f"unconditionally."
            )
            return False

        denom = max(self._min_abs_baseline, self._abs_vol)
        r = self._net_flow / denom
        net = self._net_flow
        busy = self._abs_vol >= self._min_busy_abs_vol

        if order.side == OrderSide.BUY:
            abs_leg = net <= -self._flow_threshold
            ratio_leg = busy and (r <= -self._ratio_threshold)
            if abs_leg or ratio_leg:
                self.log.debug(
                    f"BUY adverse: abs_leg={abs_leg} (net={net:.2f} vs "
                    f"-{self._flow_threshold:.2f}), ratio_leg={ratio_leg} "
                    f"(ratio={r:.3f} vs -{self._ratio_threshold:.3f}, "
                    f"abs_vol={self._abs_vol:.2f} vs {self._min_busy_abs_vol:.2f}); "
                    f"SKIP."
                )
                return True
        else:  # SELL
            abs_leg = net >= self._flow_threshold
            ratio_leg = busy and (r >= self._ratio_threshold)
            if abs_leg or ratio_leg:
                self.log.debug(
                    f"SELL adverse: abs_leg={abs_leg} (net={net:.2f} vs "
                    f"{self._flow_threshold:.2f}), ratio_leg={ratio_leg} "
                    f"(ratio={r:.3f} vs {self._ratio_threshold:.3f}, "
                    f"abs_vol={self._abs_vol:.2f} vs {self._min_busy_abs_vol:.2f}); "
                    f"SKIP."
                )
                return True

        return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on disjunction of absolute OR (ratio AND busy) flow tests."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Forced re-entry after a skip — always submit to prevent cascade.
        if self._position_flat:
            self.log.debug(
                f"Re-entry (first or post-skip); submitting "
                f"{order.client_order_id} unconditionally."
            )
            self._position_flat = False
            self.submit_order(order)
            return

        # Evaluate disjunctive (absolute OR ratio-with-busy-floor) aggressor-flow gate.
        if self._flow_is_adverse(order):
            self.log.info(
                f"SKIP {order.client_order_id} — disjunctive adverse flow "
                f"(net_flow={self._net_flow:.2f}, abs_vol={self._abs_vol:.2f}, "
                f"side={'BUY' if order.side == OrderSide.BUY else 'SELL'})."
            )
            self._position_flat = True
            # Do NOT call submit_order — quantity invariant preserved.
        else:
            self.log.debug(
                f"SUBMIT {order.client_order_id} — neither disjunctive leg adverse "
                f"(net_flow={self._net_flow:.2f}, abs_vol={self._abs_vol:.2f})."
            )
            self._position_flat = False
            self.submit_order(order)

    def on_quote_tick(self, tick) -> None:
        """Passively receive quote ticks (kept for quote-cache side-effects)."""
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_seconds: float = 10.0,
    flow_threshold: float = 2.0,
    ratio_threshold: float = 0.35,
    min_abs_baseline: float = 2.0,
    min_busy_abs_vol: float = 5.0,
) -> AfgBL3Algorithm:
    """Instantiate and return the AfgBL3Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_seconds : float
        Rolling window for aggressor-flow accumulation, in seconds. Default 10.0s.
    flow_threshold : float
        Min |net_flow| (contracts) for the absolute leg of the disjunction. Default 2.0.
    ratio_threshold : float
        Min |net_flow|/max(min_abs_baseline, abs_vol) for the ratio leg. Default 0.35.
    min_abs_baseline : float
        Floor on the ratio denominator (contracts). Default 2.0.
    min_busy_abs_vol : float
        Min abs_vol_window for the ratio leg to be allowed to fire. Default 5.0.
    """
    config = AfgBL3Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        flow_threshold=flow_threshold,
        ratio_threshold=ratio_threshold,
        min_abs_baseline=min_abs_baseline,
        min_busy_abs_vol=min_busy_abs_vol,
    )
    return AfgBL3Algorithm(config=config)
