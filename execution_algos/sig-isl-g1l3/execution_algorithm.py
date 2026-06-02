"""sig-isl-g1l3 — island-sig, generation 1, loop 3.

Adds a rolling-spread-p75 OPEN-side SKIP axis ON TOP of `sig-isl-g1l2`'s
opposite-tape (Lipton imbalance + Kolm OFI) AND-gate, with OR-skip
composition semantics. The opposite-tape gate is preserved bit-for-bit
from G1L2 — predicate direction, thresholds, window, AND-composition,
OFI computation, anti-cascade contract — so the only attributable
behavioral change is the *addition* of the spread axis.

Why this design (mechanism)
---------------------------
The cross-island migrations (`migrations/generation-1.json` through
`generation-4.json`) establish that composing strictly orthogonal SKIP
axes ON TOP of an unmodified base is the most reliable PnL mechanism
across the experiment. Single-axis spread-p75 lifted base PnL on every
island it was tried on (island-0 g1l1 +26.55%, stacked on island-1 g2l1
+70.29%, stacked on island-2 g2l1 +223.42%). The mechanism is that the
oracle's 30s forward signal degrades disproportionately during wide-spread
liquidity-vacuum windows, AND that this regime is structurally
near-independent of the other documented adverse-microstructure axes —
so adding the spread axis to an existing gate compounds rather than
overlaps. Drawdown TIGHTENED on every island where stacking worked,
evidence the filtered slice carries tail-loss trades.

G1L2's opposite-tape gate is a SIGNED-FLOW axis (book direction +
per-quote OFI direction); rolling spread is a BOOK-DISTANCE axis (the
absolute quote-distance, side-agnostic). These axes are structurally
orthogonal: a quote can have a high spread regardless of which side has
the heavier resting size, and the OFI can be strongly adverse regardless
of whether the spread is wide or tight.

OR-skip composition (not AND-skip)
----------------------------------
The canonical winning recipe on `afg-isl-g2l1` uses OR-skip — each gate
independently vetoes an entry. AND-skip would *loosen* the existing G1L2
gate, a behavior pattern the migrations established as a consistent
regression. OR-skip preserves G1L2's existing skip set as a strict subset
of the new skip set, and adds the spread-extreme slice as a new
orthogonal contribution.

Algorithm
---------
Maintain two independent rolling structures:
  - OFI deque (from on_quote_tick): unchanged from G1L2.
  - Spread deque (from on_quote_tick): (ts_event_ns, spread = ask - bid).

For each OPEN order:
  1. Reduce-only orders always submit (intraday_flat compliance).
  2. Forced re-entry after a skip is unconditional (anti-cascade contract
     preserved from G1L2).
  3. Spread gate (NEW, cross-island import — book-distance axis):
       Prune spread deque to entries within `spread_window_seconds`.
       If at least `min_samples` samples are present, compute the
       `spread_quantile`-th quantile of the rolling spreads. If the
       latest spread strictly exceeds that quantile → SKIP.
  4. Opposite-tape gate (unchanged from G1L2 — signed-flow axis):
       SKIP BUY iff `I < -imbalance_threshold` AND `recent_ofi < -ofi_threshold`.
       SKIP SELL iff `I > imbalance_threshold` AND `recent_ofi > ofi_threshold`.
  5. Submit only if BOTH gates pass. After ANY skip,
     `_position_flat = True` (next open unconditional).

Order quantity is never modified — quantity invariant preserved.

No look-ahead: both deques are fed by `on_quote_tick` callbacks in replay
chronological order; pruning uses `order.ts_init` as the cutoff anchor.

Instrumentation
---------------
Preserves G1L2's `_evaluated_count_*` and `_skipped_count_*` totals.
Adds per-axis attribution counters `_skipped_by_spread_*` and
`_skipped_by_opposite_tape_*`. With OR-skip the spread gate is evaluated
first; if it fires, the opposite-tape gate is not consulted (so the two
per-axis counters sum to the totals exactly only in the absence of
co-firing, and a co-firing order is attributed to spread — documented
in on_stop logs).
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class SigIslG1L3Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the sig-isl-g1l3 spread+opposite-tape stack.

    Opposite-tape leg (unchanged from G1L2):
      imbalance_threshold : float
          Threshold on |I| for the static-imbalance leg of the AND gate.
          Default 0.33 — preserved from G1L2.
      ofi_window_seconds : float
          Rolling window over which per-quote-tick OFI increments are
          summed for the flow leg of the AND gate. Default 2.0s —
          preserved from G1L2.
      ofi_threshold : float
          Threshold on |recent_ofi| (in contracts) for the flow leg of
          the AND gate. Default 5.0 — preserved from G1L2.

    Spread leg (NEW, cross-island import from island-0 g1l1):
      spread_window_seconds : float
          Rolling window for spread samples, in seconds. Default 60.0 —
          ported verbatim from island-0 g1l1 (cross-island winner, used
          on island-1 g2l1 and island-2 g2l1 without retuning).
      spread_quantile : float
          Quantile threshold for the spread gate (0 < q < 1). Skip OPEN
          when the latest spread strictly exceeds this quantile of the
          rolling window. Default 0.75 — ported verbatim from
          island-0 g1l1; gen-3 ptg-isl-g3l2 confirmed q=0.75 sits on
          the EV peak across multiple bases.
      min_samples : int
          Minimum spread samples required before the spread gate fires.
          Below this, the spread gate is a no-op (warm-up). Default
          50 — ported verbatim from island-0 g1l1.
    """

    imbalance_threshold: float = 0.33
    ofi_window_seconds: float = 2.0
    ofi_threshold: float = 5.0
    spread_window_seconds: float = 60.0
    spread_quantile: float = 0.75
    min_samples: int = 50


class SigIslG1L3Algorithm(ExecAlgorithm):
    """Opposite-tape (Lipton + Kolm) gate stacked with rolling-spread-p75.

    OR-skip composition: OPEN order is skipped if EITHER gate fires.
    Preserves G1L2's opposite-tape gate bit-for-bit; spread gate is the
    only new behavior.

    Decision in `on_order` (opening, non-reduce-only):
      1. Anti-cascade re-entry submits unconditionally.
      2. Pull latest `quote_tick` from cache.
      3. Spread gate: prune, threshold check on latest_spread.
      4. Opposite-tape gate: compute I + recent_ofi, apply AND predicate.
      5. Skip if either fires; submit otherwise; toggle `_position_flat`.

    Instrumentation:
      - `_evaluated_count_{buy,sell}` — opening orders that reached the
        gate region (excludes reduce-only and anti-cascade re-entries).
      - `_skipped_count_{buy,sell}` — total orders skipped by EITHER gate.
      - `_skipped_by_spread_{buy,sell}` — skipped because spread gate
        fired (spread is checked first; co-firing orders attribute here).
      - `_skipped_by_opposite_tape_{buy,sell}` — skipped because the
        opposite-tape gate fired and spread did not.
      - All counters logged on `on_stop`.
    """

    def __init__(self, config: SigIslG1L3Config) -> None:
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
        if config.spread_window_seconds <= 0.0:
            raise ValueError(
                "spread_window_seconds must be > 0 "
                f"(got {config.spread_window_seconds})."
            )
        if not (0.0 < config.spread_quantile < 1.0):
            raise ValueError(
                "spread_quantile must lie in (0, 1) "
                f"(got {config.spread_quantile})."
            )
        if config.min_samples <= 0:
            raise ValueError(
                "min_samples must be > 0 "
                f"(got {config.min_samples})."
            )

        # Opposite-tape gate parameters (unchanged from G1L2).
        self._imbalance_threshold: float = config.imbalance_threshold
        self._ofi_window_ns: int = int(config.ofi_window_seconds * 1_000_000_000)
        self._ofi_threshold: float = config.ofi_threshold

        # Spread gate parameters (NEW, cross-island import).
        self._spread_window_ns: int = int(
            config.spread_window_seconds * 1_000_000_000
        )
        self._spread_quantile: float = config.spread_quantile
        self._min_samples: int = config.min_samples

        # OFI deque + running sum (per Kolm eqs. 2, 3, 5, level 1 only).
        self._ofi_deque: deque[tuple[int, float]] = deque()
        self._net_ofi: float = 0.0

        # Previous quote state for computing OFI increments.
        self._prev_bid_price: float | None = None
        self._prev_bid_size: float | None = None
        self._prev_ask_price: float | None = None
        self._prev_ask_size: float | None = None

        # Spread deque + latest observed spread.
        self._spread_deque: deque[tuple[int, float]] = deque()
        self._latest_spread: float | None = None

        # Anti-cascade: forced re-entry after any skip.
        self._position_flat: bool = True

        # Subscription tracking.
        self._subscribed: set[str] = set()

        # Instrumentation counters (per G1 migration insight).
        self._evaluated_count_buy: int = 0
        self._evaluated_count_sell: int = 0
        self._skipped_count_buy: int = 0
        self._skipped_count_sell: int = 0
        # Per-axis attribution (spread evaluated first; co-firing -> spread).
        self._skipped_by_spread_buy: int = 0
        self._skipped_by_spread_sell: int = 0
        self._skipped_by_opposite_tape_buy: int = 0
        self._skipped_by_opposite_tape_sell: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            "SigIslG1L3Algorithm started "
            f"(imbalance_threshold={self._imbalance_threshold:.3f}, "
            f"ofi_window={self._ofi_window_ns / 1e9:.2f}s, "
            f"ofi_threshold={self._ofi_threshold:.2f}, "
            f"spread_window={self._spread_window_ns / 1e9:.1f}s, "
            f"spread_quantile={self._spread_quantile:.2f}, "
            f"min_samples={self._min_samples}). "
            "Composition: OR-skip across opposite-tape (G1L2) and "
            "rolling-spread-p75 (cross-island import)."
        )

    def on_stop(self) -> None:
        ev_b = self._evaluated_count_buy
        ev_s = self._evaluated_count_sell
        sk_b = self._skipped_count_buy
        sk_s = self._skipped_count_sell
        sb_b = self._skipped_by_spread_buy
        sb_s = self._skipped_by_spread_sell
        sot_b = self._skipped_by_opposite_tape_buy
        sot_s = self._skipped_by_opposite_tape_sell
        rate_b = (sk_b / ev_b) if ev_b > 0 else 0.0
        rate_s = (sk_s / ev_s) if ev_s > 0 else 0.0
        self.log.info(
            "SigIslG1L3 gate stats (spread first, co-firing -> spread): "
            f"BUY  eval={ev_b} skip={sk_b} rate={rate_b:.4f} "
            f"(spread={sb_b}, oppositeTape={sot_b}) | "
            f"SELL eval={ev_s} skip={sk_s} rate={rate_s:.4f} "
            f"(spread={sb_s}, oppositeTape={sot_s})"
        )

    def on_reset(self) -> None:
        self._ofi_deque.clear()
        self._net_ofi = 0.0
        self._prev_bid_price = None
        self._prev_bid_size = None
        self._prev_ask_price = None
        self._prev_ask_size = None
        self._spread_deque.clear()
        self._latest_spread = None
        self._position_flat = True
        self._subscribed.clear()
        self._evaluated_count_buy = 0
        self._evaluated_count_sell = 0
        self._skipped_count_buy = 0
        self._skipped_count_sell = 0
        self._skipped_by_spread_buy = 0
        self._skipped_by_spread_sell = 0
        self._skipped_by_opposite_tape_buy = 0
        self._skipped_by_opposite_tape_sell = 0

    # ------------------------------------------------------------------
    # Subscription helper
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Quote tick handler — compute OFI increment AND update spread deque
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        """Compute the level-1 OFI increment and append a spread sample.

        OFI block: identical to G1L2.
        Spread block: NEW — append (ts_event, ask - bid) to the rolling
        spread deque and update `_latest_spread`. Defensive on
        crossed-book ticks.
        """
        try:
            bid_price = float(str(tick.bid_price))
            ask_price = float(str(tick.ask_price))
            bid_size = float(str(tick.bid_size))
            ask_size = float(str(tick.ask_size))
        except Exception:
            # Malformed tick — skip without polluting state.
            return

        # Spread block (NEW). Independent of OFI priming — every well-formed
        # quote provides a spread sample, even the very first one.
        spread = ask_price - bid_price
        if spread >= 0.0:  # defensive against crossed-book ticks
            self._spread_deque.append((tick.ts_event, spread))
            self._latest_spread = spread

        # OFI block (unchanged from G1L2).
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
    # OFI window helpers (unchanged from G1L2)
    # ------------------------------------------------------------------

    def _prune_ofi(self, cutoff_ns: int) -> None:
        """Remove OFI deque entries older than cutoff_ns, updating _net_ofi."""
        while self._ofi_deque and self._ofi_deque[0][0] < cutoff_ns:
            _, old_incr = self._ofi_deque.popleft()
            self._net_ofi -= old_incr

    # ------------------------------------------------------------------
    # Spread window helpers (NEW, ported from afg-isl-g2l1)
    # ------------------------------------------------------------------

    def _prune_spread(self, cutoff_ns: int) -> None:
        while self._spread_deque and self._spread_deque[0][0] < cutoff_ns:
            self._spread_deque.popleft()

    def _spread_gate_skip(self, order) -> bool:
        """Return True iff the latest spread sits above the rolling quantile.

        Warm-up branch: if the deque holds fewer than `min_samples` samples,
        return False (do not gate on the spread axis).

        Ported verbatim (math + control flow) from afg-isl-g2l1.
        """
        cutoff_ns = order.ts_init - self._spread_window_ns
        self._prune_spread(cutoff_ns)

        n = len(self._spread_deque)
        if n < self._min_samples or self._latest_spread is None:
            return False  # warm-up: defer to the opposite-tape gate alone

        # Quantile via sorted copy with linear interpolation.
        sorted_spreads = sorted(s for _, s in self._spread_deque)
        idx_f = self._spread_quantile * (n - 1)
        lo = int(idx_f)
        hi = min(lo + 1, n - 1)
        frac = idx_f - lo
        threshold = (
            sorted_spreads[lo] * (1.0 - frac) + sorted_spreads[hi] * frac
        )

        if self._latest_spread > threshold:
            self.log.debug(
                f"SPREAD SKIP {order.client_order_id}: "
                f"latest_spread={self._latest_spread:.5f} > "
                f"q{self._spread_quantile:.2f}={threshold:.5f} (n={n})."
            )
            return True
        return False

    # ------------------------------------------------------------------
    # Opposite-tape gate (UNCHANGED from G1L2)
    # ------------------------------------------------------------------

    def _opposite_tape_skip(self, order, quote) -> bool:
        """Opposite-tape AND-gate (G1L2). Returns True to skip, else False.

        For each side, the gate fires only when BOTH the static imbalance
        AND the recent OFI point AGAINST the trade direction.
        """
        try:
            bid_size = float(str(quote.bid_size))
            ask_size = float(str(quote.ask_size))
        except Exception:
            return False
        denom = bid_size + ask_size
        if denom <= 0.0:
            return False
        imbalance = (bid_size - ask_size) / denom

        cutoff_ns = order.ts_init - self._ofi_window_ns
        self._prune_ofi(cutoff_ns)
        recent_ofi = self._net_ofi

        if order.side == OrderSide.BUY:
            adverse_imbalance = imbalance < -self._imbalance_threshold
            adverse_ofi = recent_ofi < -self._ofi_threshold
            if adverse_imbalance and adverse_ofi:
                self.log.debug(
                    f"OPPOSITE-TAPE SKIP BUY {order.client_order_id}: "
                    f"I={imbalance:.3f} < -thr={-self._imbalance_threshold:.3f} "
                    f"AND ofi_{self._ofi_window_ns / 1e9:.1f}s={recent_ofi:.2f} "
                    f"< -thr={-self._ofi_threshold:.2f}."
                )
                return True
            return False
        else:  # SELL
            adverse_imbalance = imbalance > self._imbalance_threshold
            adverse_ofi = recent_ofi > self._ofi_threshold
            if adverse_imbalance and adverse_ofi:
                self.log.debug(
                    f"OPPOSITE-TAPE SKIP SELL {order.client_order_id}: "
                    f"I={imbalance:.3f} > thr={self._imbalance_threshold:.3f} "
                    f"AND ofi_{self._ofi_window_ns / 1e9:.1f}s={recent_ofi:.2f} "
                    f"> thr={self._ofi_threshold:.2f}."
                )
                return True
            return False

    # ------------------------------------------------------------------
    # Main order handler — OR-skip composition
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route an order: submit only if BOTH gates pass (OR-skip)."""
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
            # No quote cached yet — fall through (matches G1L2 behavior).
            self._position_flat = False
            self.submit_order(order)
            return

        # Instrument: this order reached the gate region.
        is_buy = order.side == OrderSide.BUY
        if is_buy:
            self._evaluated_count_buy += 1
        else:
            self._evaluated_count_sell += 1

        # Gate A: spread (NEW, cross-island import — book-distance axis).
        if self._spread_gate_skip(order):
            if is_buy:
                self._skipped_count_buy += 1
                self._skipped_by_spread_buy += 1
            else:
                self._skipped_count_sell += 1
                self._skipped_by_spread_sell += 1
            self.log.info(
                f"SKIP {order.client_order_id} — spread gate "
                f"(latest={self._latest_spread}, side="
                f"{'BUY' if is_buy else 'SELL'})."
            )
            self._position_flat = True
            return

        # Gate B: opposite-tape (UNCHANGED from G1L2 — signed-flow axis).
        if self._opposite_tape_skip(order, quote):
            if is_buy:
                self._skipped_count_buy += 1
                self._skipped_by_opposite_tape_buy += 1
            else:
                self._skipped_count_sell += 1
                self._skipped_by_opposite_tape_sell += 1
            self.log.info(
                f"SKIP {order.client_order_id} — opposite-tape microstructure "
                f"(static imbalance AND OFI both against trade, side="
                f"{'BUY' if is_buy else 'SELL'})."
            )
            self._position_flat = True
            return

        # Both gates passed — submit.
        self._position_flat = False
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    imbalance_threshold: float = 0.33,
    ofi_window_seconds: float = 2.0,
    ofi_threshold: float = 5.0,
    spread_window_seconds: float = 60.0,
    spread_quantile: float = 0.75,
    min_samples: int = 50,
) -> SigIslG1L3Algorithm:
    """Instantiate and return the sig-isl-g1l3 algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    imbalance_threshold : float
        Threshold on |I| for the static-imbalance (Lipton) leg of the
        opposite-tape AND gate. Default 0.33 (preserved from G1L2).
    ofi_window_seconds : float
        Rolling window for the per-tick OFI sum (Kolm leg). Default 2.0s
        (preserved from G1L2).
    ofi_threshold : float
        Threshold on |recent_ofi| (in contracts) for the OFI leg of the
        opposite-tape AND gate. Default 5.0 (preserved from G1L2).
    spread_window_seconds : float
        Rolling window for spread samples, in seconds. Default 60.0
        (ported verbatim from island-0 g1l1).
    spread_quantile : float
        Quantile threshold for the spread gate. Default 0.75 (ported
        verbatim from island-0 g1l1; gen-3 ptg-isl-g3l2 confirmed
        this sits on the EV peak across multiple bases).
    min_samples : int
        Minimum spread samples before the spread gate fires. Default 50
        (ported verbatim from island-0 g1l1).
    """
    config = SigIslG1L3Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        imbalance_threshold=imbalance_threshold,
        ofi_window_seconds=ofi_window_seconds,
        ofi_threshold=ofi_threshold,
        spread_window_seconds=spread_window_seconds,
        spread_quantile=spread_quantile,
        min_samples=min_samples,
    )
    return SigIslG1L3Algorithm(config=config)
