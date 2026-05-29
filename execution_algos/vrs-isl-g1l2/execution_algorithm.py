"""Trend-reinforced choppiness-gated sizer execution algorithm.

Island experiment — island-2 (base: vol-regime-sizer), generation 1, loop 2.

Mechanism: Extend vrs-isl-g1l1's choppiness gate with a **directional-efficiency
reinforcer**. Over the same rolling window already maintained for chop:

    trend = sum(delta_mid_i) / max(path_length, eps)        # ∈ [-1, +1]

Use |trend| to BOOST the effective neutral threshold:

    effective_neutral = chop_neutral + trend_boost * |trend|
    excess            = max(0, chop_ratio - effective_neutral)
    p_submit          = max(min_prob, exp(-sensitivity * excess))

Asymmetric by design: trend_boost ≥ 0 can only RAISE the threshold, never
lower it. Pure whipsaws (|trend|=0) are gated identically to g1l1; clean
trends (|trend|→1) get a wider neutral band so brief chop spikes inside a
trend no longer cost participation. At trend_boost=0 this collapses to
g1l1 exactly.

Quantity invariant: child_qty == parent_qty == 1, always.
Reduce-only (close) orders: always submitted unconditionally.
"""
from __future__ import annotations

import hashlib
import math
import struct
from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class TrendReinforcedChoppinessSizerConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the trend-reinforced choppiness-gated sizer.

    Parameters
    ----------
    window_ticks : int
        Number of recent quote ticks for both the chop ratio and trend
        signed-sum windows. Default 30 (matches g1l1).
    chop_neutral : float
        Baseline chop ratio at/below which p_submit = 1.0. Default 1.5.
    trend_boost : float
        How much |trend| raises the effective neutral threshold.
        effective_neutral = chop_neutral + trend_boost * |trend|.
        Default 1.0 (effective neutral can grow from 1.5 to 2.5).
        At 0.0 this algorithm reduces exactly to g1l1.
    sensitivity : float
        Exponential decay rate on chop excess. Default 1.0.
    min_prob : float
        Floor on submission probability. Default 0.05.
    min_ticks : int
        Cold-start guard: submit at p=1.0 until this many quote ticks have
        been observed. Default 40.
    chop_eps : float
        Lower bound on displacement / path_length (divide-by-zero guard).
        Default 1e-9.
    max_chop : float
        Cap on chop_ratio before applying sensitivity. Default 20.0.
    """

    window_ticks: int = 30
    chop_neutral: float = 1.5
    trend_boost: float = 1.0
    sensitivity: float = 1.0
    min_prob: float = 0.05
    min_ticks: int = 40
    chop_eps: float = 1e-9
    max_chop: float = 20.0


class TrendReinforcedChoppinessSizerAlgorithm(ExecAlgorithm):
    """Probabilistic submitter gated on chop, reinforced by directional efficiency."""

    def __init__(self, config: TrendReinforcedChoppinessSizerConfig) -> None:
        super().__init__(config=config)

        self._window_ticks: int = int(config.window_ticks)
        self._chop_neutral: float = float(config.chop_neutral)
        self._trend_boost: float = float(config.trend_boost)
        self._sensitivity: float = float(config.sensitivity)
        self._min_prob: float = float(config.min_prob)
        self._min_ticks: int = int(config.min_ticks)
        self._chop_eps: float = float(config.chop_eps)
        self._max_chop: float = float(config.max_chop)

        # Rolling state.
        # `_mids` keeps the last (window_ticks + 1) mid prices so we can read
        # both the current mid (head) and the mid window_ticks ago (tail) for
        # displacement. `_signed_deltas` keeps the last `window_ticks` per-tick
        # (mid - prev_mid) values; we maintain `_path_sum` (sum of absolute
        # deltas) and `_signed_sum` (sum of signed deltas) incrementally so
        # each tick is O(1).
        self._mids: deque[float] = deque(maxlen=self._window_ticks + 1)
        self._signed_deltas: deque[float] = deque(maxlen=self._window_ticks)
        self._path_sum: float = 0.0
        self._signed_sum: float = 0.0
        self._tick_count: int = 0

        # Subscription tracking
        self._subscribed: set[str] = set()

        # Diagnostic counters
        self._submitted: int = 0
        self._skipped: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"TrendReinforcedChoppinessSizerAlgorithm started "
            f"(window_ticks={self._window_ticks}, chop_neutral={self._chop_neutral}, "
            f"trend_boost={self._trend_boost}, sensitivity={self._sensitivity}, "
            f"min_prob={self._min_prob}, min_ticks={self._min_ticks})."
        )

    def on_reset(self) -> None:
        self._mids.clear()
        self._signed_deltas.clear()
        self._path_sum = 0.0
        self._signed_sum = 0.0
        self._tick_count = 0
        self._subscribed.clear()
        self._submitted = 0
        self._skipped = 0

    # ------------------------------------------------------------------
    # Quote-tick handler — maintain rolling window
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    def on_quote_tick(self, tick) -> None:
        try:
            bid = float(str(tick.bid_price))
            ask = float(str(tick.ask_price))
            mid = (bid + ask) / 2.0
        except Exception:
            return

        if self._mids:
            prev_mid = self._mids[-1]
            signed_delta = mid - prev_mid
            abs_delta = abs(signed_delta)

            # Incremental maintenance of both sums: add new entry; subtract
            # the one falling off the back of the window, if any.
            if len(self._signed_deltas) == self._window_ticks:
                old_signed = self._signed_deltas[0]
                self._path_sum -= abs(old_signed)
                self._signed_sum -= old_signed
            self._signed_deltas.append(signed_delta)
            self._path_sum += abs_delta
            self._signed_sum += signed_delta

        self._mids.append(mid)
        self._tick_count += 1

    # ------------------------------------------------------------------
    # Submission probability
    # ------------------------------------------------------------------

    def _compute_submit_prob(self) -> float:
        """Return submission probability in [min_prob, 1.0].

        Returns 1.0 (full participation) on cold start or undefined window.
        """
        if self._tick_count < self._min_ticks:
            return 1.0

        if len(self._mids) < self._window_ticks + 1 or len(self._signed_deltas) < self._window_ticks:
            # Window not yet filled; treat as calm.
            return 1.0

        path_length = self._path_sum
        displacement = abs(self._mids[-1] - self._mids[0])
        denom = max(displacement, self._chop_eps)
        chop_ratio = min(path_length / denom, self._max_chop)

        # Directional efficiency in [-1, +1]; |trend|=1 means every tick the
        # same sign, |trend|=0 means perfectly balanced up/down ticks.
        path_denom = max(path_length, self._chop_eps)
        trend = self._signed_sum / path_denom
        abs_trend = min(abs(trend), 1.0)

        # Trend-boosted neutral band: clean trends get a wider tolerance for
        # transient chop spikes; pure noise gets g1l1's threshold unchanged.
        effective_neutral = self._chop_neutral + self._trend_boost * abs_trend

        excess = max(0.0, chop_ratio - effective_neutral)
        prob = math.exp(-self._sensitivity * excess)
        prob = max(self._min_prob, prob)

        self.log.debug(
            f"chop_ratio={chop_ratio:.4f} trend={trend:+.4f} "
            f"eff_neutral={effective_neutral:.4f} excess={excess:.4f} "
            f"path={path_length:.8f} disp={displacement:.8f} "
            f"p_submit={prob:.4f}"
        )
        return prob

    # ------------------------------------------------------------------
    # Deterministic pseudo-random draw
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
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on trend-reinforced chop gate."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders: always submit — intraday_flat compliance.
        if order.is_reduce_only:
            self.log.debug(
                f"Reduce-only {order.client_order_id}: submitting unconditionally."
            )
            self.submit_order(order)
            return

        p = self._compute_submit_prob()

        if p >= 1.0 - 1e-9:
            # Full participation (calm / trending / cold start).
            self._submitted += 1
            self.log.debug(f"SUBMIT {order.client_order_id} (p=1.0).")
            self.submit_order(order)
            return

        u = self._order_uniform(str(order.client_order_id))

        if u < p:
            self._submitted += 1
            self.log.debug(
                f"SUBMIT {order.client_order_id} (p={p:.4f}, u={u:.4f})."
            )
            self.submit_order(order)
        else:
            self._skipped += 1
            self.log.info(
                f"SKIP {order.client_order_id} (p={p:.4f}, u={u:.4f}, chop-gated). "
                f"submitted={self._submitted} skipped={self._skipped}."
            )
            # Do NOT call submit_order — quantity invariant preserved.


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_ticks: int = 30,
    chop_neutral: float = 1.5,
    trend_boost: float = 1.0,
    sensitivity: float = 1.0,
    min_prob: float = 0.05,
    min_ticks: int = 40,
    chop_eps: float = 1e-9,
    max_chop: float = 20.0,
) -> TrendReinforcedChoppinessSizerAlgorithm:
    """Instantiate the trend-reinforced choppiness-gated sizer.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier.
    window_ticks : int
        Rolling window length in quote ticks. Default 30.
    chop_neutral : float
        Baseline chop ratio at/below which p_submit = 1.0. Default 1.5.
    trend_boost : float
        Multiplier on |trend| added to chop_neutral. Default 1.0
        (effective neutral grows from 1.5 to at most 2.5).
    sensitivity : float
        Exponential decay rate on chop excess. Default 1.0.
    min_prob : float
        Floor on submission probability. Default 0.05.
    min_ticks : int
        Cold-start guard before gating activates. Default 40.
    chop_eps : float
        Lower bound on displacement / path_length (divide-by-zero guard).
        Default 1e-9.
    max_chop : float
        Cap on chop_ratio before sensitivity is applied. Default 20.0.
    """
    config = TrendReinforcedChoppinessSizerConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_ticks=window_ticks,
        chop_neutral=chop_neutral,
        trend_boost=trend_boost,
        sensitivity=sensitivity,
        min_prob=min_prob,
        min_ticks=min_ticks,
        chop_eps=chop_eps,
        max_chop=max_chop,
    )
    return TrendReinforcedChoppinessSizerAlgorithm(config=config)
