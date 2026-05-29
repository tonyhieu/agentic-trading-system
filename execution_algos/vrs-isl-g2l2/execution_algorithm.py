"""Chop + spread + aggressor-flow triple-gate sizer.

Island experiment — island-2 (base: vol-regime-sizer), generation 2,
loop 2.

Cross-island composition (gen-1 migration synthesis + g2l1 next):

- Inherits from vrs-isl-g2l1:
    * Chop gate (price-path axis) from vrs-isl-g1l1 — choppiness ratio
      (path_length / displacement) on a 30-tick window with exponential
      skip-probability decay above chop_neutral=1.5.
    * Rolling-spread quantile gate (book-state axis) from
      ptg-isl-g1l1 — skip when latest top-of-book spread exceeds the
      rolling p75 over the past spread_window_seconds.
- ADDS the aggressor-flow gate (trade-flow axis) from
  `aggressor-flow-gate/execution_algorithm.py` — skip BUYs when
  net signed aggressor flow over the last flow_window_seconds is
  <= -flow_threshold, skip SELLs when net flow >= flow_threshold.

Gate composition is OR-on-skip / AND-on-submit:
  For an OPEN to be submitted, all three gates must pass. Reduce-only
  / closing orders bypass all three gates (intraday_flat).

Defaults are inherited verbatim from each gate's source loop:
  - chop:   window_ticks=30, chop_neutral=1.5, sensitivity=1.0,
            min_prob=0.05, min_ticks=40, trend_boost=0.0
            (from vrs-isl-g1l1 / vrs-isl-g2l1).
  - spread: window_seconds=60.0, quantile=0.75, min_samples=50
            (from ptg-isl-g1l1 / vrs-isl-g2l1).
  - flow:   window_seconds=10.0, threshold=2.0 contracts
            (from aggressor-flow-gate).

Side-awareness: flow is the only side-aware gate (BUY vs SELL get
different thresholds). Chop and spread are direction-blind. This
side-awareness is why the flow axis is expected to carry residual
information even after chop+spread already gate adverse regimes.

Instrumentation:
  Per-gate skip counters track every combination of which gate(s)
  fired (chop-only, spread-only, flow-only, chop+spread, chop+flow,
  spread+flow, all-three). Each skip log line carries the full
  counter set so per-date logs let us quantify whether the flow gate
  catches uniquely-adverse-flow trades or is redundant with chop /
  spread (the gen-1 migration's instrumentation discipline).

Quantity invariant: child_qty == parent_qty == 1, always.
"""
from __future__ import annotations

import hashlib
import math
import struct
from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class VrsIslG2L2Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for vrs-isl-g2l2.

    Choppiness-gate parameters
    --------------------------
    window_ticks : int
        Rolling window length (quote ticks) for chop ratio + signed
        trend. Default 30.
    chop_neutral : float
        Baseline chop ratio at/below which chop p_submit = 1.0.
        Default 1.5.
    trend_boost : float
        Multiplier on |trend| added to chop_neutral. Default 0.0 —
        gen-1 showed trend_boost > 0 added ~zero marginal EV; plumbing
        retained for inverted-sign future experiments.
    sensitivity : float
        Exponential decay rate on chop excess. Default 1.0.
    min_prob : float
        Floor on chop submission probability. Default 0.05.
    min_ticks : int
        Cold-start tick count before chop gating activates. Default 40.
    chop_eps : float
        Lower bound on path_length / displacement (div guard). 1e-9.
    max_chop : float
        Cap on chop_ratio before sensitivity is applied. Default 20.0.

    Spread-gate parameters
    ----------------------
    spread_window_seconds : float
        Rolling window for spread samples (seconds). Default 60.0.
    spread_quantile : float
        Quantile threshold for the spread gate; skip OPEN when the
        latest spread is strictly greater than this rolling quantile.
        Default 0.75 — gates the wide-spread tail. 0 < q < 1.
    min_spread_samples : int
        Warm-up: spread gate is a no-op until this many samples have
        been observed in the window. Default 50.

    Aggressor-flow-gate parameters
    ------------------------------
    flow_window_seconds : float
        Rolling look-back window for trade prints, in seconds.
        Default 10.0 (matches aggressor-flow-gate base).
    flow_threshold : float
        Minimum absolute net signed flow (in contracts) to trigger a
        skip. For BUY orders, skip when net_flow <= -flow_threshold;
        for SELL orders, skip when net_flow >= flow_threshold.
        Default 2.0 contracts (matches aggressor-flow-gate base).
    """

    # Chop gate
    window_ticks: int = 30
    chop_neutral: float = 1.5
    trend_boost: float = 0.0
    sensitivity: float = 1.0
    min_prob: float = 0.05
    min_ticks: int = 40
    chop_eps: float = 1e-9
    max_chop: float = 20.0

    # Spread gate
    spread_window_seconds: float = 60.0
    spread_quantile: float = 0.75
    min_spread_samples: int = 50

    # Aggressor-flow gate
    flow_window_seconds: float = 10.0
    flow_threshold: float = 2.0


class VrsIslG2L2Algorithm(ExecAlgorithm):
    """Probabilistic chop gate AND hard spread-quantile gate AND
    side-aware aggressor-flow gate.
    """

    def __init__(self, config: VrsIslG2L2Config) -> None:
        super().__init__(config=config)

        # Chop config
        self._window_ticks: int = int(config.window_ticks)
        self._chop_neutral: float = float(config.chop_neutral)
        self._trend_boost: float = float(config.trend_boost)
        self._sensitivity: float = float(config.sensitivity)
        self._min_prob: float = float(config.min_prob)
        self._min_ticks: int = int(config.min_ticks)
        self._chop_eps: float = float(config.chop_eps)
        self._max_chop: float = float(config.max_chop)

        # Spread config
        self._spread_window_ns: int = int(
            config.spread_window_seconds * 1_000_000_000
        )
        self._spread_quantile: float = float(config.spread_quantile)
        self._min_spread_samples: int = int(config.min_spread_samples)

        # Flow config
        self._flow_window_ns: int = int(
            config.flow_window_seconds * 1_000_000_000
        )
        self._flow_threshold: float = float(config.flow_threshold)

        # ----- Chop rolling state -----
        # `_mids` keeps last (window_ticks + 1) mid prices so we can
        # read both current mid (head) and mid window_ticks ago (tail)
        # for displacement. `_signed_deltas` keeps the last
        # `window_ticks` per-tick (mid - prev_mid) values; `_path_sum`
        # and `_signed_sum` are maintained incrementally for O(1)
        # per-tick updates.
        self._mids: deque[float] = deque(maxlen=self._window_ticks + 1)
        self._signed_deltas: deque[float] = deque(maxlen=self._window_ticks)
        self._path_sum: float = 0.0
        self._signed_sum: float = 0.0
        self._tick_count: int = 0

        # ----- Spread rolling state -----
        # Time-windowed deque of (ts_event_ns, spread_price),
        # pruned by order.ts_init at gate evaluation.
        self._spread_deque: deque[tuple[int, float]] = deque()
        self._latest_spread: float | None = None

        # ----- Flow rolling state -----
        # Time-windowed deque of (ts_event_ns, signed_volume),
        # pruned by order.ts_init at gate evaluation.
        # signed_vol = +size (BUYER aggressor), -size (SELLER), 0 (none).
        self._flow_deque: deque[tuple[int, float]] = deque()
        self._net_flow: float = 0.0

        # Subscription tracking
        self._subscribed: set[str] = set()

        # Per-gate diagnostic counters — every distinct combination of
        # which gate(s) fired the skip. Helps diagnose whether the
        # third (flow) axis is informative or redundant with chop /
        # spread on this base.
        self._submitted: int = 0
        self._skipped_chop_only: int = 0
        self._skipped_spread_only: int = 0
        self._skipped_flow_only: int = 0
        self._skipped_chop_spread: int = 0
        self._skipped_chop_flow: int = 0
        self._skipped_spread_flow: int = 0
        self._skipped_all_three: int = 0
        self._reduce_only_submitted: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"VrsIslG2L2Algorithm started "
            f"(window_ticks={self._window_ticks}, "
            f"chop_neutral={self._chop_neutral}, "
            f"trend_boost={self._trend_boost}, "
            f"sensitivity={self._sensitivity}, "
            f"min_prob={self._min_prob}, "
            f"min_ticks={self._min_ticks}, "
            f"spread_window={self._spread_window_ns / 1e9:.1f}s, "
            f"spread_quantile={self._spread_quantile:.2f}, "
            f"min_spread_samples={self._min_spread_samples}, "
            f"flow_window={self._flow_window_ns / 1e9:.1f}s, "
            f"flow_threshold={self._flow_threshold:.2f})."
        )

    def on_reset(self) -> None:
        self._mids.clear()
        self._signed_deltas.clear()
        self._path_sum = 0.0
        self._signed_sum = 0.0
        self._tick_count = 0

        self._spread_deque.clear()
        self._latest_spread = None

        self._flow_deque.clear()
        self._net_flow = 0.0

        self._subscribed.clear()

        self._submitted = 0
        self._skipped_chop_only = 0
        self._skipped_spread_only = 0
        self._skipped_flow_only = 0
        self._skipped_chop_spread = 0
        self._skipped_chop_flow = 0
        self._skipped_spread_flow = 0
        self._skipped_all_three = 0
        self._reduce_only_submitted = 0

    # ------------------------------------------------------------------
    # Subscription helper
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self.subscribe_trade_ticks(instrument_id)
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Quote tick handler — maintain chop and spread rolling windows
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        try:
            bid = float(str(tick.bid_price))
            ask = float(str(tick.ask_price))
        except Exception:
            return
        mid = (bid + ask) / 2.0
        spread = ask - bid

        # ----- Chop state update -----
        if self._mids:
            prev_mid = self._mids[-1]
            signed_delta = mid - prev_mid
            abs_delta = abs(signed_delta)
            if len(self._signed_deltas) == self._window_ticks:
                old_signed = self._signed_deltas[0]
                self._path_sum -= abs(old_signed)
                self._signed_sum -= old_signed
            self._signed_deltas.append(signed_delta)
            self._path_sum += abs_delta
            self._signed_sum += signed_delta
        self._mids.append(mid)
        self._tick_count += 1

        # ----- Spread state update -----
        if spread >= 0.0:
            # Defensive: crossed book is dropped (mirrors ptg-isl-g1l1).
            self._spread_deque.append((int(tick.ts_event), spread))
            self._latest_spread = spread

    # ------------------------------------------------------------------
    # Trade tick handler — maintain rolling signed aggressor flow
    # ------------------------------------------------------------------

    def on_trade_tick(self, tick) -> None:
        """Receive a trade tick and update the rolling aggressor-flow deque.

        Mirrors `aggressor-flow-gate` verbatim: BUYER aggressor contributes
        +size, SELLER contributes -size, NO_AGGRESSOR contributes 0.
        Chop/spread state is quote-tick-driven and is NOT touched here.
        """
        aggressor = tick.aggressor_side
        size = float(str(tick.size))

        if aggressor == AggressorSide.BUYER:
            signed_vol = size
        elif aggressor == AggressorSide.SELLER:
            signed_vol = -size
        else:
            signed_vol = 0.0

        self._flow_deque.append((int(tick.ts_event), signed_vol))
        self._net_flow += signed_vol

    # ------------------------------------------------------------------
    # Chop-gate probability
    # ------------------------------------------------------------------

    def _compute_chop_submit_prob(self) -> float:
        """Submission probability from the chop gate, in [min_prob, 1.0]."""
        if self._tick_count < self._min_ticks:
            return 1.0
        if (
            len(self._mids) < self._window_ticks + 1
            or len(self._signed_deltas) < self._window_ticks
        ):
            return 1.0

        path_length = self._path_sum
        displacement = abs(self._mids[-1] - self._mids[0])
        denom = max(displacement, self._chop_eps)
        chop_ratio = min(path_length / denom, self._max_chop)

        path_denom = max(path_length, self._chop_eps)
        trend = self._signed_sum / path_denom
        abs_trend = min(abs(trend), 1.0)

        effective_neutral = self._chop_neutral + self._trend_boost * abs_trend
        excess = max(0.0, chop_ratio - effective_neutral)
        prob = math.exp(-self._sensitivity * excess)
        prob = max(self._min_prob, prob)
        return prob

    # ------------------------------------------------------------------
    # Spread-gate hard test
    # ------------------------------------------------------------------

    def _prune_spread_window(self, cutoff_ns: int) -> None:
        while self._spread_deque and self._spread_deque[0][0] < cutoff_ns:
            self._spread_deque.popleft()

    def _spread_gate_skip(self, order) -> bool:
        """Return True if the latest spread sits strictly above the rolling quantile."""
        cutoff_ns = int(order.ts_init) - self._spread_window_ns
        self._prune_spread_window(cutoff_ns)

        n = len(self._spread_deque)
        if n < self._min_spread_samples or self._latest_spread is None:
            return False  # warm-up: do not gate

        sorted_spreads = sorted(s for _, s in self._spread_deque)
        idx_f = self._spread_quantile * (n - 1)
        lo = int(idx_f)
        hi = min(lo + 1, n - 1)
        frac = idx_f - lo
        threshold = sorted_spreads[lo] * (1.0 - frac) + sorted_spreads[hi] * frac

        return self._latest_spread > threshold

    # ------------------------------------------------------------------
    # Flow-gate side-aware hard test
    # ------------------------------------------------------------------

    def _prune_flow_window(self, cutoff_ns: int) -> None:
        """Remove flow deque entries older than cutoff_ns, updating net_flow."""
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            _, old_vol = self._flow_deque.popleft()
            self._net_flow -= old_vol

    def _flow_gate_skip(self, order) -> bool:
        """Return True if net aggressor flow is adverse for this order direction.

        BUY  order: adverse when net_flow <= -flow_threshold (sellers dominate)
        SELL order: adverse when net_flow >=  flow_threshold (buyers dominate)

        Returns False (do not skip) when:
          - Flow deque is empty after prune (warm-up / thin market)
          - |net_flow| < flow_threshold (neutral / near-balanced)
        """
        cutoff_ns = int(order.ts_init) - self._flow_window_ns
        self._prune_flow_window(cutoff_ns)

        if not self._flow_deque:
            return False

        net = self._net_flow

        if order.side == OrderSide.BUY:
            return net <= -self._flow_threshold
        else:  # SELL
            return net >= self._flow_threshold

    # ------------------------------------------------------------------
    # Deterministic pseudo-random draw (per order)
    # ------------------------------------------------------------------

    @staticmethod
    def _order_uniform(order_id_str: str) -> float:
        digest = hashlib.sha256(order_id_str.encode()).digest()
        val = struct.unpack(">Q", digest[:8])[0]
        return val / (2**64)

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Compose three independent gates; skip if ANY fires."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        if order.is_reduce_only:
            self._reduce_only_submitted += 1
            self.log.debug(
                f"Reduce-only {order.client_order_id}: submitting unconditionally."
            )
            self.submit_order(order)
            return

        # Evaluate all three gates independently so we can attribute the skip.
        spread_skip = self._spread_gate_skip(order)
        flow_skip = self._flow_gate_skip(order)

        p_chop = self._compute_chop_submit_prob()
        if p_chop >= 1.0 - 1e-9:
            chop_skip = False
            u = 0.0  # unused; full participation
        else:
            u = self._order_uniform(str(order.client_order_id))
            chop_skip = not (u < p_chop)

        # Counter selection — count every distinct skip combination so
        # logs can be reduced to per-axis cardinalities post-hoc.
        if chop_skip and spread_skip and flow_skip:
            self._skipped_all_three += 1
            self._log_skip(order, "all_three", p_chop, u)
            return
        if chop_skip and spread_skip:
            self._skipped_chop_spread += 1
            self._log_skip(order, "chop+spread", p_chop, u)
            return
        if chop_skip and flow_skip:
            self._skipped_chop_flow += 1
            self._log_skip(order, "chop+flow", p_chop, u)
            return
        if spread_skip and flow_skip:
            self._skipped_spread_flow += 1
            self._log_skip(order, "spread+flow", p_chop, u)
            return
        if chop_skip:
            self._skipped_chop_only += 1
            self._log_skip(order, "chop-only", p_chop, u)
            return
        if spread_skip:
            self._skipped_spread_only += 1
            self._log_skip(order, "spread-only", p_chop, u)
            return
        if flow_skip:
            self._skipped_flow_only += 1
            self._log_skip(order, "flow-only", p_chop, u)
            return

        # All gates passed.
        self._submitted += 1
        self.log.debug(
            f"SUBMIT {order.client_order_id} "
            f"(p_chop={p_chop:.4f}, spread_ok, flow_ok, "
            f"net_flow={self._net_flow:.2f})."
        )
        self.submit_order(order)

    def _log_skip(self, order, which: str, p_chop: float, u: float) -> None:
        self.log.info(
            f"SKIP {order.client_order_id} ({which}) "
            f"p_chop={p_chop:.4f} u={u:.4f} "
            f"net_flow={self._net_flow:.2f} side="
            f"{'BUY' if order.side == OrderSide.BUY else 'SELL'}. "
            f"submitted={self._submitted} "
            f"skip_chop={self._skipped_chop_only} "
            f"skip_spread={self._skipped_spread_only} "
            f"skip_flow={self._skipped_flow_only} "
            f"skip_chop_spread={self._skipped_chop_spread} "
            f"skip_chop_flow={self._skipped_chop_flow} "
            f"skip_spread_flow={self._skipped_spread_flow} "
            f"skip_all={self._skipped_all_three}."
        )


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_ticks: int = 30,
    chop_neutral: float = 1.5,
    trend_boost: float = 0.0,
    sensitivity: float = 1.0,
    min_prob: float = 0.05,
    min_ticks: int = 40,
    chop_eps: float = 1e-9,
    max_chop: float = 20.0,
    spread_window_seconds: float = 60.0,
    spread_quantile: float = 0.75,
    min_spread_samples: int = 50,
    flow_window_seconds: float = 10.0,
    flow_threshold: float = 2.0,
) -> VrsIslG2L2Algorithm:
    """Instantiate the chop + spread + aggressor-flow triple-gate sizer.

    Defaults mirror each gate's source-of-truth loop:
      - chop:   vrs-isl-g1l1 / vrs-isl-g2l1
      - spread: ptg-isl-g1l1 / vrs-isl-g2l1
      - flow:   aggressor-flow-gate (island-1 base)
    so the composition is a pure stack of three independently-proven
    skip gates with no parameter tuning at this loop.
    """
    config = VrsIslG2L2Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_ticks=window_ticks,
        chop_neutral=chop_neutral,
        trend_boost=trend_boost,
        sensitivity=sensitivity,
        min_prob=min_prob,
        min_ticks=min_ticks,
        chop_eps=chop_eps,
        max_chop=max_chop,
        spread_window_seconds=spread_window_seconds,
        spread_quantile=spread_quantile,
        min_spread_samples=min_spread_samples,
        flow_window_seconds=flow_window_seconds,
        flow_threshold=flow_threshold,
    )
    return VrsIslG2L2Algorithm(config=config)
