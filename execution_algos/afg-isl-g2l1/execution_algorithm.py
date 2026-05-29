"""afg-isl-g2l1 — island-1, generation 2, loop 1.

Unmodified base aggressor-flow-gate, with a rolling-spread-p75 OPEN-gate
STACKED on top (cross-island import from island-0 g1l1, which gained
+26.55% PnL by adding the same spread gate to its own base).

Why this design (vs g1l2)
-------------------------
Both prior loops on island-1 LOOSENED the base gate. Both regressed:
  - g1l1 (-43.13% PnL): two-window persistence + flow-flip reversal
    exception. Falsified.
  - g1l2 (-21.15% PnL): single-window base + min_trade_count=8
    precondition. Falsified on PnL, but documented the headline
    finding for migration: an IS-vs-PnL dissonance proving the base's
    gate carries path-risk information invisible to is_weighted_bps.
    Loosening the gate destroys PnL even when arrival-price quality
    improves.

The gen-1 migration report is unambiguous about the productive
direction:
  - what_worked: SKIP-based gating on adverse-microstructure regimes
    (rolling-spread-p75 on island-0 +26.55%; choppiness-ratio on
    island-2 +34.13%).
  - what_failed: LOOSENING existing skip gates (island-1's two loops
    plus island-2 g1l2 all regressed).
  - generalizable: spread-quantile and choppiness-ratio target
    near-orthogonal axes (book-state vs price-path); a composed
    stack is the highest-leverage gen-2 direction.

This loop acts on that finding. The base aggressor-flow gate stays
exactly as in `aggressor-flow-gate/execution_algorithm.py` (no
modifications, none of g1l1/g1l2's logic carries forward). The
spread-p75 gate is layered on top with the verbatim parameters
proven on island-0 g1l1.

Algorithm
---------
Maintain two independent rolling structures:
  - Aggressor-flow deque (from on_trade_tick): same as base.
  - Spread deque (from on_quote_tick): (ts_event_ns, spread) samples,
    where spread = ask_price - bid_price in raw price units.

For each OPEN order:
  1. Reduce-only orders always submit (intraday_flat compliance).
  2. Forced re-entry after a skip is unconditional (anti-cascade —
     unchanged contract from base and from all prior island-1 loops).
  3. Spread gate (orthogonal axis, cross-island import):
       Prune spread deque to entries within `spread_window_seconds`.
       If at least `min_samples` samples are present, compute the
       `spread_quantile`-th quantile of the rolling spreads. If the
       latest spread strictly exceeds that quantile → SKIP.
  4. Aggressor-flow gate (BASE, unmodified):
       Prune flow deque to entries within `window_seconds`.
       BUY  skip iff net_flow <= -flow_threshold
       SELL skip iff net_flow >=  flow_threshold
  5. Submit only if both gates pass. After ANY skip,
     `_position_flat = True` (next open unconditional).

Order quantity is never modified — quantity invariant preserved.

No look-ahead: both deques are fed by Nautilus callbacks in replay
chronological order; pruning uses `order.ts_init` as the cutoff
anchor.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class AfgIslG2L1Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for afg-isl-g2l1: base aggressor-flow-gate + spread-p75.

    Parameters
    ----------
    window_seconds : float
        Aggressor-flow rolling window, in seconds. Default 10.0 — matches
        base aggressor-flow-gate.
    flow_threshold : float
        Aggressor-flow adverse threshold (contracts). Default 2.0 — matches
        base aggressor-flow-gate.
    spread_window_seconds : float
        Rolling window for spread samples, in seconds. Default 60.0 — matches
        the known-good value from island-0 g1l1 (the cross-island winner).
    spread_quantile : float
        Quantile threshold for the spread gate (0 < q < 1). Skip OPEN when
        the latest spread strictly exceeds this quantile of the rolling
        window. Default 0.75 — matches island-0 g1l1.
    min_samples : int
        Minimum spread samples required before the spread gate fires. Below
        this, the spread gate is a no-op (warm-up). Default 50 — matches
        island-0 g1l1.
    """

    window_seconds: float = 10.0
    flow_threshold: float = 2.0
    spread_window_seconds: float = 60.0
    spread_quantile: float = 0.75
    min_samples: int = 50


class AfgIslG2L1Algorithm(ExecAlgorithm):
    """Base aggressor-flow-gate UNMODIFIED, composed with a spread-p75 gate.

    Opening orders (is_reduce_only == False):
      - Forced re-entry after a skip is unconditional (anti-cascade).
      - Gate A (spread, orthogonal axis from island-0 g1l1):
          Skip OPEN when the latest spread > p75 of the rolling spread
          distribution (warm-up no-op until min_samples are present).
      - Gate B (aggressor-flow, base unchanged):
          BUY  skip iff net_flow <= -flow_threshold
          SELL skip iff net_flow >=  flow_threshold
      - Submit only if BOTH gates pass.
      - After any skip: `_position_flat = True` (next open unconditional).

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    Quantity invariant: never modify `order.quantity`.
    """

    def __init__(self, config: AfgIslG2L1Config) -> None:
        super().__init__(config=config)

        # Aggressor-flow state (mirrors base aggressor-flow-gate).
        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._flow_threshold: float = config.flow_threshold
        # Deque of (ts_event_ns, signed_vol).
        # signed_vol = +size (BUYER), -size (SELLER), 0 (NO_AGGRESSOR).
        self._flow_deque: deque[tuple[int, float]] = deque()
        # Running sum of signed volume in the flow deque (O(1) updates).
        self._net_flow: float = 0.0

        # Spread-gate state (mirrors island-0 g1l1).
        self._spread_window_ns: int = int(
            config.spread_window_seconds * 1_000_000_000
        )
        self._spread_quantile: float = config.spread_quantile
        self._min_samples: int = config.min_samples
        # Deque of (ts_event_ns, spread) in raw price units.
        self._spread_deque: deque[tuple[int, float]] = deque()
        # Most recent observed spread (the comparison point for the gate).
        self._latest_spread: float | None = None

        # Anti-cascade contract: forced re-entry after any skip.
        self._position_flat: bool = True

        # Subscription tracking.
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            "AfgIslG2L1Algorithm started "
            f"(flow_window={self._window_ns / 1e9:.1f}s, "
            f"flow_threshold={self._flow_threshold:.2f}, "
            f"spread_window={self._spread_window_ns / 1e9:.1f}s, "
            f"spread_quantile={self._spread_quantile:.2f}, "
            f"min_samples={self._min_samples})."
        )

    def on_reset(self) -> None:
        self._flow_deque.clear()
        self._net_flow = 0.0
        self._spread_deque.clear()
        self._latest_spread = None
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
        """Update the rolling aggressor-flow deque (base behavior)."""
        aggressor = tick.aggressor_side
        size = float(str(tick.size))

        if aggressor == AggressorSide.BUYER:
            signed_vol = size
        elif aggressor == AggressorSide.SELLER:
            signed_vol = -size
        else:
            # NO_AGGRESSOR — treat as neutral; do not bias the flow signal.
            signed_vol = 0.0

        self._flow_deque.append((tick.ts_event, signed_vol))
        self._net_flow += signed_vol

    # ------------------------------------------------------------------
    # Quote tick handler — maintain rolling spread deque
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        """Update the rolling spread deque (cross-island axis)."""
        try:
            bid = float(str(tick.bid_price))
            ask = float(str(tick.ask_price))
        except Exception:
            return
        spread = ask - bid
        if spread < 0.0:
            # Defensive: crossed book — skip the sample.
            return
        self._spread_deque.append((tick.ts_event, spread))
        self._latest_spread = spread

    # ------------------------------------------------------------------
    # Flow gate (base, unmodified)
    # ------------------------------------------------------------------

    def _prune_flow_window(self, cutoff_ns: int) -> None:
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            _, old_vol = self._flow_deque.popleft()
            self._net_flow -= old_vol

    def _flow_is_adverse(self, order) -> bool:
        """Base aggressor-flow-gate logic. Unchanged."""
        cutoff_ns = order.ts_init - self._window_ns
        self._prune_flow_window(cutoff_ns)

        if not self._flow_deque:
            # No trade data in window — do not gate (warm-up / thin market).
            return False

        net = self._net_flow

        if order.side == OrderSide.BUY:
            if net <= -self._flow_threshold:
                self.log.debug(
                    f"FLOW SKIP BUY {order.client_order_id} — "
                    f"net_flow={net:.2f} <= -threshold={-self._flow_threshold:.2f}."
                )
                return True
        else:  # SELL
            if net >= self._flow_threshold:
                self.log.debug(
                    f"FLOW SKIP SELL {order.client_order_id} — "
                    f"net_flow={net:.2f} >= threshold={self._flow_threshold:.2f}."
                )
                return True

        return False

    # ------------------------------------------------------------------
    # Spread gate (cross-island import from island-0 g1l1)
    # ------------------------------------------------------------------

    def _prune_spread_window(self, cutoff_ns: int) -> None:
        while self._spread_deque and self._spread_deque[0][0] < cutoff_ns:
            self._spread_deque.popleft()

    def _spread_gate_skip(self, order) -> bool:
        """Return True if the latest spread sits above the rolling quantile.

        Warm-up branch: if the deque holds fewer than `min_samples` samples,
        return False (do not gate on the spread axis).
        """
        cutoff_ns = order.ts_init - self._spread_window_ns
        self._prune_spread_window(cutoff_ns)

        n = len(self._spread_deque)
        if n < self._min_samples or self._latest_spread is None:
            return False  # warm-up: defer to the flow gate alone

        # Quantile via sorted copy. Deque size is bounded by samples-per-second
        # × window_seconds — for MES on a 60s window this is low thousands at
        # most, so sorted() per order event is acceptable. If profiling shows
        # this is a hot path, a future loop can switch to a streaming-quantile
        # algorithm; the math/threshold semantics here would be unchanged.
        sorted_spreads = sorted(s for _, s in self._spread_deque)
        idx_f = self._spread_quantile * (n - 1)
        lo = int(idx_f)
        hi = min(lo + 1, n - 1)
        frac = idx_f - lo
        threshold = sorted_spreads[lo] * (1.0 - frac) + sorted_spreads[hi] * frac

        if self._latest_spread > threshold:
            self.log.debug(
                f"SPREAD SKIP {order.client_order_id} — "
                f"latest_spread={self._latest_spread:.5f} > "
                f"q{self._spread_quantile:.2f}={threshold:.5f} (n={n})."
            )
            return True
        return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit only if BOTH spread and flow gates pass."""
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

        # Gate A: spread (orthogonal axis from island-0 g1l1).
        if self._spread_gate_skip(order):
            self.log.info(
                f"SKIP {order.client_order_id} — spread gate "
                f"(latest={self._latest_spread}, side="
                f"{'BUY' if order.side == OrderSide.BUY else 'SELL'})."
            )
            self._position_flat = True
            return

        # Gate B: aggressor-flow (base, unmodified).
        if self._flow_is_adverse(order):
            self.log.info(
                f"SKIP {order.client_order_id} — adverse aggressor flow "
                f"(net_flow={self._net_flow:.2f}, side="
                f"{'BUY' if order.side == OrderSide.BUY else 'SELL'})."
            )
            self._position_flat = True
            return

        # Both gates passed — submit.
        self._position_flat = False
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_seconds: float = 10.0,
    flow_threshold: float = 2.0,
    spread_window_seconds: float = 60.0,
    spread_quantile: float = 0.75,
    min_samples: int = 50,
) -> AfgIslG2L1Algorithm:
    """Instantiate and return the afg-isl-g2l1 algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_seconds : float
        Aggressor-flow rolling window, in seconds. Default 10.0 (base).
    flow_threshold : float
        Aggressor-flow adverse threshold (contracts). Default 2.0 (base).
    spread_window_seconds : float
        Rolling window for spread samples, in seconds. Default 60.0
        (matches island-0 g1l1).
    spread_quantile : float
        Quantile threshold for the spread gate. Default 0.75 (matches
        island-0 g1l1).
    min_samples : int
        Minimum spread samples before the spread gate fires. Default 50
        (matches island-0 g1l1).
    """
    config = AfgIslG2L1Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        flow_threshold=flow_threshold,
        spread_window_seconds=spread_window_seconds,
        spread_quantile=spread_quantile,
        min_samples=min_samples,
    )
    return AfgIslG2L1Algorithm(config=config)
