"""afg-b-l6: aggressor-flow-gate with LOOSENED absolute threshold (flow=3.0).

Derived from afg-b-l5 (the prior loop). Mechanically L5 was a no-op vs L4
(0.5 and 1.0 are equivalent predicates because net_flow is integer-valued
on this oracle -- trade sizes are integer contracts -- so the open interval
(0, 1) contains no admissible net_flow values).

Brief-summary context only (L1+L2+L3+L4+L5 summary_out, no other reads of
prior NOTES.md or any full_reasoning text):

  L1 (pure-ratio, |r|>=0.35):     WORSE than base (-53%, +13.5k extra admits).
  L2 (base AND ratio):            WORSE than base (-52%, +14.2k extra admits)
                                  -- ANDing admitted the UNION of admits.
  L3 (base OR ratio-with-floor):  EXACTLY equal to base -- ratio leg
                                  structurally dominated by absolute leg.
  L4 (ratio removed, flow=1.0):   BEATS base (+12.16% pnl: $1088 vs $970;
                                  -1,671 trades; sharpe 5.36 vs 4.58).
                                  Validates L1 monotone-yield rule:
                                  ~$70.6 per 1k extra skips.
  L5 (ratio removed, flow=0.5):   BIT-FOR-BIT IDENTICAL to L4. The
                                  flow_threshold lever has INTEGER
                                  RESOLUTION on this oracle; decimal-
                                  fraction tweaks below 1.0 are inert.

Per the L5 next text and the integer-resolution lesson: the only
informative single-parameter monotone changes along the absolute-
threshold axis are INTEGER STEPS from the effective L4=L5 state of
flow=1.0. Going DOWN to flow=0 degenerates (gate fires on |net|>=0
i.e. essentially always non-empty deque -> skip nearly all entries,
catastrophic). Going UP one integer step from flow=1 to flow=2 returns
to base (already known at $970 / 87,760 trades; no new info). Going UP
two integer steps from flow=1 to flow=3 is the most informative
remaining single-parameter test:

    skip iff |net_flow_window| >= 3.0  (10s window)

This is LOOSER than both L4 and base -- orders with |net_flow| in
[2, 3) that base would skip are now ADMITTED. L6 tests whether the L1
monotone-yield rule extrapolates to the loose side:

Hypothesis (informed only by L1+L2+L3+L4+L5 brief_summary plus the
integer-resolution finding from L5, plus mechanical inspection of
afg-b-l4 and afg-b-l5 source for class / parameter shape):

  - vs base (threshold=2): trade_count strictly > base (admitting
    orders with |net|=2 that base skips, since base uses >= 2).
    Actually wait -- L6's predicate is >= 3, so orders with
    |net|=2 are now SUBMITTED where base would SKIP them. So L6
    admits a strict superset of base's admits.
  - vs L4 (threshold=1): trade_count strictly > L4 (transitively).
  - pnl: by the L1 monotone-yield rule, extra admits beyond base
    cost ~$47-$70/1k pnl. The orders newly-admitted at |net|=2
    (and possibly |net|=2 only -- the [2,3) interval contains the
    single integer 2 on this oracle) are by hypothesis weakly
    anti-informative. Predicted: pnl drops below base's $970.
  - If pnl_L6 < $970, L1 monotone-yield rule extrapolates to the
    loose side, threshold sweep firmly maximized at flow=1 across
    integer values, no surprises on the loose side.
  - If pnl_L6 > $1088, the curve is non-monotone with a secondary
    maximum on the loose side -- much more surprising and would
    suggest the L1 rule was an artefact of the particular order
    distribution near |net|=1.5 rather than a general property of
    near-margin admits.
  - If pnl_L6 between $970 and $1088, the curve is monotone
    with peak at flow=1 (consistent with L4 being the integer
    optimum); pnl drops smoothly as threshold loosens.

The expected magnitude of the trade_count delta: depends on how
frequently 10s windows have |net_flow| exactly equal to 2 vs |net|
>=3. From the L4 vs base delta we know |net|=1 windows admit
~1,671 orders over 11 dates. The |net|=2 stratum likely contains
fewer orders (the magnitude distribution typically thins out), but
not catastrophically fewer.

Quantity invariant: orders are skipped or submitted unchanged.
Same as base + L1 + L2 + L3 + L4 + L5.

No look-ahead bias: only ticks with ts_event <= order.ts_init are
in the deque at decision time.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class AfgBL6Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for afg-b-l6.

    Parameters
    ----------
    window_seconds : float
        Rolling look-back window for trade prints, in seconds.
        Default 10.0 seconds (same as base + L1 + L2 + L3 + L4 + L5).
    flow_threshold : float
        Minimum absolute net signed flow (in contracts) to skip the
        order. Default 3.0 (LOOSENED from base/L2/L3's 2.0 and from
        L4/L5's effective 1.0; one integer step BEYOND base in the
        loose direction).
    """

    window_seconds: float = 10.0
    flow_threshold: float = 3.0


class AfgBL6Algorithm(ExecAlgorithm):
    """Aggressor-flow gate using a loosened absolute threshold (ratio leg absent).

    Opening orders (is_reduce_only == False):
      - Compute signed net flow over the same `window_seconds` window.
      - Skip BUY  entries when net_flow <= -flow_threshold.
      - Skip SELL entries when net_flow >=  flow_threshold.
      - Submit unconditionally when the deque is empty (warm-up) or the
        absolute threshold is not crossed in the adverse direction.
      - After any skip: _position_flat = True (next open unconditional;
        anti-cascade guarantee preserved from base + L1 + L2 + L3 + L4 + L5).

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).
    """

    def __init__(self, config: AfgBL6Config) -> None:
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
            f"AfgBL6Algorithm started "
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
        """Route order: submit or skip based on the loosened absolute aggressor-flow gate."""
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

        # Evaluate loosened absolute aggressor-flow gate.
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
    flow_threshold: float = 3.0,
) -> AfgBL6Algorithm:
    """Instantiate and return the AfgBL6Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_seconds : float
        Rolling window for aggressor-flow accumulation, in seconds. Default 10.0s.
    flow_threshold : float
        Minimum |net_flow| (in contracts) to skip the order. Default 3.0
        (LOOSENED from base/L2/L3's 2.0 and from L4/L5's effective 1.0).
    """
    config = AfgBL6Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        flow_threshold=flow_threshold,
    )
    return AfgBL6Algorithm(config=config)
