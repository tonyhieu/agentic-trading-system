"""ptg-pc-r5 execution algorithm.

ORDER-BOOK-DELTA-BACKED ADVERSE-MOM SKIP gate, layered on top of
position-tier-gate (cap=1).

Hypothesis (see NOTES.md):
  Same as r4 — exploit the oracle's overreaction to transient 100ms adverse
  mid moves in tight-spread regimes. Offline analysis on the 12-date train
  window showed +13.74% PnL when the signal is sampled at MBP-1 cadence.
  r4's LIVE implementation collapsed to -3.14% because on_quote_tick fires
  only on top-of-book CHANGES (hypothesis (c) per r4 NOTES), under-firing
  by 10-15x in dense periods.

Three concrete fixes vs r4:
  (1) STRUCTURAL: subscribe to order_book_deltas (every level update) rather
      than quote_ticks (TOB changes only). This is the channel switch that
      directly addresses hypothesis (c).
  (2) STALENESS GUARDS: at on_order, refuse to SKIP when the buffer's view
      of "now" is causally inconsistent (future) or too old (>100ms stale)
      relative to the order's ts_init. Bounds live downside to ~r4 levels.
  (3) DIAGNOSTICS: count callbacks and emit a session-end log line. Makes
      the under-fire root cause empirically observable in one run.

Decision rule (per on_order, OPENs only, after cap=1 passes):
  - signed_mom_100 = (mid_now - mid_100ms_ago) / TICK_SIZE * side_sign
  - spread_ticks = (ask - bid) / TICK_SIZE  (from buffer's latest entry)
  - SKIP iff signed_mom_100 <= -1.0 AND spread_ticks <= 1.0
  - Else SUBMIT

Buffer is a deque of (ts_event_ns, mid, spread) tuples, populated in
on_order_book_deltas (NOT on_quote_tick). Pruned from the LEFT while
ts_event_ns < latest_ts - 200ms.

CLOSE orders (is_reduce_only=True) always submit unchanged.

No look-ahead: bisect_right on the buffer at on_order() time selects the
latest buffered quote with ts_event <= now - 100ms; the buffer only contains
deltas already delivered to on_order_book_deltas (= ts_event <= current sim
time). The causal-violation staleness guard makes this explicit.

No quantity modification: quantity invariant preserved.
"""
from __future__ import annotations

import bisect
from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import BookType
from nautilus_trader.model.identifiers import ExecAlgorithmId, InstrumentId


# MES tick size (USD). Hard-coded since the instrument is fixed by config.
TICK_SIZE = 0.25

# Lookback window for the signed_mom_100 measurement (nanoseconds).
LOOKBACK_NS = 100_000_000  # 100 ms

# Buffer retention (nanoseconds). 2x lookback ensures at least one quote
# exists at or before now - LOOKBACK_NS for any decision-time call.
BUFFER_RETENTION_NS = 200_000_000  # 200 ms

# Staleness guard: refuse to SKIP if buffer's latest ts is more than this
# many ns OLDER than the order's ts_init.
MAX_BUFFER_LAG_NS = 100_000_000  # 100 ms

# Staleness guard: refuse to SKIP if the lookback quote itself is more than
# this many ns OLDER than the (now - LOOKBACK_NS) target.
MAX_LOOKBACK_STALENESS_NS = 500_000_000  # 500 ms


class PtgPcR5Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for ptg-pc-r5.

    Parameters
    ----------
    position_cap : int
        Maximum absolute net position size (contracts) at which new OPEN-leg
        orders are still allowed. Default 1 (matches base position-tier-gate).
    adverse_tick_threshold : float
        signed_mom_100 (in tick units) at or below which the OPEN is skipped
        (after passing the spread gate). Default -1.0.
    spread_max_ticks : float
        Maximum spread (in tick units) at which the adverse-mom filter
        activates. Default 1.0 (MES tick floor).
    """

    position_cap: int = 1
    adverse_tick_threshold: float = -1.0
    spread_max_ticks: float = 1.0


class PtgPcR5Algorithm(ExecAlgorithm):
    """position-tier-gate (cap=1) + order-book-delta-backed adverse-mom SKIP."""

    def __init__(self, config: PtgPcR5Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        self._adverse_threshold: float = config.adverse_tick_threshold
        self._spread_max_ticks: float = config.spread_max_ticks

        # Subscription tracking.
        self._subscribed_instruments: set = set()

        # Rolling buffer of recent quotes derived from order book deltas.
        self._ts_buf: deque = deque()
        self._mid_buf: deque = deque()
        self._spread_buf: deque = deque()

        # Diagnostic counters.
        self._n_deltas: int = 0
        self._n_deltas_with_book: int = 0
        self._n_orders_seen: int = 0
        self._n_closes: int = 0
        self._n_opens: int = 0
        self._n_skips_cap: int = 0
        self._n_skips_adverse: int = 0
        self._n_submits_passed_both: int = 0
        self._n_safe_submit_no_book: int = 0
        self._n_safe_submit_cold_buffer: int = 0
        self._n_safe_submit_no_lookback: int = 0
        self._n_safe_submit_buffer_future: int = 0
        self._n_safe_submit_buffer_stale: int = 0
        self._n_safe_submit_lookback_stale: int = 0
        self._n_safe_submit_exception: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"PtgPcR5Algorithm started "
            f"(position_cap={self._position_cap}, "
            f"adverse_threshold={self._adverse_threshold:.2f} ticks, "
            f"spread_max={self._spread_max_ticks:.2f} ticks)."
        )

        # Eager subscription: walk the cache for known instruments and
        # subscribe to order book deltas for each. If the cache is empty
        # at on_start (instruments not yet loaded), we fall back to lazy
        # subscription on the first on_order().
        try:
            instruments = self.cache.instruments()
            for instrument in instruments:
                self._ensure_book_subscription(instrument.id)
            if not instruments:
                self.log.info(
                    "No instruments in cache at on_start; will lazily subscribe "
                    "on first on_order()."
                )
        except Exception as exc:  # pragma: no cover - defensive
            self.log.warning(f"Eager instrument subscription failed: {exc}")

    def on_stop(self) -> None:
        # Emit the diagnostic line. This is the falsifiability hook —
        # if n_deltas is low, hypothesis (c) holds at the dataset level
        # (the structural channel switch did not raise delivery density).
        self.log.info(
            "PtgPcR5Algorithm diagnostics: "
            f"n_deltas={self._n_deltas} "
            f"n_deltas_with_book={self._n_deltas_with_book} "
            f"buffer_len_at_stop={len(self._ts_buf)} "
            f"n_orders_seen={self._n_orders_seen} "
            f"n_closes={self._n_closes} "
            f"n_opens={self._n_opens} "
            f"n_skips_cap={self._n_skips_cap} "
            f"n_skips_adverse={self._n_skips_adverse} "
            f"n_submits_passed_both={self._n_submits_passed_both} "
            f"n_safe_submit_no_book={self._n_safe_submit_no_book} "
            f"n_safe_submit_cold_buffer={self._n_safe_submit_cold_buffer} "
            f"n_safe_submit_no_lookback={self._n_safe_submit_no_lookback} "
            f"n_safe_submit_buffer_future={self._n_safe_submit_buffer_future} "
            f"n_safe_submit_buffer_stale={self._n_safe_submit_buffer_stale} "
            f"n_safe_submit_lookback_stale={self._n_safe_submit_lookback_stale} "
            f"n_safe_submit_exception={self._n_safe_submit_exception}"
        )

    def on_reset(self) -> None:
        self._subscribed_instruments.clear()
        self._ts_buf.clear()
        self._mid_buf.clear()
        self._spread_buf.clear()
        # Diagnostic counters reset.
        self._n_deltas = 0
        self._n_deltas_with_book = 0
        self._n_orders_seen = 0
        self._n_closes = 0
        self._n_opens = 0
        self._n_skips_cap = 0
        self._n_skips_adverse = 0
        self._n_submits_passed_both = 0
        self._n_safe_submit_no_book = 0
        self._n_safe_submit_cold_buffer = 0
        self._n_safe_submit_no_lookback = 0
        self._n_safe_submit_buffer_future = 0
        self._n_safe_submit_buffer_stale = 0
        self._n_safe_submit_lookback_stale = 0
        self._n_safe_submit_exception = 0

    # ------------------------------------------------------------------
    # Order book delta handler — populate buffer from level updates.
    # ------------------------------------------------------------------

    def on_order_book_deltas(self, deltas) -> None:
        """On each batch of order book deltas, derive current best bid/ask
        from the cache's reconstructed book and append to the buffer.

        on_order_book_deltas fires for every level update (not just top-of-book
        changes), which is structurally a strict superset of on_quote_tick.
        Whether the actual MBP-1 stream emits multiple deltas per timestamp is
        a data-density question — the diagnostic counter exposes it.
        """
        try:
            self._n_deltas += 1
            instrument_id = deltas.instrument_id

            book = self.cache.order_book(instrument_id)
            if book is None:
                return

            bid = book.best_bid_price()
            ask = book.best_ask_price()
            if bid is None or ask is None:
                return

            bid_f = float(bid)
            ask_f = float(ask)
            mid = (bid_f + ask_f) / 2.0
            spread = ask_f - bid_f
            ts = int(deltas.ts_event)

            self._ts_buf.append(ts)
            self._mid_buf.append(mid)
            self._spread_buf.append(spread)
            self._n_deltas_with_book += 1

            # Prune left while leftmost ts < latest_ts - BUFFER_RETENTION_NS.
            cutoff = ts - BUFFER_RETENTION_NS
            while self._ts_buf and self._ts_buf[0] < cutoff:
                self._ts_buf.popleft()
                self._mid_buf.popleft()
                self._spread_buf.popleft()
        except Exception:  # pragma: no cover - defensive
            # Never let buffer maintenance errors crash the algo.
            return

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _current_net_qty(self, instrument_id) -> float:
        """Return absolute net position quantity for the instrument."""
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        return sum(float(str(p.quantity)) for p in open_positions)

    def _ensure_book_subscription(self, instrument_id) -> None:
        """Subscribe to L2_MBP order book deltas for this instrument (idempotent)."""
        if instrument_id in self._subscribed_instruments:
            return
        try:
            self.subscribe_order_book_deltas(
                instrument_id=instrument_id,
                book_type=BookType.L2_MBP,
            )
            self._subscribed_instruments.add(instrument_id)
            self.log.info(
                f"Subscribed to order book deltas (L2_MBP) for {instrument_id}."
            )
        except Exception as exc:  # pragma: no cover - defensive
            self.log.warning(
                f"Failed to subscribe_order_book_deltas for {instrument_id}: {exc}"
            )

    def _should_skip_open_adverse_mom(self, order) -> bool:
        """Return True iff the OPEN should be skipped by the adverse-mom filter.

        Safe defaults (return False = SUBMIT) when measurement is impossible
        or the data is stale/causally inconsistent.
        """
        try:
            # Need at least 2 buffered entries to compute a delta.
            if len(self._ts_buf) < 2:
                self._n_safe_submit_cold_buffer += 1
                return False

            # Use buffer's own latest entry for "now" — guarantees algorithm-
            # internal consistency between mid_now and mid_back (both sourced
            # from the same delta stream).
            buffer_latest_ts = self._ts_buf[-1]
            mid_now = self._mid_buf[-1]
            spread_now = self._spread_buf[-1]
            spread_ticks = spread_now / TICK_SIZE

            # Use the order's ts_init as the "decision time" reference.
            ts_decision = int(order.ts_init)

            # Causality guard: buffer should never contain a quote with
            # ts_event > order.ts_init (would be a future-data violation).
            if buffer_latest_ts > ts_decision:
                self._n_safe_submit_buffer_future += 1
                return False

            # Staleness guard: if buffer's latest is more than 100ms older
            # than the decision time, the signal is unreliable — SUBMIT.
            if buffer_latest_ts < ts_decision - MAX_BUFFER_LAG_NS:
                self._n_safe_submit_buffer_stale += 1
                return False

            # Find the buffered entry at or before (buffer_latest_ts - LOOKBACK_NS).
            ts_back_target = buffer_latest_ts - LOOKBACK_NS
            idx = bisect.bisect_right(self._ts_buf, ts_back_target) - 1
            if idx < 0:
                self._n_safe_submit_no_lookback += 1
                return False

            mid_back = self._mid_buf[idx]
            lookback_actual_ts = self._ts_buf[idx]

            # Lookback-staleness guard: if the selected back-quote is more
            # than 500ms older than the target (the buffer was sparse during
            # the lookback window), the signal isn't a clean 100ms diff.
            if lookback_actual_ts < ts_back_target - MAX_LOOKBACK_STALENESS_NS:
                self._n_safe_submit_lookback_stale += 1
                return False

            # Determine side sign. OrderSide enum: BUY=1, SELL=2.
            side_str = str(order.side)
            if side_str.endswith("BUY") or side_str == "1":
                side_sign = 1.0
            elif side_str.endswith("SELL") or side_str == "2":
                side_sign = -1.0
            else:  # pragma: no cover - defensive
                return False

            signed_mom_ticks = (mid_now - mid_back) / TICK_SIZE * side_sign

            # SKIP iff adverse momentum AND tight spread.
            if (
                signed_mom_ticks <= self._adverse_threshold
                and spread_ticks <= self._spread_max_ticks
            ):
                return True
            return False
        except Exception as exc:  # pragma: no cover - defensive
            self._n_safe_submit_exception += 1
            self.log.warning(
                f"_should_skip_open_adverse_mom error: {exc}"
            )
            return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: position-cap gate, then adverse-mom gate, on OPENs."""
        self._n_orders_seen += 1

        # Lazy fallback subscription if eager on_start subscription found no
        # instruments. This handles a rare race where the cache is empty at
        # on_start but populated by the time orders flow.
        self._ensure_book_subscription(order.instrument_id)

        # CLOSE leg: always submit (intraday_flat compliance).
        if order.is_reduce_only:
            self._n_closes += 1
            self.submit_order(order)
            return

        self._n_opens += 1

        # OPEN leg: position-cap gate (verbatim from base position-tier-gate).
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty >= self._position_cap:
            self._n_skips_cap += 1
            return

        # OPEN leg: adverse-mom gate (only when cap=1 allows the order).
        # The cache.order_book() call inside on_order_book_deltas may return
        # None during early-session warmup; that case is handled in the
        # callback (we simply don't append). Here we additionally guard
        # against the buffer being empty at decision time.
        if self._should_skip_open_adverse_mom(order):
            self._n_skips_adverse += 1
            return

        self._n_submits_passed_both += 1
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    adverse_tick_threshold: float = -1.0,
    spread_max_ticks: float = 1.0,
) -> PtgPcR5Algorithm:
    """Instantiate the ptg-pc-r5 execution algorithm."""
    config = PtgPcR5Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        adverse_tick_threshold=adverse_tick_threshold,
        spread_max_ticks=spread_max_ticks,
    )
    return PtgPcR5Algorithm(config=config)
