"""ptg-isl-g1l2: position-cap + rolling-spread + queue-imbalance gates.

Builds on `ptg-isl-g1l1` (island-0, generation 1, loop 1) by adding a
third, orthogonal OPEN gate: side-dependent top-of-book queue imbalance.

Gates evaluated in order at `on_order()` for non-reduce-only orders:
  1. position-tier-gate: skip if net_qty >= position_cap.
  2. rolling-spread gate: skip if latest spread > rolling p75 of recent
     spreads (60s window, min 50 samples).
  3. queue-imbalance gate (NEW):
       q = bid_size / (bid_size + ask_size) from the most recent quote.
       - BUY  OPEN: skip if q < buy_block_threshold  (default 0.30).
       - SELL OPEN: skip if q > sell_block_threshold (default 0.70).

Hypothesis
----------
g1l1's spread gate filtered only ~3.4% of post-position-cap entries yet
captured a +26.55% pnl lift. The surviving entries mostly sit in calm
spread regimes; residual losses concentrate on a different
microstructure axis — direction of immediate book pressure. Queue
imbalance (q) measures which side of the top-of-book is being eaten or
stacked. For a BUY, very low q (sellers dominant) typically precedes a
downtick within sub-second horizons; for a SELL, very high q (buyers
dominant) precedes an uptick. Blocking these direction-wrong opens
should remove a small slice of high-variance losers without harming
the bulk of edge-positive entries.

Composition rationale: spread says "how wide is the top," imbalance
says "which side is being eaten." The two filters address orthogonal
sources of adverse selection and should compose additively.

No look-ahead: quote-tick fields populate `_latest_*` in chronological
replay order; `on_order` reads cached latest values only.

No quantity modification: SKIP means do not submit.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PtgIslG1L2Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for ptg-isl-g1l2.

    Parameters
    ----------
    position_cap : int
        Inherited from position-tier-gate. Skip OPEN if absolute net
        position >= position_cap. Default 1.
    spread_window_seconds : float
        Rolling window for spread samples (seconds). Default 60.0.
    spread_quantile : float
        Spread-gate quantile in (0, 1). Default 0.75.
    min_samples : int
        Minimum samples before the spread gate fires. Default 50.
    buy_block_threshold : float
        BUY OPENs are skipped when bid_share q = bid_size / (bid_size +
        ask_size) is strictly less than this. Default 0.30.
    sell_block_threshold : float
        SELL OPENs are skipped when q is strictly greater than this.
        Default 0.70.
    """

    position_cap: int = 1
    spread_window_seconds: float = 60.0
    spread_quantile: float = 0.75
    min_samples: int = 50
    buy_block_threshold: float = 0.30
    sell_block_threshold: float = 0.70


class PtgIslG1L2Algorithm(ExecAlgorithm):
    """ExecAlgorithm: position-cap + spread-quantile + queue-imbalance gates."""

    def __init__(self, config: PtgIslG1L2Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        self._spread_window_ns: int = int(config.spread_window_seconds * 1_000_000_000)
        self._spread_quantile: float = config.spread_quantile
        self._min_samples: int = config.min_samples
        self._buy_block_threshold: float = config.buy_block_threshold
        self._sell_block_threshold: float = config.sell_block_threshold

        # Rolling spread samples: (ts_event_ns, spread).
        self._spread_deque: deque[tuple[int, float]] = deque()
        # Most recent observed spread + top-of-book sizes.
        self._latest_spread: float | None = None
        self._latest_bid_size: float | None = None
        self._latest_ask_size: float | None = None

        # Subscription tracking (we need quote ticks).
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"PtgIslG1L2Algorithm started "
            f"(position_cap={self._position_cap}, "
            f"spread_window={self._spread_window_ns / 1e9:.1f}s, "
            f"spread_quantile={self._spread_quantile:.2f}, "
            f"min_samples={self._min_samples}, "
            f"buy_block_threshold={self._buy_block_threshold:.2f}, "
            f"sell_block_threshold={self._sell_block_threshold:.2f})."
        )

    def on_reset(self) -> None:
        self._spread_deque.clear()
        self._latest_spread = None
        self._latest_bid_size = None
        self._latest_ask_size = None
        self._subscribed.clear()

    # ------------------------------------------------------------------
    # Subscription helper
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Quote tick handler — maintain rolling spread samples + latest sizes
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

        self._spread_deque.append((tick.ts_event, spread))
        self._latest_spread = spread
        self._latest_bid_size = bid_size
        self._latest_ask_size = ask_size

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
        """Return True if the latest spread sits above the rolling quantile."""
        cutoff_ns = order.ts_init - self._spread_window_ns
        self._prune_spread_window(cutoff_ns)

        n = len(self._spread_deque)
        if n < self._min_samples or self._latest_spread is None:
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
                f"q{self._spread_quantile:.2f}={threshold:.5f} "
                f"(n={n})."
            )
            return True
        return False

    def _imbalance_gate_skip(self, order) -> bool:
        """Return True if directional queue imbalance is adverse for this side."""
        bid_size = self._latest_bid_size
        ask_size = self._latest_ask_size
        if bid_size is None or ask_size is None:
            return False  # no quote seen yet
        total = bid_size + ask_size
        if total <= 0.0:
            return False  # invalid / both sides empty — cannot reason
        q = bid_size / total

        # Robust side detection (Nautilus OrderSide enum string repr varies).
        side_str = str(order.side).upper()
        is_buy = side_str.endswith("BUY")
        is_sell = side_str.endswith("SELL")

        if is_buy and q < self._buy_block_threshold:
            self.log.debug(
                f"IMBALANCE SKIP {order.client_order_id} — BUY blocked: "
                f"q={q:.3f} < {self._buy_block_threshold:.2f} "
                f"(bid_size={bid_size:.0f}, ask_size={ask_size:.0f})."
            )
            return True
        if is_sell and q > self._sell_block_threshold:
            self.log.debug(
                f"IMBALANCE SKIP {order.client_order_id} — SELL blocked: "
                f"q={q:.3f} > {self._sell_block_threshold:.2f} "
                f"(bid_size={bid_size:.0f}, ask_size={ask_size:.0f})."
            )
            return True
        return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        if order.is_reduce_only:
            self.submit_order(order)
            return

        # Gate 1: position-tier-gate (inherited base behavior).
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty >= self._position_cap:
            self.log.debug(
                f"POSITION SKIP {order.client_order_id} — net_qty={net_qty:.1f} "
                f">= cap={self._position_cap}."
            )
            return

        # Gate 2: rolling-spread quantile gate.
        if self._spread_gate_skip(order):
            return

        # Gate 3: directional queue-imbalance gate (NEW).
        if self._imbalance_gate_skip(order):
            return

        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    spread_window_seconds: float = 60.0,
    spread_quantile: float = 0.75,
    min_samples: int = 50,
    buy_block_threshold: float = 0.30,
    sell_block_threshold: float = 0.70,
) -> PtgIslG1L2Algorithm:
    config = PtgIslG1L2Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        spread_window_seconds=spread_window_seconds,
        spread_quantile=spread_quantile,
        min_samples=min_samples,
        buy_block_threshold=buy_block_threshold,
        sell_block_threshold=sell_block_threshold,
    )
    return PtgIslG1L2Algorithm(config=config)
