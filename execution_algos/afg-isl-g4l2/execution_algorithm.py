"""afg-isl-g4l2 — island-1, generation 4, loop 2.

Adds a **fifth orthogonal SKIP axis** on top of the FOUR-gate stack frozen
in afg-isl-g3l2 (the island-1 lineage best at PnL +233.05% vs base, sharpe
17.80). g4l1 attempted a different fifth axis (signed mid-price velocity)
and produced a NULL result (PnL inside the ±2% null band vs g3l2, sharpe
indistinguishable, only 9 fewer trades on a ~96k base — the 0.50 $/s
threshold over a 5s window sat in the empty tail of the 4-gate-conditioned
distribution). g4l1's own `summary_out.next` explicitly preferred this
loop's direction:

  "(B) PIVOT to recent-trade-side flow (alternative 5th axis) — the
  candidate g3l2 originally named as more conservative, structurally
  different from velocity (conditions on TRADE-side, not mid-drift) and
  from base flow C (TRADE-side, not net-volume sign). … (B) is higher
  information per loop because (A) is a single-knob sweep on an
  already-shown-inert mechanic at moderate threshold, whereas (B)
  introduces a structurally new candidate axis at the same loop cost."

This loop therefore **drops the inert velocity axis** (reverts to the
g3l2 four-gate stack as the implementation base) and **adds recent-trade-
side flow** as the fifth axis, retaining all g3l2 parameters verbatim.

Why this design
---------------
The base aggressor-flow gate (axis C) uses **signed net volume over a
10-second window** with an absolute contract threshold (2.0). The new
fifth axis (axis E, "recent-side flow") differs along THREE structural
dimensions simultaneously:

1. **Time horizon**: 1.5s rolling window vs base's 10s — captures very
   recent aggressor pressure that is too short-lived to materially shift
   the 10s net-volume calculation.
2. **Aggregation mechanic**: COUNT of trade-side dominance (how many of
   the last N trades came in on which side), not NET SIGNED VOLUME. Two
   one-lot seller-aggressor prints contribute the same dominance signal
   as one two-lot seller-aggressor print — the size weighting is the
   base's mechanic, not this one's.
3. **Threshold style**: a RATIO (e.g. ≥ 70% of recent trades on the
   contra side) rather than an absolute volume threshold, so the gate is
   self-normalizing across high- and low-volume periods (the base flow
   gate's 2.0-contract threshold becomes less informative when typical
   short-window prints are sub-contract or burst above 10).

Skip logic — symmetric and side-aware:
  - Skip BUY OPEN when, of the last `recent_min_trades` trades in the
    last `recent_window_seconds`, at least `recent_dominance_ratio` are
    SELLER-aggressor (sellers actively crossing into the bid → likely
    getting picked off if we BUY now).
  - Skip SELL OPEN when, of those recent trades, at least
    `recent_dominance_ratio` are BUYER-aggressor (symmetric).

Gen-3 migration `base_specific` (2): "afg accepts a fourth orthogonal
axis cleanly and is the right island to probe the five-axis frontier
next — the gen-2 three-gate stack survived size-asymmetry addition
without regression and operates on a base whose surviving population has
the most remaining headroom across the three islands." g3l2 confirmed
this for axis 4 (size-asymmetry) at +21.59% vs g2l2. g4l1's null on the
velocity axis is consistent with that 4-gate-conditioned population still
having headroom but NOT in the slow-window mid-drift direction; this
loop tests whether a SHORT-window, COUNT-based, RATIO-thresholded
trade-side axis is the right mechanic to access the remaining headroom.

Cross-island prior on the trade-side mechanic
---------------------------------------------
No island has yet tested a trade-side-count gate. It is one of the two
named candidates from gen-2 migration's `what_worked` / candidate-axis
list, and was deferred at g3l2 in favor of size-asymmetry (which won at
+21.59%). It also differs from island-0 g1l2's queue-imbalance gate
(book-depth state, not trade-side flow) and from island-2 g2l2's
verbatim flow port (which regressed because the OPERATING POINT did not
transfer — this loop changes both the MECHANIC and the OPERATING POINT,
so no direct prior).

Parameters (g3l2 four gates preserved verbatim)
-----------------------------------------------
  - flow_window_seconds   = 10.0   (base flow, unchanged)
  - flow_threshold        = 2.0    (base flow, unchanged)
  - spread_window_seconds = 60.0   (axis A, unchanged)
  - spread_quantile       = 0.75   (axis A, unchanged)
  - min_samples           = 50     (axis A, unchanged)
  - chop_window_ticks     = 30     (axis B, unchanged)
  - chop_neutral          = 1.5    (axis B, unchanged — base-robust per gen-3 migration)
  - chop_min_ticks        = 40     (axis B, unchanged)
  - size_asym_ratio       = 1.5    (axis D, unchanged from g3l2)
  - recent_window_seconds = 1.5    (axis E, NEW — middle of g4l1.next's "1-2s" band)
  - recent_min_trades     = 5      (axis E, NEW — warm-up; need ≥5 trades to evaluate)
  - recent_dominance_ratio = 0.70  (axis E, NEW — ≥70% contra-side dominance to skip)

Instrumentation
---------------
g3l2 introduced per-gate counters. This loop extends them to the fifth
axis: `_skipped_recent_buy`, `_skipped_recent_sell`. Counters are
emitted on `on_stop` so a null result is diagnosable.

Algorithm
---------
Maintain FIVE independent rolling structures:
  - Aggressor-flow deque (from on_trade_tick): unchanged from g3l2.
  - Spread deque (from on_quote_tick): unchanged from g3l2.
  - Chop window (from on_quote_tick): unchanged from g3l2.
  - Latest bid/ask sizes (from on_quote_tick): unchanged from g3l2.
  - **NEW**: Recent-trade-side deque (from on_trade_tick) — a separate
    short-window structure that stores tuples of (ts_event, side_code)
    where side_code is +1 for BUYER-aggressor, -1 for SELLER-aggressor,
    0 for NO_AGGRESSOR. Maintained independently from the flow deque to
    isolate the count mechanic from the volume mechanic.

Reduce-only orders always submit (intraday_flat). Forced re-entry after
a skip is unconditional (anti-cascade contract). Order quantity is
never modified.

Falsification
-------------
Pre-stated success criterion for g4l2:
- Confirmation: PnL > g3l2 (4182.00) AND drawdown does not widen AND
  trade_count drop ≤ 10%. (Strong confirmation: PnL > +2% vs g3l2.)
- Null (defined ex-ante): metrics inside the ±2% null band vs g3l2 AND
  the new gate fires <0.5% of OPEN evaluations OR co-skips with another
  gate at near-100% rate. If null fires, the four-axis stack is the
  empirical ceiling for THIS island AND THIS combination of axes; gen-4
  migration should flag whether the five-axis frontier is closed or
  whether a yet-different fifth axis (volume-burst, time-of-day) remains.
- Regression: PnL < g3l2 by > 2% OR trade_count drops > 10% — the recent-
  trade-side axis is mechanically redundant with axis C (base flow), and
  the right next direction is operating-point retuning of axes A–D, not
  further fifth-axis exploration.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class AfgIslG4L2Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for afg-isl-g4l2: g3l2 four-gate stack + recent-trade-side flow (fifth axis).

    All g3l2 parameters preserved verbatim. New parameters:

    recent_window_seconds : float
        Rolling window for the recent-trade-side count gate, in seconds.
        Default 1.5 — middle of g4l1's recommended "1-2s" band and well
        below the base flow gate's 10s window (so the two trade-pressure
        axes operate on structurally distinct time horizons).
    recent_min_trades : int
        Minimum number of trades that must be present in the recent
        window before the gate may fire. Default 5 — guards against
        thin-print false positives.
    recent_dominance_ratio : float
        Fraction of recent trades that must be on the CONTRA side for
        the gate to skip. Default 0.70 — strict enough to be informative
        (~70% one-sided burst over 1.5s is a real microstructure signal),
        not so strict the gate never fires.
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
    recent_window_seconds: float = 1.5
    recent_min_trades: int = 5
    recent_dominance_ratio: float = 0.70


class AfgIslG4L2Algorithm(ExecAlgorithm):
    """g3l2 four-gate stack (spread + chop + base-flow + size-asym) + recent-trade-side flow (axis E).

    Opening orders (is_reduce_only == False):
      - Forced re-entry after a skip is unconditional (anti-cascade).
      - Gate A (spread, book-state):       skip OPEN when latest spread > q75.
      - Gate B (chop, price-path):         skip OPEN when chop_ratio > chop_neutral.
      - Gate C (aggressor-flow, base):     BUY  skip iff net_flow <= -flow_threshold
                                            SELL skip iff net_flow >=  flow_threshold
      - Gate D (size-asym, book-depth):    BUY  skip iff ask_size >= ratio * bid_size
                                            SELL skip iff bid_size >= ratio * ask_size
      - Gate E (recent-side, NEW):         BUY  skip iff sellers/total >= dominance_ratio
                                            SELL skip iff buyers/total >= dominance_ratio
                                            (only after recent_min_trades trades in window).
      - Submit only if ALL FIVE gates pass.
      - After any skip: `_position_flat = True` (next open unconditional).

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    Quantity invariant: never modify `order.quantity`.
    """

    def __init__(self, config: AfgIslG4L2Config) -> None:
        super().__init__(config=config)

        # ---- Aggressor-flow state (base, unmodified — mirrors g3l2) ----
        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._flow_threshold: float = float(config.flow_threshold)
        self._flow_deque: deque[tuple[int, float]] = deque()
        self._net_flow: float = 0.0

        # ---- Spread-gate state (unchanged from g3l2) ----
        self._spread_window_ns: int = int(
            config.spread_window_seconds * 1_000_000_000
        )
        self._spread_quantile: float = float(config.spread_quantile)
        self._min_samples: int = int(config.min_samples)
        self._spread_deque: deque[tuple[int, float]] = deque()
        self._latest_spread: float | None = None

        # ---- Chop-gate state (unchanged from g3l2) ----
        self._chop_window_ticks: int = int(config.chop_window_ticks)
        self._chop_neutral: float = float(config.chop_neutral)
        self._chop_min_ticks: int = int(config.chop_min_ticks)
        self._chop_eps: float = float(config.chop_eps)
        self._chop_max_ratio: float = float(config.chop_max_ratio)
        self._mids: deque[float] = deque(maxlen=self._chop_window_ticks + 1)
        self._abs_deltas: deque[float] = deque(maxlen=self._chop_window_ticks)
        self._path_sum: float = 0.0
        self._tick_count: int = 0

        # ---- Size-asymmetry-gate state (unchanged from g3l2) ----
        self._size_asym_ratio: float = float(config.size_asym_ratio)
        self._latest_bid_size: float | None = None
        self._latest_ask_size: float | None = None

        # ---- Recent-trade-side-flow gate state (NEW fifth axis) ----
        # Separate deque from the base flow deque to isolate the COUNT
        # mechanic from the VOLUME mechanic. Stores (ts_event, side_code)
        # where side_code is +1 BUYER-aggr, -1 SELLER-aggr, 0 NO_AGGR.
        self._recent_window_ns: int = int(
            config.recent_window_seconds * 1_000_000_000
        )
        self._recent_min_trades: int = int(config.recent_min_trades)
        self._recent_dominance_ratio: float = float(
            config.recent_dominance_ratio
        )
        self._recent_deque: deque[tuple[int, int]] = deque()
        self._recent_buy_count: int = 0  # BUYER-aggressor trades currently in window.
        self._recent_sell_count: int = 0  # SELLER-aggressor trades currently in window.

        # ---- Anti-cascade contract (unchanged) ----
        self._position_flat: bool = True

        # ---- Subscription tracking ----
        self._subscribed: set[str] = set()

        # ---- Instrumentation counters (gen-1 migration mandate) ----
        self._evaluated_count: int = 0
        self._skipped_spread: int = 0
        self._skipped_chop: int = 0
        self._skipped_flow_buy: int = 0
        self._skipped_flow_sell: int = 0
        self._skipped_size_asym_buy: int = 0
        self._skipped_size_asym_sell: int = 0
        self._skipped_recent_buy: int = 0
        self._skipped_recent_sell: int = 0
        self._submitted_count: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            "AfgIslG4L2Algorithm started "
            f"(flow_window={self._window_ns / 1e9:.1f}s, "
            f"flow_threshold={self._flow_threshold:.2f}, "
            f"spread_window={self._spread_window_ns / 1e9:.1f}s, "
            f"spread_quantile={self._spread_quantile:.2f}, "
            f"min_samples={self._min_samples}, "
            f"chop_window_ticks={self._chop_window_ticks}, "
            f"chop_neutral={self._chop_neutral:.2f}, "
            f"chop_min_ticks={self._chop_min_ticks}, "
            f"size_asym_ratio={self._size_asym_ratio:.2f}, "
            f"recent_window={self._recent_window_ns / 1e9:.2f}s, "
            f"recent_min_trades={self._recent_min_trades}, "
            f"recent_dominance_ratio={self._recent_dominance_ratio:.2f})."
        )

    def on_stop(self) -> None:
        """Emit per-gate instrumentation counters for null-result diagnosis."""
        self.log.info(
            "AfgIslG4L2Algorithm gate counters: "
            f"evaluated={self._evaluated_count}, "
            f"submitted={self._submitted_count}, "
            f"skip_spread={self._skipped_spread}, "
            f"skip_chop={self._skipped_chop}, "
            f"skip_flow_buy={self._skipped_flow_buy}, "
            f"skip_flow_sell={self._skipped_flow_sell}, "
            f"skip_size_asym_buy={self._skipped_size_asym_buy}, "
            f"skip_size_asym_sell={self._skipped_size_asym_sell}, "
            f"skip_recent_buy={self._skipped_recent_buy}, "
            f"skip_recent_sell={self._skipped_recent_sell}."
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
        self._recent_deque.clear()
        self._recent_buy_count = 0
        self._recent_sell_count = 0
        self._position_flat = True
        self._subscribed.clear()
        self._evaluated_count = 0
        self._skipped_spread = 0
        self._skipped_chop = 0
        self._skipped_flow_buy = 0
        self._skipped_flow_sell = 0
        self._skipped_size_asym_buy = 0
        self._skipped_size_asym_sell = 0
        self._skipped_recent_buy = 0
        self._skipped_recent_sell = 0
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
    # Trade-tick handler — maintain BOTH the base signed-flow deque AND
    # the new recent-trade-side count deque.
    # ------------------------------------------------------------------

    def on_trade_tick(self, tick) -> None:
        """Update the rolling aggressor-flow deque (base behavior) AND the
        recent-trade-side count deque (new fifth axis).
        """
        aggressor = tick.aggressor_side
        size = float(str(tick.size))

        # ---- Base signed-flow deque (unchanged) ----
        if aggressor == AggressorSide.BUYER:
            signed_vol = size
        elif aggressor == AggressorSide.SELLER:
            signed_vol = -size
        else:
            # NO_AGGRESSOR — treat as neutral; do not bias the flow signal.
            signed_vol = 0.0

        self._flow_deque.append((tick.ts_event, signed_vol))
        self._net_flow += signed_vol

        # ---- Recent-trade-side count deque (NEW) ----
        # Track aggressor side as a count signal independent of size.
        if aggressor == AggressorSide.BUYER:
            side_code = 1
            self._recent_buy_count += 1
        elif aggressor == AggressorSide.SELLER:
            side_code = -1
            self._recent_sell_count += 1
        else:
            # NO_AGGRESSOR — record but do not contribute to either side's
            # count (acts as a denominator-only entry, which we'll handle
            # in the gate by using buy_count + sell_count as the
            # informative-trade total).
            side_code = 0

        self._recent_deque.append((tick.ts_event, side_code))

    # ------------------------------------------------------------------
    # Quote-tick handler — feeds the spread deque, the chop window, AND
    # the latest top-of-book sizes (unchanged from g3l2).
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
            # defensively. Identical contract to g3l2.
            return

        # ---- Chop window (price-path axis, unchanged from g3l2) ----
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

        # ---- Latest top-of-book sizes (size-asym gate state, unchanged) ----
        self._latest_bid_size = bid_size
        self._latest_ask_size = ask_size

    # ------------------------------------------------------------------
    # Flow gate (base, unmodified — unchanged from g3l2)
    # ------------------------------------------------------------------

    def _prune_flow_window(self, cutoff_ns: int) -> None:
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            _, old_vol = self._flow_deque.popleft()
            self._net_flow -= old_vol

    def _flow_is_adverse(self, order) -> bool:
        """Base aggressor-flow-gate logic. Unchanged from base / g3l2."""
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
    # Spread gate (unchanged from g3l2)
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
    # Chop gate (unchanged from g3l2)
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
    # Size-asymmetry gate (unchanged from g3l2)
    # ------------------------------------------------------------------

    def _size_asym_gate_skip(self, order) -> bool:
        """Return True if the contra side massively dominates this side."""
        bid_size = self._latest_bid_size
        ask_size = self._latest_ask_size
        if bid_size is None or ask_size is None:
            return False
        if bid_size <= 0.0 and ask_size <= 0.0:
            return False

        ratio = self._size_asym_ratio

        if order.side == OrderSide.BUY:
            if ask_size >= ratio * bid_size and ask_size > 0.0:
                return True
        else:  # SELL
            if bid_size >= ratio * ask_size and bid_size > 0.0:
                return True

        return False

    # ------------------------------------------------------------------
    # Recent-trade-side flow gate (NEW — fifth orthogonal axis)
    # ------------------------------------------------------------------

    def _prune_recent_window(self, cutoff_ns: int) -> None:
        """Drop entries older than the recent-side window and decrement
        the per-side running counts to keep them O(1)-amortized.
        """
        while self._recent_deque and self._recent_deque[0][0] < cutoff_ns:
            _, old_side = self._recent_deque.popleft()
            if old_side == 1:
                self._recent_buy_count -= 1
            elif old_side == -1:
                self._recent_sell_count -= 1
            # side_code == 0 → no count to decrement.

    def _recent_side_gate_skip(self, order) -> bool:
        """Return True if recent-trade-side dominance is on the CONTRA side.

        Uses the COUNT of trades with informative aggressor side (BUYER or
        SELLER) over a `recent_window_seconds`-long rolling window.
        Defers (returns False) until at least `recent_min_trades` informative
        trades are in the window.

        Skip BUY  if sellers / (buyers + sellers) >= recent_dominance_ratio.
        Skip SELL if buyers  / (buyers + sellers) >= recent_dominance_ratio.

        NO_AGGRESSOR prints are in the deque (so they correctly age out)
        but do not enter the dominance numerator or denominator — only
        informative directional prints count.
        """
        cutoff_ns = order.ts_init - self._recent_window_ns
        self._prune_recent_window(cutoff_ns)

        informative_total = self._recent_buy_count + self._recent_sell_count
        if informative_total < self._recent_min_trades:
            return False

        ratio = self._recent_dominance_ratio

        if order.side == OrderSide.BUY:
            # Contra side = sellers.
            sell_share = self._recent_sell_count / informative_total
            if sell_share >= ratio:
                return True
        else:  # SELL
            # Contra side = buyers.
            buy_share = self._recent_buy_count / informative_total
            if buy_share >= ratio:
                return True

        return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit only if ALL FIVE gates pass."""
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

        # Gate D: size-asymmetry (book-depth axis).
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

        # Gate E: recent-trade-side flow (NEW fifth axis).
        if self._recent_side_gate_skip(order):
            if order.side == OrderSide.BUY:
                self._skipped_recent_buy += 1
            else:
                self._skipped_recent_sell += 1
            self.log.info(
                f"SKIP {order.client_order_id} — recent-trade-side gate "
                f"(buy_ct={self._recent_buy_count}, "
                f"sell_ct={self._recent_sell_count}, side="
                f"{'BUY' if order.side == OrderSide.BUY else 'SELL'})."
            )
            self._position_flat = True
            return

        # All five gates passed — submit.
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
    recent_window_seconds: float = 1.5,
    recent_min_trades: int = 5,
    recent_dominance_ratio: float = 0.70,
) -> AfgIslG4L2Algorithm:
    """Instantiate and return the afg-isl-g4l2 algorithm.

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
        (verbatim from g3l2).
    spread_quantile : float
        Quantile threshold for the spread gate. Default 0.75 (verbatim
        from g3l2).
    min_samples : int
        Minimum spread samples before the spread gate fires. Default 50
        (verbatim from g3l2).
    chop_window_ticks : int
        Rolling window length for the chop ratio, in quote ticks. Default
        30 (verbatim from g3l2).
    chop_neutral : float
        Chop ratio threshold for binary hard-skip. Default 1.5 (verbatim
        from g3l2; gen-3 migration confirmed base-robust across all three
        islands).
    chop_min_ticks : int
        Cold-start guard before the chop gate activates. Default 40
        (verbatim from g3l2).
    chop_eps : float
        Lower bound on displacement (divide-by-zero guard). Default 1e-9.
    chop_max_ratio : float
        Cap on chop_ratio (numerical-stability guard). Default 20.0.
    size_asym_ratio : float
        Top-of-book size-asymmetry threshold. Default 1.5 (verbatim from
        g3l2).
    recent_window_seconds : float
        Rolling window for the recent-trade-side count gate, in seconds.
        Default 1.5 — middle of g4l1's recommended 1-2s band and
        structurally distinct from the base flow gate's 10s window.
    recent_min_trades : int
        Minimum informative (BUYER- or SELLER-aggressor) trades in the
        recent window before the gate may fire. Default 5.
    recent_dominance_ratio : float
        Fraction of informative recent trades that must be on the CONTRA
        side for the gate to skip. Default 0.70 — strict enough to be
        informative without being so strict the gate never fires.
    """
    config = AfgIslG4L2Config(
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
        recent_window_seconds=recent_window_seconds,
        recent_min_trades=recent_min_trades,
        recent_dominance_ratio=recent_dominance_ratio,
    )
    return AfgIslG4L2Algorithm(config=config)
