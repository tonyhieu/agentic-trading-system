"""Position-tier + Order Flow Imbalance (OFI) gate execution algorithm.

Builds on `position-tier-imbalance-gate` (iter 1 PASS). The single
targeted change is REPLACING the static top-of-book size-ratio
imbalance gate with a rolling-window **Order Flow Imbalance** gate
per Cont/Kukanov/Stoikov (2014). All other components are inherited
verbatim:

  - Positional gate (position_cap=1): blocks the cascade open under
    the netting OMS when the current absolute net qty is at or above
    the cap.
  - Reduce-only fast-path: closing orders always submit unconditionally,
    keeping intraday_flat compliance and the ability to flatten at any
    moment.
  - Thin-book guard (min_total_size=2.0): OFI updates are skipped for
    quote events where bid_size + ask_size is below this threshold;
    the depth read is too noisy to trust.

OFI definition (per Cont/Kukanov/Stoikov 2014, "The Price Impact of
Order Book Events"):

  e_n =  +bid_size_n              if bid_px_n > bid_px_{n-1}      (bid level moved up)
         +(bid_size_n - bid_size_{n-1}) if bid_px_n == bid_px_{n-1} (same level, size delta)
         -bid_size_{n-1}          if bid_px_n < bid_px_{n-1}      (bid level moved down)
      +  -ask_size_n              if ask_px_n < ask_px_{n-1}      (ask level moved down)
         -(ask_size_n - ask_size_{n-1}) if ask_px_n == ask_px_{n-1} (same level, size delta)
         +ask_size_{n-1}          if ask_px_n > ask_px_{n-1}      (ask level moved up)

Positive OFI = net buying pressure (bids accumulating / asks draining).
Negative OFI = net selling pressure (asks accumulating / bids draining).

Gate semantics on the OPEN leg:

  BUY  orders SKIP when sum(OFI over window) <= -flow_threshold
                                    (sell pressure adverse to buying)
  SELL orders SKIP when sum(OFI over window) >=  flow_threshold
                                    (buy pressure adverse to selling)

No look-ahead: OFI events are kept in a deque keyed by ts_event_ns and
only events with ts_event_ns <= order.ts_init at decision time
contribute to the sum. The deque is pruned by the window-look-back at
each order event.

Quantity invariant: every parent order is either submitted intact or
skipped entirely. No quantity is ever modified.
"""
from __future__ import annotations

from collections import deque
from typing import Deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PositionTierOfiGateConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the position-tier + OFI gate algorithm.

    Parameters
    ----------
    position_cap : int
        Maximum absolute net position (contracts) at which new open-leg
        orders are still allowed. When |net_qty| >= position_cap the
        open leg is skipped. Default 1.
    window_seconds : float
        Rolling look-back window for accumulated OFI, in seconds.
        Default 10.0 — short enough to be a near-term flow read but long
        enough to integrate several order-book events at typical FX-futures
        quote rates.
    flow_threshold : float
        Minimum absolute net OFI (in contract-equivalent units) over the
        window required to fire the gate.
          BUY  orders: SKIP when OFI <= -flow_threshold
          SELL orders: SKIP when OFI >=  flow_threshold
        Default 2.0. Matches the related aggressor-flow-gate threshold
        so the family of flow gates is comparable.
    min_total_size : float
        Minimum bid_size + ask_size for a quote event to contribute to
        the OFI update. Below this the top-of-book is too thin to read
        a meaningful depth change. Default 2.0 contracts.
    """

    position_cap: int = 1
    window_seconds: float = 10.0
    flow_threshold: float = 2.0
    min_total_size: float = 2.0


class PositionTierOfiGateAlgorithm(ExecAlgorithm):
    """Execution algorithm: position-tier gate + rolling Order Flow Imbalance gate.

    Opening orders (is_reduce_only == False):
      - If |current net qty| >= position_cap: SKIP.
      - Else, sum OFI events with ts_event_ns >= (order.ts_init - window_ns):
          BUY:  SKIP when sum <= -flow_threshold
          SELL: SKIP when sum >=  flow_threshold
        If OFI has not been seeded (first quote not yet observed, or
        every quote so far was thin-book-guarded) treat as neutral
        (do not skip).
      - Otherwise: SUBMIT.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    Quote ticks (on_quote_tick):
      - Maintain a per-instrument deque of (ts_event_ns, e_n) where e_n
        is the per-event OFI contribution. Update only when the new tick
        passes the thin-book guard. Prune entries older than the window.
    """

    def __init__(self, config: PositionTierOfiGateConfig) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._flow_threshold: float = config.flow_threshold
        self._min_total_size: float = config.min_total_size

        # Quote-subscription tracking (need quote ticks for OFI signal).
        self._subscribed: set[str] = set()

        # Per-instrument OFI event deque: (ts_event_ns, e_n).
        self._ofi_events: dict[str, Deque[tuple[int, float]]] = {}

        # Per-instrument last observed top-of-book (bid_px, bid_size, ask_px, ask_size).
        # These are the previous-tick fields used to compute the next e_n.
        self._last_quote: dict[str, tuple[float, float, float, float]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"PositionTierOfiGateAlgorithm started "
            f"(position_cap={self._position_cap}, "
            f"window_ns={self._window_ns}, "
            f"flow_threshold={self._flow_threshold:.2f}, "
            f"min_total_size={self._min_total_size:.1f})."
        )

    def on_reset(self) -> None:
        self._subscribed.clear()
        self._ofi_events.clear()
        self._last_quote.clear()

    # ------------------------------------------------------------------
    # Subscription helper
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Position helper
    # ------------------------------------------------------------------

    def _current_net_qty(self, instrument_id) -> float:
        """Return absolute net position quantity for the instrument.

        Uses self.cache.positions_open() — returns 0.0 when flat.
        """
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        total = sum(float(str(p.quantity)) for p in open_positions)
        return total

    # ------------------------------------------------------------------
    # OFI computation + maintenance
    # ------------------------------------------------------------------

    def _compute_e_n(
        self,
        prev: tuple[float, float, float, float],
        curr: tuple[float, float, float, float],
    ) -> float:
        """Compute the per-event OFI contribution e_n given (prev, curr).

        Each tuple is (bid_px, bid_size, ask_px, ask_size).
        Returns e_n as defined in Cont/Kukanov/Stoikov (2014).
        """
        bid_px_p, bid_sz_p, ask_px_p, ask_sz_p = prev
        bid_px_c, bid_sz_c, ask_px_c, ask_sz_c = curr

        # Bid side contribution.
        if bid_px_c > bid_px_p:
            bid_term = +bid_sz_c
        elif bid_px_c < bid_px_p:
            bid_term = -bid_sz_p
        else:
            bid_term = bid_sz_c - bid_sz_p

        # Ask side contribution (sign convention: ask additions are negative OFI).
        if ask_px_c < ask_px_p:
            ask_term = -ask_sz_c
        elif ask_px_c > ask_px_p:
            ask_term = +ask_sz_p
        else:
            ask_term = -(ask_sz_c - ask_sz_p)

        return bid_term + ask_term

    def _prune_window(self, key: str, now_ns: int) -> None:
        """Drop OFI events older than now_ns - window_ns."""
        cutoff = now_ns - self._window_ns
        dq = self._ofi_events.get(key)
        if dq is None:
            return
        while dq and dq[0][0] < cutoff:
            dq.popleft()

    def _ofi_window_sum(self, instrument_id, now_ns: int) -> float | None:
        """Return summed OFI over the rolling window for the instrument.

        Returns None when no OFI events have been recorded yet (warm-up
        or perpetually thin book) — caller treats this as neutral.
        """
        key = str(instrument_id)
        dq = self._ofi_events.get(key)
        if dq is None or len(dq) == 0:
            return None
        self._prune_window(key, now_ns)
        if len(dq) == 0:
            return None
        return sum(e for _ts, e in dq)

    def _ofi_is_adverse(self, order, now_ns: int) -> bool:
        """Return True if rolling-window OFI is adverse to the order direction.

        Returns False (do not skip) when:
          - OFI has not been seeded yet (warm-up).
          - |OFI window sum| < flow_threshold (neutral / ambiguous).
        """
        total = self._ofi_window_sum(order.instrument_id, now_ns)
        if total is None:
            return False

        if order.side == OrderSide.BUY:
            if total <= -self._flow_threshold:
                self.log.debug(
                    f"BUY adverse OFI: window_sum={total:.2f} <= "
                    f"-threshold={-self._flow_threshold:.2f}; SKIP."
                )
                return True
        else:  # SELL
            if total >= self._flow_threshold:
                self.log.debug(
                    f"SELL adverse OFI: window_sum={total:.2f} >= "
                    f"threshold={self._flow_threshold:.2f}; SKIP."
                )
                return True
        return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip via position-tier + OFI gates."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # --- Positional gate ------------------------------------------
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty >= self._position_cap:
            self.log.debug(
                f"SKIP {order.client_order_id} — position cap reached "
                f"(net_qty={net_qty:.1f} >= cap={self._position_cap})."
            )
            return

        # --- OFI gate -------------------------------------------------
        now_ns = int(order.ts_init)
        if self._ofi_is_adverse(order, now_ns):
            side = "BUY" if order.side == OrderSide.BUY else "SELL"
            self.log.info(
                f"SKIP {order.client_order_id} — adverse OFI flow "
                f"(side={side})."
            )
            return

        # Both gates pass — submit.
        self.log.debug(
            f"SUBMIT {order.client_order_id} — both gates passed "
            f"(net_qty={net_qty:.1f})."
        )
        self.submit_order(order)

    # ------------------------------------------------------------------
    # Quote tick handler
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        """Update per-instrument OFI deque from each new quote tick.

        Thin-book guard: skip the update when bid_size + ask_size <
        min_total_size. The prev-quote state is also NOT advanced in
        that case so we keep a stable reference until a normal-sized
        quote arrives — otherwise a single thin tick would corrupt the
        next OFI event by anchoring to a degenerate depth.
        """
        try:
            bid_px = float(str(tick.bid_price))
            bid_sz = float(str(tick.bid_size))
            ask_px = float(str(tick.ask_price))
            ask_sz = float(str(tick.ask_size))
            ts_event_ns = int(tick.ts_event)
        except Exception:
            return

        if bid_sz + ask_sz < self._min_total_size or (bid_sz + ask_sz) <= 0.0:
            return  # thin-book guard

        key = str(tick.instrument_id)
        prev = self._last_quote.get(key)
        if prev is None:
            # Warm-up: seed the previous-quote state but emit no event yet.
            self._last_quote[key] = (bid_px, bid_sz, ask_px, ask_sz)
            return

        e_n = self._compute_e_n(prev, (bid_px, bid_sz, ask_px, ask_sz))
        self._last_quote[key] = (bid_px, bid_sz, ask_px, ask_sz)

        dq = self._ofi_events.get(key)
        if dq is None:
            dq = deque()
            self._ofi_events[key] = dq
        dq.append((ts_event_ns, e_n))
        # Prune at update time as well to keep the deque bounded.
        self._prune_window(key, ts_event_ns)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    window_seconds: float = 10.0,
    flow_threshold: float = 2.0,
    min_total_size: float = 2.0,
) -> PositionTierOfiGateAlgorithm:
    """Instantiate and return the PositionTierOfiGateAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    position_cap : int
        Maximum absolute net position (contracts) before skipping new opens.
        Default 1.
    window_seconds : float
        Rolling look-back window for OFI accumulation, in seconds. Default 10.0.
    flow_threshold : float
        Minimum |OFI sum| over the window required to fire the gate. Default 2.0.
    min_total_size : float
        Minimum bid_size + ask_size required for a quote to contribute to
        OFI updates. Default 2.0.
    """
    config = PositionTierOfiGateConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        window_seconds=window_seconds,
        flow_threshold=flow_threshold,
        min_total_size=min_total_size,
    )
    return PositionTierOfiGateAlgorithm(config=config)
