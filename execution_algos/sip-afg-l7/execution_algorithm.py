"""sip-afg-l7 — volume-normalized imbalance ratio AND-gate.

Builds on ``aggressor-flow-gate`` (the base algorithm under study).
The base maintains a 10s rolling window of signed aggressor volume
(BUYER aggressor → +size, SELLER aggressor → -size) and skips
opening orders when |net_flow| >= flow_threshold (default 2.0) and
adverse to the order side.

Identified weakness of the base mechanism
------------------------------------------
The base's gate fires on an ABSOLUTE contract count
(``|net_flow| >= 2.0``) regardless of total window volume. The
statistical significance of "2 contracts net adverse" depends
strongly on how many trades occurred in the window:

  - Slow regime (e.g. 4 total trades summing |signed_vol|=4):
    net_flow=+2 means 75% buy-side. Strong directional signal.
  - Fast regime (e.g. 100 trades summing |signed_vol|=100):
    net_flow=+2 means 51% buy-side. Statistical noise.

The base treats both regimes identically. In the fast regime, the
gate fires on near-balanced flow and skips an order that has no
meaningful adverse directional signal — likely a false-positive
skip.

Modification — single-axis change
---------------------------------
Add a SECOND, conjunctive gate condition: require the directional
imbalance to also be **proportionally** meaningful. Specifically:

  imbalance_ratio = |net_flow| / max(total_window_vol, 1.0)
  skip iff (|net_flow| >= flow_threshold) AND (imbalance_ratio >= ratio_threshold)

with ``ratio_threshold = 0.20`` by default — i.e. the directional
share must be at least 20% of total window volume one-sided. This is
a strictly tighter conjunction than the base, so it can only
DECREASE the skip rate — fewer skips, every skip strictly stronger
in proportional terms.

Expected direction (hypothesis prediction):
  - realized_pnl: small positive vs base (eliminate noise skips in
    high-volume regimes that were not actually adverse).
  - trade_count: increases (some base skips are now submitted).
  - sharpe / max_drawdown: marginal improvement if removed skips
    were noise; flat-to-slight regression if they were genuinely
    adverse.
  - mean_slippage: unchanged at 0.0 (gate-only; no fill mechanics).

All constraint compliance is identical to base:
  - Quantity invariant: only submit/skip; never modify quantity.
  - top_of_book_only: no fill mechanics change.
  - participation_cap: no order sizing.
  - intraday_flat: reduce-only orders always submit.

No look-ahead bias: trade-tick deque pruning uses ``order.ts_init``
as the reference time; only ticks with ``tick.ts_event <=
order.ts_init`` are considered (backtest replay is strictly
chronological).

Anti-cascade safety: identical to base — after any skip,
``_position_flat = True`` so the next opening order submits
unconditionally.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class SipAfgL7Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the sip-afg-l7 execution algorithm.

    Parameters
    ----------
    window_seconds : float
        Rolling look-back window for trade prints, in seconds.
        Default 10.0 (identical to base).
    flow_threshold : float
        Minimum absolute net signed flow (in contracts) for the
        primary (count-based) condition. Default 2.0 (identical to
        base).
    ratio_threshold : float
        Minimum |net_flow| / total_window_volume for the secondary
        (proportional) condition. Default 0.20 — the imbalance must
        be at least 20% of total window volume one-sided to count
        as a meaningful directional signal.
    """

    window_seconds: float = 10.0
    flow_threshold: float = 2.0
    ratio_threshold: float = 0.20


class SipAfgL7Algorithm(ExecAlgorithm):
    """Aggressor-flow gate with conjunctive volume-normalized
    imbalance-ratio condition.

    Decision rule for an opening order:
      cutoff_ns = order.ts_init - window_ns
      prune deque to cutoff_ns
      net_flow   = signed sum in window
      total_vol  = |signed| sum in window
      ratio      = |net_flow| / max(total_vol, 1.0)
      adverse_count = (BUY  and net_flow <= -flow_threshold) or
                      (SELL and net_flow >=  flow_threshold)
      skip iff adverse_count AND (ratio >= ratio_threshold)
    """

    def __init__(self, config: SipAfgL7Config) -> None:
        super().__init__(config=config)
        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._flow_threshold: float = float(config.flow_threshold)
        self._ratio_threshold: float = float(config.ratio_threshold)

        # Deque of (ts_event_ns: int, signed_vol: float). signed_vol
        # = +size (BUYER), -size (SELLER), 0 (NO_AGGRESSOR).
        self._flow_deque: deque[tuple[int, float]] = deque()

        # Running sum of signed volume in the deque (O(1) updates).
        self._net_flow: float = 0.0
        # Running sum of |signed_vol| in the deque (denominator).
        self._abs_flow: float = 0.0

        # Anti-cascade safety: forced unconditional submit after any
        # skip (identical semantics to base aggressor-flow-gate).
        self._position_flat: bool = True

        # Subscription tracking
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"SipAfgL7Algorithm started "
            f"(window={self._window_ns / 1e9:.1f}s, "
            f"flow_threshold={self._flow_threshold:.2f}, "
            f"ratio_threshold={self._ratio_threshold:.2f})."
        )

    def on_reset(self) -> None:
        self._flow_deque.clear()
        self._net_flow = 0.0
        self._abs_flow = 0.0
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
    # Trade tick handler — maintain rolling signed + |signed| flow.
    # ------------------------------------------------------------------

    def on_trade_tick(self, tick) -> None:
        """Receive a trade tick and update the rolling flow deque."""
        aggressor = tick.aggressor_side
        size = float(str(tick.size))

        if aggressor == AggressorSide.BUYER:
            signed_vol = size
        elif aggressor == AggressorSide.SELLER:
            signed_vol = -size
        else:
            # NO_AGGRESSOR — neutral; do not bias the flow signal.
            # Contributes 0 to net_flow AND 0 to total_volume (its
            # direction is unknown, so cannot count it as
            # directional volume either).
            signed_vol = 0.0

        self._flow_deque.append((tick.ts_event, signed_vol))
        self._net_flow += signed_vol
        self._abs_flow += abs(signed_vol)

    # ------------------------------------------------------------------
    # Flow evaluation
    # ------------------------------------------------------------------

    def _prune_window(self, cutoff_ns: int) -> None:
        """Remove deque entries older than cutoff_ns."""
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            _, old_vol = self._flow_deque.popleft()
            self._net_flow -= old_vol
            self._abs_flow -= abs(old_vol)

    def _flow_is_adverse(self, order) -> bool:
        """Return True if net aggressor flow is adverse AND
        proportionally meaningful for this order direction.

        BUY  order: adverse when net_flow <= -flow_threshold
        SELL order: adverse when net_flow >=  flow_threshold
        AND in both cases: |net_flow| / total_window_volume >= ratio_threshold.

        Returns False (do not skip) when:
          - Flow deque is empty (warm-up).
          - |net_flow| < flow_threshold (count gate fails).
          - imbalance ratio < ratio_threshold (proportion gate fails).
        """
        # Prune stale entries relative to order timestamp.
        cutoff_ns = order.ts_init - self._window_ns
        self._prune_window(cutoff_ns)

        if not self._flow_deque:
            self.log.debug(
                f"No trade data in window; submitting {order.client_order_id} "
                f"unconditionally."
            )
            return False

        net = self._net_flow
        # Floor abs_flow at 1.0 to avoid divide-by-zero. With a non-empty
        # deque whose only entries are NO_AGGRESSOR (abs_flow=0), the
        # ratio is 0/1=0 and the gate cannot fire — correct: no signed
        # directional flow means no directional signal.
        abs_vol = max(self._abs_flow, 1.0)
        abs_net = abs(net)
        ratio = abs_net / abs_vol

        # Count gate.
        if order.side == OrderSide.BUY:
            count_adverse = net <= -self._flow_threshold
        else:  # SELL
            count_adverse = net >= self._flow_threshold

        if not count_adverse:
            return False

        # Proportion gate (conjunctive).
        if ratio < self._ratio_threshold:
            self.log.debug(
                f"Adverse count met but proportion gate fails: "
                f"|net|={abs_net:.2f} abs_vol={abs_vol:.2f} ratio={ratio:.3f} "
                f"< ratio_threshold={self._ratio_threshold:.2f}; SUBMIT."
            )
            return False

        # Both gates met → adverse.
        self.log.debug(
            f"Adverse flow + proportion gate met: net_flow={net:.2f}, "
            f"abs_vol={abs_vol:.2f}, ratio={ratio:.3f} "
            f">= ratio_threshold={self._ratio_threshold:.2f}; SKIP."
        )
        return True

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on volume-normalized
        aggressor-flow gate."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat
        # compliance.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Forced re-entry after a skip — always submit to prevent
        # cascade (identical to base).
        if self._position_flat:
            self.log.debug(
                f"Re-entry (first or post-skip); submitting "
                f"{order.client_order_id} unconditionally."
            )
            self._position_flat = False
            self.submit_order(order)
            return

        # Evaluate conjunctive gate.
        if self._flow_is_adverse(order):
            self.log.info(
                f"SKIP {order.client_order_id} — adverse aggressor flow "
                f"(net_flow={self._net_flow:.2f}, side="
                f"{'BUY' if order.side == OrderSide.BUY else 'SELL'})."
            )
            self._position_flat = True
            # Do NOT call submit_order — quantity invariant preserved.
        else:
            self.log.debug(
                f"SUBMIT {order.client_order_id} — gate not met "
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
    flow_threshold: float = 2.0,
    ratio_threshold: float = 0.20,
) -> SipAfgL7Algorithm:
    """Instantiate and return the SipAfgL7Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_seconds : float
        Rolling window for aggressor-flow accumulation, in seconds.
        Default 10.0s (identical to base).
    flow_threshold : float
        Count-gate threshold in contracts. Default 2.0 (identical to base).
    ratio_threshold : float
        Proportion-gate threshold (|net_flow|/total_vol). Default 0.20.
    """
    config = SipAfgL7Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        flow_threshold=flow_threshold,
        ratio_threshold=ratio_threshold,
    )
    return SipAfgL7Algorithm(config=config)
