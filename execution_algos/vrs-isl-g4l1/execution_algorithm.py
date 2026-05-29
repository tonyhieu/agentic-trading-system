"""vrs-isl-g4l1 — island-2, generation 4, loop 1.

Single-knob retune of the **vrs-isl-g3l2 lineage tip** (PnL +522.30% vs base,
sharpe 19.11 — the island-2 lineage best): the top-of-book size-asymmetry
threshold is loosened from 1.5 to 2.0.

For each OPEN order:
  - Gate A (chop, price-path):     probabilistic skip via chop_ratio
                                   exponential decay (vrs-isl-g1l1 mechanic;
                                   unchanged from g3l2).
  - Gate B (spread, book-state):   hard skip OPEN when latest spread > q75
                                   of the rolling spread distribution
                                   (unchanged from g3l2).
  - Gate C (size-asymmetry):       RETUNED — skip BUY  when
                                   ask_size >= 2.0 * bid_size
                                   skip SELL when bid_size >= 2.0 * ask_size
                                   (latest-quote-only, side-aware;
                                   threshold raised from 1.5 to 2.0 — gate
                                   becomes strictly LOOSER than g3l2).
  - Submit only if ALL THREE gates pass.

Why this change — gen-3 migration base_specific (3) + island-1 g4l1 null
------------------------------------------------------------------------
g3l2's `summary_out.next` named two strong options for g4l1:
  (a) Retune size_asym_ratio in [1.25, 2.0] specifically against vrs's
      chop+spread base.
  (b) Add a FOURTH orthogonal axis.

The gen-3 migration's `base_specific (3)` finding makes this concrete:

  "vrs accepts size-asymmetry strongly but rejects flow mechanically —
   the chop+spread two-gate base has substantial headroom (the +92.42%
   jump used a single 1.5-threshold size-asymmetry gate), and the
   immediate next move is a ratio retune in [1.25, 2.0] on vrs
   specifically because the threshold was ported from a four-gate
   composition into a three-gate composition with more headroom; the
   marginal gate fires harder here."

Direct cross-island evidence from this generation: island-1 g4l1 chose
option (b) — added a 5th orthogonal axis (signed mid-velocity gate,
0.50 $/s threshold, 5s window) on top of its four-gate composition —
and produced a NULL result: PnL 4180.25 vs g3l2 parent 4182.00 (-0.04%,
inside +/-2% null band), trade_count delta -9 on a ~96k base, sharpe
and drawdown unchanged. The new axis barely fired on the four-gate-
conditioned surviving population. This is empirical evidence that
adding a yet-more-orthogonal axis on top of a heavy stack tends to
inert — pushing toward option (a) (retune) as the higher-information
move this loop.

Why 2.0 specifically (not 1.25 or 1.75)
---------------------------------------
g3l2 is candidly over-restrictive at 1.5: trade_count fell 28.25% vs
g2l1 (the pre-declared <=10% band was busted), and is_weighted_bps
deteriorated +88.1% on surviving orders even though absolute PnL more
than doubled. Both signals indicate the 1.5 threshold removes some
lower-EV trades along with the adverse slice it targets.

  - 1.25 is TIGHTER (more skips) — wrong direction given the trade-
    count / bps evidence.
  - 1.75 is a safer mid-band move; likely small monotonic delta.
  - 2.0 is at the loose end of the recommended band — maximum
    information per loop: largest expected effect size, sharpest
    falsification surface. The migration explicitly characterizes
    vrs's chop+spread base as having "more headroom" and the marginal
    gate as firing "harder here", both phrases pointing toward a value
    materially looser than 1.5.

Parameter choice
----------------
- size_asym_ratio = 2.0 — top of g3l2's recommended [1.25, 2.0] band.
- Everything else verbatim from g3l2: chop (window_ticks=30,
  chop_neutral=1.5, trend_boost=0.0, sensitivity=1.0, min_prob=0.05,
  min_ticks=40, chop_eps=1e-9, max_chop=20.0), spread
  (spread_window_seconds=60.0, spread_quantile=0.75,
  min_spread_samples=50), composition (AND-skip-on-submit;
  reduce-only bypass; child_qty == parent_qty == 1), latest-quote-only
  size-asym contract.

Instrumentation
---------------
Per-gate skip counters + multi-gate co-skip counters from g3l2 are
preserved verbatim — size-asym gate is direction-aware so it keeps
BUY/SELL splits. The co-skip counters specifically diagnose whether
loosening to 2.0 (a) reduces total size-asym skips, (b) shifts skip
mass from "size-asym-only" toward "size-asym + chop" or "size-asym +
spread" co-skips (redundancy diagnostic), or (c) leaves total skips
unchanged because the 1.5-2.0 band has near-zero mass.

Falsification (pre-declared, single-knob ablation against g3l2)
---------------------------------------------------------------
- Confirmation: PnL > 4925 (5% above g3l2 4690.75) AND trade_count >
  85,000 (recover at least a quarter of the 28% drop g3l2 took vs
  g2l1) AND is_weighted_bps < g3l2 (any improvement in per-share cost
  on surviving orders).
- Null: PnL in [4596, 4784] (+/-2% of g3l2) — declare the [1.5, 2.0]
  band a plateau and pivot to option (b) on g4l2.
- Regression: PnL < 4596 (>2% below g3l2) — g3l2 wins; declare 1.5
  the operating point and revert. The interpretive verdict would be
  that the EV-vs-ratio curve drops more sharply on the loose side
  than expected, meaning the adverse-asymmetry mass is concentrated
  in the contra >= 1.5x tail.
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


class VrsIslG4L1Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for vrs-isl-g4l1: g3l2 with size_asym_ratio retuned 1.5 -> 2.0.

    All g3l2 parameters preserved verbatim except:

    size_asym_ratio : float
        Top-of-book size-asymmetry threshold. Skip a BUY OPEN when
        ``ask_size >= size_asym_ratio * bid_size`` (contra side dominates);
        skip a SELL OPEN when ``bid_size >= size_asym_ratio * ask_size``.
        Default 2.0 — top of g3l2's recommended [1.25, 2.0] band, loosened
        from g3l2's 1.5 because g3l2's -28.25% trade-count drop and +88.1%
        is_weighted_bps regression vs g2l1 indicated the 1.5 threshold
        (ported from island-1's four-gate composition) was over-aggressive
        for vrs's lighter three-gate composition.
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

    # Size-asymmetry gate — RETUNED (1.5 -> 2.0)
    size_asym_ratio: float = 2.0


class VrsIslG4L1Algorithm(ExecAlgorithm):
    """Probabilistic chop + hard rolling-spread quantile + size-asymmetry gate.

    Identical to vrs-isl-g3l2 in mechanism and composition; only difference is
    the default size_asym_ratio (1.5 -> 2.0). Counters and lifecycle preserved.
    """

    def __init__(self, config: VrsIslG4L1Config) -> None:
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

        # Size-asymmetry config (RETUNED — only changed knob)
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

        # ----- Size-asymmetry state (unchanged from g3l2 — latest top-of-book sizes) -----
        self._latest_bid_size: float | None = None
        self._latest_ask_size: float | None = None

        # Subscription tracking
        self._subscribed: set[str] = set()

        # Per-gate diagnostic counters (verbatim from g3l2). The size-asym
        # gate is direction-aware so it gets BUY/SELL splits. The co-skip
        # counters specifically diagnose redundancy shifts under the retune.
        self._submitted: int = 0
        self._evaluated: int = 0
        self._skipped_chop_only: int = 0
        self._skipped_spread_only: int = 0
        self._skipped_size_asym_buy: int = 0
        self._skipped_size_asym_sell: int = 0
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
            f"VrsIslG4L1Algorithm started "
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
        """Emit per-gate instrumentation counters for retune diagnosis."""
        self.log.info(
            "VrsIslG4L1Algorithm gate counters: "
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
        # (matches g3l2 / g2l1 spread handling).
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
        # Single-quote-only semantics; no rolling history. Stored only on
        # well-formed (non-crossed) quotes per the early-return guard above.
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
    # Size-asymmetry gate (RETUNED — same mechanism as g3l2, looser threshold)
    # ------------------------------------------------------------------

    def _size_asym_gate_skip(self, order) -> bool:
        """Return True if the contra side massively dominates this side.

        BUY OPEN skipped when ``ask_size >= ratio * bid_size`` (contra
        side thick, our side thin -> likely getting picked off into a
        top-tier liquidity-asymmetry window).
        SELL OPEN skipped when ``bid_size >= ratio * ask_size`` (symmetric).

        Warm-up: if no quote has yet been observed, defer to remaining
        gates (return False). Identical contract to g3l2; only the
        threshold default differs (1.5 -> 2.0).
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
    size_asym_ratio: float = 2.0,
) -> VrsIslG4L1Algorithm:
    """Instantiate the chop + rolling-spread + size-asymmetry composed gate sizer.

    Defaults mirror vrs-isl-g3l2 in every parameter except size_asym_ratio,
    which is loosened from 1.5 to 2.0 — the top of g3l2's recommended
    [1.25, 2.0] band. The retune targets g3l2's candid trade-count and
    is_weighted_bps regressions vs g2l1, which indicate the 1.5 threshold
    (ported from island-1's four-gate composition) was over-aggressive
    for vrs's lighter three-gate composition.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_ticks : int
        Rolling window length (quote ticks) for chop ratio + signed
        trend. Default 30 (verbatim from g3l2 / vrs-isl-g1l1).
    chop_neutral : float
        Baseline chop ratio at/below which chop p_submit = 1.0.
        Default 1.5 (verbatim from g3l2; gen-3 migration confirmed
        base-agnostic).
    trend_boost : float
        Multiplier on |trend| added to chop_neutral. Default 0.0 —
        collapses g1l2's trend-reinforcer to a no-op.
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
        Default 0.75 — gates the wide-spread tail (peak plateau per
        ptg-isl-g3l2's cross-island sweep).
    min_spread_samples : int
        Warm-up: spread gate is a no-op until this many samples have
        been observed in the window. Default 50.
    size_asym_ratio : float
        Top-of-book size-asymmetry threshold. Skip BUY when
        ``ask_size >= size_asym_ratio * bid_size``; skip SELL when
        ``bid_size >= size_asym_ratio * ask_size``. Default 2.0 —
        loosened from g3l2's 1.5 because g3l2 was over-restrictive
        (-28.25% trade-count vs g2l1, +88.1% is_weighted_bps); the
        gen-3 migration's `base_specific (3)` finding explicitly
        recommends a ratio retune in [1.25, 2.0] for vrs.
    """
    config = VrsIslG4L1Config(
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
    return VrsIslG4L1Algorithm(config=config)
