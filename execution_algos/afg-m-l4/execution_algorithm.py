"""afg-m-l4 execution algorithm.

Per-iteration experiment, base_algo `aggressor-flow-gate`, context mode
`metrics-only`, loop 4. Starting point: afg-m-l3.

This variant keeps the afg-m-l3 EXPONENTIALLY-DECAYED signed-flow gate but
makes it markedly TIGHTER. Numbers-only read of the prior loops: loop 3 has
the worst pnl_vs_base (-38.0%) and worst Sharpe (3.30), and also the highest
trade_count (113358, vs 107623/106724 for loops 1/2). Loop 1 — the least bad
P&L (-7.3%) — sits at trade_count 107623. Pushing trade_count above ~107k
coincided with P&L and Sharpe collapsing. Loop-4 reverses loop-3's direction:
  - flow_threshold:  2.5  -> 0.7  (tighter gate; trips on weaker imbalances)
  - window_seconds:  4.0  -> 9.0  (longer look-back => larger decayed flow,
    so the now-lower threshold is reached more readily)
  - half_life_seconds: 4.0 -> 3.0 (modestly faster decay so recent prints
    still dominate within the longer window)
The goal is to skip more adverse-flow orders so trade_count drops back toward
loop 1's ~107.6k level, expecting P&L and Sharpe to recover.

Variant of `aggressor-flow-gate`. The base algo gates the OPEN leg of each
oracle signal on a FLAT-window net signed aggressor-flow signal (every trade
print in the last `window_seconds` weighted equally). This variant replaces
that flat sum with an EXPONENTIALLY-DECAYED signed flow:

    decayed_flow(T) = sum( signed_vol_i * 0.5 ** (age_i / half_life) )

where `age_i = T - ts_event_i` for each in-window trade print, and `T` is the
order's `ts_init`. Recent aggressor prints therefore dominate the gate
decision, while stale prints fade out smoothly instead of dropping abruptly
at the window edge.

Algorithm:
  - Maintain a deque of (ts_event_ns, signed_volume) from trade ticks
    delivered via on_trade_tick().  signed_volume = +size for BUYER
    aggressor (crossed the ask), -size for SELLER aggressor (hit the bid),
    0 for NO_AGGRESSOR.
  - At each order event, prune entries older than `window_seconds`, then
    recompute the decayed flow by iterating the in-window deque.
  - For BUY  orders: skip when decayed_flow <= -flow_threshold (sell-dominated)
  - For SELL orders: skip when decayed_flow >=  flow_threshold (buy-dominated)
  - No signal (empty window or |decayed_flow| < threshold): submit.
  - Reduce-only / position-closing orders always execute.
  - After any skip: _position_flat = True so the NEXT open is unconditional
    (anti-cascade guarantee consistent with all passing algorithms).

No look-ahead bias: only trade ticks with ts_event <= order.ts_init are in
the deque at decision time (replay is strictly chronological; the window
prune and the decay ages both use the order's ts_init, never a future
timestamp).
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class AggressorFlowDecayGateConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the afg-m-l4 execution algorithm.

    Parameters
    ----------
    window_seconds : float
        Rolling look-back window for trade prints, in seconds. Prints older
        than this are pruned and contribute nothing. Default 9.0 seconds
        (loop-4: lengthened from afg-m-l3's 4.0s so more prints accumulate
        and the decayed-flow magnitude is larger -> the lower threshold is
        reached more readily -> more skips).
    half_life_seconds : float
        Half-life of the exponential decay applied to each in-window print.
        A print of age == half_life_seconds contributes half its signed
        volume; age == 2 * half_life_seconds contributes a quarter; and so
        on. Default 3.0 seconds (loop-4: shortened from afg-m-l3's 4.0s so
        recent prints still dominate within the longer 9.0s window).
    flow_threshold : float
        Minimum absolute decayed net signed flow (in contracts) to trigger a
        skip. For BUY orders: skip when decayed_flow <= -flow_threshold.
        For SELL orders: skip when decayed_flow >= flow_threshold.
        Default 0.7 contracts (loop-4: lowered from afg-m-l3's 2.5 to make
        the gate much tighter -- it trips on weaker imbalances, so far more
        orders are skipped).
    """

    window_seconds: float = 9.0
    half_life_seconds: float = 3.0
    flow_threshold: float = 0.7


class AggressorFlowDecayGateAlgorithm(ExecAlgorithm):
    """Execution algorithm gating open orders on recency-weighted aggressor flow.

    Opening orders (is_reduce_only == False):
      - Recompute the exponentially-decayed net signed aggressor flow over the
        last `window_seconds`. BUY aggressor prints contribute +size, SELLER
        contributes -size, each weighted by 0.5 ** (age / half_life).
      - Skip BUY  entries when decayed_flow <= -flow_threshold (sell pressure).
      - Skip SELL entries when decayed_flow >=  flow_threshold (buy pressure).
      - Submit unconditionally when no trade data is available (warm-up) or
        when |decayed_flow| < threshold (neutral / ambiguous period).
      - After any skip: _position_flat = True (next open unconditional).

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is ever modified. Quantity invariant always preserved.
    """

    def __init__(self, config: AggressorFlowDecayGateConfig) -> None:
        super().__init__(config=config)
        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._half_life_ns: float = float(config.half_life_seconds * 1_000_000_000)
        self._flow_threshold: float = config.flow_threshold

        # Deque of (ts_event_ns: int, signed_vol: float)
        # signed_vol = +size (BUYER), -size (SELLER), 0 (NO_AGGRESSOR)
        self._flow_deque: deque[tuple[int, float]] = deque()

        # Safety: forced re-entry after any skip to prevent cascade
        self._position_flat: bool = True

        # Subscription tracking
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"AggressorFlowDecayGateAlgorithm started "
            f"(window={self._window_ns / 1e9:.1f}s, "
            f"half_life={self._half_life_ns / 1e9:.1f}s, "
            f"flow_threshold={self._flow_threshold:.2f} contracts)."
        )

    def on_reset(self) -> None:
        self._flow_deque.clear()
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
    # Trade tick handler — append to rolling signed flow deque
    # ------------------------------------------------------------------

    def on_trade_tick(self, tick) -> None:
        """Receive a trade tick and append its signed volume to the deque."""
        aggressor = tick.aggressor_side
        size = float(str(tick.size))

        if aggressor == AggressorSide.BUYER:
            signed_vol = size
        elif aggressor == AggressorSide.SELLER:
            signed_vol = -size
        else:
            # NO_AGGRESSOR — treat as neutral; do not bias the flow signal
            signed_vol = 0.0

        self._flow_deque.append((tick.ts_event, signed_vol))

    # ------------------------------------------------------------------
    # Flow evaluation
    # ------------------------------------------------------------------

    def _prune_window(self, cutoff_ns: int) -> None:
        """Remove deque entries older than cutoff_ns (window edge)."""
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            self._flow_deque.popleft()

    def _decayed_flow(self, now_ns: int) -> float:
        """Exponentially-decayed net signed flow as of now_ns.

        Each in-window print contributes signed_vol * 0.5 ** (age / half_life),
        where age = now_ns - ts_event_ns >= 0.
        """
        total = 0.0
        half_life = self._half_life_ns
        for ts_event_ns, signed_vol in self._flow_deque:
            age = now_ns - ts_event_ns
            if age < 0:
                age = 0  # defensive: same-ns ticks treated as age 0
            total += signed_vol * (0.5 ** (age / half_life))
        return total

    def _flow_is_adverse(self, order) -> bool:
        """Return True if decayed aggressor flow is adverse for this order.

        BUY  order: adverse when decayed_flow <= -flow_threshold (sellers dominate)
        SELL order: adverse when decayed_flow >=  flow_threshold (buyers dominate)

        Returns False (do not skip) when:
          - Flow deque is empty (no trades seen yet — warm-up)
          - |decayed_flow| < flow_threshold (neutral / near-balanced window)
        """
        # Prune stale entries relative to order timestamp
        cutoff_ns = order.ts_init - self._window_ns
        self._prune_window(cutoff_ns)

        if not self._flow_deque:
            # No trade data in window — do not gate (warm-up / thin market)
            self.log.debug(
                f"No trade data in window; submitting {order.client_order_id} "
                f"unconditionally."
            )
            return False

        net = self._decayed_flow(order.ts_init)

        if order.side == OrderSide.BUY:
            if net <= -self._flow_threshold:
                self.log.debug(
                    f"BUY adverse decayed flow: {net:.3f} <= "
                    f"-threshold={-self._flow_threshold:.2f}; SKIP."
                )
                return True
        else:  # SELL
            if net >= self._flow_threshold:
                self.log.debug(
                    f"SELL adverse decayed flow: {net:.3f} >= "
                    f"threshold={self._flow_threshold:.2f}; SKIP."
                )
                return True

        return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on recency-weighted aggressor flow."""
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

        # Evaluate decayed-aggressor-flow gate.
        if self._flow_is_adverse(order):
            self.log.info(
                f"SKIP {order.client_order_id} — adverse decayed aggressor flow "
                f"(side={'BUY' if order.side == OrderSide.BUY else 'SELL'})."
            )
            self._position_flat = True
            # Do NOT call submit_order — quantity invariant preserved.
        else:
            self.log.debug(
                f"SUBMIT {order.client_order_id} — decayed flow neutral/favorable."
            )
            self._position_flat = False
            self.submit_order(order)

    def on_quote_tick(self, tick) -> None:
        """Passively receive quote ticks (kept for quote-cache side-effects)."""
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_seconds: float = 9.0,
    half_life_seconds: float = 3.0,
    flow_threshold: float = 0.7,
) -> AggressorFlowDecayGateAlgorithm:
    """Instantiate and return the AggressorFlowDecayGateAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_seconds : float
        Rolling window for aggressor-flow accumulation, in seconds. Default 9.0s
        (loop-4: lengthened from afg-m-l3's 4.0s).
    half_life_seconds : float
        Half-life of the exponential decay weighting, in seconds. Default 3.0s
        (loop-4: shortened from afg-m-l3's 4.0s).
    flow_threshold : float
        Minimum absolute decayed net aggressor flow (contracts) to trigger a
        skip. Default 0.7 contracts (loop-4: lowered from afg-m-l3's 2.5 for
        a much tighter gate).
    """
    config = AggressorFlowDecayGateConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        half_life_seconds=half_life_seconds,
        flow_threshold=flow_threshold,
    )
    return AggressorFlowDecayGateAlgorithm(config=config)
