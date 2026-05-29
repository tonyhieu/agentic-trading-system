"""afg-f-l8 execution algorithm.

Per-iteration experiment, base_algo `aggressor-flow-gate`, context mode
`full-trace`, loop 8 (**final loop**). Starting point: `afg-f-l7` (prior loop).

Single behavioural change vs `afg-f-l7`:

  **window_seconds: 30.0 (l7) -> 60.0 (l8).**

  A *doubling* step, the largest single window-lever step in the arm.

  Loop 7 lengthened the window from 20 s (l6) to 30 s and produced the
  best-in-arm result on every metric tracked (pnl +32.59 % vs base,
  sharpe +1.81 vs base, drawdown best-in-arm, IS -4.58 % vs base,
  trade_count -2.86 % vs base -- still firmly in the selective-gate
  regime). The per-5s marginal P&L gain across the window sweep has
  been flat-to-rising for three consecutive lengthening experiments:

      loop 3 (10 s) -> loop 5 (15 s):  +0.508 %/5s
      loop 5 (15 s) -> loop 6 (20 s):  +1.408 %/5s
      loop 6 (20 s) -> loop 7 (30 s):  +1.572 %/5s
        (averaged over a 10 s extension)

  No diminishing-returns signal has appeared. trade_count has been
  essentially flat across the entire 15-30 s sweep (104,836 -> 104,515
  -> 104,138 = a 0.7 % total reduction over doubling the window length),
  so the selective regime is robust across the full range tested.

  Loop 7's forward-looking note priority-1'd `window_seconds = 60.0` for
  this loop with a DOUBLING step (not the conservative 45 s step),
  reasoning that:

    (a) the per-5s pace argument predicts continued gain at 45 s (low
        information return);
    (b) the trade_count headroom at 30 s (104,138 = 97.1 % of base)
        gives substantial buffer before anti-cascade alternation would
        dominate (which would put trade_count near 85,000);
    (c) this is the FINAL loop of the arm, so the test should bound
        the lever's productive range -- a doubling step probes an
        entire octave of unknown parameter space and disambiguates
        between continued-gain, saturation, and degeneracy outcomes
        more decisively than any smaller step;
    (d) a "no further gain" or "degeneracy onset" result at 60 s is
        still informative -- it brackets the window-lever boundary
        within [30, 60] for future arms.

  All other parameters preserved unchanged from afg-f-l3 through afg-f-l7:
    flow_threshold = 1.0 contracts (catches |net_flow| >= 1).
    min_gross_volume = 0.0 contracts (floor effectively disabled).

Decision logic (effective, unchanged from afg-f-l3 onward in structure):

    if gross_volume < min_gross_volume  (== 0.0, never true):  submit
    elif side == BUY  and net_flow <= -flow_threshold:         SKIP
    elif side == SELL and net_flow >= +flow_threshold:         SKIP
    else:                                                       submit

  -- only the deque's effective look-back grows from 30 s (l7) to 60 s (l8).

All other behaviours (anti-cascade `_position_flat=True` after any skip,
reduce-only orders always execute, quantity invariant preserved, O(1)
running sums for both `_net_flow` and `_gross_volume`) are preserved
unchanged from base / afg-f-l1 / afg-f-l2 / afg-f-l3 / afg-f-l4 /
afg-f-l5 / afg-f-l6 / afg-f-l7.

No look-ahead bias: only trade ticks with ts_event <= order.ts_init
are in the deque at decision time (replay is strictly chronological;
the prune uses order.ts_init, never a future timestamp). Lengthening
the window widens the look-*back* -- it does not change look-ahead
semantics. The cutoff_ns = ts_init - window_ns arithmetic remains
correct for any window size, including 60 s.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class AggressorFlowGateL8Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the afg-f-l8 execution algorithm.

    Parameters
    ----------
    window_seconds : float
        Rolling look-back window for trade prints, in seconds.
        Default **60.0 seconds** -- doubled from afg-f-l7's 30.0 s
        (which itself extended afg-f-l6's 20.0 s via a 10 s jump, on
        the same accelerating-marginal-gain diagnosis that now
        motivates the doubling step). The 60 s setting is the
        priority-1 final test of the window-length lever, chosen to
        bound the lever's productive range in a single loop:
        durability continues past 60 s (push to 90-120 s in a future
        arm); saturation between 30 s and 60 s (loop 7's 30 s is the
        operating point and the arm closes with the lever bounded);
        early-degeneracy onset between 30 s and 60 s (loop 7's 30 s
        is the operating point and the arm closes having located the
        degeneracy boundary within [30, 60]).
    flow_threshold : float
        Minimum absolute net signed flow (in contracts) to trigger a skip.
        For BUY  orders: skip when net_flow <= -flow_threshold.
        For SELL orders: skip when net_flow >= +flow_threshold.
        Default 1.0 contracts (carried forward from afg-f-l3 through
        afg-f-l7; the integer equivalence class (0, 1] catches all
        windows where buyers and sellers differ by even one contract).
    min_gross_volume : float
        Minimum gross in-window trade volume (sum of |size|) required
        before the gate may fire. Default 0.0 contracts -- effectively
        disabled (gross_volume is always >= 0). Carried forward
        unchanged from afg-f-l2 onward (revert of loop 1's harmful
        floor). Retained in the config so future loops or arms can
        re-enable the floor with a different value without code
        changes; at 0.0 it is a no-op.
    """

    window_seconds: float = 60.0
    flow_threshold: float = 1.0
    min_gross_volume: float = 0.0


class AggressorFlowGateL8Algorithm(ExecAlgorithm):
    """Aggressor-flow gate with a 60 s window (doubled from l7 30 s / l6 20 s / l5 15 s / base 10 s).

    Opening orders (is_reduce_only == False):
      - Maintain a 60 s deque of signed-volume trade prints with O(1)
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

    def __init__(self, config: AggressorFlowGateL8Config) -> None:
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
            f"AggressorFlowGateL8Algorithm started "
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

        At flow_threshold=1.0 with the 60 s window, that catches any
        60 s window where buyers and sellers differ by even one contract
        -- structurally the same gate condition as afg-f-l3 through
        afg-f-l7 but evaluated on a longer look-back.

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
    window_seconds: float = 60.0,
    flow_threshold: float = 1.0,
    min_gross_volume: float = 0.0,
) -> AggressorFlowGateL8Algorithm:
    """Instantiate and return the AggressorFlowGateL8Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_seconds : float
        Rolling window for aggressor-flow accumulation, in seconds.
        Default **60.0 s** (doubled from afg-f-l7's 30.0 s -- the
        loop 8 treatment under test, the final loop of the arm. The
        doubling step is the highest-information one-loop move because
        it bounds the window-lever boundary in a single iteration).
    flow_threshold : float
        Minimum absolute net aggressor flow (contracts) to trigger a skip.
        Default 1.0 contracts (carried forward from afg-f-l3 onward --
        catches |net_flow| >= 1 windows).
    min_gross_volume : float
        Minimum in-window gross trade volume required before the gate
        may fire. Default 0.0 (floor effectively disabled; carried
        forward from afg-f-l2 onward).
    """
    config = AggressorFlowGateL8Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        flow_threshold=flow_threshold,
        min_gross_volume=min_gross_volume,
    )
    return AggressorFlowGateL8Algorithm(config=config)
