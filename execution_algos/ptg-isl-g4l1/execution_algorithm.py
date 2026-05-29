"""ptg-isl-g4l1: Position-tier-gate + probabilistic spread-band submission decay.

Island experiment — island-0 (base: position-tier-gate), generation 4, loop 1.

Branched from ptg-isl-g1l1 (island-0 lineage best — saturated peak at the
two-axis composition of position-cap + rolling-spread-p75 hard cut). This
loop replaces the binary spread-quantile gate with a STRUCTURALLY NEW
mechanism: a quantity-modulation axis expressed as a probabilistic
submission-decay across the [p_lower, p_upper] spread band.

Hypothesis
----------
Generation 3 closed the third-axis question on ptg with two clean
falsifications (chop in g2, aggressor-flow in g3l1) and a single-knob
spread-quantile retune (g3l2: 0.75 → 0.80) that landed ~1.96% below g1l1.
The gen-3 migration's `base_specific (1)` finding for island-0 is verbatim:

  "STOP stacking skip-axes; try non-quantile knobs on the same stack OR
   quantity-modulation as a new mechanism — open at partial qty when
   spread is in the [p50, p75] band."

We are choosing the quantity-modulation branch over the spread_window_seconds
sweep because window-length is a sibling single-knob retune to g3l2's
quantile retune — it bounds the operating-point peak (low risk) but cannot
exceed g1l1 (low upside, per the gen-3 plateau finding). Quantity-modulation
is a structurally distinct mechanism class (sizing / probabilistic admission
rather than threshold-cut), shown to work cross-island (vrs-isl-g1l1's
chop-decay produced +34% vs base on a different base) and untested on ptg.

The strategy ships integer trade_size=1, so "open at partial qty in the
[p50, p75] band" is implemented as a PROBABILISTIC SUBMIT-DECAY: each
order in the band is admitted with probability p ∈ [min_prob, 1.0], where
p decays linearly with rank-in-window from 1.0 at the lower quantile to
min_prob at the upper quantile. In expectation across many orders, this
reproduces the desired partial-qty exposure to the [p_lower, p_upper] band
while keeping each individual order an integer-contract trade. Above the
upper quantile we keep g1l1's HARD SKIP — the gen-3 g3l2 evidence is that
the [p75, p80] band is empirically EV-negative; we do not re-admit it.

Mechanism (why this should beat g1l1)
-------------------------------------
g1l1 treats the entire [p50, p75] band identically — all admitted at full
size. If conditional EV varies smoothly with spread rank in the band (a
plausible structural assumption: adverse-selection cost grows monotonically
with spread, and the oracle's 30s edge is smooth), then opening at FULL
size at the p70 mark is over-exposing to the high-cost edge of the band
relative to the p55 mark. A linear decay from 1.0 at p_lower to min_prob
at p_upper assigns expected exposure proportional to roughly (1 − rank),
which is the first-order optimal sizing under a linear-EV-decay assumption.
Net effect: shifts expected qty from the costly high-quantile half of the
band toward the cheap low-quantile half, without re-admitting the proven-bad
tail above p_upper.

This is also distinguishable from g3l2's quantile retune in a useful way:
g3l2 moved the threshold (cut depth) and showed the peak is a plateau;
this loop reshapes the function inside the same threshold (cut shape).
If g4l1 also lands within ±2% of g1l1, that is the second axis of evidence
pinning the saturation conclusion — the EV-vs-quantile curve is flat across
[p50, p75], not just at the peak point. If it lifts cleanly, we have
located a new mechanism class on this base.

Composition with the base
-------------------------
- Gate 1 (position-tier-gate, cap=1): unchanged; hard SKIP if abs net
  position >= cap. Reduce-only orders bypass this gate (intraday_flat).
- Gate 2 (probabilistic spread-band decay):
  * If latest spread > p_upper quantile → HARD SKIP (g1l1 behavior).
  * If latest spread <= p_lower quantile → submit prob = 1.0.
  * Otherwise: linear decay
        p_submit = 1.0 - (rank - p_lower) / (p_upper - p_lower) * (1.0 - min_prob)
    Deterministic per-order draw: SHA-256 of client_order_id (vrs-isl-g1l1
    pattern); preserves reproducibility and decouples the draw from
    cross-day RNG state.
- Quantity invariant: each individual order is full-size or unsent; no
  fractional contracts, no order splitting. Participation cap and
  top_of_book_only remain compliant (we only ever submit fewer orders;
  the order itself is untouched).

Falsification line
------------------
If this loop produces vs_base_pnl_pct within ±2% of g1l1's +26.55% (i.e.
[+24.5%, +28.5%]) — the same band g3l2 landed in — the EV-vs-spread-rank
curve is empirically flat across [p_lower, p_upper] and a quantity-modulation
axis on the spread quantile does not lift above the two-axis saturation
peak. If it lifts noticeably (>+28.5%), the new mechanism class works on
this base and g4l2 should retune p_lower / min_prob / decay shape. If it
regresses (<+24.5%), the linear-EV assumption is wrong and an exponential
decay (vrs-style) should be tried before declaring the axis dead.

No look-ahead
-------------
Quote ticks are inserted in chronological replay order; the deque prune
at on_order() uses the order's ts_init, never a future timestamp. The
`_latest_spread` reflects the most recent quote delivered before this
order — strictly in the past.
"""
from __future__ import annotations

import hashlib
import struct
from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PtgIslG4L1Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for ptg-isl-g4l1.

    Parameters
    ----------
    position_cap : int
        Inherited from position-tier-gate. Skip OPEN if absolute net
        position >= position_cap. Default 1 (proven by base / g1l1).
    spread_window_seconds : float
        Rolling window for spread samples (seconds). Default 60.0
        (matches g1l1 / g3l2 — single-knob discipline: we change ONLY
        the gate semantics, not the window).
    spread_quantile_lower : float
        Lower quantile defining the start of the decay band. At/below
        this quantile, p_submit = 1.0 (full participation). Default 0.50
        — splits the surviving (post-p75) band in half by population.
    spread_quantile_upper : float
        Upper quantile defining the end of the decay band AND the hard
        cut. Above this quantile, HARD SKIP (preserves g1l1 / g3l2
        evidence that the [p75, p80] band is EV-negative). Default 0.75
        (matches g1l1's empirical peak).
    min_prob : float
        Floor on submission probability at the upper edge of the decay
        band. Default 0.05 — matches vrs-isl-g1l1's chop-decay floor;
        empirically validated to avoid degenerate gating.
    min_samples : int
        Minimum samples required before either quantile gate fires.
        Below this, all orders submitted (warm-up). Default 50
        (matches g1l1).
    """

    position_cap: int = 1
    spread_window_seconds: float = 60.0
    spread_quantile_lower: float = 0.50
    spread_quantile_upper: float = 0.75
    min_prob: float = 0.05
    min_samples: int = 50


class PtgIslG4L1Algorithm(ExecAlgorithm):
    """Position-tier-gate combined with a probabilistic spread-band submit-decay."""

    def __init__(self, config: PtgIslG4L1Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = int(config.position_cap)
        self._spread_window_ns: int = int(config.spread_window_seconds * 1_000_000_000)
        self._q_lower: float = float(config.spread_quantile_lower)
        self._q_upper: float = float(config.spread_quantile_upper)
        self._min_prob: float = float(config.min_prob)
        self._min_samples: int = int(config.min_samples)

        if not (0.0 < self._q_lower < self._q_upper < 1.0):
            raise ValueError(
                f"Quantile band invalid: lower={self._q_lower}, upper={self._q_upper}; "
                "require 0 < lower < upper < 1."
            )
        if not (0.0 < self._min_prob <= 1.0):
            raise ValueError(f"min_prob must be in (0, 1]; got {self._min_prob}.")

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
            f"PtgIslG4L1Algorithm started "
            f"(position_cap={self._position_cap}, "
            f"spread_window={self._spread_window_ns / 1e9:.1f}s, "
            f"q_lower={self._q_lower:.2f}, q_upper={self._q_upper:.2f}, "
            f"min_prob={self._min_prob:.3f}, min_samples={self._min_samples})."
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
        """Linear-interpolation quantile (same convention as g1l1)."""
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
        uint64; normalized. Pattern reused from vrs-isl-g1l1 — preserves
        reproducibility and decouples the draw from cross-day RNG state.
        """
        digest = hashlib.sha256(order_id_str.encode()).digest()
        val = struct.unpack(">Q", digest[:8])[0]
        return val / (2**64)

    def _spread_submit_prob(self, order) -> float:
        """Return submit probability in [min_prob, 1.0], or 0.0 to HARD SKIP.

        Returns:
          1.0  → submit unconditionally (below p_lower, or warm-up)
          (min_prob, 1.0) → in-band probabilistic decay
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
            return 0.0  # hard skip (g1l1 / g3l2 behavior — proven-bad band)
        if latest <= thr_lower:
            return 1.0  # full participation (cheap-spread half)

        # In-band linear decay from 1.0 at thr_lower to min_prob at thr_upper.
        # Guard against numerically-tight bands.
        span = thr_upper - thr_lower
        if span <= 0.0:
            return 1.0
        frac = (latest - thr_lower) / span  # in (0, 1]
        prob = 1.0 - frac * (1.0 - self._min_prob)
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

        # Gate 2: probabilistic spread-band decay.
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
                f"SUBMIT (decay) {order.client_order_id} "
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
    min_samples: int = 50,
) -> PtgIslG4L1Algorithm:
    config = PtgIslG4L1Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        spread_window_seconds=spread_window_seconds,
        spread_quantile_lower=spread_quantile_lower,
        spread_quantile_upper=spread_quantile_upper,
        min_prob=min_prob,
        min_samples=min_samples,
    )
    return PtgIslG4L1Algorithm(config=config)
