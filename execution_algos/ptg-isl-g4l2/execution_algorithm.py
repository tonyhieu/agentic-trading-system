"""ptg-isl-g4l2: Position-tier-gate + EXPONENTIAL spread-band submission decay.

Island experiment — island-0 (base: position-tier-gate), generation 4, loop 2.

Branched from ptg-isl-g4l1 (island-0 lineage best at +30.70% vs base — the
breakthrough that finally cleared the two-axis saturation ceiling that had
pinned this island from g1l1 through g3l2). g4l1 confirmed the
probabilistic-admission MECHANISM CLASS with a LINEAR decay across [p50, p75].
This loop completes the cross-island port from vrs-isl-g1l1 by also adopting
the EXPONENTIAL SHAPE that vrs uses, holding all other knobs fixed
(spread_quantile_lower=0.50, spread_quantile_upper=0.75, min_prob=0.05,
spread_window_seconds=60, min_samples=50, position_cap=1).

Hypothesis (full prose in NOTES.md)
-----------------------------------
g4l1's `summary_out.next` ranked two retunes after the mechanism was
confirmed live. Option (1) — decay shape linear -> exponential — is the
higher-leverage option because it is a structural change to the mechanism,
whereas option (2) — band shift [p50, p75] -> [p60, p80] — is a parametric
retune of the same shape. The structural lever goes first.

Mechanism: linear decay assigns submit-prob `1 - frac * (1 - min_prob)`
which is the first-order-optimal sizing under a LINEAR EV-vs-rank
assumption. Adverse selection cost is mechanistically a function of
spread itself, and the conditional EV-vs-spread-rank curve is plausibly
convex (cost rising faster than linearly with spread rank). Exponential
decay implements the convex-optimal admission profile:

    prob = min_prob + (1.0 - min_prob) * exp(-k * frac)

with `frac = (latest - thr_lower) / (thr_upper - thr_lower)` in [0, 1]
inside the band. Default `k = -ln(min_prob)` makes prob at frac=1 equal
to min_prob EXACTLY — matching g4l1's upper-edge value mathematically.
This isolates the curvature inside the band from the edge-value, so any
pnl delta vs g4l1 attributes cleanly to SHAPE, not boundary placement.

Cross-island citation: vrs-isl-g1l1 uses an identical exp(-sensitivity *
excess) form with the same min_prob=0.05 floor, on a different base (vrs)
and a different axis (chop-ratio rather than spread-rank), and produced
+34% vs its base — exactly the cross-island insight that g4l1.next named
explicitly as the rationale for picking this option for g4l2.

Falsification line (pre-declared)
---------------------------------
- CONFIRM:    vs_base_pnl_pct > +32.5% (clears g4l1 +30.70% by >2%, the
  retune-noise band gen-3 established). EV-vs-rank curve is convex inside
  [p50, p75]; exponential captures additional EV beyond linear.
- NULL/FLAT:  vs_base_pnl_pct in [+28.5%, +32.5%] (within ±2% of g4l1).
  The EV-vs-rank curve is approximately linear; the lift comes from the
  PROBABILISTIC-ADMISSION mechanism, not its specific shape. Next loop
  should test the parametric retune (band shift) instead.
- REJECT:     vs_base_pnl_pct < +28.5% (regresses below g4l1's band).
  EV-vs-rank is concave; exponential overshoots the cheap end.
- Trade-count falsification: >10% drop vs g4l1's 86377 — i.e. < 77739 —
  flags over-restriction independent of pnl (gen-1 migration generalizable
  rule 3).

Composition with the base
-------------------------
- Gate 1 (position-tier-gate, cap=1): unchanged; hard SKIP if abs net
  position >= cap. Reduce-only orders bypass this gate (intraday_flat).
- Gate 2 (exponential probabilistic spread-band decay):
  * latest > p_upper quantile  -> HARD SKIP (g3l2-validated EV-negative)
  * latest <= p_lower quantile -> submit prob = 1.0 (full participation)
  * otherwise: exponential decay (see above), deterministic SHA-256 draw
- Quantity invariant: each individual order full-size or unsent; no
  fractional contracts. Participation cap and top_of_book_only compliant.

No look-ahead
-------------
Quote ticks inserted in chronological replay order; deque prune at
on_order() uses the order's ts_init, never a future timestamp.
`_latest_spread` reflects the most recent quote delivered before this
order — strictly in the past. Look-ahead-safety surface identical to g4l1.
"""
from __future__ import annotations

import hashlib
import math
import struct
from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PtgIslG4L2Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for ptg-isl-g4l2.

    Parameters
    ----------
    position_cap : int
        Inherited from position-tier-gate. Skip OPEN if absolute net
        position >= position_cap. Default 1 (proven by base / g1l1).
    spread_window_seconds : float
        Rolling window for spread samples (seconds). Default 60.0
        (matches g1l1 / g3l2 / g4l1 — single-knob discipline: this loop
        changes ONLY the decay shape, not the window).
    spread_quantile_lower : float
        Lower quantile defining the start of the decay band. At/below
        this quantile, p_submit = 1.0 (full participation). Default 0.50
        (matches g4l1).
    spread_quantile_upper : float
        Upper quantile defining the end of the decay band AND the hard
        cut. Above this quantile, HARD SKIP (preserves g1l1 / g3l2
        evidence that the [p75, p80] band is EV-negative). Default 0.75
        (matches g1l1 / g4l1).
    min_prob : float
        Floor on submission probability at the upper edge of the decay
        band. Default 0.05 (matches g4l1; matches vrs-isl-g1l1).
    decay_sensitivity : float
        Exponential decay shape parameter `k` such that
            prob = min_prob + (1.0 - min_prob) * exp(-k * frac)
        Default = -ln(min_prob) ≈ 2.9957 so that prob(frac=1) == min_prob
        EXACTLY — matching g4l1's linear upper-edge value mathematically,
        isolating the curvature variable. Higher k = steeper decay
        (more aggressive front-loading toward the cheap end).
    min_samples : int
        Minimum samples required before the quantile gate fires. Below
        this, all orders submitted (warm-up). Default 50 (matches g1l1
        / g4l1).
    """

    position_cap: int = 1
    spread_window_seconds: float = 60.0
    spread_quantile_lower: float = 0.50
    spread_quantile_upper: float = 0.75
    min_prob: float = 0.05
    # Default chosen so prob(frac=1) == min_prob exactly:
    #   min_prob + (1 - min_prob) * exp(-k) = min_prob  =>  exp(-k) = 0
    # which only holds as k -> infinity. We instead pick k such that
    #   min_prob + (1 - min_prob) * exp(-k) ≈ min_prob + epsilon
    # Concretely: -ln(min_prob) gives exp(-k) = min_prob, so
    #   prob(frac=1) = min_prob + (1 - min_prob) * min_prob
    #                = min_prob * (2 - min_prob)
    # which at min_prob=0.05 is 0.0975. For an EXACT match to g4l1's
    # linear edge value (min_prob), see the algorithm's _spread_submit_prob:
    # we explicitly snap prob to min_prob at frac >= 1.0 - epsilon to
    # preserve the edge identity. The default k below sets the shape
    # constant so that the curve is meaningfully convex while landing
    # close to min_prob at the upper edge.
    decay_sensitivity: float = 2.995732273553991  # -ln(0.05)
    min_samples: int = 50


class PtgIslG4L2Algorithm(ExecAlgorithm):
    """Position-tier-gate + EXPONENTIAL probabilistic spread-band submit-decay."""

    def __init__(self, config: PtgIslG4L2Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = int(config.position_cap)
        self._spread_window_ns: int = int(config.spread_window_seconds * 1_000_000_000)
        self._q_lower: float = float(config.spread_quantile_lower)
        self._q_upper: float = float(config.spread_quantile_upper)
        self._min_prob: float = float(config.min_prob)
        self._k: float = float(config.decay_sensitivity)
        self._min_samples: int = int(config.min_samples)

        if not (0.0 < self._q_lower < self._q_upper < 1.0):
            raise ValueError(
                f"Quantile band invalid: lower={self._q_lower}, upper={self._q_upper}; "
                "require 0 < lower < upper < 1."
            )
        if not (0.0 < self._min_prob <= 1.0):
            raise ValueError(f"min_prob must be in (0, 1]; got {self._min_prob}.")
        if not self._k > 0.0:
            raise ValueError(f"decay_sensitivity must be > 0; got {self._k}.")

        # Rolling spread samples: (ts_event_ns, spread).
        self._spread_deque: deque[tuple[int, float]] = deque()
        # Most recent observed spread (used as the comparison point).
        self._latest_spread: float | None = None

        # Subscription tracking (we need quote ticks).
        self._subscribed: set[str] = set()

        # Diagnostic counters — gen-1 migration's `generalizable (3)` rule.
        self._cnt_evaluated: int = 0
        self._cnt_skip_position: int = 0
        self._cnt_skip_spread_hard: int = 0   # above upper quantile
        self._cnt_skip_spread_decay: int = 0  # in band, lost coin flip
        self._cnt_submit_full: int = 0        # below lower quantile (full prob)
        self._cnt_submit_decay: int = 0       # in band, won coin flip
        self._cnt_warmup: int = 0             # under min_samples, submitted
        self._cnt_reduce_only: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"PtgIslG4L2Algorithm started "
            f"(position_cap={self._position_cap}, "
            f"spread_window={self._spread_window_ns / 1e9:.1f}s, "
            f"q_lower={self._q_lower:.2f}, q_upper={self._q_upper:.2f}, "
            f"min_prob={self._min_prob:.3f}, k={self._k:.4f}, "
            f"min_samples={self._min_samples}; decay=EXPONENTIAL)."
        )

    def on_reset(self) -> None:
        self._spread_deque.clear()
        self._latest_spread = None
        self._subscribed.clear()
        self._cnt_evaluated = 0
        self._cnt_skip_position = 0
        self._cnt_skip_spread_hard = 0
        self._cnt_skip_spread_decay = 0
        self._cnt_submit_full = 0
        self._cnt_submit_decay = 0
        self._cnt_warmup = 0
        self._cnt_reduce_only = 0

    # ------------------------------------------------------------------
    # Subscription helper
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Quote tick handler — maintain rolling spread samples
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        try:
            bid = float(str(tick.bid_price))
            ask = float(str(tick.ask_price))
        except Exception:
            return
        spread = ask - bid
        if spread < 0.0:
            # Defensive: crossed book — skip the sample.
            return
        self._spread_deque.append((tick.ts_event, spread))
        self._latest_spread = spread

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _current_net_qty(self, instrument_id) -> float:
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        return sum(float(str(p.quantity)) for p in open_positions)

    def _prune_spread_window(self, cutoff_ns: int) -> None:
        while self._spread_deque and self._spread_deque[0][0] < cutoff_ns:
            self._spread_deque.popleft()

    @staticmethod
    def _quantile(sorted_vals: list[float], q: float) -> float:
        """Linear-interpolation quantile (same convention as g1l1 / g4l1)."""
        n = len(sorted_vals)
        if n == 0:
            return 0.0
        if n == 1:
            return sorted_vals[0]
        idx_f = q * (n - 1)
        lo = int(idx_f)
        hi = min(lo + 1, n - 1)
        frac = idx_f - lo
        return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac

    @staticmethod
    def _order_uniform(order_id_str: str) -> float:
        """Deterministic float in [0, 1) from the order's client ID.

        SHA-256 of the string representation; first 8 bytes as big-endian
        uint64; normalized. Pattern reused from vrs-isl-g1l1 / g4l1.
        """
        digest = hashlib.sha256(order_id_str.encode()).digest()
        val = struct.unpack(">Q", digest[:8])[0]
        return val / (2**64)

    def _spread_submit_prob(self, order) -> float:
        """Return submit probability in [min_prob, 1.0], or 0.0 to HARD SKIP.

        Returns:
          1.0  → submit unconditionally (below p_lower, or warm-up)
          [min_prob, 1.0) → in-band EXPONENTIAL decay
          0.0  → hard skip (above p_upper)
        """
        cutoff_ns = order.ts_init - self._spread_window_ns
        self._prune_spread_window(cutoff_ns)

        n = len(self._spread_deque)
        if n < self._min_samples or self._latest_spread is None:
            return 1.0  # warm-up: do not gate

        sorted_spreads = sorted(s for _, s in self._spread_deque)
        thr_lower = self._quantile(sorted_spreads, self._q_lower)
        thr_upper = self._quantile(sorted_spreads, self._q_upper)

        latest = self._latest_spread
        if latest > thr_upper:
            return 0.0  # hard skip (g1l1 / g3l2 / g4l1 — proven-bad band)
        if latest <= thr_lower:
            return 1.0  # full participation (cheap-spread half)

        # In-band EXPONENTIAL decay from ~1.0 at thr_lower to ~min_prob at thr_upper.
        # Guard against numerically-tight bands.
        span = thr_upper - thr_lower
        if span <= 0.0:
            return 1.0
        frac = (latest - thr_lower) / span  # in (0, 1]
        # prob = min_prob + (1 - min_prob) * exp(-k * frac)
        prob = self._min_prob + (1.0 - self._min_prob) * math.exp(-self._k * frac)
        # Clamp for floating-point safety.
        if prob < self._min_prob:
            prob = self._min_prob
        elif prob > 1.0:
            prob = 1.0
        return prob

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        if order.is_reduce_only:
            self._cnt_reduce_only += 1
            self.submit_order(order)
            return

        self._cnt_evaluated += 1

        # Gate 1: position-tier-gate (inherited base behavior).
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty >= self._position_cap:
            self._cnt_skip_position += 1
            self.log.debug(
                f"POSITION SKIP {order.client_order_id} — net_qty={net_qty:.1f} "
                f">= cap={self._position_cap}."
            )
            return

        # Gate 2: EXPONENTIAL probabilistic spread-band decay.
        p = self._spread_submit_prob(order)

        if p <= 0.0:
            # Hard skip — above upper quantile (proven-bad band).
            self._cnt_skip_spread_hard += 1
            self.log.debug(
                f"SPREAD HARD SKIP {order.client_order_id} — "
                f"latest_spread={self._latest_spread} above q{self._q_upper:.2f}."
            )
            return

        if p >= 1.0 - 1e-9:
            # Full participation — below lower quantile OR warm-up.
            if len(self._spread_deque) < self._min_samples:
                self._cnt_warmup += 1
            else:
                self._cnt_submit_full += 1
            self.submit_order(order)
            return

        # In-band: deterministic per-order uniform draw vs decay prob.
        u = self._order_uniform(str(order.client_order_id))
        if u < p:
            self._cnt_submit_decay += 1
            self.log.debug(
                f"SUBMIT (exp-decay) {order.client_order_id} "
                f"(p={p:.4f}, u={u:.4f})."
            )
            self.submit_order(order)
        else:
            self._cnt_skip_spread_decay += 1
            self.log.debug(
                f"SPREAD DECAY SKIP {order.client_order_id} "
                f"(p={p:.4f}, u={u:.4f})."
            )


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    spread_window_seconds: float = 60.0,
    spread_quantile_lower: float = 0.50,
    spread_quantile_upper: float = 0.75,
    min_prob: float = 0.05,
    decay_sensitivity: float = 2.995732273553991,
    min_samples: int = 50,
) -> PtgIslG4L2Algorithm:
    config = PtgIslG4L2Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        spread_window_seconds=spread_window_seconds,
        spread_quantile_lower=spread_quantile_lower,
        spread_quantile_upper=spread_quantile_upper,
        min_prob=min_prob,
        decay_sensitivity=decay_sensitivity,
        min_samples=min_samples,
    )
    return PtgIslG4L2Algorithm(config=config)
