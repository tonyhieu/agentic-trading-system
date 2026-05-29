"""ptg-pc-r4 execution algorithm.

ADVERSE-TICK-FLOW SKIP gate, layered on top of position-tier-gate (cap=1).

Hypothesis (see NOTES.md):
  In tight-spread regimes (modal MES state), a sharp 100ms adverse mid move
  BEFORE the oracle's OPEN signals that the oracle is reacting to a transient
  price excursion that has already partially mean-reverted away from the
  oracle's 30s direction estimate. Empirical analysis of the 12-date train
  window (re-validated at orders.csv ts_init) shows these trades have win
  rate ~30% (vs 37% overall) and aggregate PnL clearly negative. SKIPping
  them yields +13.74% improvement in train.

Algorithm (per on_order):
  1. CLOSE (is_reduce_only=True): always SUBMIT.
  2. OPEN:
     a. Apply the position-cap gate (cap=1, from base position-tier-gate).
        If net_qty >= 1, SKIP.
     b. Otherwise apply the adverse-tick filter:
        - Fetch latest quote from cache.quote_tick(instrument_id).
        - Find the buffered quote with ts_event <= now - 100ms via
          bisect_right on the timestamp deque.
        - If either is missing, SUBMIT (safe default).
        - Compute signed_mom_100 = (mid_now - mid_back) / TICK_SIZE * side_sign
          where side_sign = +1 for BUY, -1 for SELL.
        - Compute spread_ticks = (ask - bid) / TICK_SIZE.
        - If signed_mom_100 <= -1.0 AND spread_ticks <= 1.0: SKIP.
        - Else: SUBMIT.

Quote tick subscription is lazy (first on_order call per instrument).

Buffer is a deque of (ts_event_ns, mid, spread) tuples, populated in
on_quote_tick. Pruned from the LEFT while ts_event_ns < latest_ts - 200ms
(2x the lookback to ensure a quote exists at or before now - 100ms).

No look-ahead: the buffer only contains quotes that have been delivered to
on_quote_tick (= ts_event <= current sim time). The bisect_right lookup at
on_order time selects the latest quote with ts_event <= now - 100ms, never
the quote that fills the order or a quote in the future.

No quantity modification: quantity invariant preserved.
"""
from __future__ import annotations

import bisect
from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


# MES tick size (USD). Hard-coded since the instrument is fixed by config.
TICK_SIZE = 0.25

# Lookback window for the signed_mom_100 measurement (nanoseconds).
LOOKBACK_NS = 100_000_000  # 100 ms

# Buffer retention (nanoseconds). 2x lookback ensures at least one quote
# exists at or before now - LOOKBACK_NS for any decision-time call.
BUFFER_RETENTION_NS = 200_000_000  # 200 ms


class PtgPcR4Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for ptg-pc-r4.

    Parameters
    ----------
    position_cap : int
        Maximum absolute net position size (contracts) at which new OPEN-leg
        orders are still allowed. Default 1 (matches base position-tier-gate).
    adverse_tick_threshold : float
        signed_mom_100 (in tick units) at or below which the OPEN is skipped
        (after passing the spread gate). Default -1.0 (one full tick against
        the OPEN direction in the last 100ms).
    spread_max_ticks : float
        Maximum spread (in tick units) at which the adverse-tick filter
        activates. Default 1.0 (MES tick floor). Wider-spread OPENs always
        submit (they are positive-EV in news/burst regimes per empirical
        analysis).
    """

    position_cap: int = 1
    adverse_tick_threshold: float = -1.0
    spread_max_ticks: float = 1.0


class PtgPcR4Algorithm(ExecAlgorithm):
    """position-tier-gate (cap=1) with an adverse-tick-flow SKIP gate."""

    def __init__(self, config: PtgPcR4Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        self._adverse_threshold: float = config.adverse_tick_threshold
        self._spread_max_ticks: float = config.spread_max_ticks

        # Lazy quote-tick subscription tracking.
        self._subscribed_instruments: set = set()

        # Rolling buffer of recent quotes. We keep three parallel deques so
        # bisect on the timestamps works without a custom key.
        self._ts_buf: deque = deque()
        self._mid_buf: deque = deque()
        self._spread_buf: deque = deque()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"PtgPcR4Algorithm started "
            f"(position_cap={self._position_cap}, "
            f"adverse_threshold={self._adverse_threshold:.2f} ticks, "
            f"spread_max={self._spread_max_ticks:.2f} ticks)."
        )

    def on_reset(self) -> None:
        self._subscribed_instruments.clear()
        self._ts_buf.clear()
        self._mid_buf.clear()
        self._spread_buf.clear()

    # ------------------------------------------------------------------
    # Quote tick handler
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        """Append the quote to the rolling buffer; prune old entries."""
        try:
            bid = float(tick.bid_price)
            ask = float(tick.ask_price)
        except Exception:  # pragma: no cover - defensive
            return

        mid = (bid + ask) / 2.0
        spread = ask - bid
        ts = int(tick.ts_event)

        self._ts_buf.append(ts)
        self._mid_buf.append(mid)
        self._spread_buf.append(spread)

        # Prune from the LEFT while leftmost ts < latest_ts - BUFFER_RETENTION_NS.
        cutoff = ts - BUFFER_RETENTION_NS
        while self._ts_buf and self._ts_buf[0] < cutoff:
            self._ts_buf.popleft()
            self._mid_buf.popleft()
            self._spread_buf.popleft()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _current_net_qty(self, instrument_id) -> float:
        """Return absolute net position quantity for the instrument."""
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        return sum(float(str(p.quantity)) for p in open_positions)

    def _ensure_quote_subscription(self, instrument_id) -> None:
        """Lazy-subscribe to quote ticks for this instrument."""
        if instrument_id in self._subscribed_instruments:
            return
        try:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed_instruments.add(instrument_id)
            self.log.info(f"Subscribed to quote ticks for {instrument_id}.")
        except Exception as exc:  # pragma: no cover - defensive
            self.log.warning(
                f"Failed to subscribe_quote_ticks for {instrument_id}: {exc}"
            )

    def _should_skip_open_adverse_tick(self, order) -> bool:
        """Return True iff the OPEN should be skipped by the adverse-tick filter.

        Safe defaults (return False = SUBMIT) when measurement is impossible:
          - latest quote not available
          - buffer too small
          - no buffered quote at or before now - 100ms
          - any exception during computation
        """
        instrument_id = order.instrument_id

        try:
            # Latest quote from the cache (also drives mid_now / spread_now).
            quote_now = self.cache.quote_tick(instrument_id)
            if quote_now is None:
                return False

            mid_now = (float(quote_now.bid_price) + float(quote_now.ask_price)) / 2.0
            spread_now = float(quote_now.ask_price) - float(quote_now.bid_price)
            spread_ticks = spread_now / TICK_SIZE

            # Cold buffer guard.
            if len(self._ts_buf) < 2:
                return False

            ts_now = self.clock.timestamp_ns()
            ts_back = ts_now - LOOKBACK_NS

            # Find latest buffered ts <= ts_back.
            idx = bisect.bisect_right(self._ts_buf, ts_back) - 1
            if idx < 0:
                return False

            mid_back = self._mid_buf[idx]

            # Signed momentum in tick units, positive = same direction as OPEN.
            side_str = str(order.side)
            # OrderSide enum: BUY = 1, SELL = 2. Stringify and check suffix.
            if side_str.endswith("BUY") or side_str == "1":
                side_sign = 1.0
            elif side_str.endswith("SELL") or side_str == "2":
                side_sign = -1.0
            else:  # pragma: no cover - defensive
                return False

            signed_mom_ticks = (mid_now - mid_back) / TICK_SIZE * side_sign

            # SKIP if adverse momentum AND tight spread.
            if (
                signed_mom_ticks <= self._adverse_threshold
                and spread_ticks <= self._spread_max_ticks
            ):
                return True
            return False
        except Exception as exc:  # pragma: no cover - defensive
            self.log.warning(
                f"_should_skip_open_adverse_tick error for {instrument_id}: {exc}"
            )
            return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: position-cap gate, then adverse-tick gate, on OPENs."""

        # Lazy quote-tick subscription on first order per instrument
        # (idempotent; the first OPEN will have an empty buffer and fall
        # through the safe-SUBMIT default).
        self._ensure_quote_subscription(order.instrument_id)

        # CLOSE leg: always submit unchanged (intraday_flat compliance).
        if order.is_reduce_only:
            self.log.debug(
                f"SUBMIT CLOSE {order.client_order_id} (reduce-only)."
            )
            self.submit_order(order)
            return

        # OPEN leg: position-cap gate (verbatim from base position-tier-gate).
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty >= self._position_cap:
            self.log.debug(
                f"SKIP OPEN {order.client_order_id} — position cap reached "
                f"(net_qty={net_qty:.1f} >= cap={self._position_cap})."
            )
            return

        # OPEN leg: adverse-tick gate (only if cap allows the order).
        if self._should_skip_open_adverse_tick(order):
            self.log.debug(
                f"SKIP OPEN {order.client_order_id} — adverse tick flow "
                f"(mom_100 <= {self._adverse_threshold:.2f} ticks AND "
                f"spread <= {self._spread_max_ticks:.2f} ticks)."
            )
            return

        self.log.debug(
            f"SUBMIT OPEN {order.client_order_id} (net_qty={net_qty:.1f})."
        )
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    adverse_tick_threshold: float = -1.0,
    spread_max_ticks: float = 1.0,
) -> PtgPcR4Algorithm:
    """Instantiate the ptg-pc-r4 execution algorithm."""
    config = PtgPcR4Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        adverse_tick_threshold=adverse_tick_threshold,
        spread_max_ticks=spread_max_ticks,
    )
    return PtgPcR4Algorithm(config=config)
