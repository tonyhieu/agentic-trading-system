"""afg-b-l4: aggressor-flow-gate with TIGHTENED absolute threshold (flow=1.0), ratio leg removed.

Derived from afg-b-l3 (the prior loop). L3 was derived from afg-b-l2, which
was derived from afg-b-l1, which was derived from the base
`aggressor-flow-gate`. Brief-summary context only:
L1 (pure-ratio) WORSE than base (-53%, +13.5k extra admits).
L2 (base AND ratio) WORSE than base (-52%, +14.2k extra admits) -- ANDing
admitted the UNION of admits.
L3 (base OR (ratio AND busy_floor=5)) EXACTLY equal to base -- the ratio leg
was structurally dominated by the absolute leg at the chosen parameters.

L1+L2+L3 collectively triangulate that the ratio reformulation cannot beat
base on this oracle no matter how it is composed. L1 also established a
monotone relationship on this oracle: marginal admits beyond base cost
~$47 per 1k extra admits. Read in reverse, marginal SKIPS beyond base
should YIELD ~$47 per 1k extra skips, provided those skipped orders are
weakly anti-informative on average.

L4 makes a single targeted change vs L3 (and vs base): REMOVE the ratio
leg entirely and TIGHTEN the absolute threshold from 2.0 -> 1.0 contracts.
The gate becomes simply:

    skip iff |net_flow_window| >= 1.0  (10s window)

This adds new skips on top of base's set (every order with |net_flow| in
[1.0, 2.0) is now skipped where base would have admitted it).

Hypothesis (informed only by L1+L2+L3 brief_summary + L3's "next" text
plus mechanical inspection of afg-b-l1, afg-b-l2, afg-b-l3 source for
the class shape / parameter shape):

  - vs base: admitted-trades strictly < base (tighter absolute threshold
    skips more orders). The L1 monotone arithmetic predicts
    pnl > base if those newly-skipped orders are weakly anti-informative
    (same distribution as L1's marginal admits, just observed from the
    other side).
  - vs L3 / L2 / L1: trade_count strictly lower (we are now ADDING skips
    on top of base's set, which all three prior loops failed to do).

Expected direction: pnl > base, trade_count < base, win_rate roughly
similar to base. If pnl improves materially over base, the brief-summary
arm finally beats its base on this lineage and the absolute-threshold
axis is the correct lever. If pnl drops below base, the base's 2.0
threshold was already on the loose side of the absolute-only optimum,
and L5 should reverse course (raise to 3.0) to RE-ADMIT what base
over-skips.

Quantity invariant: orders are skipped or submitted unchanged -- never
modified, split, or duplicated. Same as base + L1 + L2 + L3.

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


class AfgBL4Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for afg-b-l4.

    Parameters
    ----------
    window_seconds : float
        Rolling look-back window for trade prints, in seconds.
        Default 10.0 seconds (same as base + L1 + L2 + L3).
    flow_threshold : float
        Minimum absolute net signed flow (in contracts) to skip the order.
        Default 1.0 (TIGHTENED from base/L2/L3's 2.0 -- adds skips on top
        of base's set).
    """

    window_seconds: float = 10.0
    flow_threshold: float = 1.0


class AfgBL4Algorithm(ExecAlgorithm):
    """Aggressor-flow gate using a tightened absolute threshold (ratio leg removed).

    Opening orders (is_reduce_only == False):
      - Compute signed net flow over the same `window_seconds` window.
      - Skip BUY  entries when net_flow <= -flow_threshold.
      - Skip SELL entries when net_flow >=  flow_threshold.
      - Submit unconditionally when the deque is empty (warm-up) or the
        absolute threshold is not crossed in the adverse direction.
      - After any skip: _position_flat = True (next open unconditional;
        anti-cascade guarantee preserved from base + L1 + L2 + L3).

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).
    """

    def __init__(self, config: AfgBL4Config) -> None:
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
            f"AfgBL4Algorithm started "
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
        """Route order: submit or skip based on the tightened absolute aggressor-flow gate."""
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

        # Evaluate tightened absolute aggressor-flow gate.
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
    window_seconds: float = 10.0,
    flow_threshold: float = 1.0,
) -> AfgBL4Algorithm:
    """Instantiate and return the AfgBL4Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_seconds : float
        Rolling window for aggressor-flow accumulation, in seconds. Default 10.0s.
    flow_threshold : float
        Minimum |net_flow| (in contracts) to skip the order. Default 1.0
        (TIGHTENED from base/L2/L3's 2.0).
    """
    config = AfgBL4Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        flow_threshold=flow_threshold,
    )
    return AfgBL4Algorithm(config=config)
