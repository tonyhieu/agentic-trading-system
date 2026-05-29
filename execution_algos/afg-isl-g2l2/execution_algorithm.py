"""afg-isl-g2l2 — island-1, generation 2, loop 2.

g2l1 (base aggressor-flow-gate UNMODIFIED + rolling-spread-p75 OPEN-gate
stacked on top) with a THIRD orthogonal SKIP gate stacked on top: the
choppiness-ratio gate ported verbatim from island-2 g1l1 (vrs-isl-g1l1,
+34.13% PnL on vol-regime-sizer). Composition rule: skip the order if ANY
of the three gates votes SKIP; submit only if ALL THREE pass.

Why this design
---------------
g2l1's `summary_out.next` explicitly named this as the highest-leverage
next direction:

  "Stack a THIRD orthogonal skip axis in g2l2: the choppiness-ratio gate
  (island-2 g1l1's winner, +34.13% on vol-regime-sizer). Spread
  (book-state) and flow (trade-pressure) are now confirmed orthogonal on
  this base; adding chop-ratio (price-path) covers the three structurally-
  distinct adverse regimes the migration identified. Calibration: keep
  all g2l1 parameters fixed (no retuning); use island-2 g1l1's known-good
  chop window and threshold verbatim for clean cross-island transfer.
  Do NOT retune the base flow gate; composition not modification."

The gen-1 migration's `generalizable` block already identified the same
direction across all three islands:

  "Skip-based gating on adverse-microstructure regimes generalizes across
  base algos: spread-quantile and choppiness-ratio both worked on
  different bases and target near-orthogonal axes (book-state vs
  price-path), so a composed spread+chop+(third axis) stack is the
  highest-leverage generation-2 direction across all islands."

g2l1 already proved orthogonality of spread + flow on this base
(+70.29% PnL, drawdown tightened, both moved together with IS bps).
This loop adds the third axis.

Binary vs probabilistic chop gate
---------------------------------
Island-2 g1l1's chop gate is a *probabilistic sizer*:
    p = max(min_prob, exp(-sensitivity * max(0, chop_ratio - chop_neutral)))
i.e. submit with probability p, skip with probability 1-p.

For clean composition with g2l1's two binary AND-skip gates, this loop
converts the chop axis to a **binary hard-skip** at the same neutral
threshold (`chop_neutral = 1.5`, verbatim from island-2 g1l1):

    SKIP iff chop_ratio > chop_neutral (and chop window fully populated).

Rationale:
1. Composition with two existing binary gates is crisper when all three
   gates share the same AND-skip semantics.
2. At chop_ratio just above the neutral threshold, island-2 g1l1's
   probabilistic gate already skips with non-trivial probability; for
   pure whipsaw (chop_ratio → ∞) it skips ~95% of orders. The binary
   form is uniformly more conservative — consistent with the migration's
   "restriction not relaxation" finding for this island.
3. The migration's `generalizable` recommendation is to use known-good
   *axes* (book-state, price-path) and *thresholds* across bases — not
   necessarily the same submission mechanic. Threshold 1.5 and window 30
   ticks are preserved verbatim; only the submit-rule above the threshold
   is changed from probabilistic-skip to hard-skip.

Algorithm
---------
Maintain three independent rolling structures:
  - Aggressor-flow deque (from on_trade_tick): same as base aggressor-
    flow-gate, same as g2l1.
  - Spread deque (from on_quote_tick): same as g2l1 (verbatim from
    island-0 g1l1).
  - Chop window (from on_quote_tick): rolling mids deque (maxlen
    `chop_window_ticks + 1`) + abs-deltas deque (maxlen
    `chop_window_ticks`) + incremental `_path_sum`. Verbatim port from
    vrs-isl-g1l1.

For each OPEN order (is_reduce_only == False):
  1. Reduce-only orders always submit (intraday_flat compliance —
     handled at the top of on_order).
  2. Forced re-entry after a skip is unconditional (anti-cascade —
     unchanged contract).
  3. **Gate A — spread** (book-state axis, from island-0 g1l1):
       If the spread deque holds at least `min_samples` samples and the
       latest spread strictly exceeds the rolling `spread_quantile` →
       SKIP.
  4. **Gate B — chop** (price-path axis, from island-2 g1l1):
       If at least `chop_min_ticks` quote ticks observed and the chop
       window is full, compute
         chop_ratio = path_sum / max(displacement, chop_eps),
       capped at chop_max_ratio. If chop_ratio > chop_neutral → SKIP.
  5. **Gate C — aggressor-flow** (trade-pressure axis, BASE unmodified):
       BUY  skip iff net_flow <= -flow_threshold
       SELL skip iff net_flow >=  flow_threshold
  6. Submit only if ALL THREE gates pass. After ANY skip,
     `_position_flat = True` (next open unconditional).

Order quantity is never modified — quantity invariant preserved.

No look-ahead: all three deques/windows are fed by Nautilus callbacks in
replay chronological order; pruning of time-windowed structures uses
`order.ts_init` as the cutoff anchor. The chop window is tick-count-based
(not time-based), matching island-2 g1l1's semantics.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class AfgIslG2L2Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for afg-isl-g2l2: g2l1 + chop-gate (third orthogonal axis).

    Parameters
    ----------
    window_seconds : float
        Aggressor-flow rolling window, in seconds. Default 10.0 — base.
    flow_threshold : float
        Aggressor-flow adverse threshold (contracts). Default 2.0 — base.
    spread_window_seconds : float
        Rolling window for spread samples, in seconds. Default 60.0 —
        verbatim from g2l1 (and from island-0 g1l1).
    spread_quantile : float
        Quantile threshold for the spread gate (0 < q < 1). Skip OPEN when
        latest spread strictly exceeds this quantile of the rolling window.
        Default 0.75 — verbatim from g2l1.
    min_samples : int
        Minimum spread samples required before the spread gate fires.
        Default 50 — verbatim from g2l1.
    chop_window_ticks : int
        Number of recent quote ticks for the chop ratio window. Default
        30 — verbatim from island-2 g1l1.
    chop_neutral : float
        Chop ratio at or below which the chop gate does NOT skip; above
        it, the gate skips (binary hard-skip). Default 1.5 — verbatim from
        island-2 g1l1 (the threshold at which its probabilistic gate
        starts skipping).
    chop_min_ticks : int
        Cold-start guard: chop gate is dormant until this many quote ticks
        have been observed. Default 40 — verbatim from island-2 g1l1.
    chop_eps : float
        Lower bound on displacement when computing chop_ratio (divide-by-
        zero guard on perfectly mean-reverting windows). Default 1e-9 —
        verbatim from island-2 g1l1.
    chop_max_ratio : float
        Cap on chop_ratio (numerical-stability guard against extreme
        outliers). Default 20.0 — verbatim from island-2 g1l1.
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


class AfgIslG2L2Algorithm(ExecAlgorithm):
    """g2l1 (base flow + spread) + chop-ratio gate as a third orthogonal axis.

    Opening orders (is_reduce_only == False):
      - Forced re-entry after a skip is unconditional (anti-cascade).
      - Gate A (spread, book-state axis from island-0 g1l1):
          Skip OPEN when the latest spread > q75 of the rolling spread
          distribution (warm-up no-op until min_samples are present).
      - Gate B (chop, price-path axis from island-2 g1l1):
          Skip OPEN when chop_ratio > chop_neutral and the chop window
          is fully populated (warm-up no-op below chop_min_ticks).
      - Gate C (aggressor-flow, base unchanged):
          BUY  skip iff net_flow <= -flow_threshold
          SELL skip iff net_flow >=  flow_threshold
      - Submit only if ALL THREE gates pass.
      - After any skip: `_position_flat = True` (next open unconditional).

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    Quantity invariant: never modify `order.quantity`.
    """

    def __init__(self, config: AfgIslG2L2Config) -> None:
        super().__init__(config=config)

        # ---- Aggressor-flow state (base, unmodified — mirrors g2l1) ----
        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._flow_threshold: float = float(config.flow_threshold)
        # Deque of (ts_event_ns, signed_vol):
        # signed_vol = +size (BUYER), -size (SELLER), 0 (NO_AGGRESSOR).
        self._flow_deque: deque[tuple[int, float]] = deque()
        # Running sum of signed volume in the flow deque (O(1) updates).
        self._net_flow: float = 0.0

        # ---- Spread-gate state (unchanged from g2l1) ----
        self._spread_window_ns: int = int(
            config.spread_window_seconds * 1_000_000_000
        )
        self._spread_quantile: float = float(config.spread_quantile)
        self._min_samples: int = int(config.min_samples)
        # Deque of (ts_event_ns, spread) in raw price units.
        self._spread_deque: deque[tuple[int, float]] = deque()
        # Most recent observed spread (the comparison point for the gate).
        self._latest_spread: float | None = None

        # ---- Chop-gate state (verbatim port from vrs-isl-g1l1) ----
        self._chop_window_ticks: int = int(config.chop_window_ticks)
        self._chop_neutral: float = float(config.chop_neutral)
        self._chop_min_ticks: int = int(config.chop_min_ticks)
        self._chop_eps: float = float(config.chop_eps)
        self._chop_max_ratio: float = float(config.chop_max_ratio)
        # `_mids` keeps the last (chop_window_ticks + 1) mid prices to read
        # both the current mid (head) and the mid chop_window_ticks ago
        # (tail) for the displacement calculation.
        self._mids: deque[float] = deque(maxlen=self._chop_window_ticks + 1)
        # `_abs_deltas` keeps the last chop_window_ticks per-tick
        # |delta_mid| values; `_path_sum` is maintained incrementally.
        self._abs_deltas: deque[float] = deque(maxlen=self._chop_window_ticks)
        self._path_sum: float = 0.0
        self._tick_count: int = 0

        # ---- Anti-cascade contract (unchanged) ----
        self._position_flat: bool = True

        # ---- Subscription tracking ----
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            "AfgIslG2L2Algorithm started "
            f"(flow_window={self._window_ns / 1e9:.1f}s, "
            f"flow_threshold={self._flow_threshold:.2f}, "
            f"spread_window={self._spread_window_ns / 1e9:.1f}s, "
            f"spread_quantile={self._spread_quantile:.2f}, "
            f"min_samples={self._min_samples}, "
            f"chop_window_ticks={self._chop_window_ticks}, "
            f"chop_neutral={self._chop_neutral:.2f}, "
            f"chop_min_ticks={self._chop_min_ticks})."
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
        self._position_flat = True
        self._subscribed.clear()

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
    # Quote-tick handler — feeds BOTH the spread deque AND the chop window
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        """Update spread deque and chop window from each quote tick."""
        try:
            bid = float(str(tick.bid_price))
            ask = float(str(tick.ask_price))
        except Exception:
            return

        # ---- Spread deque (book-state axis) ----
        spread = ask - bid
        if spread >= 0.0:
            self._spread_deque.append((tick.ts_event, spread))
            self._latest_spread = spread
        # If spread is negative (crossed book), skip the sample defensively;
        # also skip feeding the chop window for this tick — a malformed
        # quote shouldn't pollute either rolling structure.
        else:
            return

        # ---- Chop window (price-path axis, verbatim from vrs-isl-g1l1) ----
        mid = (bid + ask) / 2.0
        if self._mids:
            prev_mid = self._mids[-1]
            abs_delta = abs(mid - prev_mid)

            # Incremental path sum: add new |delta|; subtract the one
            # falling off the back of the window, if any.
            if len(self._abs_deltas) == self._chop_window_ticks:
                self._path_sum -= self._abs_deltas[0]
            self._abs_deltas.append(abs_delta)
            self._path_sum += abs_delta

        self._mids.append(mid)
        self._tick_count += 1

    # ------------------------------------------------------------------
    # Flow gate (base, unmodified)
    # ------------------------------------------------------------------

    def _prune_flow_window(self, cutoff_ns: int) -> None:
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            _, old_vol = self._flow_deque.popleft()
            self._net_flow -= old_vol

    def _flow_is_adverse(self, order) -> bool:
        """Base aggressor-flow-gate logic. Unchanged from base / g2l1."""
        cutoff_ns = order.ts_init - self._window_ns
        self._prune_flow_window(cutoff_ns)

        if not self._flow_deque:
            # No trade data in window — do not gate (warm-up / thin market).
            return False

        net = self._net_flow

        if order.side == OrderSide.BUY:
            if net <= -self._flow_threshold:
                self.log.debug(
                    f"FLOW SKIP BUY {order.client_order_id} — "
                    f"net_flow={net:.2f} <= -threshold={-self._flow_threshold:.2f}."
                )
                return True
        else:  # SELL
            if net >= self._flow_threshold:
                self.log.debug(
                    f"FLOW SKIP SELL {order.client_order_id} — "
                    f"net_flow={net:.2f} >= threshold={self._flow_threshold:.2f}."
                )
                return True

        return False

    # ------------------------------------------------------------------
    # Spread gate (unchanged from g2l1 — cross-island import island-0 g1l1)
    # ------------------------------------------------------------------

    def _prune_spread_window(self, cutoff_ns: int) -> None:
        while self._spread_deque and self._spread_deque[0][0] < cutoff_ns:
            self._spread_deque.popleft()

    def _spread_gate_skip(self, order) -> bool:
        """Return True if the latest spread sits above the rolling quantile.

        Warm-up branch: if the deque holds fewer than `min_samples`
        samples, return False (do not gate on the spread axis).
        """
        cutoff_ns = order.ts_init - self._spread_window_ns
        self._prune_spread_window(cutoff_ns)

        n = len(self._spread_deque)
        if n < self._min_samples or self._latest_spread is None:
            return False  # warm-up: defer to remaining gates

        # Quantile via sorted copy. Deque size is bounded by samples-per-
        # second × window_seconds — for MES on a 60s window this is low
        # thousands at most, so sorted() per order event is acceptable.
        sorted_spreads = sorted(s for _, s in self._spread_deque)
        idx_f = self._spread_quantile * (n - 1)
        lo = int(idx_f)
        hi = min(lo + 1, n - 1)
        frac = idx_f - lo
        threshold = sorted_spreads[lo] * (1.0 - frac) + sorted_spreads[hi] * frac

        if self._latest_spread > threshold:
            self.log.debug(
                f"SPREAD SKIP {order.client_order_id} — "
                f"latest_spread={self._latest_spread:.5f} > "
                f"q{self._spread_quantile:.2f}={threshold:.5f} (n={n})."
            )
            return True
        return False

    # ------------------------------------------------------------------
    # Chop gate (third orthogonal axis — verbatim port from vrs-isl-g1l1,
    # converted to a binary hard-skip at chop_neutral)
    # ------------------------------------------------------------------

    def _chop_gate_skip(self, order) -> bool:
        """Return True if chop_ratio exceeds chop_neutral.

        Warm-up branches (return False — do not gate):
          - Fewer than `chop_min_ticks` quote ticks observed.
          - Chop window not yet populated (this can happen if quote ticks
            with crossed-book / parse errors were dropped above, leaving
            the window count below the increment expected from
            _tick_count). Defensive parity with vrs-isl-g1l1's check.
        """
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
            self.log.debug(
                f"CHOP SKIP {order.client_order_id} — "
                f"chop_ratio={chop_ratio:.4f} > "
                f"chop_neutral={self._chop_neutral:.4f} "
                f"(path={path_length:.8f} disp={displacement:.8f})."
            )
            return True
        return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit only if ALL three gates pass.

        Gate order: spread → chop → flow. The order of evaluation does not
        affect the binary composition result (the rule is "skip if ANY
        gate votes skip"); it only determines which gate's log line fires
        first on a co-skip event.
        """
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

        # Gate A: spread (book-state axis, from island-0 g1l1).
        if self._spread_gate_skip(order):
            self.log.info(
                f"SKIP {order.client_order_id} — spread gate "
                f"(latest={self._latest_spread}, side="
                f"{'BUY' if order.side == OrderSide.BUY else 'SELL'})."
            )
            self._position_flat = True
            return

        # Gate B: chop (price-path axis, from island-2 g1l1 — third axis).
        if self._chop_gate_skip(order):
            self.log.info(
                f"SKIP {order.client_order_id} — chop gate "
                f"(tick_count={self._tick_count}, side="
                f"{'BUY' if order.side == OrderSide.BUY else 'SELL'})."
            )
            self._position_flat = True
            return

        # Gate C: aggressor-flow (trade-pressure axis, BASE unmodified).
        if self._flow_is_adverse(order):
            self.log.info(
                f"SKIP {order.client_order_id} — adverse aggressor flow "
                f"(net_flow={self._net_flow:.2f}, side="
                f"{'BUY' if order.side == OrderSide.BUY else 'SELL'})."
            )
            self._position_flat = True
            return

        # All three gates passed — submit.
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
) -> AfgIslG2L2Algorithm:
    """Instantiate and return the afg-isl-g2l2 algorithm.

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
        (verbatim from g2l1 / island-0 g1l1).
    spread_quantile : float
        Quantile threshold for the spread gate. Default 0.75 (verbatim from
        g2l1 / island-0 g1l1).
    min_samples : int
        Minimum spread samples before the spread gate fires. Default 50
        (verbatim from g2l1).
    chop_window_ticks : int
        Rolling window length for the chop ratio, in quote ticks. Default
        30 (verbatim from vrs-isl-g1l1).
    chop_neutral : float
        Chop ratio threshold for binary hard-skip. Default 1.5 (verbatim
        from vrs-isl-g1l1).
    chop_min_ticks : int
        Cold-start guard before the chop gate activates. Default 40
        (verbatim from vrs-isl-g1l1).
    chop_eps : float
        Lower bound on displacement (divide-by-zero guard). Default 1e-9.
    chop_max_ratio : float
        Cap on chop_ratio (numerical-stability guard). Default 20.0.
    """
    config = AfgIslG2L2Config(
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
    )
    return AfgIslG2L2Algorithm(config=config)
