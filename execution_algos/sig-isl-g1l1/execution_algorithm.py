"""sig-isl-g1l1 — island-sig, generation 1, loop 1.

Two-signal microstructure gate: skip an opening order when BOTH
  (a) Lipton's static top-of-book imbalance `I = (q_b - q_a)/(q_b + q_a)`,
      and
  (b) Kolm's rolling per-quote-tick Order Flow Imbalance (OFI), summed over
      a short window,
point against the trade direction.

Concretely:
  - SKIP a BUY iff `I > imbalance_threshold` AND `recent_ofi > ofi_threshold`.
    (Book is heavily bid-heavy AND that bid-heaviness is actively being
    reinforced — fresh buyer pressure pushing mid up just before our market
    BUY would print.)
  - SKIP a SELL iff `I < -imbalance_threshold` AND `recent_ofi < -ofi_threshold`.
  - Otherwise submit.
  - Reduce-only (close) orders always submit (intraday_flat).
  - Anti-cascade: after any skip, `_position_flat = True`; the next opening
    order submits unconditionally.

Per-quote OFI follows Kolm, Turiel, Westray (2023) eqs. (2)-(3), (5)
specialized to level 1:
    bOF = +v_b              if  b   > b_prev
        =  v_b - v_b_prev   if  b  == b_prev
        = -v_b_prev         if  b   < b_prev
    aOF = -v_a_prev         if  a   > a_prev
        =  v_a - v_a_prev   if  a  == a_prev
        = +v_a              if  a   < a_prev
    OFI_increment = bOF - aOF

Hypothesis (see NOTES.md): Lipton's `I` is a level signal (where is the book
now?), Kolm's OFI is a change signal (where is the book going?). Requiring
BOTH to agree against the trade direction concentrates the skip on the
literature's high-confidence adverse cases and avoids the individually-noisy
middle of either distribution.

No look-ahead: the OFI deque is fed strictly by `on_quote_tick` callbacks in
replay-chronological order; pruning at order arrival uses `order.ts_init` as
the cutoff anchor.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class SigIslG1L1Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the sig-isl-g1l1 two-signal microstructure gate.

    Parameters
    ----------
    imbalance_threshold : float
        Threshold on |I| for the static-imbalance leg of the AND gate.
        Default 0.33 (≈2:1 book ratio — region where Lipton's calibrated
        Vodafone curves first show clearly elevated unfavorable-move
        probability).
    ofi_window_seconds : float
        Rolling window over which per-quote-tick OFI increments are summed
        for the flow leg of the AND gate. Default 2.0s — Kolm's reported
        effective horizon is "about two average price changes" which is
        roughly 1-3s on liquid futures.
    ofi_threshold : float
        Threshold on |recent_ofi| (in contracts) for the flow leg of the AND
        gate. Default 5.0.
    """

    imbalance_threshold: float = 0.33
    ofi_window_seconds: float = 2.0
    ofi_threshold: float = 5.0


class SigIslG1L1Algorithm(ExecAlgorithm):
    """Two-signal microstructure (Lipton imbalance + Kolm OFI) gate.

    See module docstring and NOTES.md for the full hypothesis. Implementation
    summary:

    State maintained by `on_quote_tick`:
      - `_prev_bid_price`, `_prev_bid_size`,
        `_prev_ask_price`, `_prev_ask_size` — the previous top-of-book quote,
        used to compute the OFI increment on the next tick.
      - `_ofi_deque` of `(ts_event_ns, ofi_increment)` plus running sum
        `_net_ofi` — pruned to `ofi_window_seconds` on demand.

    Decision in `on_order` (opening, non-reduce-only):
      1. Pull latest `quote_tick` from cache.
      2. Compute `I` from current bid_size / ask_size.
      3. Prune the OFI deque to the window ending at `order.ts_init`.
      4. Apply the AND gate (see module docstring).
      5. Skip or submit accordingly; toggle `_position_flat`.
    """

    def __init__(self, config: SigIslG1L1Config) -> None:
        super().__init__(config=config)
        if not (0.0 < config.imbalance_threshold < 1.0):
            raise ValueError(
                "imbalance_threshold must lie in (0, 1) "
                f"(got {config.imbalance_threshold})."
            )
        if config.ofi_window_seconds <= 0.0:
            raise ValueError(
                "ofi_window_seconds must be > 0 "
                f"(got {config.ofi_window_seconds})."
            )
        if config.ofi_threshold <= 0.0:
            raise ValueError(
                "ofi_threshold must be > 0 "
                f"(got {config.ofi_threshold})."
            )

        self._imbalance_threshold: float = config.imbalance_threshold
        self._ofi_window_ns: int = int(config.ofi_window_seconds * 1_000_000_000)
        self._ofi_threshold: float = config.ofi_threshold

        # OFI deque + running sum (per Kolm eqs. 2, 3, 5, level 1 only).
        self._ofi_deque: deque[tuple[int, float]] = deque()
        self._net_ofi: float = 0.0

        # Previous quote state for computing OFI increments.
        self._prev_bid_price: float | None = None
        self._prev_bid_size: float | None = None
        self._prev_ask_price: float | None = None
        self._prev_ask_size: float | None = None

        # Anti-cascade: forced re-entry after any skip.
        self._position_flat: bool = True

        # Subscription tracking.
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            "SigIslG1L1Algorithm started "
            f"(imbalance_threshold={self._imbalance_threshold:.3f}, "
            f"ofi_window={self._ofi_window_ns / 1e9:.2f}s, "
            f"ofi_threshold={self._ofi_threshold:.2f})."
        )

    def on_reset(self) -> None:
        self._ofi_deque.clear()
        self._net_ofi = 0.0
        self._prev_bid_price = None
        self._prev_bid_size = None
        self._prev_ask_price = None
        self._prev_ask_size = None
        self._position_flat = True
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
    # Quote tick handler — compute and accumulate per-tick OFI
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        """Compute the level-1 OFI increment from the previous quote and
        append it to the rolling deque.
        """
        try:
            bid_price = float(str(tick.bid_price))
            ask_price = float(str(tick.ask_price))
            bid_size = float(str(tick.bid_size))
            ask_size = float(str(tick.ask_size))
        except Exception:
            # Malformed tick — skip without polluting state.
            return

        if (
            self._prev_bid_price is None
            or self._prev_bid_size is None
            or self._prev_ask_price is None
            or self._prev_ask_size is None
        ):
            # First tick: prime state, no OFI increment yet.
            self._prev_bid_price = bid_price
            self._prev_bid_size = bid_size
            self._prev_ask_price = ask_price
            self._prev_ask_size = ask_size
            return

        # bOF (Kolm eq. 2, level 1):
        if bid_price > self._prev_bid_price:
            bof = bid_size
        elif bid_price == self._prev_bid_price:
            bof = bid_size - self._prev_bid_size
        else:  # bid_price < prev
            bof = -self._prev_bid_size

        # aOF (Kolm eq. 3, level 1):
        if ask_price > self._prev_ask_price:
            aof = -self._prev_ask_size
        elif ask_price == self._prev_ask_price:
            aof = ask_size - self._prev_ask_size
        else:  # ask_price < prev
            aof = ask_size

        ofi_increment = bof - aof
        self._ofi_deque.append((tick.ts_event, ofi_increment))
        self._net_ofi += ofi_increment

        # Update previous-quote state.
        self._prev_bid_price = bid_price
        self._prev_bid_size = bid_size
        self._prev_ask_price = ask_price
        self._prev_ask_size = ask_size

    # ------------------------------------------------------------------
    # OFI window helpers
    # ------------------------------------------------------------------

    def _prune_ofi(self, cutoff_ns: int) -> None:
        """Remove OFI deque entries older than cutoff_ns, updating _net_ofi."""
        while self._ofi_deque and self._ofi_deque[0][0] < cutoff_ns:
            _, old_incr = self._ofi_deque.popleft()
            self._net_ofi -= old_incr

    # ------------------------------------------------------------------
    # Gate decision
    # ------------------------------------------------------------------

    def _should_skip(self, order, quote) -> bool:
        """AND-gate skip decision. Returns True to skip, False to submit."""
        # Static imbalance leg (Lipton).
        try:
            bid_size = float(str(quote.bid_size))
            ask_size = float(str(quote.ask_size))
        except Exception:
            return False
        denom = bid_size + ask_size
        if denom <= 0.0:
            return False
        imbalance = (bid_size - ask_size) / denom

        # OFI leg (Kolm) — prune to window ending at order.ts_init.
        cutoff_ns = order.ts_init - self._ofi_window_ns
        self._prune_ofi(cutoff_ns)
        recent_ofi = self._net_ofi

        if order.side == OrderSide.BUY:
            # Book heavily bid-heavy AND bid-heaviness is being reinforced.
            adverse_imbalance = imbalance > self._imbalance_threshold
            adverse_ofi = recent_ofi > self._ofi_threshold
            if adverse_imbalance and adverse_ofi:
                self.log.debug(
                    f"SKIP BUY {order.client_order_id}: "
                    f"I={imbalance:.3f} > thr={self._imbalance_threshold:.3f} "
                    f"AND ofi_{self._ofi_window_ns / 1e9:.1f}s={recent_ofi:.2f} "
                    f"> thr={self._ofi_threshold:.2f}."
                )
                return True
            return False
        else:  # SELL
            adverse_imbalance = imbalance < -self._imbalance_threshold
            adverse_ofi = recent_ofi < -self._ofi_threshold
            if adverse_imbalance and adverse_ofi:
                self.log.debug(
                    f"SKIP SELL {order.client_order_id}: "
                    f"I={imbalance:.3f} < -thr={-self._imbalance_threshold:.3f} "
                    f"AND ofi_{self._ofi_window_ns / 1e9:.1f}s={recent_ofi:.2f} "
                    f"< -thr={-self._ofi_threshold:.2f}."
                )
                return True
            return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route an order: submit or skip based on the two-signal AND gate."""
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

        quote = self.cache.quote_tick(order.instrument_id)
        if quote is None:
            # No quote cached yet — fall through (matches baseline behavior).
            self._position_flat = False
            self.submit_order(order)
            return

        if self._should_skip(order, quote):
            self.log.info(
                f"SKIP {order.client_order_id} — adverse microstructure "
                "(static imbalance AND OFI both against trade)."
            )
            self._position_flat = True
            # Do NOT call submit_order — quantity invariant preserved.
        else:
            self._position_flat = False
            self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    imbalance_threshold: float = 0.33,
    ofi_window_seconds: float = 2.0,
    ofi_threshold: float = 5.0,
) -> SigIslG1L1Algorithm:
    """Instantiate and return the sig-isl-g1l1 algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    imbalance_threshold : float
        Threshold on |I| for the static-imbalance (Lipton) leg of the AND
        gate. Default 0.33.
    ofi_window_seconds : float
        Rolling window for the per-tick OFI sum (Kolm leg). Default 2.0s.
    ofi_threshold : float
        Threshold on |recent_ofi| (in contracts) for the OFI leg of the AND
        gate. Default 5.0.
    """
    config = SigIslG1L1Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        imbalance_threshold=imbalance_threshold,
        ofi_window_seconds=ofi_window_seconds,
        ofi_threshold=ofi_threshold,
    )
    return SigIslG1L1Algorithm(config=config)
