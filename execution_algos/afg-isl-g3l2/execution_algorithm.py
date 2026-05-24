"""afg-isl-g3l2 — island-1, generation 3, loop 2.

Adds a **fourth orthogonal SKIP axis** on top of the three-gate stack
frozen in afg-isl-g2l2 (PnL +173.95% vs base — the island-1 best):
**top-of-book size-asymmetry**.

For each OPEN order:
  - Gate A (spread, book-state):   skip OPEN when latest spread > q75 of
                                   the rolling spread distribution.
  - Gate B (chop, price-path):     skip OPEN when chop_ratio > chop_neutral.
  - Gate C (aggressor-flow):       skip OPEN per BASE aggressor-flow-gate.
  - Gate D (size-asymmetry, NEW):  skip BUY  when `ask_size >= size_asym_ratio * bid_size`
                                   skip SELL when `bid_size >= size_asym_ratio * ask_size`
  - Submit only if ALL FOUR gates pass.

Why this design
---------------
g3l1's `summary_out.next` explicitly named this as the highest-leverage
next direction:

  "Recommendation for g3l2: option (b) — top-of-book bid_size/ask_size
  ratio is the most independent-from-existing candidate (book-DEPTH
  imbalance is structurally distinct from spread's quote-DISTANCE and
  from flow's signed-trade pressure; volume bursts correlate with flow;
  time-of-day correlates with spread). Composition rule: binary AND-skip
  (consistent with g2l2's working composition)."

g3l1 itself (chop_neutral 1.5 → 1.7) was a null result vs g2l2 (-1.16%,
indistinguishable on every secondary metric), exhausting chop
calibration on this base. The chop axis is at its operating point.

Cross-island prior on this axis
-------------------------------
Island-0 g1l2 (`ptg-isl-g1l2`) added a side-dependent queue-imbalance
gate (`q = bid_size / (bid_size + ask_size)`; skip BUY when q < 0.30,
skip SELL when q > 0.70) on top of ptg's position-cap + spread-p75
composition — and produced bit-for-bit identical metrics to g1l1 on
every reported field. The gen-1 migration's `what_failed` block names
this as the canonical null-result example. **Evidence the
size-asymmetry axis may NOT add value on this base either.** Two
reasons it might still:

1. Different composition partner: g1l2 stacked imbalance on
   `position-cap + spread`. This loop stacks it on
   `base-flow + spread + chop`. The base flow gate removes the
   signed-trade-pressure slice but not resting book DEPTH; on the afg
   base the residual imbalance signal may differ.
2. Different threshold: g1l2's `q < 0.30` corresponds to
   `ask_size > 2.33 * bid_size` (a fairly extreme imbalance). g1l2's
   own `next` block recommended tightening toward `[0.40, 0.60]`. This
   loop picks `size_asym_ratio = 1.5` (equivalent to `q < 0.40` for
   BUY skip / `q > 0.60` for SELL skip), which is strictly tighter
   than g1l2 and directly tests g1l2's own recommended remediation
   path on a different base.

Instrumentation
---------------
Per the gen-1 migration's `what_failed` finding on island-0 g1l2 —
"stacking a second gate on an orthogonal axis WITHOUT instrumentation
... bit-for-bit identical metrics — undiagnosable null result" — this
loop ships per-gate counters:

  - _evaluated_count (OPEN orders that reached the gate stack)
  - _skipped_spread, _skipped_chop, _skipped_flow_buy,
    _skipped_flow_sell, _skipped_size_asym_buy, _skipped_size_asym_sell

Counters are emitted on `on_stop` so a null result (g3l2 metrics ==
g2l2 metrics) is diagnosable as "gate never fired" vs "gate fired but
EV-neutral" vs "gate fully redundant with one of the prior three".

Algorithm
---------
Maintain four independent rolling structures (three from g2l2, plus
latest top-of-book sizes from quote ticks):
  - Aggressor-flow deque (from on_trade_tick): unchanged from base.
  - Spread deque (from on_quote_tick): unchanged from g2l1 / island-0 g1l1.
  - Chop window (from on_quote_tick): unchanged from g2l2 / vrs-isl-g1l1.
  - Latest bid/ask sizes (from on_quote_tick): single-quote-only, no
    rolling history; updated in-place each quote tick.

Reduce-only orders always submit (intraday_flat). Forced re-entry after
a skip is unconditional (anti-cascade contract). Order quantity is
never modified.

No look-ahead: all rolling structures are fed by Nautilus callbacks in
replay chronological order; latest sizes use the most recent quote
observed at or before order arrival, identical to ptg-isl-g1l2's
contract.

Falsification
-------------
- Confirmation: PnL > g2l2 (3439.50) AND drawdown does not widen AND
  trade_count drop <= 10%.
- Null: metrics indistinguishable from g2l2 AND counters show the
  size-asym gate fires < 0.5% of OPEN evaluations OR co-skips with
  another gate at near-100% rate.
- Regression: PnL < g2l2 by > 2% OR trade_count drops > 10% — verdict
  is a hard three-axis ceiling on this base for this experiment.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class AfgIslG3L2Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for afg-isl-g3l2: g2l2 + size-asymmetry (fourth axis).

    All g2l2 parameters preserved verbatim. New parameter:

    size_asym_ratio : float
        Ratio threshold for the top-of-book size-asymmetry gate. Skip a
        BUY OPEN when `ask_size >= size_asym_ratio * bid_size` (contra
        side dominates); skip a SELL OPEN when
        `bid_size >= size_asym_ratio * ask_size`. Default 1.5 — strictly
        tighter than ptg-isl-g1l2's implied 2.33 (q < 0.30) and within
        the lower end of g1l2's own recommended `[0.40, 0.60]` share
        band.
    """

    window_seconds: float = 10.0
    flow_threshold: float = 2.0
    spread_window_seconds: float = 60.0
    spread_quantile: float = 0.75
    min_samples: int = 50
    chop_window_ticks: int = 30
    chop_neutral: float = 1.5
    chop_min_ticks: int = 40
    chop_eps: float = 1e-9
    chop_max_ratio: float = 20.0
    size_asym_ratio: float = 1.5


class AfgIslG3L2Algorithm(ExecAlgorithm):
    """g2l2 (base flow + spread + chop) + size-asymmetry gate (fourth axis).

    Opening orders (is_reduce_only == False):
      - Forced re-entry after a skip is unconditional (anti-cascade).
      - Gate A (spread, book-state):    skip OPEN when latest spread > q75.
      - Gate B (chop, price-path):      skip OPEN when chop_ratio > chop_neutral.
      - Gate C (aggressor-flow, base):  BUY  skip iff net_flow <= -flow_threshold
                                        SELL skip iff net_flow >=  flow_threshold
      - Gate D (size-asym, NEW):        BUY  skip iff ask_size >= ratio * bid_size
                                        SELL skip iff bid_size >= ratio * ask_size
      - Submit only if ALL FOUR gates pass.
      - After any skip: `_position_flat = True` (next open unconditional).

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    Quantity invariant: never modify `order.quantity`.

    Instrumentation: per-gate skip counters and an evaluated-order counter
    are emitted on `on_stop` so null-result diagnosis is possible.
    """

    def __init__(self, config: AfgIslG3L2Config) -> None:
        super().__init__(config=config)

        # ---- Aggressor-flow state (base, unmodified — mirrors g2l2) ----
        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._flow_threshold: float = float(config.flow_threshold)
        self._flow_deque: deque[tuple[int, float]] = deque()
        self._net_flow: float = 0.0

        # ---- Spread-gate state (unchanged from g2l2) ----
        self._spread_window_ns: int = int(
            config.spread_window_seconds * 1_000_000_000
        )
        self._spread_quantile: float = float(config.spread_quantile)
        self._min_samples: int = int(config.min_samples)
        self._spread_deque: deque[tuple[int, float]] = deque()
        self._latest_spread: float | None = None

        # ---- Chop-gate state (unchanged from g2l2 — verbatim port from vrs-isl-g1l1) ----
        self._chop_window_ticks: int = int(config.chop_window_ticks)
        self._chop_neutral: float = float(config.chop_neutral)
        self._chop_min_ticks: int = int(config.chop_min_ticks)
        self._chop_eps: float = float(config.chop_eps)
        self._chop_max_ratio: float = float(config.chop_max_ratio)
        self._mids: deque[float] = deque(maxlen=self._chop_window_ticks + 1)
        self._abs_deltas: deque[float] = deque(maxlen=self._chop_window_ticks)
        self._path_sum: float = 0.0
        self._tick_count: int = 0

        # ---- Size-asymmetry-gate state (NEW fourth axis) ----
        # Latest top-of-book sizes from the most recent quote tick. No
        # rolling history (parity with ptg-isl-g1l2's contract).
        self._size_asym_ratio: float = float(config.size_asym_ratio)
        self._latest_bid_size: float | None = None
        self._latest_ask_size: float | None = None

        # ---- Anti-cascade contract (unchanged) ----
        self._position_flat: bool = True

        # ---- Subscription tracking ----
        self._subscribed: set[str] = set()

        # ---- Instrumentation counters (gen-1 migration mandate) ----
        # Number of OPEN orders that REACHED the gate stack (i.e. not
        # reduce-only, not forced re-entry). Skipped counters are
        # per-gate, side-specific where the gate is direction-aware.
        self._evaluated_count: int = 0
        self._skipped_spread: int = 0
        self._skipped_chop: int = 0
        self._skipped_flow_buy: int = 0
        self._skipped_flow_sell: int = 0
        self._skipped_size_asym_buy: int = 0
        self._skipped_size_asym_sell: int = 0
        # OPEN orders that passed all four gates and were submitted.
        self._submitted_count: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            "AfgIslG3L2Algorithm started "
            f"(flow_window={self._window_ns / 1e9:.1f}s, "
            f"flow_threshold={self._flow_threshold:.2f}, "
            f"spread_window={self._spread_window_ns / 1e9:.1f}s, "
            f"spread_quantile={self._spread_quantile:.2f}, "
            f"min_samples={self._min_samples}, "
            f"chop_window_ticks={self._chop_window_ticks}, "
            f"chop_neutral={self._chop_neutral:.2f}, "
            f"chop_min_ticks={self._chop_min_ticks}, "
            f"size_asym_ratio={self._size_asym_ratio:.2f})."
        )

    def on_stop(self) -> None:
        """Emit per-gate instrumentation counters for null-result diagnosis."""
        self.log.info(
            "AfgIslG3L2Algorithm gate counters: "
            f"evaluated={self._evaluated_count}, "
            f"submitted={self._submitted_count}, "
            f"skip_spread={self._skipped_spread}, "
            f"skip_chop={self._skipped_chop}, "
            f"skip_flow_buy={self._skipped_flow_buy}, "
            f"skip_flow_sell={self._skipped_flow_sell}, "
            f"skip_size_asym_buy={self._skipped_size_asym_buy}, "
            f"skip_size_asym_sell={self._skipped_size_asym_sell}."
        )

    def on_reset(self) -> None:
        self._flow_deque.clear()
        self._net_flow = 0.0
        self._spread_deque.clear()
        self._latest_spread = None
        self._mids.clear()
        self._abs_deltas.clear()
        self._path_sum = 0.0
        self._tick_count = 0
        self._latest_bid_size = None
        self._latest_ask_size = None
        self._position_flat = True
        self._subscribed.clear()
        self._evaluated_count = 0
        self._skipped_spread = 0
        self._skipped_chop = 0
        self._skipped_flow_buy = 0
        self._skipped_flow_sell = 0
        self._skipped_size_asym_buy = 0
        self._skipped_size_asym_sell = 0
        self._submitted_count = 0

    # ------------------------------------------------------------------
    # Subscription helper
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_trade_ticks(instrument_id)
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Trade-tick handler — maintain rolling signed-flow deque
    # ------------------------------------------------------------------

    def on_trade_tick(self, tick) -> None:
        """Update the rolling aggressor-flow deque (base behavior)."""
        aggressor = tick.aggressor_side
        size = float(str(tick.size))

        if aggressor == AggressorSide.BUYER:
            signed_vol = size
        elif aggressor == AggressorSide.SELLER:
            signed_vol = -size
        else:
            # NO_AGGRESSOR — treat as neutral; do not bias the flow signal.
            signed_vol = 0.0

        self._flow_deque.append((tick.ts_event, signed_vol))
        self._net_flow += signed_vol

    # ------------------------------------------------------------------
    # Quote-tick handler — feeds the spread deque, the chop window, AND
    # the latest top-of-book sizes (fourth gate's state).
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        """Update spread deque, chop window, AND latest bid/ask sizes."""
        try:
            bid = float(str(tick.bid_price))
            ask = float(str(tick.ask_price))
            bid_size = float(str(tick.bid_size))
            ask_size = float(str(tick.ask_size))
        except Exception:
            return

        # ---- Spread deque (book-state axis) ----
        spread = ask - bid
        if spread >= 0.0:
            self._spread_deque.append((tick.ts_event, spread))
            self._latest_spread = spread
        else:
            # Crossed book — drop this quote from all rolling structures
            # defensively. Identical contract to g2l2.
            return

        # ---- Chop window (price-path axis, verbatim from g2l2) ----
        mid = (bid + ask) / 2.0
        if self._mids:
            prev_mid = self._mids[-1]
            abs_delta = abs(mid - prev_mid)

            if len(self._abs_deltas) == self._chop_window_ticks:
                self._path_sum -= self._abs_deltas[0]
            self._abs_deltas.append(abs_delta)
            self._path_sum += abs_delta

        self._mids.append(mid)
        self._tick_count += 1

        # ---- Latest top-of-book sizes (NEW fourth-gate state) ----
        # Single-quote-only semantics (no rolling); identical contract to
        # ptg-isl-g1l2. Updated only on well-formed (non-crossed) quotes
        # so a malformed quote does not poison the gate.
        self._latest_bid_size = bid_size
        self._latest_ask_size = ask_size

    # ------------------------------------------------------------------
    # Flow gate (base, unmodified — unchanged from g2l2)
    # ------------------------------------------------------------------

    def _prune_flow_window(self, cutoff_ns: int) -> None:
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            _, old_vol = self._flow_deque.popleft()
            self._net_flow -= old_vol

    def _flow_is_adverse(self, order) -> bool:
        """Base aggressor-flow-gate logic. Unchanged from base / g2l2."""
        cutoff_ns = order.ts_init - self._window_ns
        self._prune_flow_window(cutoff_ns)

        if not self._flow_deque:
            return False

        net = self._net_flow

        if order.side == OrderSide.BUY:
            if net <= -self._flow_threshold:
                return True
        else:  # SELL
            if net >= self._flow_threshold:
                return True

        return False

    # ------------------------------------------------------------------
    # Spread gate (unchanged from g2l2 — cross-island import island-0 g1l1)
    # ------------------------------------------------------------------

    def _prune_spread_window(self, cutoff_ns: int) -> None:
        while self._spread_deque and self._spread_deque[0][0] < cutoff_ns:
            self._spread_deque.popleft()

    def _spread_gate_skip(self, order) -> bool:
        """Return True if the latest spread sits above the rolling quantile."""
        cutoff_ns = order.ts_init - self._spread_window_ns
        self._prune_spread_window(cutoff_ns)

        n = len(self._spread_deque)
        if n < self._min_samples or self._latest_spread is None:
            return False

        sorted_spreads = sorted(s for _, s in self._spread_deque)
        idx_f = self._spread_quantile * (n - 1)
        lo = int(idx_f)
        hi = min(lo + 1, n - 1)
        frac = idx_f - lo
        threshold = sorted_spreads[lo] * (1.0 - frac) + sorted_spreads[hi] * frac

        if self._latest_spread > threshold:
            return True
        return False

    # ------------------------------------------------------------------
    # Chop gate (unchanged from g2l2 — verbatim port from vrs-isl-g1l1)
    # ------------------------------------------------------------------

    def _chop_gate_skip(self, order) -> bool:
        """Return True if chop_ratio exceeds chop_neutral."""
        if self._tick_count < self._chop_min_ticks:
            return False
        if (
            len(self._mids) < self._chop_window_ticks + 1
            or len(self._abs_deltas) < self._chop_window_ticks
        ):
            return False

        path_length = self._path_sum
        displacement = abs(self._mids[-1] - self._mids[0])
        denom = max(displacement, self._chop_eps)
        chop_ratio = min(path_length / denom, self._chop_max_ratio)

        if chop_ratio > self._chop_neutral:
            return True
        return False

    # ------------------------------------------------------------------
    # Size-asymmetry gate (NEW — fourth orthogonal axis)
    # ------------------------------------------------------------------

    def _size_asym_gate_skip(self, order) -> bool:
        """Return True if the contra side massively dominates this side.

        BUY OPEN skipped when `ask_size >= ratio * bid_size` (contra side
        thick, our side thin → likely getting picked off into a top-tier
        liquidity-asymmetry window).
        SELL OPEN skipped when `bid_size >= ratio * ask_size` (symmetric).

        Warm-up: if no quote has yet been observed, defer to remaining
        gates (return False). Identical contract to ptg-isl-g1l2.
        """
        bid_size = self._latest_bid_size
        ask_size = self._latest_ask_size
        if bid_size is None or ask_size is None:
            return False
        # Defensive: a zero size on the same side is treated as extreme
        # asymmetry only if the contra side has any size at all (avoid
        # 0 vs 0 firing on illiquid moments — same-direction warm-up
        # behavior).
        if bid_size <= 0.0 and ask_size <= 0.0:
            return False

        ratio = self._size_asym_ratio

        if order.side == OrderSide.BUY:
            # Skip BUY when ask is at least `ratio` times the bid.
            # If bid_size == 0 but ask_size > 0, ratio * 0 == 0 and
            # ask_size >= 0 is True — gate fires, which is the intended
            # extreme-asymmetry behavior.
            if ask_size >= ratio * bid_size and ask_size > 0.0:
                return True
        else:  # SELL
            if bid_size >= ratio * ask_size and bid_size > 0.0:
                return True

        return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit only if ALL FOUR gates pass."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat.
        if order.is_reduce_only:
            self.submit_order(order)
            return

        # Forced re-entry after a skip — always submit to prevent cascade.
        if self._position_flat:
            self._position_flat = False
            self.submit_order(order)
            return

        # This order reached the gate stack — count it as evaluated.
        self._evaluated_count += 1

        # Gate A: spread (book-state axis).
        if self._spread_gate_skip(order):
            self._skipped_spread += 1
            self.log.info(
                f"SKIP {order.client_order_id} — spread gate "
                f"(latest={self._latest_spread})."
            )
            self._position_flat = True
            return

        # Gate B: chop (price-path axis).
        if self._chop_gate_skip(order):
            self._skipped_chop += 1
            self.log.info(
                f"SKIP {order.client_order_id} — chop gate "
                f"(tick_count={self._tick_count})."
            )
            self._position_flat = True
            return

        # Gate C: aggressor-flow (trade-pressure axis, BASE unmodified).
        if self._flow_is_adverse(order):
            if order.side == OrderSide.BUY:
                self._skipped_flow_buy += 1
            else:
                self._skipped_flow_sell += 1
            self.log.info(
                f"SKIP {order.client_order_id} — adverse aggressor flow "
                f"(net_flow={self._net_flow:.2f}, side="
                f"{'BUY' if order.side == OrderSide.BUY else 'SELL'})."
            )
            self._position_flat = True
            return

        # Gate D: size-asymmetry (book-depth axis — NEW).
        if self._size_asym_gate_skip(order):
            if order.side == OrderSide.BUY:
                self._skipped_size_asym_buy += 1
            else:
                self._skipped_size_asym_sell += 1
            self.log.info(
                f"SKIP {order.client_order_id} — size-asymmetry gate "
                f"(bid_size={self._latest_bid_size}, "
                f"ask_size={self._latest_ask_size}, side="
                f"{'BUY' if order.side == OrderSide.BUY else 'SELL'})."
            )
            self._position_flat = True
            return

        # All four gates passed — submit.
        self._submitted_count += 1
        self._position_flat = False
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_seconds: float = 10.0,
    flow_threshold: float = 2.0,
    spread_window_seconds: float = 60.0,
    spread_quantile: float = 0.75,
    min_samples: int = 50,
    chop_window_ticks: int = 30,
    chop_neutral: float = 1.5,
    chop_min_ticks: int = 40,
    chop_eps: float = 1e-9,
    chop_max_ratio: float = 20.0,
    size_asym_ratio: float = 1.5,
) -> AfgIslG3L2Algorithm:
    """Instantiate and return the afg-isl-g3l2 algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_seconds : float
        Aggressor-flow rolling window, in seconds. Default 10.0 (base).
    flow_threshold : float
        Aggressor-flow adverse threshold (contracts). Default 2.0 (base).
    spread_window_seconds : float
        Rolling window for spread samples, in seconds. Default 60.0
        (verbatim from g2l2 / island-0 g1l1).
    spread_quantile : float
        Quantile threshold for the spread gate. Default 0.75 (verbatim
        from g2l2 / island-0 g1l1).
    min_samples : int
        Minimum spread samples before the spread gate fires. Default 50
        (verbatim from g2l2).
    chop_window_ticks : int
        Rolling window length for the chop ratio, in quote ticks. Default
        30 (verbatim from g2l2 / vrs-isl-g1l1).
    chop_neutral : float
        Chop ratio threshold for binary hard-skip. Default 1.5 (verbatim
        from g2l2 / vrs-isl-g1l1; g3l1's 1.5 → 1.7 sweep was null vs
        g2l2, so the base-robust operating point is preserved).
    chop_min_ticks : int
        Cold-start guard before the chop gate activates. Default 40
        (verbatim from g2l2).
    chop_eps : float
        Lower bound on displacement (divide-by-zero guard). Default 1e-9.
    chop_max_ratio : float
        Cap on chop_ratio (numerical-stability guard). Default 20.0.
    size_asym_ratio : float
        Top-of-book size-asymmetry threshold. Skip BUY when
        `ask_size >= size_asym_ratio * bid_size`; skip SELL when
        `bid_size >= size_asym_ratio * ask_size`. Default 1.5 — strictly
        tighter than ptg-isl-g1l2's implied 2.33 (q < 0.30) and within
        the lower end of g1l2's own recommended `[0.40, 0.60]` share
        band.
    """
    config = AfgIslG3L2Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_seconds=window_seconds,
        flow_threshold=flow_threshold,
        spread_window_seconds=spread_window_seconds,
        spread_quantile=spread_quantile,
        min_samples=min_samples,
        chop_window_ticks=chop_window_ticks,
        chop_neutral=chop_neutral,
        chop_min_ticks=chop_min_ticks,
        chop_eps=chop_eps,
        chop_max_ratio=chop_max_ratio,
        size_asym_ratio=size_asym_ratio,
    )
    return AfgIslG3L2Algorithm(config=config)
