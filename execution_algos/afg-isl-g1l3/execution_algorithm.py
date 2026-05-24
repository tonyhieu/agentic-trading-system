"""afg-isl-g1l3 — island-1, generation 1, loop 3.

Single-window aggressor-flow gate with a NARROW PRICE-CONFIRMATION
override (do not loosen the gate broadly; admit only specific
adverse-flow skips where mid has already moved favorably).

Why this design (vs g1l1, g1l2):

  g1l1 added a two-window "persistence + reversal" structure where the
  short-window flow-direction *flip* was used as a proxy for price
  reversal. Falsified: flow-flip is NOT price reversal, flow direction
  can flip while mid is still mid-adverse, and the "reversal exception"
  entries fired at adverse mids and were net P&L destroyers
  (pnl -43.1% vs base).

  g1l2 reverted g1l1's structure entirely and tested a different lever:
  population-based suppression (min_trade_count=8) — skip the gate
  when the window has too few prints. IS_weighted_bps improved by
  ~half the base's regression, but PnL still came in at -21.1% vs
  base. The diagnostic finding: IS and PnL moved in OPPOSITE
  directions, meaning the base's gate captures *path-risk* information
  beyond arrival-price quality. Population-based admission lets in
  trades that have decent arrival prices but poor path-loss
  characteristics inside the oracle's 30s horizon.

  g1l3 takes the corrective lesson from BOTH prior loops:
  - From g1l1: do not use a flow-derived proxy for price movement;
    use mid PRICE itself.
  - From g1l2: do not broadly loosen the gate (the gate's strictness
    is doing useful path-risk work); instead override only the
    specific adverse-flow skips where independent evidence shows price
    has moved favorably.

Algorithm:
  - Trade-tick handler maintains the base's signed-flow deque exactly
    as in g1l2/base (window_seconds=10.0, flow_threshold=2.0).
  - Quote-tick handler maintains a separate mid-price deque:
    (ts_event_ns, mid=(bid+ask)/2), pruned to the last
    confirm_window_seconds.
  - At order time:
      * Reduce-only: SUBMIT.
      * _position_flat (post-skip): SUBMIT, clear flag.
      * Evaluate base gate (signed-flow threshold). If NOT adverse:
        SUBMIT.
      * If adverse: evaluate PRICE-CONFIRMATION OVERRIDE.
          - If _mid_deque has < 2 entries: do not override, skip.
          - Compute mid_now (most recent entry), mid_then (oldest
            entry still inside confirm_window).
          - BUY  override iff (mid_then - mid_now) >=
                 confirm_ticks * tick_size  (mid has fallen).
          - SELL override iff (mid_now - mid_then) >=
                 confirm_ticks * tick_size  (mid has risen).
          - If override fires: SUBMIT, _position_flat = False.
          - Else: SKIP, _position_flat = True.
  - Quantity invariant: order.quantity never modified.
  - Tick size: hard-coded 0.25 for MES.

No look-ahead: both deques are fed by replay-chronological callbacks
and pruned by order.ts_init at decision time.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


# MES tick size in index points. Hard-coded — this algorithm targets MES.
_MES_TICK_SIZE: float = 0.25


class AfgIslG1L3Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the afg-isl-g1l3 single-window + price-confirmation gate.

    Parameters
    ----------
    window_seconds : float
        Rolling look-back window for trade prints (signed-flow gate), in
        seconds. Default 10.0. Matches the base aggressor-flow-gate window.
    flow_threshold : float
        Minimum absolute net signed flow (contracts) to trigger the base
        gate's adverse-flow skip.
        BUY:  base gate skips when net_flow <= -flow_threshold.
        SELL: base gate skips when net_flow >=  flow_threshold.
        Default 2.0 (matches base).
    confirm_window_seconds : float
        Sub-window (inside the flow window) over which we measure the
        favorable mid-price movement that authorizes an override of the
        base gate's skip. Default 3.0s — short enough that the move is
        still "fresh" at order time, long enough to register an actual
        mid move beyond per-tick noise.
    confirm_ticks : float
        Required favorable mid movement (in MES ticks; 1 tick = 0.25
        index points) over the confirm window for the override to fire.
        Default 1.0 — a 1-tick mid move in the order's favor is a
        small but non-noise confirmation. Conservative by design:
        admit only the highest-quality overrides.
    """

    window_seconds: float = 10.0
    flow_threshold: float = 2.0
    confirm_window_seconds: float = 3.0
    confirm_ticks: float = 1.0


class AfgIslG1L3Algorithm(ExecAlgorithm):
    """Single-window signed-flow gate with a narrow price-confirmation override.

    Opening orders (is_reduce_only == False):
      - Evaluate net signed aggressor flow over the last `window_seconds`.
      - If NOT adverse (per base's flow_threshold rule): SUBMIT.
      - If adverse: evaluate the price-confirmation override.
          - BUY  override: mid has fallen >= confirm_ticks * tick_size
            during the last confirm_window_seconds.
          - SELL override: mid has risen >= confirm_ticks * tick_size
            during the last confirm_window_seconds.
          - Override fires → SUBMIT; else → SKIP.
      - After any skip: `_position_flat = True` (next open unconditional).

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is ever modified.
    """

    def __init__(self, config: AfgIslG1L3Config) -> None:
        super().__init__(config=config)

        if config.confirm_window_seconds <= 0:
            raise ValueError(
                f"confirm_window_seconds must be > 0 "
                f"(got {config.confirm_window_seconds})."
            )
        if config.confirm_window_seconds > config.window_seconds:
            raise ValueError(
                f"confirm_window_seconds ({config.confirm_window_seconds}) "
                f"must be <= window_seconds ({config.window_seconds})."
            )
        if config.confirm_ticks <= 0:
            raise ValueError(
                f"confirm_ticks must be > 0 (got {config.confirm_ticks})."
            )

        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._flow_threshold: float = config.flow_threshold
        self._confirm_window_ns: int = int(
            config.confirm_window_seconds * 1_000_000_000
        )
        self._confirm_threshold_price: float = (
            config.confirm_ticks * _MES_TICK_SIZE
        )

        # Trade-flow deque: (ts_event_ns, signed_vol).
        # signed_vol = +size (BUYER), -size (SELLER), 0 (NO_AGGRESSOR).
        self._flow_deque: deque[tuple[int, float]] = deque()
        # Running sum of signed volume in _flow_deque (O(1) updates).
        self._net_flow: float = 0.0

        # Mid-price deque: (ts_event_ns, mid). Used ONLY for the
        # price-confirmation override.
        self._mid_deque: deque[tuple[int, float]] = deque()

        # Safety: forced re-entry after any skip to prevent cascade.
        self._position_flat: bool = True

        # Subscription tracking.
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            "AfgIslG1L3Algorithm started "
            f"(window={self._window_ns / 1e9:.1f}s, "
            f"flow_threshold={self._flow_threshold:.2f}, "
            f"confirm_window={self._confirm_window_ns / 1e9:.1f}s, "
            f"confirm_threshold_price={self._confirm_threshold_price:.4f})."
        )

    def on_reset(self) -> None:
        self._flow_deque.clear()
        self._net_flow = 0.0
        self._mid_deque.clear()
        self._position_flat = True
        self._subscribed.clear()

    # ------------------------------------------------------------------
    # Subscription helper
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_trade_ticks(instrument_id)
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Trade tick handler — maintain rolling signed flow deque
    # ------------------------------------------------------------------

    def on_trade_tick(self, tick) -> None:
        """Receive a trade tick and update the rolling aggressor-flow deque."""
        aggressor = tick.aggressor_side
        size = float(str(tick.size))

        if aggressor == AggressorSide.BUYER:
            signed_vol = size
        elif aggressor == AggressorSide.SELLER:
            signed_vol = -size
        else:
            # NO_AGGRESSOR — treat as neutral.
            signed_vol = 0.0

        self._flow_deque.append((tick.ts_event, signed_vol))
        self._net_flow += signed_vol

    # ------------------------------------------------------------------
    # Quote tick handler — maintain rolling mid-price deque
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        """Receive a quote tick and update the rolling mid-price deque."""
        try:
            bid = float(str(tick.bid_price))
            ask = float(str(tick.ask_price))
        except Exception:
            return

        # Defensive: ignore obviously invalid quotes (zero/crossed).
        if bid <= 0.0 or ask <= 0.0 or ask < bid:
            return

        mid = (bid + ask) * 0.5
        self._mid_deque.append((tick.ts_event, mid))

    # ------------------------------------------------------------------
    # Window pruning
    # ------------------------------------------------------------------

    def _prune_flow_window(self, cutoff_ns: int) -> None:
        """Remove flow-deque entries older than cutoff_ns, updating _net_flow."""
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            _, old_vol = self._flow_deque.popleft()
            self._net_flow -= old_vol

    def _prune_mid_window(self, cutoff_ns: int) -> None:
        """Remove mid-deque entries older than cutoff_ns."""
        while self._mid_deque and self._mid_deque[0][0] < cutoff_ns:
            self._mid_deque.popleft()

    # ------------------------------------------------------------------
    # Gate evaluation
    # ------------------------------------------------------------------

    def _flow_is_adverse(self, order) -> bool:
        """Return True iff base-gate signed flow is adverse for this order.

        BUY  adverse: net_flow <= -flow_threshold (sellers dominate).
        SELL adverse: net_flow >=  flow_threshold (buyers dominate).
        """
        cutoff_ns = order.ts_init - self._window_ns
        self._prune_flow_window(cutoff_ns)

        if not self._flow_deque:
            return False

        net = self._net_flow
        if order.side == OrderSide.BUY:
            return net <= -self._flow_threshold
        else:  # SELL
            return net >= self._flow_threshold

    def _price_confirmation_override(self, order) -> bool:
        """Return True iff mid has moved favorably enough to override the skip.

        BUY  override: mid has fallen by >= confirm_threshold_price over
                       the confirm window (better arrival price for a BUY).
        SELL override: mid has risen by >= confirm_threshold_price over
                       the confirm window (better arrival price for a SELL).

        Returns False (do NOT override) when the mid deque has fewer than
        2 entries inside the confirm window — absence of evidence is not
        evidence of favorable movement.
        """
        cutoff_ns = order.ts_init - self._confirm_window_ns
        self._prune_mid_window(cutoff_ns)

        if len(self._mid_deque) < 2:
            return False

        mid_then = self._mid_deque[0][1]   # oldest entry still inside window
        mid_now = self._mid_deque[-1][1]   # most recent entry

        if order.side == OrderSide.BUY:
            # Favorable for BUY: mid fell (we now buy lower).
            move = mid_then - mid_now
        else:  # SELL
            # Favorable for SELL: mid rose (we now sell higher).
            move = mid_now - mid_then

        return move >= self._confirm_threshold_price

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: base flow gate + narrow price-confirmation override."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        if order.is_reduce_only:
            self.submit_order(order)
            return

        # Forced re-entry after a skip — always submit to prevent cascade.
        if self._position_flat:
            self._position_flat = False
            self.submit_order(order)
            return

        if not self._flow_is_adverse(order):
            # Base gate would submit — no override needed.
            self._position_flat = False
            self.submit_order(order)
            return

        # Base gate would skip — evaluate price-confirmation override.
        if self._price_confirmation_override(order):
            self.log.debug(
                f"PRICE-CONFIRM OVERRIDE {order.client_order_id} "
                f"(net_flow={self._net_flow:.2f}, "
                f"side={'BUY' if order.side == OrderSide.BUY else 'SELL'}); "
                f"SUBMIT despite adverse flow."
            )
            self._position_flat = False
            self.submit_order(order)
            return

        # No override — execute the base skip.
        self.log.info(
            f"SKIP {order.client_order_id} — adverse aggressor flow "
            f"(net_flow={self._net_flow:.2f}, "
            f"n_prints={len(self._flow_deque)}, "
            f"side={'BUY' if order.side == OrderSide.BUY else 'SELL'}); "
            f"no price-confirmation override."
        )
        self._position_flat = True
        # Do NOT call submit_order — quantity invariant preserved.


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_seconds: float = 10.0,
    flow_threshold: float = 2.0,
    confirm_window_seconds: float = 3.0,
    confirm_ticks: float = 1.0,
) -> AfgIslG1L3Algorithm:
    """Instantiate and return the afg-isl-g1l3 algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_seconds : float
        Rolling window for aggressor flow, in seconds. Default 10.0s.
    flow_threshold : float
        Minimum absolute net signed flow (contracts) to trigger the
        base gate's adverse-flow skip. Default 2.0 (matches base).
    confirm_window_seconds : float
        Sub-window over which a favorable mid-price move authorizes
        the override. Default 3.0s.
    confirm_ticks : float
        Required favorable mid movement (in MES ticks; 1 tick = 0.25
        index points) over the confirm window. Default 1.0.
    """
    config = AfgIslG1L3Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        flow_threshold=flow_threshold,
        confirm_window_seconds=confirm_window_seconds,
        confirm_ticks=confirm_ticks,
    )
    return AfgIslG1L3Algorithm(config=config)
