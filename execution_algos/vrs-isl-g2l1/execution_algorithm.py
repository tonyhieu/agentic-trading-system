"""Chop + rolling-spread composed gate sizer.

Island experiment — island-2 (base: vol-regime-sizer), generation 2,
loop 1.

Cross-island composition (gen-1 migration synthesis):

- Inherits island-2's choppiness-ratio gate from vrs-isl-g1l1 /
  vrs-isl-g1l2 — a price-path axis identifying whipsaw regimes via
  path_length / displacement on a 30-tick window.
- Adds island-0's rolling-spread quantile gate from ptg-isl-g1l1 —
  a book-state axis identifying liquidity-vacuum regimes via the
  current top-of-book spread compared against its rolling p75 over
  the last `spread_window_seconds`.

Gate composition is AND-on-submit (equivalently, OR-on-skip): for an
OPEN to be submitted, the spread gate must pass AND the chop gate's
probabilistic draw must select submit. Reduce-only / closing orders
bypass both gates.

Defaults are inherited verbatim:
- chop:   window_ticks=30, chop_neutral=1.5, sensitivity=1.0,
          min_prob=0.05, min_ticks=40 (from vrs-isl-g1l1).
- spread: window_seconds=60.0, quantile=0.75, min_samples=50
          (from ptg-isl-g1l1).
- trend_boost default 0.0 (collapses g1l2's trend-reinforcer to a
  no-op since gen-1 showed it added ~zero EV; plumbing retained for
  inverted-sign future experiments).

Instrumentation:
- Per-gate skip counters (chop_only, spread_only, both, neither) are
  logged on every order decision so that null-effect results vs g1l1
  remain diagnosable (gen-1 migration cited island-0 g1l2 as a loop
  lost to lack of instrumentation).

Quantity invariant: child_qty == parent_qty == 1, always.
"""
from __future__ import annotations

import hashlib
import math
import struct
from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class VrsIslG2L1Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for vrs-isl-g2l1.

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
        collapses g1l2's trend-reinforcer to a no-op (gen-1 showed
        trend_boost > 0 added ~zero marginal EV). Plumbing retained
        so inverted-sign future loops can revisit.
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


class VrsIslG2L1Algorithm(ExecAlgorithm):
    """Probabilistic chop gate composed with hard rolling-spread quantile gate."""

    def __init__(self, config: VrsIslG2L1Config) -> None:
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
        # Time-windowed (not count-windowed) deque of
        # (ts_event_ns, spread_price) tuples, pruned by ts_init at
        # gate evaluation.
        self._spread_deque: deque[tuple[int, float]] = deque()
        self._latest_spread: float | None = None

        # Subscription tracking
        self._subscribed: set[str] = set()

        # Per-gate diagnostic counters — split by which gate(s) caused
        # the skip. Helps diagnose orthogonal-vs-redundant outcomes.
        self._submitted: int = 0
        self._skipped_chop_only: int = 0
        self._skipped_spread_only: int = 0
        self._skipped_both: int = 0
        self._reduce_only_submitted: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"VrsIslG2L1Algorithm started "
            f"(window_ticks={self._window_ticks}, "
            f"chop_neutral={self._chop_neutral}, "
            f"trend_boost={self._trend_boost}, "
            f"sensitivity={self._sensitivity}, "
            f"min_prob={self._min_prob}, "
            f"min_ticks={self._min_ticks}, "
            f"spread_window={self._spread_window_ns / 1e9:.1f}s, "
            f"spread_quantile={self._spread_quantile:.2f}, "
            f"min_spread_samples={self._min_spread_samples})."
        )

    def on_reset(self) -> None:
        self._mids.clear()
        self._signed_deltas.clear()
        self._path_sum = 0.0
        self._signed_sum = 0.0
        self._tick_count = 0

        self._spread_deque.clear()
        self._latest_spread = None

        self._subscribed.clear()

        self._submitted = 0
        self._skipped_chop_only = 0
        self._skipped_spread_only = 0
        self._skipped_both = 0
        self._reduce_only_submitted = 0

    # ------------------------------------------------------------------
    # Subscription helper
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Quote tick handler — maintain both rolling windows
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
    # Chop-gate probability
    # ------------------------------------------------------------------

    def _compute_chop_submit_prob(self) -> float:
        """Submission probability from the chop gate, in [min_prob, 1.0].

        Returns 1.0 (full participation) on cold start or before the
        window has filled.
        """
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
        """Compose spread gate AND chop gate; skip if either gates the order."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        if order.is_reduce_only:
            self._reduce_only_submitted += 1
            self.log.debug(
                f"Reduce-only {order.client_order_id}: submitting unconditionally."
            )
            self.submit_order(order)
            return

        # Evaluate both gates independently so we can record which one fired.
        spread_skip = self._spread_gate_skip(order)

        p_chop = self._compute_chop_submit_prob()
        if p_chop >= 1.0 - 1e-9:
            chop_skip = False
            u = 0.0  # unused; full participation
        else:
            u = self._order_uniform(str(order.client_order_id))
            chop_skip = not (u < p_chop)

        if spread_skip and chop_skip:
            self._skipped_both += 1
            self.log.info(
                f"SKIP {order.client_order_id} (both gates) "
                f"spread>{self._spread_quantile:.2f} p_chop={p_chop:.4f} u={u:.4f}. "
                f"submitted={self._submitted} "
                f"skip_chop={self._skipped_chop_only} "
                f"skip_spread={self._skipped_spread_only} "
                f"skip_both={self._skipped_both}."
            )
            return

        if spread_skip:
            self._skipped_spread_only += 1
            self.log.info(
                f"SKIP {order.client_order_id} (spread-only) "
                f"latest_spread>{self._spread_quantile:.2f} p_chop={p_chop:.4f} u={u:.4f}. "
                f"submitted={self._submitted} "
                f"skip_chop={self._skipped_chop_only} "
                f"skip_spread={self._skipped_spread_only} "
                f"skip_both={self._skipped_both}."
            )
            return

        if chop_skip:
            self._skipped_chop_only += 1
            self.log.info(
                f"SKIP {order.client_order_id} (chop-only) "
                f"p_chop={p_chop:.4f} u={u:.4f}. "
                f"submitted={self._submitted} "
                f"skip_chop={self._skipped_chop_only} "
                f"skip_spread={self._skipped_spread_only} "
                f"skip_both={self._skipped_both}."
            )
            return

        # Both gates passed.
        self._submitted += 1
        self.log.debug(
            f"SUBMIT {order.client_order_id} "
            f"(p_chop={p_chop:.4f}, spread_ok)."
        )
        self.submit_order(order)


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
) -> VrsIslG2L1Algorithm:
    """Instantiate the chop + rolling-spread composed gate sizer.

    Defaults mirror vrs-isl-g1l1 (chop) and ptg-isl-g1l1 (spread) so the
    composition is a pure stack of two known-positive gates from gen-1.
    """
    config = VrsIslG2L1Config(
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
    )
    return VrsIslG2L1Algorithm(config=config)
