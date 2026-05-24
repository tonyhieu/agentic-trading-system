"""ptg-isl-g1l3: position-cap + rolling-spread + adaptive (rolling-quantile)
queue-imbalance gates.

Builds on `ptg-isl-g1l2` (island-0, generation 1, loop 2), which produced
a NULL result vs ptg-isl-g1l1 — bit-for-bit identical metrics despite
adding a queue-imbalance gate. Diagnosis (see NOTES.md): the static
thresholds 0.30 / 0.70 were too extreme for the q distribution that
*survives* the upstream position-cap + rolling-spread gates. On that
surviving slice the top-of-book sits in calm regimes where bid_size and
ask_size cluster near 50/50, so `q < 0.30` or `q > 0.70` effectively
never occurred and the gate was a no-op.

g1l3 replaces the static imbalance thresholds with an **adaptive
rolling-quantile** imbalance gate sharing the spread gate's 60-second
window:

Gates evaluated in order at `on_order()` for non-reduce-only orders:
  1. position-tier-gate: skip if net_qty >= position_cap.
  2. rolling-spread gate: skip if latest spread > rolling p75 of recent
     spreads (60s window, min 50 samples).
  3. adaptive imbalance gate (CHANGED):
       q = bid_size / (bid_size + ask_size) from the most recent quote.
       Track a rolling deque of q samples on the same 60s window.
       - BUY  OPEN: skip if latest q < rolling p_lo (default 0.10) of q.
       - SELL OPEN: skip if latest q > rolling p_hi (default 0.90) of q.

Adaptive thresholds self-calibrate: by construction the gate fires on
roughly the bottom (top) 10% of the recent q distribution, regardless
of where that distribution sits. This resolves g1l2's "gate never fires"
problem while keeping the orthogonal "which side is being eaten"
signal that the original hypothesis targeted.

Instrumentation: per-gate skip counters are accumulated through the run
and logged at `on_stop`. Resolves g1l2's diagnostic gap — future
island-0 loops can distinguish "never fired", "fired but EV-neutral",
and "implementation bug" by reading the backtest stdout/log.

No look-ahead: quote-tick fields populate caches and deques in
chronological replay order; `on_order` reads cached latest values only.

No quantity modification: SKIP means do not submit.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PtgIslG1L3Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for ptg-isl-g1l3.

    Parameters
    ----------
    position_cap : int
        Inherited from position-tier-gate. Skip OPEN if absolute net
        position >= position_cap. Default 1.
    spread_window_seconds : float
        Rolling window (seconds) shared by both the spread gate and the
        adaptive imbalance gate. Default 60.0.
    spread_quantile : float
        Spread-gate quantile in (0, 1). Default 0.75.
    min_samples : int
        Minimum rolling samples before *either* adaptive gate (spread or
        imbalance) is allowed to fire. Default 50.
    imbalance_lower_quantile : float
        BUY OPENs are skipped when latest q is strictly less than this
        rolling quantile of q over the window. Default 0.10.
    imbalance_upper_quantile : float
        SELL OPENs are skipped when latest q is strictly greater than
        this rolling quantile of q over the window. Default 0.90.
    """

    position_cap: int = 1
    spread_window_seconds: float = 60.0
    spread_quantile: float = 0.75
    min_samples: int = 50
    imbalance_lower_quantile: float = 0.10
    imbalance_upper_quantile: float = 0.90


class PtgIslG1L3Algorithm(ExecAlgorithm):
    """ExecAlgorithm: position-cap + spread-quantile + adaptive-imbalance gates."""

    def __init__(self, config: PtgIslG1L3Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        self._spread_window_ns: int = int(config.spread_window_seconds * 1_000_000_000)
        self._spread_quantile: float = config.spread_quantile
        self._min_samples: int = config.min_samples
        self._imb_lo_q: float = config.imbalance_lower_quantile
        self._imb_hi_q: float = config.imbalance_upper_quantile

        # Rolling samples: (ts_event_ns, value).
        self._spread_deque: deque[tuple[int, float]] = deque()
        self._q_deque: deque[tuple[int, float]] = deque()

        # Most recent observed values from quote ticks.
        self._latest_spread: float | None = None
        self._latest_q: float | None = None

        # Subscription tracking (we need quote ticks).
        self._subscribed: set[str] = set()

        # Diagnostic counters — emitted at on_stop. Resolves g1l2's
        # "cannot tell if gate fired" gap.
        self._evaluated_open_orders: int = 0
        self._skipped_position: int = 0
        self._skipped_spread: int = 0
        self._skipped_imbalance_buy: int = 0
        self._skipped_imbalance_sell: int = 0
        self._passed_all_gates: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"PtgIslG1L3Algorithm started "
            f"(position_cap={self._position_cap}, "
            f"spread_window={self._spread_window_ns / 1e9:.1f}s, "
            f"spread_quantile={self._spread_quantile:.2f}, "
            f"min_samples={self._min_samples}, "
            f"imbalance_lo_q={self._imb_lo_q:.2f}, "
            f"imbalance_hi_q={self._imb_hi_q:.2f})."
        )

    def on_reset(self) -> None:
        self._spread_deque.clear()
        self._q_deque.clear()
        self._latest_spread = None
        self._latest_q = None
        self._subscribed.clear()
        self._evaluated_open_orders = 0
        self._skipped_position = 0
        self._skipped_spread = 0
        self._skipped_imbalance_buy = 0
        self._skipped_imbalance_sell = 0
        self._passed_all_gates = 0

    def on_stop(self) -> None:
        # Emit gate diagnostics so future loops can distinguish
        # "gate never fired" from "gate fired but EV-neutral".
        self.log.info(
            f"PtgIslG1L3Algorithm gate counters: "
            f"evaluated_open_orders={self._evaluated_open_orders}, "
            f"skipped_position={self._skipped_position}, "
            f"skipped_spread={self._skipped_spread}, "
            f"skipped_imbalance_buy={self._skipped_imbalance_buy}, "
            f"skipped_imbalance_sell={self._skipped_imbalance_sell}, "
            f"passed_all_gates={self._passed_all_gates}."
        )

    # ------------------------------------------------------------------
    # Subscription helper
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Quote tick handler — maintain rolling spread + q samples
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        try:
            bid = float(str(tick.bid_price))
            ask = float(str(tick.ask_price))
            bid_size = float(str(tick.bid_size))
            ask_size = float(str(tick.ask_size))
        except Exception:
            return

        spread = ask - bid
        if spread < 0.0:
            # Defensive: crossed book — skip the sample entirely.
            return

        ts_ns = tick.ts_event
        self._spread_deque.append((ts_ns, spread))
        self._latest_spread = spread

        total = bid_size + ask_size
        if total > 0.0:
            q = bid_size / total
            self._q_deque.append((ts_ns, q))
            self._latest_q = q
        # If total == 0 (both sides empty), do not update q caches —
        # the prior latest_q remains as best-available context.

    # ------------------------------------------------------------------
    # Gate helpers
    # ------------------------------------------------------------------

    def _current_net_qty(self, instrument_id) -> float:
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        return sum(float(str(p.quantity)) for p in open_positions)

    @staticmethod
    def _prune_window(dq: deque[tuple[int, float]], cutoff_ns: int) -> None:
        while dq and dq[0][0] < cutoff_ns:
            dq.popleft()

    @staticmethod
    def _linear_quantile(sorted_vals: list[float], q: float) -> float:
        """Linear-interpolation quantile on a pre-sorted list."""
        n = len(sorted_vals)
        if n == 1:
            return sorted_vals[0]
        idx_f = q * (n - 1)
        lo = int(idx_f)
        hi = min(lo + 1, n - 1)
        frac = idx_f - lo
        return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac

    def _spread_gate_skip(self, order) -> bool:
        """Return True if the latest spread sits above the rolling quantile."""
        cutoff_ns = order.ts_init - self._spread_window_ns
        self._prune_window(self._spread_deque, cutoff_ns)

        n = len(self._spread_deque)
        if n < self._min_samples or self._latest_spread is None:
            return False  # warm-up: do not gate

        sorted_spreads = sorted(s for _, s in self._spread_deque)
        threshold = self._linear_quantile(sorted_spreads, self._spread_quantile)

        if self._latest_spread > threshold:
            self.log.debug(
                f"SPREAD SKIP {order.client_order_id} — "
                f"latest_spread={self._latest_spread:.5f} > "
                f"q{self._spread_quantile:.2f}={threshold:.5f} "
                f"(n={n})."
            )
            return True
        return False

    def _imbalance_gate_skip(self, order) -> tuple[bool, str | None]:
        """Return (skip?, side_label) for the adaptive imbalance gate.

        side_label is "buy" or "sell" when a skip fires (for counter
        attribution); None otherwise.
        """
        cutoff_ns = order.ts_init - self._spread_window_ns
        self._prune_window(self._q_deque, cutoff_ns)

        n = len(self._q_deque)
        if n < self._min_samples or self._latest_q is None:
            return False, None  # warm-up: do not gate

        sorted_q = sorted(v for _, v in self._q_deque)
        lo_threshold = self._linear_quantile(sorted_q, self._imb_lo_q)
        hi_threshold = self._linear_quantile(sorted_q, self._imb_hi_q)

        # Robust side detection (Nautilus OrderSide enum string repr
        # commonly ends in BUY / SELL).
        side_str = str(order.side).upper()
        is_buy = side_str.endswith("BUY")
        is_sell = side_str.endswith("SELL")

        if is_buy and self._latest_q < lo_threshold:
            self.log.debug(
                f"IMBALANCE SKIP {order.client_order_id} — BUY blocked: "
                f"q={self._latest_q:.3f} < p{self._imb_lo_q:.2f}={lo_threshold:.3f} "
                f"(n={n})."
            )
            return True, "buy"
        if is_sell and self._latest_q > hi_threshold:
            self.log.debug(
                f"IMBALANCE SKIP {order.client_order_id} — SELL blocked: "
                f"q={self._latest_q:.3f} > p{self._imb_hi_q:.2f}={hi_threshold:.3f} "
                f"(n={n})."
            )
            return True, "sell"
        return False, None

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        if order.is_reduce_only:
            self.submit_order(order)
            return

        self._evaluated_open_orders += 1

        # Gate 1: position-tier-gate (inherited base behavior).
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty >= self._position_cap:
            self.log.debug(
                f"POSITION SKIP {order.client_order_id} — net_qty={net_qty:.1f} "
                f">= cap={self._position_cap}."
            )
            self._skipped_position += 1
            return

        # Gate 2: rolling-spread quantile gate.
        if self._spread_gate_skip(order):
            self._skipped_spread += 1
            return

        # Gate 3: adaptive (rolling-quantile) queue-imbalance gate.
        skip, side_label = self._imbalance_gate_skip(order)
        if skip:
            if side_label == "buy":
                self._skipped_imbalance_buy += 1
            else:
                self._skipped_imbalance_sell += 1
            return

        self._passed_all_gates += 1
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    spread_window_seconds: float = 60.0,
    spread_quantile: float = 0.75,
    min_samples: int = 50,
    imbalance_lower_quantile: float = 0.10,
    imbalance_upper_quantile: float = 0.90,
) -> PtgIslG1L3Algorithm:
    config = PtgIslG1L3Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        spread_window_seconds=spread_window_seconds,
        spread_quantile=spread_quantile,
        min_samples=min_samples,
        imbalance_lower_quantile=imbalance_lower_quantile,
        imbalance_upper_quantile=imbalance_upper_quantile,
    )
    return PtgIslG1L3Algorithm(config=config)
