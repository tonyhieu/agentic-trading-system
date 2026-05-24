"""afg-isl-g1l2 — island-1, generation 1, loop 2.

Single-window aggressor-flow gate with a TRADE-COUNT MINIMUM (tighten,
do not loosen).

Why this design (vs g1l1):
  g1l1 added a two-window "persistence + reversal" structure on top of
  the base. The reversal exception (short-window flow-flip used as a
  proxy for price reversal) was decisively falsified — flow-flip is not
  price reversal, the marginal entries it admitted were net P&L
  destroyers, and is_weighted_bps regressed +7.4% vs base. The
  short-window persistence-AND tightener was also moot because the
  reversal exception simultaneously relaxed the gate in the same
  direction.

  g1l2 reverts the entire g1l1 mechanism (drop short-window,
  drop reversal exception) and returns to the base's single-window
  signed-flow gate. The single change is a TRADE-COUNT MINIMUM:
  the gate only fires when the deque holds at least `min_trade_count`
  prints. Below that, the window is too thin for a 2-contract net flow
  to be a meaningful adverse-pressure signal — it's more likely a
  one-or-two-trade artifact, and gating on it is what's costing the
  base its is_weighted_bps regression.

Algorithm (open orders):
  - Maintain a deque of (ts_event_ns, signed_volume) from trade ticks.
  - At order time, prune entries older than `window_seconds`.
  - If `len(deque) < min_trade_count`: SUBMIT (thin window — gate
    has insufficient evidence to skip; matches base's warm-up
    behavior, just extended).
  - Else apply the BASE gate exactly:
      BUY  skip iff net_flow <= -flow_threshold
      SELL skip iff net_flow >=  flow_threshold
  - Reduce-only orders always submit.
  - After any skip: `_position_flat = True` (anti-cascade contract
    preserved, same as base and g1l1).
  - Quantity invariant: never modify `order.quantity`.

Hypothesis (see NOTES.md): the base aggressor-flow-gate sometimes
gates on thin-window signals where only 2-4 prints comprise the
`net_flow >= 2.0` threshold. Those prints can easily be one large
sweep followed by a quiet pocket — not a regime, just a single
event. Requiring a minimum print count before the gate is allowed
to fire suppresses these thin-window false positives, recapturing
the favorable-arrival-price entries the base's NOTES.md identified
as the IS regression source. P&L should improve while skip-rate
on truly persistent adverse flow stays roughly intact (those
periods always have many prints).

No look-ahead: the deque is fed strictly by `on_trade_tick` callbacks
in replay-chronological order; pruning uses `order.ts_init`.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class AfgIslG1L2Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the afg-isl-g1l2 single-window + min-count gate.

    Parameters
    ----------
    window_seconds : float
        Rolling look-back window for trade prints, in seconds. Default 10.0.
        Matches the base aggressor-flow-gate window.
    flow_threshold : float
        Minimum absolute net signed flow (contracts) to trigger a skip.
        BUY:  skip when net_flow <= -flow_threshold.
        SELL: skip when net_flow >=  flow_threshold.
        Default 2.0 (matches base).
    min_trade_count : int
        Minimum number of trade prints that must be present in the window
        for the gate to be ALLOWED to fire. Below this, the window is
        treated as too thin for a meaningful adverse-flow verdict and the
        order is submitted unconditionally. Default 8 — at typical MES
        cadence, ~8 prints in a 10s window represents a populated regime;
        fewer is a noisy/quiet pocket where flow-direction is essentially
        a 1-2-event artifact rather than a sustained pressure signal.
    """

    window_seconds: float = 10.0
    flow_threshold: float = 2.0
    min_trade_count: int = 8


class AfgIslG1L2Algorithm(ExecAlgorithm):
    """Single-window signed-flow gate with a thin-window suppression rule.

    Opening orders (is_reduce_only == False):
      - Evaluate net signed aggressor flow over the last `window_seconds`.
      - If fewer than `min_trade_count` prints are in the window, SUBMIT
        unconditionally (window too thin for the gate to be reliable).
      - Else, apply the standard adverse-flow skip:
          BUY  skip iff net_flow <= -flow_threshold
          SELL skip iff net_flow >=  flow_threshold
      - After any skip: `_position_flat = True` (next open unconditional).

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is ever modified.
    """

    def __init__(self, config: AfgIslG1L2Config) -> None:
        super().__init__(config=config)
        if config.min_trade_count < 1:
            raise ValueError(
                f"min_trade_count must be >= 1 (got {config.min_trade_count})."
            )

        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._flow_threshold: float = config.flow_threshold
        self._min_trade_count: int = config.min_trade_count

        # Deque of (ts_event_ns: int, signed_vol: float).
        # signed_vol = +size (BUYER), -size (SELLER), 0 (NO_AGGRESSOR).
        self._flow_deque: deque[tuple[int, float]] = deque()

        # Running sum of signed volume in the deque (O(1) updates).
        self._net_flow: float = 0.0

        # Safety: forced re-entry after any skip to prevent cascade.
        self._position_flat: bool = True

        # Subscription tracking.
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            "AfgIslG1L2Algorithm started "
            f"(window={self._window_ns / 1e9:.1f}s, "
            f"flow_threshold={self._flow_threshold:.2f}, "
            f"min_trade_count={self._min_trade_count})."
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
    # Flow evaluation
    # ------------------------------------------------------------------

    def _prune_window(self, cutoff_ns: int) -> None:
        """Remove deque entries older than cutoff_ns, updating _net_flow."""
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            _, old_vol = self._flow_deque.popleft()
            self._net_flow -= old_vol

    def _flow_is_adverse(self, order) -> bool:
        """Return True if net aggressor flow is adverse AND window is populated.

        BUY  order: adverse when net_flow <= -flow_threshold (sellers dominate).
        SELL order: adverse when net_flow >=  flow_threshold (buyers dominate).

        Returns False (do not skip) when:
          - Window is empty (warm-up / thin market).
          - len(deque) < min_trade_count (thin window — gate suppressed).
          - |net_flow| < flow_threshold (neutral / near-balanced window).
        """
        cutoff_ns = order.ts_init - self._window_ns
        self._prune_window(cutoff_ns)

        if not self._flow_deque:
            # Warm-up / no trade data in window.
            return False

        n_prints = len(self._flow_deque)
        if n_prints < self._min_trade_count:
            # Thin window — suppress gate, submit unconditionally.
            self.log.debug(
                f"THIN WINDOW: n_prints={n_prints} < "
                f"min_trade_count={self._min_trade_count}; SUBMIT "
                f"{order.client_order_id} unconditionally."
            )
            return False

        net = self._net_flow

        if order.side == OrderSide.BUY:
            if net <= -self._flow_threshold:
                self.log.debug(
                    f"BUY adverse flow: net_flow={net:.2f} <= "
                    f"-threshold={-self._flow_threshold:.2f} "
                    f"(n_prints={n_prints}); SKIP."
                )
                return True
        else:  # SELL
            if net >= self._flow_threshold:
                self.log.debug(
                    f"SELL adverse flow: net_flow={net:.2f} >= "
                    f"threshold={self._flow_threshold:.2f} "
                    f"(n_prints={n_prints}); SKIP."
                )
                return True

        return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on populated-window flow gate."""
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

        if self._flow_is_adverse(order):
            self.log.info(
                f"SKIP {order.client_order_id} — adverse aggressor flow "
                f"(net_flow={self._net_flow:.2f}, "
                f"n_prints={len(self._flow_deque)}, side="
                f"{'BUY' if order.side == OrderSide.BUY else 'SELL'})."
            )
            self._position_flat = True
            # Do NOT call submit_order — quantity invariant preserved.
        else:
            self._position_flat = False
            self.submit_order(order)

    def on_quote_tick(self, tick) -> None:
        """Passively receive quote ticks (kept for quote-cache side-effects)."""
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_seconds: float = 10.0,
    flow_threshold: float = 2.0,
    min_trade_count: int = 8,
) -> AfgIslG1L2Algorithm:
    """Instantiate and return the afg-isl-g1l2 algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_seconds : float
        Rolling window for aggressor flow, in seconds. Default 10.0s.
    flow_threshold : float
        Minimum absolute net signed flow (contracts) to trigger a skip.
        Default 2.0 (matches base).
    min_trade_count : int
        Minimum number of trade prints required in the window before the
        gate is allowed to fire. Default 8.
    """
    config = AfgIslG1L2Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        flow_threshold=flow_threshold,
        min_trade_count=min_trade_count,
    )
    return AfgIslG1L2Algorithm(config=config)
