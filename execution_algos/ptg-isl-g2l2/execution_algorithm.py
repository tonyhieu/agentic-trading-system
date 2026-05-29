"""ptg-isl-g2l2: position-cap + rolling-spread + probabilistic chop-decay gates.

Island experiment — island-0 (base: position-tier-gate), generation 2, loop 2.

Builds on `ptg-isl-g2l1` (the prior loop in this island's lineage) by
replacing the **boolean** chop-skip (skip when chop_ratio > 2.0) with the
**probabilistic exponential-decay** form that island-2's vrs-isl-g1l1
actually used:

    excess   = max(0, chop_ratio - chop_neutral)
    p_submit = max(min_prob, exp(-sensitivity * excess))

A deterministic SHA-256(client_order_id)-derived uniform `u in [0, 1)`
decides submission: SUBMIT iff `u < p_submit`. Reproducible given the
oracle's fixed seed.

Gates evaluated in order at `on_order()` for non-reduce-only orders:
  1. position-tier-gate (boolean): skip if net_qty >= position_cap.
  2. rolling-spread gate (boolean): skip if latest spread > rolling p75
     of recent spreads (60s window, min 50 samples).
  3. chop-decay gate (PROBABILISTIC, NEW vs g2l1):
        chop_ratio computed exactly as g2l1 (window=30 ticks,
        path/displacement, eps & cap guards). Mapped to p_submit via
        exponential decay above chop_neutral=1.5. Deterministic uniform
        draw decides skip vs submit.

Why this change is the single-variable test that g2l1 set up:
  g2l1 falsified the boolean port (-23.14% vs base) and its
  `summary_out.next` explicitly recommended porting island-2's actual
  *probabilistic* semantics. The constants chop_neutral=1.5,
  sensitivity=1.0, min_prob=0.05 are taken verbatim from vrs-isl-g1l1
  (which produced +34% PnL on its base). Position-cap and
  spread-p75 layers are unchanged. The ONLY variable changed is the
  chop-gate decision rule (hard cutoff → soft decay).

No look-ahead: mid-price samples populate `_mids` in chronological
replay order from `on_quote_tick`; `on_order` reads cached values
only.

No quantity modification: SKIP means do not submit; quantity invariant
preserved.
"""
from __future__ import annotations

import hashlib
import math
import struct
from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PtgIslG2L2Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for ptg-isl-g2l2.

    Parameters
    ----------
    position_cap : int
        Inherited from position-tier-gate. Skip OPEN if absolute net
        position >= position_cap. Default 1.
    spread_window_seconds : float
        Rolling window for spread samples (seconds). Default 60.0.
    spread_quantile : float
        Spread-gate quantile in (0, 1). Default 0.75.
    spread_min_samples : int
        Minimum samples before the spread gate fires. Default 50.
    chop_window_ticks : int
        Rolling window length (in quote ticks) for the chop ratio.
        Default 30. Matches island-2 vrs-isl-g1l1.
    chop_neutral : float
        Chop ratio at and below which `p_submit = 1.0`. Default 1.5.
        Matches vrs-isl-g1l1 exactly.
    chop_sensitivity : float
        Exponential decay rate on chop excess:
        `p = exp(-sensitivity * (chop_ratio - chop_neutral))` for
        `chop_ratio > chop_neutral`. Default 1.0. Matches vrs-isl-g1l1.
    chop_min_prob : float
        Floor on submission probability for extreme whipsaws. Default
        0.05. Matches vrs-isl-g1l1.
    chop_min_ticks : int
        Cold-start guard: chop gate is a no-op (p=1.0) until this many
        quote ticks have been observed. Default 40 (>= chop_window_ticks).
    chop_eps : float
        Lower bound on displacement (divide-by-zero guard). Default 1e-9.
    chop_max_ratio : float
        Cap on chop_ratio before threshold/decay comparison (defensive,
        prevents pathological values from breaking math.exp). Default 20.0.
    log_every_n_skips : int
        Emit a running-counter info log line every N total skips
        (across all gates). Default 500.
    """

    position_cap: int = 1
    spread_window_seconds: float = 60.0
    spread_quantile: float = 0.75
    spread_min_samples: int = 50
    chop_window_ticks: int = 30
    chop_neutral: float = 1.5
    chop_sensitivity: float = 1.0
    chop_min_prob: float = 0.05
    chop_min_ticks: int = 40
    chop_eps: float = 1e-9
    chop_max_ratio: float = 20.0
    log_every_n_skips: int = 500


class PtgIslG2L2Algorithm(ExecAlgorithm):
    """ExecAlgorithm: position-cap + spread-quantile + probabilistic chop-decay."""

    def __init__(self, config: PtgIslG2L2Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = int(config.position_cap)
        self._spread_window_ns: int = int(config.spread_window_seconds * 1_000_000_000)
        self._spread_quantile: float = float(config.spread_quantile)
        self._spread_min_samples: int = int(config.spread_min_samples)
        self._chop_window_ticks: int = int(config.chop_window_ticks)
        self._chop_neutral: float = float(config.chop_neutral)
        self._chop_sensitivity: float = float(config.chop_sensitivity)
        self._chop_min_prob: float = float(config.chop_min_prob)
        self._chop_min_ticks: int = int(config.chop_min_ticks)
        self._chop_eps: float = float(config.chop_eps)
        self._chop_max_ratio: float = float(config.chop_max_ratio)
        self._log_every_n_skips: int = int(config.log_every_n_skips)

        # Rolling spread samples: (ts_event_ns, spread).
        self._spread_deque: deque[tuple[int, float]] = deque()
        self._latest_spread: float | None = None

        # Chop window state — incrementally maintained O(1) per tick.
        # `_mids` holds up to (chop_window_ticks + 1) most-recent mids so
        # displacement = |mids[-1] - mids[0]| and path is the sum of the
        # last `chop_window_ticks` |delta_mid| values.
        self._mids: deque[float] = deque(maxlen=self._chop_window_ticks + 1)
        self._abs_deltas: deque[float] = deque(maxlen=self._chop_window_ticks)
        self._path_sum: float = 0.0
        self._tick_count: int = 0

        # Subscription tracking
        self._subscribed: set[str] = set()

        # Instrumentation counters (per-run lifetime).
        self._evaluated: int = 0
        self._skipped_position: int = 0
        self._skipped_spread: int = 0
        self._skipped_chop: int = 0
        self._submitted: int = 0
        # New: distinguishes "chop gate fires (p<1) but doesn't skip"
        # from "chop gate never fires" — gen-1 taught us to instrument.
        self._chop_p_submit_lt_1_count: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"PtgIslG2L2Algorithm started "
            f"(position_cap={self._position_cap}, "
            f"spread_window={self._spread_window_ns / 1e9:.1f}s, "
            f"spread_quantile={self._spread_quantile:.2f}, "
            f"spread_min_samples={self._spread_min_samples}, "
            f"chop_window_ticks={self._chop_window_ticks}, "
            f"chop_neutral={self._chop_neutral:.2f}, "
            f"chop_sensitivity={self._chop_sensitivity:.2f}, "
            f"chop_min_prob={self._chop_min_prob:.3f}, "
            f"chop_min_ticks={self._chop_min_ticks})."
        )

    def on_reset(self) -> None:
        self._spread_deque.clear()
        self._latest_spread = None
        self._mids.clear()
        self._abs_deltas.clear()
        self._path_sum = 0.0
        self._tick_count = 0
        self._subscribed.clear()
        self._evaluated = 0
        self._skipped_position = 0
        self._skipped_spread = 0
        self._skipped_chop = 0
        self._submitted = 0
        self._chop_p_submit_lt_1_count = 0

    def on_stop(self) -> None:
        # Final instrumentation dump — survives in logs even if
        # intermediate counter snapshots were missed.
        self.log.info(
            f"PtgIslG2L2Algorithm stopping — counters: "
            f"evaluated={self._evaluated} "
            f"submitted={self._submitted} "
            f"skipped_position={self._skipped_position} "
            f"skipped_spread={self._skipped_spread} "
            f"skipped_chop={self._skipped_chop} "
            f"chop_p_submit_lt_1_count={self._chop_p_submit_lt_1_count}."
        )

    # ------------------------------------------------------------------
    # Subscription helper
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Quote tick handler — maintain rolling spread + chop windows
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        try:
            bid = float(str(tick.bid_price))
            ask = float(str(tick.ask_price))
        except Exception:
            return

        spread = ask - bid
        if spread < 0.0:
            # Defensive: crossed book — skip the sample entirely.
            return

        # Update spread window.
        self._spread_deque.append((tick.ts_event, spread))
        self._latest_spread = spread

        # Update chop window.
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

    # ------------------------------------------------------------------
    # Gate helpers
    # ------------------------------------------------------------------

    def _current_net_qty(self, instrument_id) -> float:
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        return sum(float(str(p.quantity)) for p in open_positions)

    def _prune_spread_window(self, cutoff_ns: int) -> None:
        while self._spread_deque and self._spread_deque[0][0] < cutoff_ns:
            self._spread_deque.popleft()

    def _spread_gate_skip(self, order) -> bool:
        """Return True if the latest spread sits above the rolling quantile."""
        cutoff_ns = order.ts_init - self._spread_window_ns
        self._prune_spread_window(cutoff_ns)

        n = len(self._spread_deque)
        if n < self._spread_min_samples or self._latest_spread is None:
            return False  # warm-up: do not gate

        sorted_spreads = sorted(s for _, s in self._spread_deque)
        idx_f = self._spread_quantile * (n - 1)
        lo = int(idx_f)
        hi = min(lo + 1, n - 1)
        frac = idx_f - lo
        threshold = sorted_spreads[lo] * (1.0 - frac) + sorted_spreads[hi] * frac

        return self._latest_spread > threshold

    def _chop_ratio(self) -> float | None:
        """Return chop_ratio over the configured window, or None on warm-up."""
        if self._tick_count < self._chop_min_ticks:
            return None
        if len(self._mids) < self._chop_window_ticks + 1:
            return None
        if len(self._abs_deltas) < self._chop_window_ticks:
            return None
        displacement = abs(self._mids[-1] - self._mids[0])
        denom = max(displacement, self._chop_eps)
        ratio = self._path_sum / denom
        if ratio > self._chop_max_ratio:
            ratio = self._chop_max_ratio
        return ratio

    def _chop_submit_prob(self) -> float:
        """Return chop-decay submission probability in [chop_min_prob, 1.0].

        Returns 1.0 (full participation) on cold start or undefined window.
        Above chop_neutral, decays exponentially with `chop_sensitivity`,
        floored at `chop_min_prob`.
        """
        ratio = self._chop_ratio()
        if ratio is None:
            return 1.0  # warm-up: do not gate

        excess = max(0.0, ratio - self._chop_neutral)
        if excess <= 0.0:
            return 1.0

        prob = math.exp(-self._chop_sensitivity * excess)
        if prob < self._chop_min_prob:
            prob = self._chop_min_prob
        return prob

    # ------------------------------------------------------------------
    # Deterministic pseudo-random draw — verbatim from vrs-isl-g1l1
    # ------------------------------------------------------------------

    @staticmethod
    def _order_uniform(order_id_str: str) -> float:
        """Deterministic float in [0, 1) from the order's client ID.

        SHA-256 of the string representation; first 8 bytes as big-endian
        uint64; normalized. Reproducible given the same oracle seed.
        """
        digest = hashlib.sha256(order_id_str.encode()).digest()
        val = struct.unpack(">Q", digest[:8])[0]
        return val / (2**64)

    # ------------------------------------------------------------------
    # Diagnostic logging helper
    # ------------------------------------------------------------------

    def _maybe_log_counters(self, reason: str, order) -> None:
        total_skips = (
            self._skipped_position + self._skipped_spread + self._skipped_chop
        )
        if (
            self._log_every_n_skips > 0
            and total_skips % self._log_every_n_skips == 0
        ):
            self.log.info(
                f"SKIP({reason}) {order.client_order_id} — running counters: "
                f"evaluated={self._evaluated} "
                f"submitted={self._submitted} "
                f"skipped_position={self._skipped_position} "
                f"skipped_spread={self._skipped_spread} "
                f"skipped_chop={self._skipped_chop} "
                f"chop_p_submit_lt_1_count={self._chop_p_submit_lt_1_count}."
            )

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        if order.is_reduce_only:
            self.submit_order(order)
            return

        self._evaluated += 1

        # Gate 1: position-tier-gate (boolean).
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty >= self._position_cap:
            self._skipped_position += 1
            self._maybe_log_counters("position", order)
            return

        # Gate 2: rolling-spread quantile gate (boolean).
        if self._spread_gate_skip(order):
            self._skipped_spread += 1
            self._maybe_log_counters("spread", order)
            return

        # Gate 3: probabilistic chop-decay gate (NEW vs g2l1).
        p = self._chop_submit_prob()
        if p < 1.0 - 1e-9:
            self._chop_p_submit_lt_1_count += 1
            u = self._order_uniform(str(order.client_order_id))
            if u >= p:
                self._skipped_chop += 1
                self._maybe_log_counters("chop", order)
                return

        self._submitted += 1
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    spread_window_seconds: float = 60.0,
    spread_quantile: float = 0.75,
    spread_min_samples: int = 50,
    chop_window_ticks: int = 30,
    chop_neutral: float = 1.5,
    chop_sensitivity: float = 1.0,
    chop_min_prob: float = 0.05,
    chop_min_ticks: int = 40,
    chop_eps: float = 1e-9,
    chop_max_ratio: float = 20.0,
    log_every_n_skips: int = 500,
) -> PtgIslG2L2Algorithm:
    config = PtgIslG2L2Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        spread_window_seconds=spread_window_seconds,
        spread_quantile=spread_quantile,
        spread_min_samples=spread_min_samples,
        chop_window_ticks=chop_window_ticks,
        chop_neutral=chop_neutral,
        chop_sensitivity=chop_sensitivity,
        chop_min_prob=chop_min_prob,
        chop_min_ticks=chop_min_ticks,
        chop_eps=chop_eps,
        chop_max_ratio=chop_max_ratio,
        log_every_n_skips=log_every_n_skips,
    )
    return PtgIslG2L2Algorithm(config=config)
