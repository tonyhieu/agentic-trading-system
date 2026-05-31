"""sig-isl-g1l2 — island-sig, generation 1, loop 2.

Sign-flipped fork of `sig-isl-g1l1`.

G1L1 hypothesized that strong same-direction microstructure (Lipton |I|
above threshold AND Kolm OFI above threshold in the trade direction) would
predict an adverse arrival price and so trades fired into that state should
be skipped. The 12-date train run falsified this: PnL fell from +$156 to
-$550 (vs `simple` baseline), because over the oracle's 30s horizon, strong
same-direction microstructure is a *continuation* signal — those are the
winners, not the losers.

G1L2 corrects the predicate direction. We skip an opening order only when
BOTH signals point AGAINST the trade direction — the *opposite-tape* regime
where the trader is fighting fresh, observable directional flow on the way in:

  - SKIP BUY iff `I  < -imbalance_threshold` AND `recent_ofi < -ofi_threshold`.
    (Book heavily ask-heavy AND that ask-heaviness is actively being
    reinforced — fresh seller pressure pushing mid down just before our
    market BUY would print. Lipton's recommendation mirrored: do not cross
    when imbalance is against you.)
  - SKIP SELL iff `I  >  imbalance_threshold` AND `recent_ofi >  ofi_threshold`.
  - Otherwise submit.
  - Reduce-only (close) orders always submit (intraday_flat).
  - Anti-cascade: after any skip, `_position_flat = True`; the next opening
    order submits unconditionally.

Per-quote OFI follows Kolm, Turiel, Westray (2023) eqs. (2)-(3), (5)
specialized to level 1, identical to G1L1:
    bOF = +v_b              if  b   > b_prev
        =  v_b - v_b_prev   if  b  == b_prev
        = -v_b_prev         if  b   < b_prev
    aOF = -v_a_prev         if  a   > a_prev
        =  v_a - v_a_prev   if  a  == a_prev
        = +v_a              if  a   < a_prev
    OFI_increment = bOF - aOF

Instrumentation: per-side `_evaluated_count_*` and `_skipped_count_*` are
maintained and logged on `on_stop` (per the G1 migration insight that gate
additions need diagnostic counters).

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


class SigIslG1L2Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the sig-isl-g1l2 opposite-tape microstructure gate.

    Parameters
    ----------
    imbalance_threshold : float
        Threshold on |I| for the static-imbalance leg of the AND gate.
        Default 0.33 — mirrored from G1L1 for a clean A/B comparison; the
        symmetric distribution of `I` around zero means the same threshold
        magnitude selects an analogous slice on the opposite tail.
    ofi_window_seconds : float
        Rolling window over which per-quote-tick OFI increments are summed
        for the flow leg of the AND gate. Default 2.0s — preserved from
        G1L1; Kolm's reported effective horizon (~two avg price changes,
        ≈1-3s on liquid futures) is sign-symmetric.
    ofi_threshold : float
        Threshold on |recent_ofi| (in contracts) for the flow leg of the
        AND gate. Default 5.0 — preserved from G1L1.
    """

    imbalance_threshold: float = 0.33
    ofi_window_seconds: float = 2.0
    ofi_threshold: float = 5.0


class SigIslG1L2Algorithm(ExecAlgorithm):
    """Opposite-tape microstructure gate (Lipton imbalance + Kolm OFI).

    Sign-flipped fork of `SigIslG1L1Algorithm`. See module docstring and
    NOTES.md for the full hypothesis.

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
      4. Apply the OPPOSITE-TAPE AND gate (see module docstring).
      5. Skip or submit accordingly; toggle `_position_flat`.

    Instrumentation:
      - `_evaluated_count_buy`, `_evaluated_count_sell` — opening orders
        that reached the gate (excludes reduce-only and anti-cascade
        re-entries).
      - `_skipped_count_buy`, `_skipped_count_sell` — orders the gate
        chose to skip.
      - All four counters are logged on `on_stop`.
    """

    def __init__(self, config: SigIslG1L2Config) -> None:
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

        # Instrumentation counters (per G1 migration insight).
        self._evaluated_count_buy: int = 0
        self._evaluated_count_sell: int = 0
        self._skipped_count_buy: int = 0
        self._skipped_count_sell: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            "SigIslG1L2Algorithm started "
            f"(imbalance_threshold={self._imbalance_threshold:.3f}, "
            f"ofi_window={self._ofi_window_ns / 1e9:.2f}s, "
            f"ofi_threshold={self._ofi_threshold:.2f}). "
            "Predicate: OPPOSITE-tape (skip when local flow fights trade)."
        )

    def on_stop(self) -> None:
        ev_b = self._evaluated_count_buy
        ev_s = self._evaluated_count_sell
        sk_b = self._skipped_count_buy
        sk_s = self._skipped_count_sell
        rate_b = (sk_b / ev_b) if ev_b > 0 else 0.0
        rate_s = (sk_s / ev_s) if ev_s > 0 else 0.0
        self.log.info(
            "SigIslG1L2 gate stats: "
            f"BUY  evaluated={ev_b} skipped={sk_b} rate={rate_b:.4f} | "
            f"SELL evaluated={ev_s} skipped={sk_s} rate={rate_s:.4f}"
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
        self._evaluated_count_buy = 0
        self._evaluated_count_sell = 0
        self._skipped_count_buy = 0
        self._skipped_count_sell = 0

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
        append it to the rolling deque. Identical to G1L1.
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
    # Gate decision (OPPOSITE-tape; sign-flipped vs G1L1)
    # ------------------------------------------------------------------

    def _should_skip(self, order, quote) -> bool:
        """Opposite-tape AND-gate. Returns True to skip, False to submit.

        For each side, the gate fires only when BOTH the static imbalance
        AND the recent OFI point AGAINST the trade direction — the trader
        is fighting fresh, observable directional flow on the way in.
        """
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
            # Book heavily ask-heavy AND ask-heaviness is being reinforced:
            # fresh seller pressure fighting our BUY.
            adverse_imbalance = imbalance < -self._imbalance_threshold
            adverse_ofi = recent_ofi < -self._ofi_threshold
            if adverse_imbalance and adverse_ofi:
                self.log.debug(
                    f"SKIP BUY {order.client_order_id}: "
                    f"I={imbalance:.3f} < -thr={-self._imbalance_threshold:.3f} "
                    f"AND ofi_{self._ofi_window_ns / 1e9:.1f}s={recent_ofi:.2f} "
                    f"< -thr={-self._ofi_threshold:.2f} (opposite tape)."
                )
                return True
            return False
        else:  # SELL
            adverse_imbalance = imbalance > self._imbalance_threshold
            adverse_ofi = recent_ofi > self._ofi_threshold
            if adverse_imbalance and adverse_ofi:
                self.log.debug(
                    f"SKIP SELL {order.client_order_id}: "
                    f"I={imbalance:.3f} > thr={self._imbalance_threshold:.3f} "
                    f"AND ofi_{self._ofi_window_ns / 1e9:.1f}s={recent_ofi:.2f} "
                    f"> thr={self._ofi_threshold:.2f} (opposite tape)."
                )
                return True
            return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route an order: submit or skip based on the opposite-tape AND gate."""
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

        # Instrument: this order reached the gate.
        if order.side == OrderSide.BUY:
            self._evaluated_count_buy += 1
        else:
            self._evaluated_count_sell += 1

        if self._should_skip(order, quote):
            if order.side == OrderSide.BUY:
                self._skipped_count_buy += 1
            else:
                self._skipped_count_sell += 1
            self.log.info(
                f"SKIP {order.client_order_id} — opposite-tape microstructure "
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
) -> SigIslG1L2Algorithm:
    """Instantiate and return the sig-isl-g1l2 algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    imbalance_threshold : float
        Threshold on |I| for the static-imbalance (Lipton) leg of the
        opposite-tape AND gate. Default 0.33 (mirrored from G1L1).
    ofi_window_seconds : float
        Rolling window for the per-tick OFI sum (Kolm leg). Default 2.0s.
    ofi_threshold : float
        Threshold on |recent_ofi| (in contracts) for the OFI leg of the
        opposite-tape AND gate. Default 5.0.
    """
    config = SigIslG1L2Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        imbalance_threshold=imbalance_threshold,
        ofi_window_seconds=ofi_window_seconds,
        ofi_threshold=ofi_threshold,
    )
    return SigIslG1L2Algorithm(config=config)
