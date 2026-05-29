"""ptg-isl-g3l1: position-cap + rolling-spread-p75 + aggressor-flow gate.

Branches from `ptg-isl-g1l1` (island-0's best loop so far, +26.55% vs
position-tier-gate base, chop-free). Adds a THIRD orthogonal SKIP axis —
the aggressor-flow gate (signed-volume imbalance from trade ticks) — as
recommended by the gen-2 migration:

    Cross-island insight (gen-2):
      "drop chop; on ptg's base, try spread+cap + book-flow imbalance as
       the third orthogonal axis."

This is the same mechanism that island-1 stacked onto its base for
+173.95% vs base (gen-2 g2l2). Flow is structurally distinct from
spread (book-state) and chop (price-path).

Algorithm
---------
On `on_order()` for an OPEN (not reduce-only):
  - Gate 1 (position-cap):     skip if net_qty >= position_cap.
  - Gate 2 (spread-p75):       skip if latest spread > p75 of 60s rolling
                                spread distribution (min 50 samples).
  - Gate 3 (aggressor-flow):   skip BUY  when net_flow_10s <= -threshold,
                                skip SELL when net_flow_10s >=  threshold.
  - If ANY gate fires, SKIP (no submit_order call). Composition is
    OR-skip across three binary gates — matches island-1's successful
    spread+flow+chop stack.
Reduce-only / closing orders ALWAYS execute (intraday_flat compliance).

Operating point — RETUNED from afg's defaults (per gen-2 migration's
"retune across base contexts" finding). afg uses window=10s,
threshold=2.0 contracts on its raw base. ptg's surviving population is
already double-pre-filtered (position-cap + spread-p75), so most
high-pressure bursts coincide with wide spreads and are already cut.
The threshold here is HIGHER (3.0 contracts) to fire only on genuine
residual adverse pressure and avoid over-cutting positive-EV trades
(symmetric to island-2 g2l2's -30% misfire at afg's default).

Instrumentation
---------------
Per-gate skip counters and evaluated/submit counts are maintained and
emitted on `on_stop()`. Gen-1 migration's `generalizable` finding #3
required this — null-effect gates without counters are undiagnosable
(island-0 g1l2 lost a loop to that exact failure mode).

No look-ahead bias
------------------
- Quote ticks and trade ticks arrive in chronological replay order.
- The deque prunes at `on_order()` use the order's `ts_init`, never a
  future timestamp.
- The `_latest_spread` and `_net_flow` reflect only data delivered
  before this order — strictly in the past.

Quantity invariant
------------------
No order quantity is ever modified. submit_order(order) is called
verbatim, or not at all.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PtgIslG3L1Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for ptg-isl-g3l1.

    Parameters
    ----------
    position_cap : int
        Skip OPEN if absolute net position >= position_cap.
        Inherited verbatim from g1l1 (and the position-tier-gate base).
    spread_window_seconds : float
        Rolling window for spread samples (seconds). Default 60.0.
        Inherited verbatim from g1l1.
    spread_quantile : float
        Quantile threshold for the spread gate (0 < q < 1). Skip OPEN
        when the latest spread is strictly greater than the q-th quantile
        of the rolling window. Default 0.75. Inherited verbatim from g1l1.
    spread_min_samples : int
        Minimum samples required before the spread gate fires. Below
        this, the spread gate is a no-op (warm-up). Default 50.
        Inherited verbatim from g1l1.
    flow_window_seconds : float
        Rolling window for signed-aggressor-flow accumulation (seconds).
        Default 10.0 — same as afg's canonical default; short-term
        pressure window.
    flow_threshold : float
        Minimum absolute net signed flow (contracts) to trigger a skip.
        BUY skip when net_flow <= -flow_threshold;
        SELL skip when net_flow >= +flow_threshold.
        Default 3.0 — RETUNED higher than afg's default 2.0 because
        ptg-g1l1's surviving population is already pre-filtered by
        position-cap + spread-p75, so fewer truly adverse-flow trades
        remain and the body of the residual distribution should be
        preserved.
    """

    position_cap: int = 1
    spread_window_seconds: float = 60.0
    spread_quantile: float = 0.75
    spread_min_samples: int = 50
    flow_window_seconds: float = 10.0
    flow_threshold: float = 3.0


class PtgIslG3L1Algorithm(ExecAlgorithm):
    """Three-gate stack: position-cap + rolling-spread-p75 + aggressor-flow."""

    def __init__(self, config: PtgIslG3L1Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap

        # Spread gate state
        self._spread_window_ns: int = int(config.spread_window_seconds * 1_000_000_000)
        self._spread_quantile: float = config.spread_quantile
        self._spread_min_samples: int = config.spread_min_samples
        self._spread_deque: deque[tuple[int, float]] = deque()
        self._latest_spread: float | None = None

        # Flow gate state
        self._flow_window_ns: int = int(config.flow_window_seconds * 1_000_000_000)
        self._flow_threshold: float = config.flow_threshold
        self._flow_deque: deque[tuple[int, float]] = deque()
        self._net_flow: float = 0.0

        # Subscription tracking
        self._subscribed: set[str] = set()

        # Instrumentation counters
        self._evaluated_open_count: int = 0
        self._position_skip_count: int = 0
        self._spread_skip_count: int = 0
        self._flow_skip_count: int = 0
        self._flow_warm_up_count: int = 0
        self._submit_count: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"PtgIslG3L1Algorithm started "
            f"(position_cap={self._position_cap}, "
            f"spread_window={self._spread_window_ns / 1e9:.1f}s, "
            f"spread_quantile={self._spread_quantile:.2f}, "
            f"spread_min_samples={self._spread_min_samples}, "
            f"flow_window={self._flow_window_ns / 1e9:.1f}s, "
            f"flow_threshold={self._flow_threshold:.2f} contracts)."
        )

    def on_reset(self) -> None:
        self._spread_deque.clear()
        self._latest_spread = None
        self._flow_deque.clear()
        self._net_flow = 0.0
        self._subscribed.clear()
        self._evaluated_open_count = 0
        self._position_skip_count = 0
        self._spread_skip_count = 0
        self._flow_skip_count = 0
        self._flow_warm_up_count = 0
        self._submit_count = 0

    def on_stop(self) -> None:
        self.log.info(
            "PtgIslG3L1Algorithm stopped — gate instrumentation: "
            f"evaluated_opens={self._evaluated_open_count}, "
            f"submitted={self._submit_count}, "
            f"position_skips={self._position_skip_count}, "
            f"spread_skips={self._spread_skip_count}, "
            f"flow_skips={self._flow_skip_count}, "
            f"flow_warm_up_passes={self._flow_warm_up_count}."
        )

    # ------------------------------------------------------------------
    # Subscription helper — need both quote AND trade ticks
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self.subscribe_trade_ticks(instrument_id)
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Quote tick handler — maintain rolling spread samples
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
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
    # Trade tick handler — maintain rolling signed flow deque (O(1) updates)
    # ------------------------------------------------------------------

    def on_trade_tick(self, tick) -> None:
        aggressor = tick.aggressor_side
        try:
            size = float(str(tick.size))
        except Exception:
            return

        if aggressor == AggressorSide.BUYER:
            signed_vol = size
        elif aggressor == AggressorSide.SELLER:
            signed_vol = -size
        else:
            signed_vol = 0.0

        self._flow_deque.append((tick.ts_event, signed_vol))
        self._net_flow += signed_vol

    # ------------------------------------------------------------------
    # Gate helpers
    # ------------------------------------------------------------------

    def _current_net_qty(self, instrument_id) -> float:
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        return sum(float(str(p.quantity)) for p in open_positions)

    def _prune_spread_window(self, cutoff_ns: int) -> None:
        while self._spread_deque and self._spread_deque[0][0] < cutoff_ns:
            self._spread_deque.popleft()

    def _spread_gate_skip(self, order) -> bool:
        """Return True if the latest spread sits above the rolling quantile.

        Verbatim port from ptg-isl-g1l1's `_spread_gate_skip` — same window,
        same quantile, same min_samples, same warm-up semantics.
        """
        cutoff_ns = order.ts_init - self._spread_window_ns
        self._prune_spread_window(cutoff_ns)

        n = len(self._spread_deque)
        if n < self._spread_min_samples or self._latest_spread is None:
            return False  # warm-up: do not gate

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

    def _prune_flow_window(self, cutoff_ns: int) -> None:
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            _, old_vol = self._flow_deque.popleft()
            self._net_flow -= old_vol

    def _flow_gate_skip(self, order) -> bool:
        """Return True if net aggressor flow is adverse for this order direction.

        BUY  order: adverse when net_flow <= -flow_threshold (sellers dominate).
        SELL order: adverse when net_flow >=  flow_threshold (buyers dominate).

        Warm-up: when no trade data is in the window, do not gate (returns
        False) and increment the warm-up counter so the diagnostic surfaces
        a "gate had no flow signal" condition distinctly from "gate evaluated
        as benign".
        """
        cutoff_ns = order.ts_init - self._flow_window_ns
        self._prune_flow_window(cutoff_ns)

        if not self._flow_deque:
            self._flow_warm_up_count += 1
            return False

        net = self._net_flow

        if order.side == OrderSide.BUY:
            if net <= -self._flow_threshold:
                self.log.debug(
                    f"BUY adverse flow: net_flow={net:.2f} <= "
                    f"-threshold={-self._flow_threshold:.2f}; SKIP."
                )
                return True
        else:  # SELL
            if net >= self._flow_threshold:
                self.log.debug(
                    f"SELL adverse flow: net_flow={net:.2f} >= "
                    f"threshold={self._flow_threshold:.2f}; SKIP."
                )
                return True

        return False

    # ------------------------------------------------------------------
    # Main order handler — three binary OR-skip gates
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        if order.is_reduce_only:
            self.submit_order(order)
            return

        # OPEN leg: evaluate all three gates (OR-skip composition).
        self._evaluated_open_count += 1

        # Gate 1: position-tier-gate (inherited base behavior).
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty >= self._position_cap:
            self.log.debug(
                f"POSITION SKIP {order.client_order_id} — net_qty={net_qty:.1f} "
                f">= cap={self._position_cap}."
            )
            self._position_skip_count += 1
            return

        # Gate 2: spread gate.
        if self._spread_gate_skip(order):
            self._spread_skip_count += 1
            return

        # Gate 3: aggressor-flow gate (NEW for g3l1).
        if self._flow_gate_skip(order):
            self._flow_skip_count += 1
            return

        self._submit_count += 1
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    spread_window_seconds: float = 60.0,
    spread_quantile: float = 0.75,
    spread_min_samples: int = 50,
    flow_window_seconds: float = 10.0,
    flow_threshold: float = 3.0,
) -> PtgIslG3L1Algorithm:
    config = PtgIslG3L1Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        spread_window_seconds=spread_window_seconds,
        spread_quantile=spread_quantile,
        spread_min_samples=spread_min_samples,
        flow_window_seconds=flow_window_seconds,
        flow_threshold=flow_threshold,
    )
    return PtgIslG3L1Algorithm(config=config)
