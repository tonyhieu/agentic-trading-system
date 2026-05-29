"""vrs-isl-g4l2 — island-2, generation 4, loop 2.

Single-knob retune of the top-of-book size-asymmetry threshold on the
lineage-best three-gate composition (vrs-isl-g3l2 — chop + rolling-spread +
size-asymmetry; PnL +522.30% vs base): **size_asym_ratio 1.5 -> 1.25**
(tightened — contra side must be >= 1.25x this side, instead of >= 1.5x).
All other parameters are frozen verbatim from g3l2; the gate plumbing,
composition semantics, instrumentation counters and reduce-only bypass are
identical. This is a strict single-axis ablation of the size-asymmetry
threshold in the OPPOSITE direction from g4l1 (which loosened to 2.0).

Hypothesis — peak-mapping the size-asym EV curve, tight flank
-------------------------------------------------------------
g4l1 (size_asym_ratio 1.5 -> 2.0) regressed -5.04% vs g3l2 (4454.50 vs
4690.75), and the regression came with a candid diagnostic signal:
is_weighted_bps actually NARROWED on surviving orders (0.0550 vs 0.0585,
-5.89%), yet realized PnL fell. The mechanism is clear: trades sitting in
the [1.5, 2.0] depth-asymmetry band are closer to the body of the
distribution than the tail; loosening admits them, they have negative net
EV, and absolute PnL drops even though average execution quality of the
larger surviving pool improves. This evidence places 1.5 AT OR BELOW the
local size-asymmetry EV peak — the OPPOSITE of what the gen-3 migration's
base_specific (3) reading predicted (the migration suggested the threshold
ported from afg's four-gate composition would be over-restrictive on vrs's
three-gate stack with more headroom; g4l1 falsified that prediction).

g4l1's `summary_out.next` PRIMARY then prescribed the most informative
follow-up move: tighten size_asym_ratio to 1.25, the opposite direction
from g4l1's 2.0. The two outcomes carry distinct, mutually-exclusive
information:

  (i) If 1.25 also regresses vs g3l2 (PnL < 4690.75 by > 2%), the EV peak
      is exactly at or very near 1.5 — both flanks of [1.25, 2.0] would
      then have been bounded as suboptimal, and the gen-3 migration's
      "the working axis transfers cleanly at the SAME threshold"
      generalizable (2) is empirically confirmed on the vrs base.
      Verdict: g3l2 IS the operating-point peak for this composition,
      and any further leverage on island-2 must come from a structurally
      new axis or a sizing-side change, not from this knob.

  (ii) If 1.25 confirms (PnL >= 4690.75 + ~2pp or sharpe ascends),
       1.5 was loose and the true peak sits at or below 1.25. This
       would reveal that the ported afg threshold was a conservative
       under-tune for the vrs base after all (just in the opposite
       direction from the migration's claim), and g4 would not yet
       be at the operating-point peak.

Either outcome maps the local EV curvature with the highest information
per loop. Avoiding 1.75 (the natural bisection of [1.5, 2.0] suggested by
the migration's `next-after-regression` heuristic) is deliberate: that
value bisects a band already known to be suboptimal and would produce a
noisy near-null with low information; tightening to 1.25 widens the sweep
to the symmetric flank and tests the "is 1.5 the peak" hypothesis more
sharply.

Why 1.25 (not, e.g., 1.35 or 1.1)
---------------------------------
- 1.25 is the bottom of g3l2's pre-declared sweep band [1.25, 2.0].
  g4l1 ran the top of that band; running the bottom completes the
  symmetric flanking sweep with maximum information per loop.
- 1.25 sits roughly equidistant from 1.5 on the tight side as 2.0 does
  on the loose side (1.5 / 1.25 = 1.2 vs 2.0 / 1.5 = 1.33), which makes
  the two ablations approximately symmetric on a log-ratio scale and
  therefore directly comparable.
- Below 1.25 (e.g., 1.1) the gate would fire so aggressively that
  trade_count could collapse far past g3l2's already-narrowed surviving
  population — the regression mode would be over-restriction rather
  than mis-tuning, conflating the diagnostic. 1.25 is the lowest value
  where the dominant failure mode (if any) is still EV-bounded
  over-restriction within the same regime, not a categorically
  different one.

Cross-island gen-3 evidence (loaded into context)
-------------------------------------------------
- Migration gen-3 `what_worked`: size-asymmetry at ratio=1.5 transferred
  cleanly across afg and vrs bases — the largest gen-3 lineage gains on
  both islands. The OPERATING POINT generalized.
- Migration gen-3 `generalizable` (2): "the working axis transfers
  cleanly at the SAME threshold when the mechanism is orthogonal." This
  is the proposition g4l1 challenged on the loose flank (FALSIFIED a
  loose retune); g4l2 now challenges on the tight flank.
- Migration gen-3 `base_specific` (3): "the immediate next move is a
  ratio retune in [1.25, 2.0]." g4l1 covered 2.0; g4l2 covers 1.25 to
  complete the band sweep.

Composition semantics — unchanged from g3l2
-------------------------------------------
- Gate A (chop) remains probabilistic via exponential decay on
  chop_ratio (vrs lineage's working semantic).
- Gate B (spread) remains a hard binary skip when latest spread
  exceeds the rolling p75 of the 60s window.
- Gate C (size-asym) remains a hard binary skip when contra-side depth
  >= size_asym_ratio * this-side depth (latest-quote-only).
- All three are evaluated independently; OPEN submits iff ALL gates pass
  (g3l2's AND-on-submit composition).
- Reduce-only orders bypass all three gates (intraday_flat compliance).
- Quantity invariant: child_qty == parent_qty == 1, always.

Instrumentation
---------------
Per-gate skip counters maintained, with size-asym counts split by side
(BUY/SELL) so a null result vs g3l2 is diagnosable as "gate never fired"
vs "gate fired but EV-neutral" vs "gate fully redundant with chop or
spread". All co-skip pairs and the all-three co-skip are counted.
Identical contract to g3l2 / g4l1.

Falsification (pre-declared)
----------------------------
- Confirmation (case (ii)): PnL > 4690.75 + ~2 pp (i.e. > ~4784.5) AND
  sharpe does not deteriorate by > 0.5 absolute AND drawdown does not
  widen by > 0.5 pp. This would reveal the true peak is at or below
  1.25; a follow-up loop should then probe 1.1 to bound the peak
  further on the tight side.
- Bounded regression (case (i)): PnL < 4690.75 by > 2% AND/OR sharpe
  drops > 0.5 absolute. Combined with g4l1's loose-side regression,
  this confirms g3l2 IS the operating-point peak for size_asym_ratio on
  this composition; gen-4 closes the knob-sweep frontier on this base
  and any further leverage requires a structurally new axis or a
  sizing-side change.
- Over-restriction edge case: trade_count drop > 25% vs g3l2 (i.e. <
  ~56,336) without proportional PnL improvement signals the tight flank
  has crossed into pure over-restriction; the regression mode would be
  uninformative for peak-mapping and a follow-up should test 1.35
  rather than 1.1.

What this loop does NOT change (single-knob ablation discipline)
----------------------------------------------------------------
- Chop gate parameters: window_ticks=30, chop_neutral=1.5,
  sensitivity=1.0, min_prob=0.05, min_ticks=40 — frozen.
- Spread gate parameters: spread_window_seconds=60, spread_quantile=0.75,
  min_spread_samples=50 — frozen.
- trend_boost=0.0 — kept disabled (g1l2 falsified its EV positivity).
- Composition semantics — frozen (AND-on-submit; reduce-only bypass).
- Quantity logic — frozen (child==parent).

Lineage parent
--------------
Source code is a verbatim copy of vrs-isl-g3l2/execution_algorithm.py
with three textual changes: class names (VrsIslG3L2{Config,Algorithm} ->
VrsIslG4L2{Config,Algorithm}), the default value of size_asym_ratio
(1.5 -> 1.25), and updated docstring/log prose. There are no code-path
changes.
"""
from __future__ import annotations

import hashlib
import math
import struct
from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class VrsIslG4L2Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for vrs-isl-g4l2: g3l2 chop+spread+size-asym, tightened ratio.

    All g3l2 parameters preserved verbatim. The sole tuned knob:

    size_asym_ratio : float
        Top-of-book size-asymmetry threshold. Skip a BUY OPEN when
        ``ask_size >= size_asym_ratio * bid_size`` (contra side dominates);
        skip a SELL OPEN when ``bid_size >= size_asym_ratio * ask_size``.
        Default 1.25 — tightened from g3l2's 1.5 (which itself was ported
        verbatim from island-1 g3l2). This is the tight-flank counterpart
        to g4l1's loose-flank 2.0 probe; together they bound the local
        EV peak.
    """

    # Chop gate (verbatim from vrs-isl-g3l2 / g2l1)
    window_ticks: int = 30
    chop_neutral: float = 1.5
    trend_boost: float = 0.0
    sensitivity: float = 1.0
    min_prob: float = 0.05
    min_ticks: int = 40
    chop_eps: float = 1e-9
    max_chop: float = 20.0

    # Spread gate (verbatim from vrs-isl-g3l2 / g2l1)
    spread_window_seconds: float = 60.0
    spread_quantile: float = 0.75
    min_spread_samples: int = 50

    # Size-asymmetry gate (RETUNED — tight-flank single-knob ablation)
    size_asym_ratio: float = 1.25


class VrsIslG4L2Algorithm(ExecAlgorithm):
    """Probabilistic chop + hard rolling-spread quantile + size-asymmetry gate (tightened)."""

    def __init__(self, config: VrsIslG4L2Config) -> None:
        super().__init__(config=config)

        # Chop config (verbatim from g3l2)
        self._window_ticks: int = int(config.window_ticks)
        self._chop_neutral: float = float(config.chop_neutral)
        self._trend_boost: float = float(config.trend_boost)
        self._sensitivity: float = float(config.sensitivity)
        self._min_prob: float = float(config.min_prob)
        self._min_ticks: int = int(config.min_ticks)
        self._chop_eps: float = float(config.chop_eps)
        self._max_chop: float = float(config.max_chop)

        # Spread config (verbatim from g3l2)
        self._spread_window_ns: int = int(
            config.spread_window_seconds * 1_000_000_000
        )
        self._spread_quantile: float = float(config.spread_quantile)
        self._min_spread_samples: int = int(config.min_spread_samples)

        # Size-asymmetry config (RETUNED 1.5 -> 1.25)
        self._size_asym_ratio: float = float(config.size_asym_ratio)

        # ----- Chop rolling state (unchanged from g3l2) -----
        self._mids: deque[float] = deque(maxlen=self._window_ticks + 1)
        self._signed_deltas: deque[float] = deque(maxlen=self._window_ticks)
        self._path_sum: float = 0.0
        self._signed_sum: float = 0.0
        self._tick_count: int = 0

        # ----- Spread rolling state (unchanged from g3l2) -----
        self._spread_deque: deque[tuple[int, float]] = deque()
        self._latest_spread: float | None = None

        # ----- Size-asymmetry state (unchanged from g3l2 — latest sizes) -----
        self._latest_bid_size: float | None = None
        self._latest_ask_size: float | None = None

        # Subscription tracking
        self._subscribed: set[str] = set()

        # Per-gate diagnostic counters — identical contract to g3l2.
        self._submitted: int = 0
        self._evaluated: int = 0
        self._skipped_chop_only: int = 0
        self._skipped_spread_only: int = 0
        self._skipped_size_asym_buy: int = 0
        self._skipped_size_asym_sell: int = 0
        # Multi-gate co-skip counters — diagnose redundancy directly.
        self._skipped_chop_and_spread: int = 0
        self._skipped_chop_and_size_asym: int = 0
        self._skipped_spread_and_size_asym: int = 0
        self._skipped_all_three: int = 0
        self._reduce_only_submitted: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"VrsIslG4L2Algorithm started "
            f"(window_ticks={self._window_ticks}, "
            f"chop_neutral={self._chop_neutral}, "
            f"trend_boost={self._trend_boost}, "
            f"sensitivity={self._sensitivity}, "
            f"min_prob={self._min_prob}, "
            f"min_ticks={self._min_ticks}, "
            f"spread_window={self._spread_window_ns / 1e9:.1f}s, "
            f"spread_quantile={self._spread_quantile:.2f}, "
            f"min_spread_samples={self._min_spread_samples}, "
            f"size_asym_ratio={self._size_asym_ratio:.2f})."
        )

    def on_stop(self) -> None:
        """Emit per-gate instrumentation counters for null-result diagnosis."""
        self.log.info(
            "VrsIslG4L2Algorithm gate counters: "
            f"evaluated={self._evaluated}, "
            f"submitted={self._submitted}, "
            f"reduce_only={self._reduce_only_submitted}, "
            f"skip_chop_only={self._skipped_chop_only}, "
            f"skip_spread_only={self._skipped_spread_only}, "
            f"skip_size_asym_buy={self._skipped_size_asym_buy}, "
            f"skip_size_asym_sell={self._skipped_size_asym_sell}, "
            f"skip_chop_and_spread={self._skipped_chop_and_spread}, "
            f"skip_chop_and_size_asym={self._skipped_chop_and_size_asym}, "
            f"skip_spread_and_size_asym={self._skipped_spread_and_size_asym}, "
            f"skip_all_three={self._skipped_all_three}."
        )

    def on_reset(self) -> None:
        self._mids.clear()
        self._signed_deltas.clear()
        self._path_sum = 0.0
        self._signed_sum = 0.0
        self._tick_count = 0

        self._spread_deque.clear()
        self._latest_spread = None

        self._latest_bid_size = None
        self._latest_ask_size = None

        self._subscribed.clear()

        self._submitted = 0
        self._evaluated = 0
        self._skipped_chop_only = 0
        self._skipped_spread_only = 0
        self._skipped_size_asym_buy = 0
        self._skipped_size_asym_sell = 0
        self._skipped_chop_and_spread = 0
        self._skipped_chop_and_size_asym = 0
        self._skipped_spread_and_size_asym = 0
        self._skipped_all_three = 0
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
    # Quote tick handler — maintain all three rolling structures
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        try:
            bid = float(str(tick.bid_price))
            ask = float(str(tick.ask_price))
            bid_size = float(str(tick.bid_size))
            ask_size = float(str(tick.ask_size))
        except Exception:
            return
        mid = (bid + ask) / 2.0
        spread = ask - bid

        # Defensive: a crossed book is dropped from ALL rolling structures
        # (matches g3l2's contract).
        if spread < 0.0:
            return

        # ----- Chop state update (unchanged from g3l2) -----
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

        # ----- Spread state update (unchanged from g3l2) -----
        self._spread_deque.append((int(tick.ts_event), spread))
        self._latest_spread = spread

        # ----- Size-asymmetry state update (unchanged from g3l2) -----
        self._latest_bid_size = bid_size
        self._latest_ask_size = ask_size

    # ------------------------------------------------------------------
    # Chop-gate probability (unchanged from g3l2)
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
    # Spread-gate hard test (unchanged from g3l2)
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
    # Size-asymmetry gate (unchanged plumbing; ratio default tightened)
    # ------------------------------------------------------------------

    def _size_asym_gate_skip(self, order) -> bool:
        """Return True if the contra side dominates this side by >= ratio.

        BUY OPEN skipped when ``ask_size >= ratio * bid_size``.
        SELL OPEN skipped when ``bid_size >= ratio * ask_size``.

        Warm-up: if no quote has yet been observed, defer to remaining
        gates (return False). Identical contract to g3l2.
        """
        bid_size = self._latest_bid_size
        ask_size = self._latest_ask_size
        if bid_size is None or ask_size is None:
            return False
        # Defensive: zero on both sides treated as warm-up (do not fire).
        if bid_size <= 0.0 and ask_size <= 0.0:
            return False

        ratio = self._size_asym_ratio

        if order.side == OrderSide.BUY:
            # Skip BUY when ask is at least `ratio` times the bid.
            if ask_size >= ratio * bid_size and ask_size > 0.0:
                return True
        else:  # SELL
            if bid_size >= ratio * ask_size and bid_size > 0.0:
                return True

        return False

    # ------------------------------------------------------------------
    # Deterministic pseudo-random draw (per order) — unchanged from g3l2
    # ------------------------------------------------------------------

    @staticmethod
    def _order_uniform(order_id_str: str) -> float:
        digest = hashlib.sha256(order_id_str.encode()).digest()
        val = struct.unpack(">Q", digest[:8])[0]
        return val / (2**64)

    # ------------------------------------------------------------------
    # Main order handler — compose all three gates (unchanged from g3l2)
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Compose chop AND spread AND size-asym gates; skip if any fire."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        if order.is_reduce_only:
            self._reduce_only_submitted += 1
            self.log.debug(
                f"Reduce-only {order.client_order_id}: submitting unconditionally."
            )
            self.submit_order(order)
            return

        self._evaluated += 1

        # Evaluate all three gates independently so per-skip combination
        # counters are diagnosable (redundancy vs orthogonality).
        spread_skip = self._spread_gate_skip(order)

        p_chop = self._compute_chop_submit_prob()
        if p_chop >= 1.0 - 1e-9:
            chop_skip = False
            u = 0.0  # unused; full participation
        else:
            u = self._order_uniform(str(order.client_order_id))
            chop_skip = not (u < p_chop)

        size_asym_skip = self._size_asym_gate_skip(order)

        # Triage by which gate combination fires. Order of cases:
        # all-three, three pairwise combos, three singles, then submit.
        if spread_skip and chop_skip and size_asym_skip:
            self._skipped_all_three += 1
            self.log.info(
                f"SKIP {order.client_order_id} (all-three) "
                f"p_chop={p_chop:.4f} u={u:.4f} "
                f"size_asym=({self._latest_bid_size},{self._latest_ask_size})."
            )
            return

        if chop_skip and spread_skip:
            self._skipped_chop_and_spread += 1
            self.log.info(
                f"SKIP {order.client_order_id} (chop+spread) "
                f"p_chop={p_chop:.4f} u={u:.4f}."
            )
            return

        if chop_skip and size_asym_skip:
            self._skipped_chop_and_size_asym += 1
            self.log.info(
                f"SKIP {order.client_order_id} (chop+size_asym) "
                f"p_chop={p_chop:.4f} u={u:.4f} side="
                f"{'BUY' if order.side == OrderSide.BUY else 'SELL'}."
            )
            return

        if spread_skip and size_asym_skip:
            self._skipped_spread_and_size_asym += 1
            self.log.info(
                f"SKIP {order.client_order_id} (spread+size_asym) "
                f"latest_spread>{self._spread_quantile:.2f} side="
                f"{'BUY' if order.side == OrderSide.BUY else 'SELL'}."
            )
            return

        if spread_skip:
            self._skipped_spread_only += 1
            self.log.info(
                f"SKIP {order.client_order_id} (spread-only) "
                f"latest_spread>{self._spread_quantile:.2f} p_chop={p_chop:.4f} u={u:.4f}."
            )
            return

        if chop_skip:
            self._skipped_chop_only += 1
            self.log.info(
                f"SKIP {order.client_order_id} (chop-only) "
                f"p_chop={p_chop:.4f} u={u:.4f}."
            )
            return

        if size_asym_skip:
            if order.side == OrderSide.BUY:
                self._skipped_size_asym_buy += 1
            else:
                self._skipped_size_asym_sell += 1
            self.log.info(
                f"SKIP {order.client_order_id} (size_asym-only) "
                f"bid_size={self._latest_bid_size} ask_size={self._latest_ask_size} "
                f"side={'BUY' if order.side == OrderSide.BUY else 'SELL'}."
            )
            return

        # All three gates passed.
        self._submitted += 1
        self.log.debug(
            f"SUBMIT {order.client_order_id} "
            f"(p_chop={p_chop:.4f}, spread_ok, size_asym_ok)."
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
    size_asym_ratio: float = 1.25,
) -> VrsIslG4L2Algorithm:
    """Instantiate the chop + rolling-spread + size-asymmetry composed gate sizer.

    Defaults mirror vrs-isl-g3l2 verbatim EXCEPT for size_asym_ratio,
    which is tightened from 1.5 to 1.25 — the tight-flank counterpart
    to g4l1's loose-flank 2.0 probe. Together they bound the local EV
    peak of the size-asymmetry knob on this composition.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_ticks : int
        Rolling window length (quote ticks) for chop ratio + signed
        trend. Default 30 (verbatim from g3l2).
    chop_neutral : float
        Baseline chop ratio at/below which chop p_submit = 1.0.
        Default 1.5 (verbatim from g3l2).
    trend_boost : float
        Multiplier on |trend| added to chop_neutral. Default 0.0
        (verbatim from g3l2; g1l2 falsified its EV positivity).
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
    spread_window_seconds : float
        Rolling window for spread samples (seconds). Default 60.0.
    spread_quantile : float
        Quantile threshold for the spread gate; skip OPEN when the
        latest spread is strictly greater than this rolling quantile.
        Default 0.75 — gates the wide-spread tail.
    min_spread_samples : int
        Warm-up: spread gate is a no-op until this many samples have
        been observed in the window. Default 50.
    size_asym_ratio : float
        Top-of-book size-asymmetry threshold. Skip BUY when
        ``ask_size >= size_asym_ratio * bid_size``; skip SELL when
        ``bid_size >= size_asym_ratio * ask_size``. **Default 1.25 —
        tightened from g3l2's 1.5.** This is the tight-flank
        counterpart to g4l1's loose-flank 2.0; the two together bound
        the local EV peak.
    """
    config = VrsIslG4L2Config(
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
        size_asym_ratio=size_asym_ratio,
    )
    return VrsIslG4L2Algorithm(config=config)
