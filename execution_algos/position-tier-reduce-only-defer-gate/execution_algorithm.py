"""Position-tier + EMA-imbalance + EXIT-side reduce-only-defer gate.

Iter-8 STRUCTURAL pivot per iter-7 NOTES.md explicit recommendation.
Builds on iter-2 best `position-tier-imbalance-ema-gate` (pnl=4503.25 on
N=11, family-best). Inherits all entry-side mechanisms verbatim:

  * position_cap=1 (cascade prevention)
  * EMA-imbalance gate on opens (alpha=0.30, threshold=0.40,
    min_total_size=2.0)
  * Quote-tick subscription to maintain the per-instrument EMA

Adds the ONE new mechanism that NO prior iteration has explored — an
EXIT-side reduce-only fast-path restructure:

  * Reduce-only orders are NOT submitted immediately. Instead they are
    held in a per-instrument FIFO defer queue WHILE the EMA book lean
    remains favourable to the position direction.
  * A deferred SELL-close (long → flat) is released when EMA imbalance
    falls back to <= close_favor_threshold (book lean turned neutral
    or adverse).
  * A deferred BUY-close (short → flat) is released when EMA imbalance
    rises to >= 1 - close_favor_threshold.
  * Hard caps to bound the defer:
      - max_defer_ticks: queue is walked on every on_quote_tick; any
        order with tick_count >= max_defer_ticks is released.
      - max_defer_seconds: any order whose ts_event delta from enqueue
        exceeds max_defer_seconds is released (intraday_flat safety).
  * If net position is already 0 at on_order time, submit immediately
    (stale reduce-only after the position closed elsewhere).

Why this axis (per iter-7 NOTES.md "iter-8 should pivot to the only
remaining unexplored mechanism in this family: the EXIT-SIDE reduce-only
fast-path"):

  Iters 2-6 cluster pnl in $4377-$4503 (a 2.9% spread on N=11) across
  five microstructure-signal variations at the OPEN decision point.
  Iter-7 added a calendar-axis (TOD) and also landed in/below this
  band (pnl=3933.50). Every variation has kept the EXIT-side
  unchanged: `submit_order(order)` immediately on the first tick a
  reduce-only arrives. If the EMA-imbalance signal has documented
  short-horizon directional power (the basis of the family's
  +10000%-region baseline gate), then by symmetry it must predict
  favorable mid-continuation for closes that align with the lean.
  Deferring a SELL-close when bids are heavy (long-favourable book)
  captures the next few ticks of upward drift before flattening.

Hypothesis:
  Pnl should rise if the EMA-imbalance signal carries any short-horizon
  predictive power beyond the open decision. Sharpe MAY fall slightly
  if the variance increase from holding positions longer outweighs the
  mean pnl gain. The release-on-adverse-lean rule should bound the
  downside per defer.

  Falsification path: if pnl falls or is unchanged, the EMA signal does
  NOT have meaningful continuation power for short horizons after the
  open decision is taken, and the entire position-tier family is
  genuinely exhausted at the iter-2 pnl band on this train window. That
  is itself a load-bearing structural takeaway.

No look-ahead:
  At on_order time and at each on_quote_tick release-check the EMA
  reflects only quotes already processed in chronological order. The
  release decision uses the EMA at the CURRENT moment (which is
  strictly past relative to the eventual fill timestamp), not the
  order's future fill price.

No quantity modification:
  Every reduce-only order is either submitted intact (after any defer
  window) or submitted intact at the safety cap. No splitting, no
  sizing. The defer queue is a holding mechanism only.
  `sum(child_fills) <= parent.quantity` always preserved.

Inherited components (verbatim from iter-2):
  - position_cap=1 (cascade-prevention positional gate)
  - EMA-imbalance gate (alpha=0.30, skip_threshold=0.40,
    min_total_size=2.0) on OPEN orders only

New components (iter-8):
  - close_favor_threshold=0.55 (EMA imbalance above this is
    long-favourable; below 1-0.55=0.45 is short-favourable)
  - max_defer_ticks=20 (per-order tick-count cap)
  - max_defer_seconds=15.0 (per-order wall-clock cap, ns granularity)
"""
from __future__ import annotations

from collections import deque
from typing import Deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PositionTierReduceOnlyDeferGateConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the iter-8 reduce-only-defer execution algorithm.

    Parameters
    ----------
    position_cap : int
        Maximum absolute net position size (contracts) at which new
        OPEN-leg orders are still allowed. Default 1.
    skip_threshold : float
        EMA-imbalance threshold for the OPEN-side gate. Imbalance is
        `bid_size / (bid_size + ask_size)` in [0, 1]; the EMA of this
        quantity is compared to the threshold.
          BUY  OPENS: SKIP when ema_imbalance <      skip_threshold
          SELL OPENS: SKIP when ema_imbalance > 1 -  skip_threshold
        Default 0.40 (matches iter-2 best).
    min_total_size : float
        Minimum bid_size + ask_size required for a quote to (a) update
        the EMA and (b) participate in any gate decision. Default 2.0.
    ema_alpha : float
        EMA smoothing factor in (0, 1]. Default 0.30 (matches iter-2).
    close_favor_threshold : float
        Threshold above which the EMA is LONG-favourable (and below
        1-x SHORT-favourable). Reduce-only orders are DEFERRED while
        the lean stays on the favourable side and RELEASED when it
        crosses back through. Default 0.55. Picked once as a small
        symmetric off-neutral band; not tuned on the train set.
    max_defer_ticks : int
        Per-order tick-count cap for the defer queue. Any held order
        whose `tick_count` reaches this is released immediately on
        the next quote-tick walk. Default 20.
    max_defer_seconds : float
        Per-order wall-clock cap for the defer queue, in seconds (the
        engine works in ns; we convert internally). Any held order
        whose ts_event delta from enqueue exceeds this is released.
        Hard intraday_flat safety. Default 15.0.
    """

    position_cap: int = 1
    skip_threshold: float = 0.40
    min_total_size: float = 2.0
    ema_alpha: float = 0.30
    close_favor_threshold: float = 0.55
    max_defer_ticks: int = 20
    max_defer_seconds: float = 15.0


class _PendingClose:
    """Holding container for a deferred reduce-only order.

    Attributes
    ----------
    order : nautilus_trader.model.orders.Order
        The reduce-only parent order to submit later.
    enqueued_ts_ns : int
        Nanoseconds-since-epoch from the first quote tick seen at or
        after enqueue. Compared to subsequent tick.ts_event values to
        enforce max_defer_seconds.
    tick_count : int
        How many quote ticks have been processed since enqueue.
    """

    __slots__ = ("order", "enqueued_ts_ns", "tick_count")

    def __init__(self, order, enqueued_ts_ns: int) -> None:
        self.order = order
        self.enqueued_ts_ns: int = enqueued_ts_ns
        self.tick_count: int = 0


class PositionTierReduceOnlyDeferGateAlgorithm(ExecAlgorithm):
    """Iter-8 execution algo: position-tier + EMA-imbalance + exit-defer.

    OPEN orders (is_reduce_only == False):
      - position-tier gate: if abs(net_qty) >= position_cap, SKIP.
      - EMA-imbalance gate (verbatim iter-2):
          BUY:  SKIP when ema <      skip_threshold
          SELL: SKIP when ema > 1 -  skip_threshold
      - Otherwise SUBMIT.

    CLOSE orders (is_reduce_only == True):
      - If net_qty == 0 already (stale close): SUBMIT immediately.
      - If EMA not yet seeded OR EMA neutral/adverse to the position:
        SUBMIT immediately.
      - Else: ENQUEUE in per-instrument defer queue. Will be released
        on a subsequent on_quote_tick when any release condition fires.
    """

    def __init__(self, config: PositionTierReduceOnlyDeferGateConfig) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        self._skip_threshold: float = config.skip_threshold
        self._min_total_size: float = config.min_total_size
        self._ema_alpha: float = config.ema_alpha
        self._close_favor_threshold: float = config.close_favor_threshold
        self._max_defer_ticks: int = config.max_defer_ticks
        self._max_defer_ns: int = int(config.max_defer_seconds * 1_000_000_000)

        self._subscribed: set[str] = set()
        # Per-instrument EMA imbalance state. Key: str(instrument_id).
        self._ema_imbalance: dict[str, float] = {}
        # Per-instrument FIFO defer queue. Key: str(instrument_id).
        self._pending_closes: dict[str, Deque[_PendingClose]] = {}
        # Most-recent tick.ts_event per instrument (ns since epoch).
        # Used to seed enqueued_ts_ns when on_order arrives between ticks.
        self._last_tick_ts_ns: dict[str, int] = {}

        # Diagnostics counters (logged on_stop is overkill; just keep for
        # potential debug — they cost a few words and are zeroed on_reset).
        self._n_deferred: int = 0
        self._n_released_adverse: int = 0
        self._n_released_tick_cap: int = 0
        self._n_released_time_cap: int = 0
        self._n_released_flat: int = 0
        self._n_submit_immediate_close: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            "PositionTierReduceOnlyDeferGateAlgorithm started "
            f"(position_cap={self._position_cap}, "
            f"skip_threshold={self._skip_threshold:.2f}, "
            f"min_total_size={self._min_total_size:.1f}, "
            f"ema_alpha={self._ema_alpha:.2f}, "
            f"close_favor_threshold={self._close_favor_threshold:.2f}, "
            f"max_defer_ticks={self._max_defer_ticks}, "
            f"max_defer_ns={self._max_defer_ns})."
        )

    def on_reset(self) -> None:
        self._subscribed.clear()
        self._ema_imbalance.clear()
        self._pending_closes.clear()
        self._last_tick_ts_ns.clear()
        self._n_deferred = 0
        self._n_released_adverse = 0
        self._n_released_tick_cap = 0
        self._n_released_time_cap = 0
        self._n_released_flat = 0
        self._n_submit_immediate_close = 0

    # ------------------------------------------------------------------
    # Subscription helper
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Position helper (NET position; sign matters for close-side direction)
    # ------------------------------------------------------------------

    def _current_net_signed_qty(self, instrument_id) -> float:
        """Return SIGNED net position quantity for the instrument.

        Positive = long, negative = short, 0 = flat. Uses the netting
        OMS cache.positions_open(); each position carries a `side`
        attribute (POSITION_LONG / POSITION_SHORT) plus a magnitude
        `quantity`. Falls back to 0.0 when flat.
        """
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        total = 0.0
        for p in open_positions:
            qty = float(str(p.quantity))
            # Position side: 1 = LONG, -1 = SHORT, 0 = FLAT in Nautilus.
            # We look up by attribute and handle both enum and int paths.
            side_obj = getattr(p, "side", None)
            sign = 1.0
            if side_obj is not None:
                side_str = str(side_obj).upper()
                if "SHORT" in side_str:
                    sign = -1.0
                elif "LONG" in side_str:
                    sign = 1.0
                elif "FLAT" in side_str:
                    sign = 0.0
            total += sign * qty
        return total

    # ------------------------------------------------------------------
    # EMA update + read
    # ------------------------------------------------------------------

    def _update_ema(self, instrument_id, bid_size: float, ask_size: float) -> None:
        """Update the per-instrument EMA imbalance from one quote tick."""
        total = bid_size + ask_size
        if total < self._min_total_size or total <= 0.0:
            return

        imbalance = bid_size / total
        key = str(instrument_id)
        prev = self._ema_imbalance.get(key)
        if prev is None:
            self._ema_imbalance[key] = imbalance
        else:
            self._ema_imbalance[key] = (
                self._ema_alpha * imbalance + (1.0 - self._ema_alpha) * prev
            )

    def _ema_open_adverse(self, order) -> bool:
        """Iter-2 verbatim: is EMA adverse to a NEW OPEN order direction?"""
        key = str(order.instrument_id)
        ema = self._ema_imbalance.get(key)
        if ema is None:
            return False

        if order.side == OrderSide.BUY:
            return ema < self._skip_threshold
        else:  # SELL
            return ema > 1.0 - self._skip_threshold

    def _ema_close_is_favourable(self, instrument_id, side: OrderSide) -> bool:
        """Is the EMA lean currently favourable to a reduce-only of `side`?

        SELL-close (closing a long): favourable when ema >  close_favor_threshold
           (bid-heavy book → continued upward drift → defer to capture more upside).
        BUY-close (closing a short): favourable when ema <  1 - close_favor_threshold
           (ask-heavy book → continued downward drift → defer to capture more downside).

        Returns False (do NOT defer; submit immediately) when:
          - EMA not yet seeded (cold start)
          - Lean is neutral or adverse to the position direction
        """
        key = str(instrument_id)
        ema = self._ema_imbalance.get(key)
        if ema is None:
            return False

        if side == OrderSide.SELL:
            # SELL-close == closing a long position
            return ema > self._close_favor_threshold
        else:  # BUY-close == closing a short
            return ema < (1.0 - self._close_favor_threshold)

    # ------------------------------------------------------------------
    # Defer queue management
    # ------------------------------------------------------------------

    def _enqueue_close(self, order, ts_ns: int) -> None:
        key = str(order.instrument_id)
        q = self._pending_closes.get(key)
        if q is None:
            q = deque()
            self._pending_closes[key] = q
        q.append(_PendingClose(order, ts_ns))
        self._n_deferred += 1
        self.log.debug(
            f"DEFER reduce-only {order.client_order_id} "
            f"(queue_len={len(q)}, ts_ns={ts_ns})."
        )

    def _walk_pending(self, instrument_id, ts_event_ns: int) -> None:
        """On each quote tick, walk pending closes for this instrument
        and submit any that meet a release condition. Releases are
        in FIFO order; iteration is shallow (per-instrument, typically
        0-2 entries at iter-2 trade scale)."""
        key = str(instrument_id)
        q = self._pending_closes.get(key)
        if not q:
            return

        # Remaining queue after this walk.
        still_pending: Deque[_PendingClose] = deque()

        for pend in q:
            pend.tick_count += 1
            order = pend.order
            release_reason: str | None = None

            # Cap checks first (cheap, deterministic).
            if pend.tick_count >= self._max_defer_ticks:
                release_reason = "tick_cap"
                self._n_released_tick_cap += 1
            elif ts_event_ns - pend.enqueued_ts_ns >= self._max_defer_ns:
                release_reason = "time_cap"
                self._n_released_time_cap += 1
            else:
                # Adverse-lean check: re-read EMA at this tick.
                # Note: this tick's EMA has already been updated by
                # the caller before _walk_pending runs.
                if not self._ema_close_is_favourable(
                    order.instrument_id, order.side
                ):
                    release_reason = "adverse_lean"
                    self._n_released_adverse += 1
                else:
                    # Stale-position check: if net is already flat,
                    # the reduce-only is a no-op; release immediately
                    # so it doesn't sit in the queue forever.
                    if self._current_net_signed_qty(order.instrument_id) == 0.0:
                        release_reason = "flat"
                        self._n_released_flat += 1

            if release_reason is not None:
                self.log.debug(
                    f"RELEASE reduce-only {order.client_order_id} "
                    f"(reason={release_reason}, ticks={pend.tick_count})."
                )
                self.submit_order(order)
            else:
                still_pending.append(pend)

        if still_pending:
            self._pending_closes[key] = still_pending
        else:
            # Cheap cleanup; not strictly necessary.
            del self._pending_closes[key]

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: SUBMIT, SKIP (opens), or ENQUEUE (closes)."""
        self._ensure_subscribed(order.instrument_id)

        # --- Closing leg ---------------------------------------------
        if order.is_reduce_only:
            instrument_id = order.instrument_id
            net = self._current_net_signed_qty(instrument_id)

            # Stale (already flat) -> submit immediately (no-op safe).
            if net == 0.0:
                self._n_submit_immediate_close += 1
                self.log.debug(
                    f"SUBMIT reduce-only {order.client_order_id} "
                    f"immediately (already flat)."
                )
                self.submit_order(order)
                return

            # Direction-consistency check: a SELL-close should be paired
            # with a long net; a BUY-close with a short net. If the
            # strategy issues a mismatched reduce-only (rare/buggy) we
            # just submit immediately and let the OMS handle it.
            side = order.side
            consistent = (
                (side == OrderSide.SELL and net > 0.0)
                or (side == OrderSide.BUY and net < 0.0)
            )
            if not consistent:
                self._n_submit_immediate_close += 1
                self.log.debug(
                    f"SUBMIT reduce-only {order.client_order_id} "
                    f"immediately (direction inconsistent with net={net:.1f})."
                )
                self.submit_order(order)
                return

            # If EMA lean is not favourable, submit immediately.
            if not self._ema_close_is_favourable(instrument_id, side):
                self._n_submit_immediate_close += 1
                self.log.debug(
                    f"SUBMIT reduce-only {order.client_order_id} "
                    f"immediately (EMA not favourable)."
                )
                self.submit_order(order)
                return

            # All checks passed — defer.
            ts_ns = self._last_tick_ts_ns.get(str(instrument_id))
            if ts_ns is None:
                # No tick seen yet for this instrument — fall back to
                # submitting immediately rather than racing the engine
                # clock. (Should be rare; the EMA-seeded path implies a
                # tick has been seen, so this is a defence-in-depth.)
                self._n_submit_immediate_close += 1
                self.log.debug(
                    f"SUBMIT reduce-only {order.client_order_id} "
                    f"immediately (no tick ts available)."
                )
                self.submit_order(order)
                return
            self._enqueue_close(order, ts_ns)
            return

        # --- Opening leg (iter-2 verbatim) ---------------------------
        net_abs = abs(self._current_net_signed_qty(order.instrument_id))
        if net_abs >= self._position_cap:
            self.log.debug(
                f"SKIP {order.client_order_id} — position cap reached "
                f"(net={net_abs:.1f} >= cap={self._position_cap})."
            )
            return

        if self._ema_open_adverse(order):
            self.log.debug(
                f"SKIP {order.client_order_id} — adverse EMA open imbalance."
            )
            return

        self.log.debug(f"SUBMIT OPEN {order.client_order_id} — both gates passed.")
        self.submit_order(order)

    # ------------------------------------------------------------------
    # Quote tick handler
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        """Update the EMA, then walk the per-instrument defer queue."""
        try:
            bid_size = float(str(tick.bid_size))
            ask_size = float(str(tick.ask_size))
            ts_event_ns = int(tick.ts_event)
        except Exception:
            return

        instrument_id = tick.instrument_id
        self._last_tick_ts_ns[str(instrument_id)] = ts_event_ns
        self._update_ema(instrument_id, bid_size, ask_size)
        self._walk_pending(instrument_id, ts_event_ns)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    skip_threshold: float = 0.40,
    min_total_size: float = 2.0,
    ema_alpha: float = 0.30,
    close_favor_threshold: float = 0.55,
    max_defer_ticks: int = 20,
    max_defer_seconds: float = 15.0,
) -> PositionTierReduceOnlyDeferGateAlgorithm:
    """Instantiate the iter-8 PositionTierReduceOnlyDeferGateAlgorithm.

    See PositionTierReduceOnlyDeferGateConfig for parameter docs.
    """
    config = PositionTierReduceOnlyDeferGateConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        skip_threshold=skip_threshold,
        min_total_size=min_total_size,
        ema_alpha=ema_alpha,
        close_favor_threshold=close_favor_threshold,
        max_defer_ticks=max_defer_ticks,
        max_defer_seconds=max_defer_seconds,
    )
    return PositionTierReduceOnlyDeferGateAlgorithm(config=config)
