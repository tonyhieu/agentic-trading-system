"""afg-isl-g4l1 — island-1, generation 4, loop 1.

Adds a **fifth orthogonal SKIP axis** on top of the four-gate stack
frozen in afg-isl-g3l2 (PnL +233.05% vs base — the island-1 best):
**short-horizon mid-price velocity** (signed directional momentum).

For each OPEN order:
  - Gate A (spread,       book-state):       skip OPEN when latest spread > q75.
  - Gate B (chop,         price-PATH):       skip OPEN when chop_ratio > chop_neutral.
  - Gate C (aggressor-flow, trade-pressure): skip OPEN per BASE aggressor-flow-gate.
  - Gate D (size-asym,    book-DEPTH):       skip BUY  when ask_size >= ratio * bid_size
                                              skip SELL when bid_size >= ratio * ask_size
  - Gate E (mid-velocity, price-MOMENTUM, NEW):
                          skip BUY  when (mid_now - mid_lookback)/dt <= -threshold
                          skip SELL when (mid_now - mid_lookback)/dt >=  threshold
  - Submit only if ALL FIVE gates pass.

Why this design (cross-island prior + lineage prior)
----------------------------------------------------
The gen-3 migration explicitly licenses the five-axis frontier on this
specific base:

  `generalizable (1)`: "the gen-2 'three-axis ceiling' hypothesis is
   FALSIFIED on two bases this generation — afg cleanly cleared four
   axes with size-asymmetry as the fourth (+21.59%)."

  `base_specific (2)`: "afg accepts a fourth orthogonal axis cleanly and
   is the right island to probe the five-axis frontier next — the gen-2
   three-gate stack survived size-asymmetry addition without regression
   and operates on a base whose surviving population has the most
   remaining headroom across the three islands."

g3l2's `summary_out.next` proposed two candidate fifth axes — recent-
trade-side flow and price-velocity. Per the operator's directive for
g4l1, we pick the **lower-leverage** option (price-velocity), which is
also the more **mechanistically distant** option. Recent-trade-side flow
stays in the trade-pressure family the base already gates on, raising
the risk of redundancy that island-2 g2l2 and g3l1 documented for flow
on a flow-pre-filtered population. Mid-velocity is a directional price
MOMENTUM signal that none of the existing four gates carries:

  - Spread (Gate A)   — quote-DISTANCE (book-state level)
  - Chop  (Gate B)    — path/displacement RATIO, scale-INVARIANT, sign-
                         INVARIANT (whipsaw irrespective of direction)
  - Flow  (Gate C)    — signed AGGRESSOR-volume (order pressure, NOT
                         mid drift; a trade can hit aggressively without
                         moving the mid, and the mid can drift on quote
                         updates alone with no trades)
  - Size-asym (Gate D) — book-DEPTH at top-of-book (static liquidity
                         picture, not direction)
  - Mid-velocity (E)  — signed mid drift rate (directional MOMENTUM,
                         NEW)

Mechanism hypothesis: even when net aggressor flow over 10s is below
threshold, the LAST few seconds of mid drift may already encode a
persistent adverse move into our order's arrival. The base flow gate
covers cumulative trade-side pressure; mid-velocity covers the
realized-price tape directly. They can disagree: quote-side passive
withdrawal (mid moves on quote updates with no trades) and brief
unidirectional aggressor bursts shorter than the 10s flow window both
register as adverse momentum but NOT as adverse flow.

Parameter choices (deliberately conservative for a first attempt)
-----------------------------------------------------------------
- velocity_window_seconds = 5.0
    Half the flow window so the two are not duplicating the same time
    horizon. Short enough to capture "what just happened" rather than
    aggregate pressure (already captured by flow at 10s).
- velocity_min_ticks = 5
    Warm-up guard. Need enough quote samples for a meaningful drift
    estimate. Same family as min_samples=50 for spread and
    chop_min_ticks=40 for chop, but cheap because mid-velocity uses a
    two-point estimate (mid_now vs mid at window-start).
- velocity_threshold = 0.50
    In $ per second. MES tick = 0.25, so 0.5 $/s ≈ 2 ticks/s — a clearly
    directional drift, not noise, but not extreme. Calibrated by analogy
    to the chop and flow operating points which are both "modest
    thresholds in the body of the distribution, not tail-only triggers"
    and to the conservative-first-attempt directive. If the gate fires
    rarely on instrumentation, future loops can loosen toward 0.30; if
    it fires too aggressively (trade_count drop > 10%), tighten toward
    1.0.

Falsification (operator-stated)
-------------------------------
- Confirmation: PnL > g3l2 (4182.00) AND drawdown does not widen AND
  trade_count drop <= 10% vs g3l2.
- Null result: metrics indistinguishable from g3l2 AND counters show
  the velocity gate fires < 0.5% of OPEN evaluations OR co-skips with
  another gate at near-100% rate.
- Regression: PnL < g3l2 by > 2% OR trade_count drops > 10% — verdict
  is a hard four-axis ceiling on this base, and g4l2 should pivot to
  multi-axis operating-point retuning rather than further axis stacking.

Instrumentation (gen-1 migration mandate)
-----------------------------------------
Per-gate counters preserved from g3l2 and EXTENDED with the new
velocity gate, side-specific:

  - _evaluated_count, _submitted_count
  - _skipped_spread, _skipped_chop
  - _skipped_flow_buy, _skipped_flow_sell
  - _skipped_size_asym_buy, _skipped_size_asym_sell
  - _skipped_velocity_buy, _skipped_velocity_sell   (NEW)

Counters emitted on `on_stop` so a null result is diagnosable.

Algorithm
---------
Maintain five independent rolling structures (four from g3l2, plus a
short rolling mid-deque for velocity):
  - Aggressor-flow deque (from on_trade_tick): unchanged from base.
  - Spread deque        (from on_quote_tick):  unchanged from g2l1 / island-0 g1l1.
  - Chop window         (from on_quote_tick):  unchanged from g2l2 / vrs-isl-g1l1.
  - Latest bid/ask sizes (from on_quote_tick): unchanged from g3l2.
  - Velocity mid-deque  (from on_quote_tick):  NEW. Stores (ts_ns, mid)
    samples; prunes anything older than `velocity_window_seconds` before
    each gate evaluation; reads (mid_now, mid_at_window_start) for a
    two-point drift estimate.

Reduce-only orders always submit (intraday_flat). Forced re-entry after
a skip is unconditional (anti-cascade contract). Order quantity is
never modified.

No look-ahead: all rolling structures are fed by Nautilus callbacks in
replay chronological order; velocity uses only quotes observed at or
before order arrival.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class AfgIslG4L1Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for afg-isl-g4l1: g3l2 + mid-velocity (fifth axis).

    All g3l2 parameters preserved verbatim. New parameters:

    velocity_window_seconds : float
        Rolling window for the mid-velocity two-point estimate, in
        seconds. Default 5.0 — half the flow window for orthogonality;
        captures short-horizon directional drift.
    velocity_threshold : float
        Adverse mid-velocity magnitude, in $ per second. Skip BUY when
        `(mid_now - mid_lookback) / dt <= -velocity_threshold`; skip
        SELL when `(mid_now - mid_lookback) / dt >= velocity_threshold`.
        Default 0.50 ($/s) ≈ 2 MES ticks per second.
    velocity_min_ticks : int
        Minimum quote samples required in the velocity window before the
        gate may fire. Default 5 — short warm-up; mid-velocity is a
        two-point estimate, not a distributional one.
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
    velocity_window_seconds: float = 5.0
    velocity_threshold: float = 0.50
    velocity_min_ticks: int = 5


class AfgIslG4L1Algorithm(ExecAlgorithm):
    """g3l2 (base flow + spread + chop + size-asym) + mid-velocity (fifth axis).

    Opening orders (is_reduce_only == False):
      - Forced re-entry after a skip is unconditional (anti-cascade).
      - Gate A (spread, book-state):    skip OPEN when latest spread > q75.
      - Gate B (chop, price-path):      skip OPEN when chop_ratio > chop_neutral.
      - Gate C (aggressor-flow, base):  BUY  skip iff net_flow <= -flow_threshold
                                        SELL skip iff net_flow >=  flow_threshold
      - Gate D (size-asym):             BUY  skip iff ask_size >= ratio * bid_size
                                        SELL skip iff bid_size >= ratio * ask_size
      - Gate E (mid-velocity, NEW):     BUY  skip iff drift_per_sec <= -velocity_threshold
                                        SELL skip iff drift_per_sec >=  velocity_threshold
      - Submit only if ALL FIVE gates pass.
      - After any skip: `_position_flat = True` (next open unconditional).

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    Quantity invariant: never modify `order.quantity`.

    Instrumentation: per-gate skip counters and an evaluated-order
    counter are emitted on `on_stop` so null-result diagnosis is
    possible.
    """

    def __init__(self, config: AfgIslG4L1Config) -> None:
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

        # ---- Mid-velocity-gate state (NEW fifth axis) ----
        # Rolling deque of (ts_event_ns, mid_price). Prune anything older
        # than `velocity_window_seconds` before each gate evaluation;
        # gate compares mid_now to mid at window-start (two-point drift).
        self._velocity_window_ns: int = int(
            config.velocity_window_seconds * 1_000_000_000
        )
        self._velocity_threshold: float = float(config.velocity_threshold)
        self._velocity_min_ticks: int = int(config.velocity_min_ticks)
        self._velocity_deque: deque[tuple[int, float]] = deque()

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
        self._skipped_velocity_buy: int = 0
        self._skipped_velocity_sell: int = 0
        self._submitted_count: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            "AfgIslG4L1Algorithm started "
            f"(flow_window={self._window_ns / 1e9:.1f}s, "
            f"flow_threshold={self._flow_threshold:.2f}, "
            f"spread_window={self._spread_window_ns / 1e9:.1f}s, "
            f"spread_quantile={self._spread_quantile:.2f}, "
            f"min_samples={self._min_samples}, "
            f"chop_window_ticks={self._chop_window_ticks}, "
            f"chop_neutral={self._chop_neutral:.2f}, "
            f"chop_min_ticks={self._chop_min_ticks}, "
            f"size_asym_ratio={self._size_asym_ratio:.2f}, "
            f"velocity_window={self._velocity_window_ns / 1e9:.1f}s, "
            f"velocity_threshold={self._velocity_threshold:.3f} $/s, "
            f"velocity_min_ticks={self._velocity_min_ticks})."
        )

    def on_stop(self) -> None:
        """Emit per-gate instrumentation counters for null-result diagnosis."""
        self.log.info(
            "AfgIslG4L1Algorithm gate counters: "
            f"evaluated={self._evaluated_count}, "
            f"submitted={self._submitted_count}, "
            f"skip_spread={self._skipped_spread}, "
            f"skip_chop={self._skipped_chop}, "
            f"skip_flow_buy={self._skipped_flow_buy}, "
            f"skip_flow_sell={self._skipped_flow_sell}, "
            f"skip_size_asym_buy={self._skipped_size_asym_buy}, "
            f"skip_size_asym_sell={self._skipped_size_asym_sell}, "
            f"skip_velocity_buy={self._skipped_velocity_buy}, "
            f"skip_velocity_sell={self._skipped_velocity_sell}."
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
        self._velocity_deque.clear()
        self._position_flat = True
        self._subscribed.clear()
        self._evaluated_count = 0
        self._skipped_spread = 0
        self._skipped_chop = 0
        self._skipped_flow_buy = 0
        self._skipped_flow_sell = 0
        self._skipped_size_asym_buy = 0
        self._skipped_size_asym_sell = 0
        self._skipped_velocity_buy = 0
        self._skipped_velocity_sell = 0
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
            signed_vol = 0.0

        self._flow_deque.append((tick.ts_event, signed_vol))
        self._net_flow += signed_vol

    # ------------------------------------------------------------------
    # Quote-tick handler — feeds spread deque, chop window, latest top-
    # of-book sizes, AND the velocity mid-deque (fifth-gate state).
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        """Update spread/chop/size/velocity rolling structures."""
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

        # ---- Chop window (price-path axis, verbatim from g3l2) ----
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

        # ---- Latest top-of-book sizes (book-depth, verbatim from g3l2) ----
        self._latest_bid_size = bid_size
        self._latest_ask_size = ask_size

        # ---- Velocity mid-deque (NEW fifth-gate state) ----
        # Append (ts_event_ns, mid). Pruning is deferred to gate eval so
        # we always use the cutoff relative to order arrival, not quote
        # arrival.
        self._velocity_deque.append((tick.ts_event, mid))

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
    # Mid-velocity gate (NEW — fifth orthogonal axis)
    # ------------------------------------------------------------------

    def _prune_velocity_window(self, cutoff_ns: int) -> None:
        while self._velocity_deque and self._velocity_deque[0][0] < cutoff_ns:
            self._velocity_deque.popleft()

    def _velocity_gate_skip(self, order) -> bool:
        """Return True if short-horizon mid drift is adverse to this side.

        Two-point estimate: drift_per_sec = (mid_now - mid_lookback) /
        (ts_now - ts_lookback). `mid_lookback` is the OLDEST mid still
        inside the velocity window after pruning anything older than
        `velocity_window_seconds`; `mid_now` is the NEWEST mid.

        BUY OPEN skipped when drift_per_sec <= -velocity_threshold
        (mid has been falling — adverse for a buyer who pays at top).
        SELL OPEN skipped when drift_per_sec >= velocity_threshold
        (mid has been rising — adverse for a seller).

        Warm-up: defers to remaining gates (returns False) until at
        least `velocity_min_ticks` quotes lie inside the window AND the
        elapsed time spans a non-zero interval.
        """
        cutoff_ns = order.ts_init - self._velocity_window_ns
        self._prune_velocity_window(cutoff_ns)

        n = len(self._velocity_deque)
        if n < self._velocity_min_ticks:
            return False

        ts_lookback, mid_lookback = self._velocity_deque[0]
        ts_now, mid_now = self._velocity_deque[-1]

        dt_ns = ts_now - ts_lookback
        if dt_ns <= 0:
            return False

        dt_sec = dt_ns / 1_000_000_000.0
        drift_per_sec = (mid_now - mid_lookback) / dt_sec

        threshold = self._velocity_threshold

        if order.side == OrderSide.BUY:
            # Adverse for a buyer: mid has been falling.
            if drift_per_sec <= -threshold:
                return True
        else:  # SELL
            # Adverse for a seller: mid has been rising.
            if drift_per_sec >= threshold:
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

        # Gate E: mid-velocity (price-momentum axis — NEW fifth axis).
        if self._velocity_gate_skip(order):
            if order.side == OrderSide.BUY:
                self._skipped_velocity_buy += 1
            else:
                self._skipped_velocity_sell += 1
            self.log.info(
                f"SKIP {order.client_order_id} — mid-velocity gate "
                f"(side={'BUY' if order.side == OrderSide.BUY else 'SELL'})."
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
    velocity_window_seconds: float = 5.0,
    velocity_threshold: float = 0.50,
    velocity_min_ticks: int = 5,
) -> AfgIslG4L1Algorithm:
    """Instantiate and return the afg-isl-g4l1 algorithm.

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
        (verbatim from g3l2 / island-0 g1l1).
    spread_quantile : float
        Quantile threshold for the spread gate. Default 0.75 (verbatim
        from g3l2 / island-0 g1l1).
    min_samples : int
        Minimum spread samples before the spread gate fires. Default 50.
    chop_window_ticks : int
        Rolling window length for the chop ratio, in quote ticks. Default
        30 (verbatim from g3l2 / vrs-isl-g1l1).
    chop_neutral : float
        Chop ratio threshold for binary hard-skip. Default 1.5 (base-
        robust per gen-3 migration; g3l1's 1.5 → 1.7 sweep was null).
    chop_min_ticks : int
        Cold-start guard before the chop gate activates. Default 40.
    chop_eps : float
        Lower bound on displacement (divide-by-zero guard). Default 1e-9.
    chop_max_ratio : float
        Cap on chop_ratio (numerical-stability guard). Default 20.0.
    size_asym_ratio : float
        Top-of-book size-asymmetry threshold. Skip BUY when
        `ask_size >= size_asym_ratio * bid_size`; skip SELL when
        `bid_size >= size_asym_ratio * ask_size`. Default 1.5 (verbatim
        from g3l2).
    velocity_window_seconds : float
        Rolling window for the mid-velocity two-point estimate, in
        seconds. Default 5.0 — half the flow window for orthogonality.
    velocity_threshold : float
        Adverse mid-velocity magnitude, in $ per second. Default 0.50 —
        roughly 2 MES ticks per second; conservative first attempt.
    velocity_min_ticks : int
        Minimum quote samples in the velocity window before the gate may
        fire. Default 5.
    """
    config = AfgIslG4L1Config(
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
        velocity_window_seconds=velocity_window_seconds,
        velocity_threshold=velocity_threshold,
        velocity_min_ticks=velocity_min_ticks,
    )
    return AfgIslG4L1Algorithm(config=config)
