"""afg-b-l8: aggressor-flow-gate with LENGTHENED window (window=20s, flow_threshold=1.0).

FINAL loop in the afg-b 8-loop brief-summary experiment.

Derived from afg-b-l4 (the in-arm leader at $1088 / 86,089 trades / sharpe
5.36) by a single ORTHOGONAL parameter change in the OPPOSITE direction
from L7: `window_seconds` 10.0 -> 20.0 with `flow_threshold` PINNED at L4's
integer optimum 1.0. Ratio leg absent (same as L4/L5/L6/L7).

Brief-summary context only (L1+L2+L3+L4+L5+L6+L7 summary_out blocks plus
headline metrics, no other reads of prior NOTES.md or full_reasoning):

  L1 (pure-ratio, |r|>=0.35):   WORSE than base (-53%, +13.5k extra admits).
  L2 (base AND ratio):          WORSE than base (-52%, +14.2k extra admits).
  L3 (base OR ratio):           EXACTLY equal to base -- ratio leg dominated.
  L4 (ratio removed, flow=1.0): BEATS base (+12.16% pnl: $1088 vs $970;
                                -1,671 trades; sharpe 5.36 vs 4.58).
  L5 (flow=0.5):                IDENTICAL to L4 -- integer-resolution lesson.
  L6 (flow=3.0):                REGRESSED (-14% vs base, -23.5% vs L4).
  L7 (window=5s, flow=1.0):     REGRESSED (-12.64% vs L4, -2.01% vs base).
                                The 5-10s flow memory is GENUINELY informative
                                (not stale noise); newly admitted orders cost
                                ~$155 per 1k extra admits.

After L6 the absolute-threshold axis was fully bracketed and monotone with
integer optimum at L4=1.0. After L7 the window axis at flow=1.0 has 2 of 3
needed points: 5s:$950.50, 10s:$1088 (leader). The gradient at 10s is
NEGATIVE going DOWN. L7's "next" text explicitly prescribes probing
window=20s at flow=1.0 as the only informative remaining single-axis probe
to bracket the window-length optimum. After L8 the window axis will be
triangulated with 3 points (5, 10, 20) mirroring the threshold sweep
(1, 2, 3) that closed in L6.

L8 single change: window_seconds 10.0 -> 20.0 at flow_threshold=1.0.
Rationale (brief-summary disciplined):

  * Window axis at flow=1.0 must be bracketed in the OPPOSITE direction
    from L7's 5s probe to triangulate the optimum (5, 10, 20).
  * Oracle horizon (visible from config.yaml, NOT from prior loops):
    horizon_seconds=30, signal_interval_seconds=1. A 20s window is ~2/3
    of the predictive forecast horizon -- the NATURAL CEILING before
    flow >= horizon-age stops being predictive and starts being post-hoc
    (a trade that happened 25s ago has had 25s for its information to
    resolve into the price the oracle is forecasting from).
  * If pnl_L8 > L4's $1088: window optimum is on the LONG side; window
    axis is the new productive lever beyond L4.
  * If pnl_L8 in ($950.50, $1088): window axis mildly convex around 10s,
    L4 remains the bracketed leader, and the window-axis sweep closes.
  * If pnl_L8 <= $950.50: window axis tightly convex around 10s with the
    optimum bracketed at 10s; threshold and window axes are now both
    fully exhausted on this oracle.

Hypothesis: L7's finding that "5-10s flow memory is informative" suggests
the 10s window is NOT capturing all informative flow. Extending to 20s
could either:
  (a) capture more informative flow imbalance and increase skips of
      genuinely anti-informative orders -> pnl > L4.
  (b) start admitting stale flow > 10s old as if it were still
      informative, mis-classifying current regime -> pnl < L4 (possibly
      < base if heavily contaminated by stale signal).

Per L7's diagnostic that flow at 5-10s is informative (not stale), and
per the oracle horizon being 30s, I lean weakly toward (a) but the data
will decide. The flow deque is a STRICT SUPERSET of L4's 10s view: every
trade in L4's 10s window is also in L8's 20s window, plus an additional
10s of history. So L8 will skip AT LEAST as many orders as L4 (admit
AT MOST as many) -- the strict-subset/superset analysis is the mirror
of L7's.

Quantity invariant: orders are skipped or submitted unchanged. Same as
base + L1 + L2 + L3 + L4 + L5 + L6 + L7.

No look-ahead bias: only ticks with ts_event <= order.ts_init are in
the deque at decision time. Prune uses `order.ts_init - window_ns` as
cutoff. Identical guarantee to L4/L7.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class AfgBL8Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for afg-b-l8.

    Parameters
    ----------
    window_seconds : float
        Rolling look-back window for trade prints, in seconds.
        Default 20.0 seconds (LENGTHENED from base + L1..L6's 10.0s; opposite
        direction from L7's 5.0s). Single parameter change vs L4.
    flow_threshold : float
        Minimum absolute net signed flow (in contracts) to skip the order.
        Default 1.0 (PINNED at L4's integer optimum; the absolute-threshold
        axis was bracketed by base/L4/L6 with L4=1.0 as the monotone integer
        optimum).
    """

    window_seconds: float = 20.0
    flow_threshold: float = 1.0


class AfgBL8Algorithm(ExecAlgorithm):
    """Aggressor-flow gate with LENGTHENED window (ratio leg absent).

    Opening orders (is_reduce_only == False):
      - Compute signed net flow over the `window_seconds` window.
      - Skip BUY  entries when net_flow <= -flow_threshold.
      - Skip SELL entries when net_flow >=  flow_threshold.
      - Submit unconditionally when the deque is empty (warm-up) or the
        absolute threshold is not crossed in the adverse direction.
      - After any skip: _position_flat = True (next open unconditional;
        anti-cascade guarantee preserved from base + L1..L7).

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).
    """

    def __init__(self, config: AfgBL8Config) -> None:
        super().__init__(config=config)
        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._flow_threshold: float = config.flow_threshold

        # Deque of (ts_event_ns: int, signed_vol: float)
        # signed_vol = +size (BUYER), -size (SELLER), 0 (NO_AGGRESSOR)
        self._flow_deque: deque[tuple[int, float]] = deque()

        # Running sum for O(1) updates
        self._net_flow: float = 0.0

        # Safety: forced re-entry after any skip to prevent cascade
        self._position_flat: bool = True

        # Subscription tracking
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"AfgBL8Algorithm started "
            f"(window={self._window_ns / 1e9:.1f}s, "
            f"flow_threshold={self._flow_threshold:.2f} contracts)."
        )

    def on_reset(self) -> None:
        self._flow_deque.clear()
        self._net_flow = 0.0
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
    # Trade tick handler — maintain rolling signed flow deque
    # ------------------------------------------------------------------

    def on_trade_tick(self, tick) -> None:
        """Append the trade tick to the rolling deque and update the sum."""
        aggressor = tick.aggressor_side
        size = float(str(tick.size))

        if aggressor == AggressorSide.BUYER:
            signed_vol = size
        elif aggressor == AggressorSide.SELLER:
            signed_vol = -size
        else:
            # NO_AGGRESSOR — neutral
            signed_vol = 0.0

        self._flow_deque.append((tick.ts_event, signed_vol))
        self._net_flow += signed_vol

    # ------------------------------------------------------------------
    # Flow evaluation
    # ------------------------------------------------------------------

    def _prune_window(self, cutoff_ns: int) -> None:
        """Remove deque entries older than cutoff_ns, updating the sum."""
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            _, old_signed = self._flow_deque.popleft()
            self._net_flow -= old_signed

    def _flow_is_adverse(self, order) -> bool:
        """Return True iff the absolute leg fires against this order's side.

        BUY  order: adverse when net_flow <= -flow_threshold.
        SELL order: adverse when net_flow >=  flow_threshold.

        Returns False (do not skip) when:
          - Flow deque is empty (no trades seen yet — warm-up).
          - Net flow has not crossed the threshold in the adverse direction.
        """
        cutoff_ns = order.ts_init - self._window_ns
        self._prune_window(cutoff_ns)

        if not self._flow_deque:
            self.log.debug(
                f"No trade data in window; submitting {order.client_order_id} "
                f"unconditionally."
            )
            return False

        net = self._net_flow

        if order.side == OrderSide.BUY:
            if net <= -self._flow_threshold:
                self.log.debug(
                    f"BUY adverse: net={net:.2f} <= -{self._flow_threshold:.2f}; SKIP."
                )
                return True
        else:  # SELL
            if net >= self._flow_threshold:
                self.log.debug(
                    f"SELL adverse: net={net:.2f} >= {self._flow_threshold:.2f}; SKIP."
                )
                return True

        return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on the lengthened-window absolute aggressor-flow gate."""
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

        # Evaluate lengthened-window absolute aggressor-flow gate.
        if self._flow_is_adverse(order):
            self.log.info(
                f"SKIP {order.client_order_id} -- absolute adverse flow "
                f"(net_flow={self._net_flow:.2f}, side="
                f"{'BUY' if order.side == OrderSide.BUY else 'SELL'})."
            )
            self._position_flat = True
            # Do NOT call submit_order — quantity invariant preserved.
        else:
            self.log.debug(
                f"SUBMIT {order.client_order_id} -- absolute threshold not crossed "
                f"(net_flow={self._net_flow:.2f})."
            )
            self._position_flat = False
            self.submit_order(order)

    def on_quote_tick(self, tick) -> None:
        """Passively receive quote ticks (kept for quote-cache side-effects)."""
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_seconds: float = 20.0,
    flow_threshold: float = 1.0,
) -> AfgBL8Algorithm:
    """Instantiate and return the AfgBL8Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_seconds : float
        Rolling window for aggressor-flow accumulation, in seconds. Default 20.0s
        (LENGTHENED from base + L1..L6's 10.0s; opposite direction from L7's 5.0s).
    flow_threshold : float
        Minimum |net_flow| (in contracts) to skip the order. Default 1.0
        (PINNED at L4's integer optimum).
    """
    config = AfgBL8Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        flow_threshold=flow_threshold,
    )
    return AfgBL8Algorithm(config=config)
