"""Incoherence-sharpened choppiness-gated sizer execution algorithm.

Island experiment — island-2 (base: vol-regime-sizer), generation 1, loop 3.

Builds on vrs-isl-g1l1's choppiness gate (path_length / displacement on a
30-tick window). g1l2's trend-reinforcer (which *widened* the neutral band
inside trends) recovered ~2548 marginal trades but those trades carried
~$0 EV on the train window. This loop pursues the inverse hypothesis from
the g1l2 NOTES (`next` item iii): within the already-gated region, the
directionally-incoherent windows are likely the negative-EV bucket — and
the gate should be *sharper* there, not gentler.

Mechanism: reuse the same rolling window, chop_ratio, and `trend` ∈ [-1,+1]
quantities as g1l2. Define

    incoherence = 1.0 - |trend|       # 1.0 = whipsaw, 0.0 = clean trend

and scale the **decay rate** (not the threshold) by incoherence:

    excess                = max(0, chop_ratio - chop_neutral)
    effective_sensitivity = sensitivity * (1 + incoherence_boost * incoherence)
    p_submit              = max(min_prob, exp(-effective_sensitivity * excess))

Asymmetric: incoherence_boost ≥ 0 can only INCREASE the decay rate, never
decrease it. Pure-trend windows (|trend|=1) reduce to g1l1 exactly.
Pure-whipsaw windows (|trend|=0) get the maximum sharpening
(effective_sensitivity = sensitivity * (1 + incoherence_boost)). At
`incoherence_boost = 0.0` the algorithm collapses to g1l1 exactly.

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


class IncoherenceSharpenedChoppinessSizerConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the incoherence-sharpened choppiness-gated sizer.

    Parameters
    ----------
    window_ticks : int
        Number of recent quote ticks for both the chop ratio and trend
        signed-sum windows. Default 30 (matches g1l1/g1l2).
    chop_neutral : float
        Baseline chop ratio at/below which p_submit = 1.0. Default 1.5
        (matches g1l1/g1l2).
    incoherence_boost : float
        How much (1 - |trend|) raises the effective sensitivity above
        threshold. effective_sensitivity = sensitivity * (1 +
        incoherence_boost * (1 - |trend|)). Default 1.0 (effective
        sensitivity grows from sensitivity at pure trend to
        sensitivity*2 at pure whipsaw). At 0.0 this algorithm reduces
        exactly to g1l1.
    sensitivity : float
        Baseline exponential decay rate on chop excess. Default 1.0.
    min_prob : float
        Floor on submission probability. Default 0.05.
    min_ticks : int
        Cold-start guard: submit at p=1.0 until this many quote ticks
        have been observed. Default 40.
    chop_eps : float
        Lower bound on displacement / path_length (divide-by-zero guard).
        Default 1e-9.
    max_chop : float
        Cap on chop_ratio before applying sensitivity. Default 20.0.
    """

    window_ticks: int = 30
    chop_neutral: float = 1.5
    incoherence_boost: float = 1.0
    sensitivity: float = 1.0
    min_prob: float = 0.05
    min_ticks: int = 40
    chop_eps: float = 1e-9
    max_chop: float = 20.0


class IncoherenceSharpenedChoppinessSizerAlgorithm(ExecAlgorithm):
    """Probabilistic submitter gated on chop, sharpened by directional incoherence."""

    def __init__(self, config: IncoherenceSharpenedChoppinessSizerConfig) -> None:
        super().__init__(config=config)

        self._window_ticks: int = int(config.window_ticks)
        self._chop_neutral: float = float(config.chop_neutral)
        self._incoherence_boost: float = float(config.incoherence_boost)
        self._sensitivity: float = float(config.sensitivity)
        self._min_prob: float = float(config.min_prob)
        self._min_ticks: int = int(config.min_ticks)
        self._chop_eps: float = float(config.chop_eps)
        self._max_chop: float = float(config.max_chop)

        # Rolling state (identical structure to g1l2 — we reuse both the
        # path_sum (chop) and signed_sum (trend) updates).
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
            f"IncoherenceSharpenedChoppinessSizerAlgorithm started "
            f"(window_ticks={self._window_ticks}, chop_neutral={self._chop_neutral}, "
            f"incoherence_boost={self._incoherence_boost}, sensitivity={self._sensitivity}, "
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

            # Incremental maintenance of both sums.
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

        # Directional efficiency in [-1, +1]; incoherence in [0, 1].
        # |trend|=1 → incoherence=0 → reduces to g1l1 (sensitivity unchanged).
        # |trend|=0 → incoherence=1 → effective_sensitivity = sensitivity*(1+boost).
        path_denom = max(path_length, self._chop_eps)
        trend = self._signed_sum / path_denom
        abs_trend = min(abs(trend), 1.0)
        incoherence = 1.0 - abs_trend

        effective_sensitivity = self._sensitivity * (1.0 + self._incoherence_boost * incoherence)

        excess = max(0.0, chop_ratio - self._chop_neutral)
        prob = math.exp(-effective_sensitivity * excess)
        prob = max(self._min_prob, prob)

        self.log.debug(
            f"chop_ratio={chop_ratio:.4f} trend={trend:+.4f} incoh={incoherence:.4f} "
            f"eff_sens={effective_sensitivity:.4f} excess={excess:.4f} "
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
        """Route order: submit or skip based on incoherence-sharpened chop gate."""
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
            # Full participation (calm / clean trend / cold start).
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
                f"SKIP {order.client_order_id} (p={p:.4f}, u={u:.4f}, incoh-chop-gated). "
                f"submitted={self._submitted} skipped={self._skipped}."
            )
            # Do NOT call submit_order — quantity invariant preserved.


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_ticks: int = 30,
    chop_neutral: float = 1.5,
    incoherence_boost: float = 1.0,
    sensitivity: float = 1.0,
    min_prob: float = 0.05,
    min_ticks: int = 40,
    chop_eps: float = 1e-9,
    max_chop: float = 20.0,
) -> IncoherenceSharpenedChoppinessSizerAlgorithm:
    """Instantiate the incoherence-sharpened choppiness-gated sizer.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier.
    window_ticks : int
        Rolling window length in quote ticks. Default 30.
    chop_neutral : float
        Baseline chop ratio at/below which p_submit = 1.0. Default 1.5.
    incoherence_boost : float
        Multiplier on (1 - |trend|) applied to baseline sensitivity above
        threshold. Default 1.0 (effective sensitivity doubles at pure
        whipsaw, unchanged at pure trend).
    sensitivity : float
        Baseline exponential decay rate on chop excess. Default 1.0.
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
    config = IncoherenceSharpenedChoppinessSizerConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_ticks=window_ticks,
        chop_neutral=chop_neutral,
        incoherence_boost=incoherence_boost,
        sensitivity=sensitivity,
        min_prob=min_prob,
        min_ticks=min_ticks,
        chop_eps=chop_eps,
        max_chop=max_chop,
    )
    return IncoherenceSharpenedChoppinessSizerAlgorithm(config=config)
