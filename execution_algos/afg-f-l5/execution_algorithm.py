"""afg-f-l5 execution algorithm.

Per-iteration experiment, base_algo `aggressor-flow-gate`, context mode
`full-trace`, loop 5. Starting point: `afg-f-l4` (prior loop).

Single behavioural change vs `afg-f-l4` (after correction of l4's
known-harmful default):

  **window_seconds: 5.0 (l4) -> 15.0 (l5).**

  The 5.0 -> 10.0 step is a correction (l4's halving was empirically
  inferior per its own NOTES.md and forward-looking note). The 10.0 ->
  15.0 step is the hypothesis under test: that the durability signal
  loop 4 documented (10 s integral does real work that the 5 s window
  cannot reproduce) continues to improve with additional samples,
  subject to the long-window degeneracy risk loop 4 flagged for 20 s+.

  All other parameters preserved unchanged from afg-f-l3 / afg-f-l4:
    flow_threshold = 1.0 contracts (catches |net_flow| >= 1).
    min_gross_volume = 0.0 contracts (floor effectively disabled).

Decision logic (effective, unchanged from afg-f-l3 / afg-f-l4 in structure):

    if gross_volume < min_gross_volume  (== 0.0, never true):  submit
    elif side == BUY  and net_flow <= -flow_threshold:         SKIP
    elif side == SELL and net_flow >= +flow_threshold:         SKIP
    else:                                                       submit

  -- only the deque's effective look-back grows from 5 s (l4) to 15 s (l5).

All other behaviours (anti-cascade `_position_flat=True` after any skip,
reduce-only orders always execute, quantity invariant preserved, O(1)
running sums for both `_net_flow` and `_gross_volume`) are preserved
unchanged from base / afg-f-l1 / afg-f-l2 / afg-f-l3 / afg-f-l4.

No look-ahead bias: only trade ticks with ts_event <= order.ts_init
are in the deque at decision time (replay is strictly chronological;
the prune uses order.ts_init, never a future timestamp). Lengthening
the window widens the look-*back* -- it does not change look-ahead
semantics. The cutoff_ns = ts_init - window_ns arithmetic remains
correct for any window size.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class AggressorFlowGateL5Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the afg-f-l5 execution algorithm.

    Parameters
    ----------
    window_seconds : float
        Rolling look-back window for trade prints, in seconds.
        Default **15.0 seconds** -- lengthened from afg-f-l3 (10.0 s,
        the loop-3 operating point that produced +10.39 % P&L vs base)
        and from afg-f-l4's empirically-inferior 5.0 s halving. The
        longer window tests the durability hypothesis from loop 4: that
        additional samples improve the gate's per-skip edge, subject to
        the long-window degeneracy risk loop 4 flagged for 20 s+.
    flow_threshold : float
        Minimum absolute net signed flow (in contracts) to trigger a skip.
        For BUY  orders: skip when net_flow <= -flow_threshold.
        For SELL orders: skip when net_flow >= +flow_threshold.
        Default 1.0 contracts (carried forward from afg-f-l3 / afg-f-l4;
        the integer equivalence class (0, 1] catches all windows where
        buyers and sellers differ by even one contract).
    min_gross_volume : float
        Minimum gross in-window trade volume (sum of |size|) required
        before the gate may fire. Default 0.0 contracts -- effectively
        disabled (gross_volume is always >= 0). Carried forward
        unchanged from afg-f-l2 / afg-f-l3 / afg-f-l4 (revert of loop
        1's harmful floor). Retained in the config so future loops can
        re-enable the floor with a different value without code changes;
        at 0.0 it is a no-op.
    """

    window_seconds: float = 15.0
    flow_threshold: float = 1.0
    min_gross_volume: float = 0.0


class AggressorFlowGateL5Algorithm(ExecAlgorithm):
    """Aggressor-flow gate with a 15 s window (lengthened from base 10 s / l4 5 s).

    Opening orders (is_reduce_only == False):
      - Maintain a 15 s deque of signed-volume trade prints with O(1)
        running sums for net flow and gross volume.
      - With the default config (min_gross_volume=0.0), the gross-volume
        floor is effectively disabled and the algo collapses to:
            skip BUY  when net_flow <= -flow_threshold  (= -1.0)
            skip SELL when net_flow >=  flow_threshold  (= +1.0)
      - Submit unconditionally when no trade data is available (warm-up).
      - After any skip: _position_flat = True (next open unconditional).

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is ever modified. Quantity invariant always preserved.
    """

    def __init__(self, config: AggressorFlowGateL5Config) -> None:
        super().__init__(config=config)
        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._flow_threshold: float = config.flow_threshold
        self._min_gross_volume: float = config.min_gross_volume

        # Deque of (ts_event_ns: int, signed_vol: float)
        # signed_vol = +size (BUYER), -size (SELLER), 0 (NO_AGGRESSOR)
        self._flow_deque: deque[tuple[int, float]] = deque()

        # O(1) running aggregates over the deque
        self._net_flow: float = 0.0
        self._gross_volume: float = 0.0

        # Safety: forced re-entry after any skip to prevent cascade
        self._position_flat: bool = True

        # Subscription tracking
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"AggressorFlowGateL5Algorithm started "
            f"(window={self._window_ns / 1e9:.1f}s, "
            f"flow_threshold={self._flow_threshold:.2f} contracts, "
            f"min_gross_volume={self._min_gross_volume:.2f} contracts)."
        )

    def on_reset(self) -> None:
        self._flow_deque.clear()
        self._net_flow = 0.0
        self._gross_volume = 0.0
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
    # Trade tick handler -- maintain rolling signed + gross aggregates
    # ------------------------------------------------------------------

    def on_trade_tick(self, tick) -> None:
        """Receive a trade tick and update the rolling deque + aggregates."""
        aggressor = tick.aggressor_side
        size = float(str(tick.size))

        if aggressor == AggressorSide.BUYER:
            signed_vol = size
        elif aggressor == AggressorSide.SELLER:
            signed_vol = -size
        else:
            # NO_AGGRESSOR -- treat as neutral (consistent with base algo).
            signed_vol = 0.0

        self._flow_deque.append((tick.ts_event, signed_vol))
        self._net_flow += signed_vol
        self._gross_volume += abs(signed_vol)

    # ------------------------------------------------------------------
    # Flow + volume evaluation
    # ------------------------------------------------------------------

    def _prune_window(self, cutoff_ns: int) -> None:
        """Remove deque entries older than cutoff_ns, updating both sums."""
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            _, old_vol = self._flow_deque.popleft()
            self._net_flow -= old_vol
            self._gross_volume -= abs(old_vol)

    def _flow_is_adverse(self, order) -> bool:
        """Return True if the gate should SKIP this order.

        With the default config (min_gross_volume=0.0), the gross-volume
        floor never fires (gross_volume >= 0 always). The skip logic
        therefore reduces to:

          BUY  order: skip when net_flow <= -flow_threshold (sellers)
          SELL order: skip when net_flow >=  flow_threshold (buyers)

        At flow_threshold=1.0 with the 15 s window, that catches any
        15 s window where buyers and sellers differ by even one contract
        -- structurally the same gate condition as afg-f-l3 / afg-f-l4
        but evaluated on a longer look-back.

        Returns False (do not skip) when:
          - Flow deque is empty (warm-up).
          - Gross in-window volume below `min_gross_volume`
            (no-op at default 0.0; retained for future-loop flexibility).
          - |net_flow| < flow_threshold (neutral / near-balanced).
        """
        # Prune stale entries relative to order timestamp
        cutoff_ns = order.ts_init - self._window_ns
        self._prune_window(cutoff_ns)

        if not self._flow_deque:
            # No trade data in window -- do not gate (warm-up / thin market)
            self.log.debug(
                f"No trade data in window; submitting {order.client_order_id} "
                f"unconditionally."
            )
            return False

        # Floor check (no-op at default min_gross_volume=0.0).
        if self._gross_volume < self._min_gross_volume:
            self.log.debug(
                f"Gross volume below floor (gross={self._gross_volume:.2f} "
                f"< min={self._min_gross_volume:.2f}); gate disabled, "
                f"submitting {order.client_order_id}."
            )
            return False

        net = self._net_flow

        if order.side == OrderSide.BUY:
            if net <= -self._flow_threshold:
                self.log.debug(
                    f"BUY adverse flow: net_flow={net:.2f} <= "
                    f"-threshold={-self._flow_threshold:.2f} "
                    f"(gross={self._gross_volume:.2f}); SKIP."
                )
                return True
        else:  # SELL
            if net >= self._flow_threshold:
                self.log.debug(
                    f"SELL adverse flow: net_flow={net:.2f} >= "
                    f"threshold={self._flow_threshold:.2f} "
                    f"(gross={self._gross_volume:.2f}); SKIP."
                )
                return True

        return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on flow + (disabled) volume gate."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute -- intraday_flat compliance.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Forced re-entry after a skip -- always submit to prevent cascade.
        if self._position_flat:
            self.log.debug(
                f"Re-entry (first or post-skip); submitting "
                f"{order.client_order_id} unconditionally."
            )
            self._position_flat = False
            self.submit_order(order)
            return

        # Evaluate the flow + (disabled) volume gate.
        if self._flow_is_adverse(order):
            self.log.info(
                f"SKIP {order.client_order_id} -- adverse aggressor flow "
                f"(net_flow={self._net_flow:.2f}, "
                f"gross={self._gross_volume:.2f}, side="
                f"{'BUY' if order.side == OrderSide.BUY else 'SELL'})."
            )
            self._position_flat = True
            # Do NOT call submit_order -- quantity invariant preserved.
        else:
            self.log.debug(
                f"SUBMIT {order.client_order_id} -- flow neutral/favorable "
                f"(net_flow={self._net_flow:.2f}, "
                f"gross={self._gross_volume:.2f})."
            )
            self._position_flat = False
            self.submit_order(order)

    def on_quote_tick(self, tick) -> None:
        """Passively receive quote ticks (kept for quote-cache side-effects)."""
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_seconds: float = 15.0,
    flow_threshold: float = 1.0,
    min_gross_volume: float = 0.0,
) -> AggressorFlowGateL5Algorithm:
    """Instantiate and return the AggressorFlowGateL5Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_seconds : float
        Rolling window for aggressor-flow accumulation, in seconds.
        Default **15.0 s** (lengthened from afg-f-l3's 10.0 s and from
        afg-f-l4's empirically-inferior 5.0 s -- the loop 5 treatment
        under test).
    flow_threshold : float
        Minimum absolute net aggressor flow (contracts) to trigger a skip.
        Default 1.0 contracts (carried forward from afg-f-l3 / afg-f-l4
        -- catches |net_flow| >= 1 windows).
    min_gross_volume : float
        Minimum in-window gross trade volume required before the gate
        may fire. Default 0.0 (floor effectively disabled; carried
        forward from afg-f-l2 / afg-f-l3 / afg-f-l4).
    """
    config = AggressorFlowGateL5Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        flow_threshold=flow_threshold,
        min_gross_volume=min_gross_volume,
    )
    return AggressorFlowGateL5Algorithm(config=config)
