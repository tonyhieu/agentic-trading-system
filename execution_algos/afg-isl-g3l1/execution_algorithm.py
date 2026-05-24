"""afg-isl-g3l1 — island-1, generation 3, loop 1.

Calibration variant of afg-isl-g2l2 (the g2 winner, +173.95% vs base): the
chop gate's `chop_neutral` is raised from 1.5 → 1.7. All other parameters
and the three-axis composition (spread + chop + flow, AND-skip binaries on
an unmodified base aggressor-flow gate) are preserved verbatim from g2l2.

Why this change
---------------
g2l2's `summary_out.next` explicitly named two calibration directions for
g3l1:

  (a) Probabilistic-vs-binary form of the chop gate (island-2 g1l1's
      original form vs g2l2's binary hard-skip at the same neutral).
  (b) Threshold sweep around chop_neutral (1.3, 1.5, 1.7, 2.0) on this
      base — the optimum is unlikely to be identical to vol-regime-sizer's
      optimum because the base filter distributions differ.

This loop chooses (b) — a threshold retune at 1.7 — because:

1. Direction (a) changes BOTH the gate shape AND its firing rate at once,
   confounding the calibration. Direction (b) holds the mechanism and
   composition semantics constant (binary AND-skip with the two existing
   binary gates) and varies only the operating point — exactly what the
   gen-2 migration's `generalizable` finding (4) prescribes:

     "When porting a gate, port the MECHANISM and the COMPOSITION
      SEMANTICS but RETUNE the operating point against the new base's
      pre-filter population — a parameter sweep around the ported value
      is cheaper than discovering the misfire after a full backtest."

2. The gen-2 migration's `base_specific` insight (1) is the dominant
   cross-island lesson this loop is testing: island-0 g2l2 ported vrs's
   `chop_neutral = 1.5` verbatim onto position-tier-gate's spread+cap
   surviving population and regressed -11.46% because 1.5 cut into the
   body of that population's distribution rather than its tail. Island-1
   g2l2 also used 1.5 verbatim, but on a *different* surviving population
   (afg base + spread). It still beat — but whether 1.5 is the optimum,
   or merely a workable value that ported well by accident, is unknown.

3. Why raise to 1.7 rather than lower to 1.3:
   - g2l2 trade_count was -6.60% vs base (well inside the -15%
     over-restrictive falsification line). Lowering chop_neutral to 1.3
     would tighten further toward that line, and any PnL loss would be
     ambiguous between "1.5 was optimal" and "we already overshot".
   - g2l2's surviving population is filtered by spread (book-state) and
     flow (trade-pressure) BEFORE chop is evaluated; both of those
     correlate with wide-spread chop bursts, so the chop_ratio
     distribution on this pre-filtered population is *narrower / less
     choppy* than vrs's population (vrs only had chop, no pre-filter).
     The fixed-1.5 threshold therefore likely sits closer to the body of
     this pre-filtered distribution than it did on vrs — the
     base-specific retune direction is to raise it toward the tail.
   - Raising the threshold admits more "near-choppy" trades that may be
     positive-EV on this pre-filtered population — the symmetric retune
     of what island-0 g2l2 *should* have done.

Falsification
-------------
- If pnl decreases vs g2l2 AND trade_count rises (chop fires less, gate
  becomes more lenient) → the admitted "near-choppy" trades are
  net-negative-EV → 1.5 is at or below the true optimum on this base, and
  g3l2 should try 1.3 instead (or revert to the probabilistic form).
- If pnl increases vs g2l2 with trade_count rising modestly → calibration
  retune confirms the gen-2 migration's `base_specific` directive that
  thresholds tuned on one base must be retuned per-base, and the optimum
  on this composed stack sits at or above 1.7.
- If pnl is flat (±2%) and trade_count moves <1% → the chop gate at the
  new threshold is firing on near-zero population (the distribution body
  is well below 1.5 already), in which case the chop axis is approaching
  saturation on this base and g3l2 should pivot to either the
  probabilistic form (axis (a)) or a different fourth axis.

What is NOT changed (composition-preservation, per gen-2 `generalizable`
finding (1) "ADD orthogonal SKIP axes ON TOP of an unmodified base; never
modify the base; never copy parameters across base contexts unretuned"):

- Base aggressor-flow gate parameters unchanged (window_seconds=10.0,
  flow_threshold=2.0).
- Spread gate unchanged (spread_window_seconds=60.0, spread_quantile=0.75,
  min_samples=50).
- Chop window unchanged (chop_window_ticks=30, chop_min_ticks=40).
- Chop gate semantics unchanged (binary hard-skip; AND-skip composition
  with spread and flow).
- Gate evaluation order unchanged (spread → chop → flow); the result is
  invariant under reordering for binary AND-skip composition.
- Quantity invariant preserved — never modify `order.quantity`.
- Anti-cascade contract preserved — `_position_flat = True` after any
  skip; next OPEN is unconditional.
- Reduce-only orders submit unconditionally — intraday_flat compliance.

Algorithm structure
-------------------
Verbatim from afg-isl-g2l2 except `chop_neutral` default is 1.7 (was 1.5).
The configurable parameter remains on the config; the factory's default
encodes the chosen calibration point.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class AfgIslG3L1Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for afg-isl-g3l1: g2l2 with `chop_neutral` retuned 1.5 → 1.7.

    Parameters
    ----------
    window_seconds : float
        Aggressor-flow rolling window, in seconds. Default 10.0 — base.
    flow_threshold : float
        Aggressor-flow adverse threshold (contracts). Default 2.0 — base.
    spread_window_seconds : float
        Rolling window for spread samples, in seconds. Default 60.0 —
        verbatim from g2l2 (and from island-0 g1l1).
    spread_quantile : float
        Quantile threshold for the spread gate (0 < q < 1). Skip OPEN when
        latest spread strictly exceeds this quantile of the rolling window.
        Default 0.75 — verbatim from g2l2.
    min_samples : int
        Minimum spread samples required before the spread gate fires.
        Default 50 — verbatim from g2l2.
    chop_window_ticks : int
        Number of recent quote ticks for the chop ratio window. Default
        30 — verbatim from g2l2 (and from island-2 g1l1).
    chop_neutral : float
        Chop ratio at or below which the chop gate does NOT skip; above
        it, the gate skips (binary hard-skip). **Default 1.7 — RETUNED for
        this base's pre-filter (spread+flow) surviving-population
        distribution, per gen-2 migration's `base_specific` (1) directive
        that thresholds tuned on one base do not transfer without retune.**
        g2l2 used 1.5 (the verbatim port from island-2 g1l1).
    chop_min_ticks : int
        Cold-start guard: chop gate is dormant until this many quote ticks
        have been observed. Default 40 — verbatim from g2l2.
    chop_eps : float
        Lower bound on displacement when computing chop_ratio (divide-by-
        zero guard on perfectly mean-reverting windows). Default 1e-9 —
        verbatim from g2l2.
    chop_max_ratio : float
        Cap on chop_ratio (numerical-stability guard against extreme
        outliers). Default 20.0 — verbatim from g2l2.
    """

    window_seconds: float = 10.0
    flow_threshold: float = 2.0
    spread_window_seconds: float = 60.0
    spread_quantile: float = 0.75
    min_samples: int = 50
    chop_window_ticks: int = 30
    chop_neutral: float = 1.7  # RETUNED: 1.5 → 1.7 (single targeted change).
    chop_min_ticks: int = 40
    chop_eps: float = 1e-9
    chop_max_ratio: float = 20.0


class AfgIslG3L1Algorithm(ExecAlgorithm):
    """g2l2 (base flow + spread + chop) with `chop_neutral` retuned 1.5 → 1.7.

    All structural behavior is identical to afg-isl-g2l2; the only change
    is the chop gate's neutral threshold. Documented at length above; the
    code below intentionally mirrors g2l2 line-for-line so that future
    diffs against g2l2 show only the parameter default change in the
    config class (and the renamed class names).

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

    def __init__(self, config: AfgIslG3L1Config) -> None:
        super().__init__(config=config)

        # ---- Aggressor-flow state (base, unmodified — mirrors g2l2) ----
        self._window_ns: int = int(config.window_seconds * 1_000_000_000)
        self._flow_threshold: float = float(config.flow_threshold)
        # Deque of (ts_event_ns, signed_vol):
        # signed_vol = +size (BUYER), -size (SELLER), 0 (NO_AGGRESSOR).
        self._flow_deque: deque[tuple[int, float]] = deque()
        # Running sum of signed volume in the flow deque (O(1) updates).
        self._net_flow: float = 0.0

        # ---- Spread-gate state (unchanged from g2l2) ----
        self._spread_window_ns: int = int(
            config.spread_window_seconds * 1_000_000_000
        )
        self._spread_quantile: float = float(config.spread_quantile)
        self._min_samples: int = int(config.min_samples)
        # Deque of (ts_event_ns, spread) in raw price units.
        self._spread_deque: deque[tuple[int, float]] = deque()
        # Most recent observed spread (the comparison point for the gate).
        self._latest_spread: float | None = None

        # ---- Chop-gate state (unchanged window shape; only neutral retuned) ----
        self._chop_window_ticks: int = int(config.chop_window_ticks)
        self._chop_neutral: float = float(config.chop_neutral)  # 1.7 by default
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
            "AfgIslG3L1Algorithm started "
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
        """Base aggressor-flow-gate logic. Unchanged from base / g2l1 / g2l2."""
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
    # Spread gate (unchanged from g2l2 — cross-island import island-0 g1l1)
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
    # Chop gate (binary hard-skip at chop_neutral; only threshold retuned)
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

        # Gate B: chop (price-path axis, from island-2 g1l1 — third axis,
        # neutral retuned for this base's pre-filter population).
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
    chop_neutral: float = 1.7,
    chop_min_ticks: int = 40,
    chop_eps: float = 1e-9,
    chop_max_ratio: float = 20.0,
) -> AfgIslG3L1Algorithm:
    """Instantiate and return the afg-isl-g3l1 algorithm.

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
        Quantile threshold for the spread gate. Default 0.75 (verbatim from
        g2l2 / island-0 g1l1).
    min_samples : int
        Minimum spread samples before the spread gate fires. Default 50
        (verbatim from g2l2).
    chop_window_ticks : int
        Rolling window length for the chop ratio, in quote ticks. Default
        30 (verbatim from g2l2 / vrs-isl-g1l1).
    chop_neutral : float
        Chop ratio threshold for binary hard-skip. **Default 1.7 — RETUNED
        for this base's pre-filter surviving-population distribution
        (single targeted change for g3l1). g2l2 used 1.5 (verbatim port
        from vrs-isl-g1l1).**
    chop_min_ticks : int
        Cold-start guard before the chop gate activates. Default 40
        (verbatim from g2l2 / vrs-isl-g1l1).
    chop_eps : float
        Lower bound on displacement (divide-by-zero guard). Default 1e-9.
    chop_max_ratio : float
        Cap on chop_ratio (numerical-stability guard). Default 20.0.
    """
    config = AfgIslG3L1Config(
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
    return AfgIslG3L1Algorithm(config=config)
