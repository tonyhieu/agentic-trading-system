"""Choppiness-gated probabilistic sizer execution algorithm.

Island experiment — island-2 (base: vol-regime-sizer), generation 1, loop 1.

Mechanism: Replace the base sizer's `fast_vol / slow_vol` regime signal with a
**choppiness ratio** computed over a single fast tick window:

    path_length(W)  = sum of |delta_mid_i| over the last W ticks
    displacement(W) = |mid_t - mid_{t-W}|
    chop_ratio(W)   = path_length(W) / max(displacement(W), eps)

Map chop_ratio to submission probability with the same exponential decay form
as the base algo:

    excess   = max(0, chop_ratio - chop_neutral)
    p_submit = max(min_prob, exp(-sensitivity * excess))

A pure trend (consecutive same-sign ticks) has chop_ratio = 1.0 → p = 1.0.
A pure whipsaw (consecutive sign-flipping ticks of equal magnitude) has
displacement → 0 → chop_ratio → ∞ → p = min_prob.

Reduce-only (close) orders are always submitted unconditionally.
Quantity invariant: child_qty == parent_qty == 1, always.

Compared to the base vol-regime-sizer (fast/slow EWM of |delta_mid|): the base
gates on the *magnitude* of recent ticks; this gates on the *directionality*
of recent ticks. Two markets with identical |delta_mid| magnitudes — one
trending, one whipsawing — receive opposite treatment here, identical
treatment under the base.
"""
from __future__ import annotations

import hashlib
import math
import struct
from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class ChoppinessGatedSizerConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the choppiness-gated probabilistic sizer.

    Parameters
    ----------
    window_ticks : int
        Number of recent quote ticks to use for the chop ratio window.
        Default 30 ticks (matches order-of-magnitude of base's fast EWM span).
    chop_neutral : float
        Chop ratio at and below which submission probability is 1.0. A pure
        trend has chop_ratio = 1.0; one reversal in a 4-step window puts
        chop_ratio around 2.0. Setting neutral at 1.5 leaves clean trends
        untouched and starts gating once whipsawing begins. Default 1.5.
    sensitivity : float
        Exponential decay rate on chop excess. p = exp(-sensitivity * (chop - neutral)).
        Default 1.0.
    min_prob : float
        Floor on submission probability. Matches base. Default 0.05.
    min_ticks : int
        Cold-start guard: submit at p=1.0 until this many quote ticks have
        been observed. Should be >= window_ticks so the chop ratio has a
        full window of history. Default 40.
    chop_eps : float
        Lower bound on displacement when computing chop_ratio (guards
        division by zero on perfectly mean-reverting windows). In dollar
        units of mid price. Default 1e-9.
    max_chop : float
        Cap on chop_ratio before applying sensitivity (prevents extreme
        outliers from forcing numeric underflow). Default 20.0.
    """

    window_ticks: int = 30
    chop_neutral: float = 1.5
    sensitivity: float = 1.0
    min_prob: float = 0.05
    min_ticks: int = 40
    chop_eps: float = 1e-9
    max_chop: float = 20.0


class ChoppinessGatedSizerAlgorithm(ExecAlgorithm):
    """Probabilistic submitter gated on tick-window choppiness."""

    def __init__(self, config: ChoppinessGatedSizerConfig) -> None:
        super().__init__(config=config)

        self._window_ticks: int = int(config.window_ticks)
        self._chop_neutral: float = float(config.chop_neutral)
        self._sensitivity: float = float(config.sensitivity)
        self._min_prob: float = float(config.min_prob)
        self._min_ticks: int = int(config.min_ticks)
        self._chop_eps: float = float(config.chop_eps)
        self._max_chop: float = float(config.max_chop)

        # Rolling state.
        # `_mids` keeps the last (window_ticks + 1) mid prices so we can read
        # both the current mid (head) and the mid window_ticks ago (tail) for
        # displacement. `_abs_deltas` keeps the last `window_ticks` per-tick
        # |delta_mid| values; we maintain `_path_sum` incrementally so each
        # tick is O(1).
        self._mids: deque[float] = deque(maxlen=self._window_ticks + 1)
        self._abs_deltas: deque[float] = deque(maxlen=self._window_ticks)
        self._path_sum: float = 0.0
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
            f"ChoppinessGatedSizerAlgorithm started "
            f"(window_ticks={self._window_ticks}, chop_neutral={self._chop_neutral}, "
            f"sensitivity={self._sensitivity}, min_prob={self._min_prob}, "
            f"min_ticks={self._min_ticks})."
        )

    def on_reset(self) -> None:
        self._mids.clear()
        self._abs_deltas.clear()
        self._path_sum = 0.0
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
            abs_delta = abs(mid - prev_mid)

            # Incremental path sum: add new |delta|; subtract the one
            # falling off the back of the window, if any.
            if len(self._abs_deltas) == self._window_ticks:
                self._path_sum -= self._abs_deltas[0]
            self._abs_deltas.append(abs_delta)
            self._path_sum += abs_delta

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

        if len(self._mids) < self._window_ticks + 1 or len(self._abs_deltas) < self._window_ticks:
            # Window not yet filled; treat as calm.
            return 1.0

        path_length = self._path_sum
        displacement = abs(self._mids[-1] - self._mids[0])
        denom = max(displacement, self._chop_eps)
        chop_ratio = min(path_length / denom, self._max_chop)

        excess = max(0.0, chop_ratio - self._chop_neutral)
        prob = math.exp(-self._sensitivity * excess)
        prob = max(self._min_prob, prob)

        self.log.debug(
            f"chop_ratio={chop_ratio:.4f} excess={excess:.4f} "
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
        """Route order: submit or skip based on choppiness-gated probability."""
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
    sensitivity: float = 1.0,
    min_prob: float = 0.05,
    min_ticks: int = 40,
    chop_eps: float = 1e-9,
    max_chop: float = 20.0,
) -> ChoppinessGatedSizerAlgorithm:
    """Instantiate the choppiness-gated probabilistic sizer.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier.
    window_ticks : int
        Rolling window length in quote ticks. Default 30.
    chop_neutral : float
        Chop ratio at/below which p_submit = 1.0. Default 1.5.
    sensitivity : float
        Exponential decay rate on chop excess. Default 1.0.
    min_prob : float
        Floor on submission probability. Default 0.05.
    min_ticks : int
        Cold-start guard before gating activates. Default 40.
    chop_eps : float
        Lower bound on displacement (divide-by-zero guard). Default 1e-9.
    max_chop : float
        Cap on chop_ratio before sensitivity is applied. Default 20.0.
    """
    config = ChoppinessGatedSizerConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_ticks=window_ticks,
        chop_neutral=chop_neutral,
        sensitivity=sensitivity,
        min_prob=min_prob,
        min_ticks=min_ticks,
        chop_eps=chop_eps,
        max_chop=max_chop,
    )
    return ChoppinessGatedSizerAlgorithm(config=config)
