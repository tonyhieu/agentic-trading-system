"""vrs-isl-g3l2 — island-2, generation 3, loop 2.

Adds a **third orthogonal SKIP axis** on top of the vrs-isl-g2l1 chop+spread
two-gate composition (PnL +223.42% vs base — the island-2 lineage best):
**top-of-book size-asymmetry**.

For each OPEN order:
  - Gate A (chop, price-path):     probabilistic skip via chop_ratio
                                   exponential decay (vrs-isl-g1l1 mechanic;
                                   unchanged from g2l1).
  - Gate B (spread, book-state):   hard skip OPEN when latest spread > q75
                                   of the rolling spread distribution
                                   (unchanged from g2l1).
  - Gate C (size-asymmetry, NEW):  skip BUY  when ask_size >= size_asym_ratio * bid_size
                                   skip SELL when bid_size >= size_asym_ratio * ask_size
                                   (latest-quote-only, parity with
                                   ptg-isl-g1l2 / afg-isl-g3l2 contracts).
  - Submit only if ALL THREE gates pass.

Why this design — pivot to option (b) from g3l1's next-list
------------------------------------------------------------
The g2l2 / g3l1 flow-axis attempts (verbatim port at 2c/10s; retune at 6c/4s)
both regressed vs the chop+spread g2l1 lineage best (-30.21% and -16.32%
respectively). g3l1's interpretive verdict was that the aggressor-flow axis
is substantially REDUNDANT with chop+spread on the vrs base — wide-spread
bursts and high-flow events overlap heavily on MES, so adding flow on top
of an already-aggressive chop+spread stack removes informative trades faster
than adverse ones. g3l1's `summary_out.next` explicitly recommended:

  "Pivot to option (b) from g2l2's next-list: implement a top-of-book
  size-asymmetry SKIP gate (bid_size vs ask_size ratio over a short rolling
  window, side-aware) on top of g2l1's chop+spread two-gate. This axis reads
  BOOK STATE, structurally different from the trade-tape pressure axis that
  flow reads, so its redundancy with chop+spread is not pre-determined by
  the same correlation chain that defeated flow here. Implementation should
  start from vrs-isl-g2l1/execution_algorithm.py (NOT g2l2 or g3l1 — their
  flow gates are the falsified mechanism) and add the size-asymmetry gate
  with conservative defaults (ratio threshold ~2.0-3.0, window 5-10s,
  OR-skip composition consistent with the other gates)."

Cross-island gen-3 evidence — STRONG signal this axis transfers
---------------------------------------------------------------
Island-1's g3l2 added exactly this gate (top-of-book size-asymmetry with
size_asym_ratio=1.5, latest-quote-only) on top of its three-gate stack
(spread + chop + base-flow) and produced **+21.59% PnL vs its g2l2 parent**
(3439.50 → 4182.00; +233.05% vs base afg), with sharpe +3.36 absolute and
drawdown tightening 0.36 pp. Trade_count dropped only 3.65% — well inside
the falsification line.

This is the key reason for confidence: island-1's g3l2 falsified the gen-1
migration's "queue imbalance is null" verdict by changing two free variables
(composition partner AND threshold). The axis itself is structurally
distinct from chop (price-path), spread (quote-distance), and flow
(trade-pressure) — it reads book DEPTH. On the vrs base the addition is
even more leveraged: the g2l1 chop+spread stack has NO flow component, so
the size-asymmetry gate is composing against a strictly thinner pre-filter
than island-1's, and the threshold (1.5) is the same operating point that
worked there.

Parameter choice
----------------
- size_asym_ratio = 1.5 — directly matches island-1 g3l2's working
  operating point. g3l1's `next` suggested 2.0-3.0, but island-1 explicitly
  reported 1.5 as the value that produced the gain, and used 1.5
  specifically because g1l2's failing 2.33-equivalent was too loose. The
  cross-island gen-3 evidence dominates the conservative-band suggestion
  from g3l1 (which was written without sight of island-1's result).
- Latest-quote-only semantics (no rolling window) — parity with
  ptg-isl-g1l2 and afg-isl-g3l2; the size-asymmetry gate uses the most
  recent observed bid_size / ask_size from on_quote_tick, not a rolling
  mean. This keeps the gate fast-acting on transient depth asymmetries
  (the structural property that distinguishes it from spread, which IS
  rolling).

Composition semantics
---------------------
- Gate A (chop) remains probabilistic — vrs lineage's working semantic.
  Do NOT convert to binary as island-1 did for chop; on island-2 the
  probabilistic decay IS the working operating point of the chop axis
  (the conversion happened on island-1 only because afg's other gates
  were binary, requiring uniform composition semantics).
- Gate B (spread) and Gate C (size-asym) are hard binary skips.
- Composition: OPEN submits iff (chop probabilistic draw passes) AND
  (spread does not skip) AND (size-asym does not skip). This is the
  natural extension of g2l1's AND-on-submit composition. Reduce-only
  orders bypass all three gates (intraday_flat compliance).
- Quantity invariant: child_qty == parent_qty == 1, always.

Instrumentation
---------------
Per-gate skip counters maintained, with size-asym counts split by side
(BUY/SELL) so a null result vs g2l1 is diagnosable as "gate never fired"
vs "gate fired but EV-neutral" vs "gate fully redundant with chop or
spread". Mandated by gen-1 migration's `what_failed` finding.

Falsification (pre-declared)
----------------------------
- Confirmation: PnL > g2l1 (2437.75) AND drawdown does not widen (>=
  -1.48%) AND trade_count drop <= 10% (>= ~94,219).
- Null: metrics indistinguishable from g2l1 AND counters show size-asym
  gate fires < 0.5% of OPEN evaluations OR co-skips with chop/spread at
  near-100% rate (full redundancy on this base).
- Regression: PnL < g2l1 by > 2% OR trade_count drops > 10% — verdict
  is the size-asym axis is also redundant on vrs (alongside flow),
  meaning the chop+spread g2l1 is the empirical island-2 ceiling and
  g4l1 must pivot to a sizing-side change (participation cap / per-tier
  modulation) rather than a fourth gate.
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


class VrsIslG3L2Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for vrs-isl-g3l2: g2l1 chop+spread + size-asymmetry.

    All g2l1 parameters preserved verbatim. New parameter:

    size_asym_ratio : float
        Top-of-book size-asymmetry threshold. Skip a BUY OPEN when
        ``ask_size >= size_asym_ratio * bid_size`` (contra side dominates);
        skip a SELL OPEN when ``bid_size >= size_asym_ratio * ask_size``.
        Default 1.5 — directly matches island-1 g3l2's working operating
        point (+21.59% vs its g2l2 parent), strictly tighter than
        ptg-isl-g1l2's implied 2.33 (q < 0.30) and within the lower end of
        g1l2's own recommended ``[0.40, 0.60]`` share band.
    """

    # Chop gate (verbatim from vrs-isl-g2l1)
    window_ticks: int = 30
    chop_neutral: float = 1.5
    trend_boost: float = 0.0
    sensitivity: float = 1.0
    min_prob: float = 0.05
    min_ticks: int = 40
    chop_eps: float = 1e-9
    max_chop: float = 20.0

    # Spread gate (verbatim from vrs-isl-g2l1)
    spread_window_seconds: float = 60.0
    spread_quantile: float = 0.75
    min_spread_samples: int = 50

    # Size-asymmetry gate (NEW — third orthogonal axis)
    size_asym_ratio: float = 1.5


class VrsIslG3L2Algorithm(ExecAlgorithm):
    """Probabilistic chop + hard rolling-spread quantile + size-asymmetry gate."""

    def __init__(self, config: VrsIslG3L2Config) -> None:
        super().__init__(config=config)

        # Chop config (verbatim from g2l1)
        self._window_ticks: int = int(config.window_ticks)
        self._chop_neutral: float = float(config.chop_neutral)
        self._trend_boost: float = float(config.trend_boost)
        self._sensitivity: float = float(config.sensitivity)
        self._min_prob: float = float(config.min_prob)
        self._min_ticks: int = int(config.min_ticks)
        self._chop_eps: float = float(config.chop_eps)
        self._max_chop: float = float(config.max_chop)

        # Spread config (verbatim from g2l1)
        self._spread_window_ns: int = int(
            config.spread_window_seconds * 1_000_000_000
        )
        self._spread_quantile: float = float(config.spread_quantile)
        self._min_spread_samples: int = int(config.min_spread_samples)

        # Size-asymmetry config (NEW)
        self._size_asym_ratio: float = float(config.size_asym_ratio)

        # ----- Chop rolling state (unchanged from g2l1) -----
        self._mids: deque[float] = deque(maxlen=self._window_ticks + 1)
        self._signed_deltas: deque[float] = deque(maxlen=self._window_ticks)
        self._path_sum: float = 0.0
        self._signed_sum: float = 0.0
        self._tick_count: int = 0

        # ----- Spread rolling state (unchanged from g2l1) -----
        self._spread_deque: deque[tuple[int, float]] = deque()
        self._latest_spread: float | None = None

        # ----- Size-asymmetry state (NEW — latest top-of-book sizes) -----
        # No rolling history; single-quote-only contract identical to
        # ptg-isl-g1l2 / afg-isl-g3l2. Updated only on well-formed
        # (non-crossed) quotes so a malformed quote does not poison the
        # gate.
        self._latest_bid_size: float | None = None
        self._latest_ask_size: float | None = None

        # Subscription tracking
        self._subscribed: set[str] = set()

        # Per-gate diagnostic counters. The chop and spread gates retain
        # the g2l1 split counters; the size-asym gate is direction-aware
        # so it gets BUY/SELL splits, consistent with afg-isl-g3l2.
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
            f"VrsIslG3L2Algorithm started "
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
            "VrsIslG3L2Algorithm gate counters: "
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
        # (matches g2l1's spread handling and afg-isl-g3l2's contract).
        if spread < 0.0:
            return

        # ----- Chop state update (unchanged from g2l1) -----
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

        # ----- Spread state update (unchanged from g2l1) -----
        self._spread_deque.append((int(tick.ts_event), spread))
        self._latest_spread = spread

        # ----- Size-asymmetry state update (NEW) -----
        # Single-quote-only semantics; no rolling history. Stored only on
        # well-formed (non-crossed) quotes per the early-return guard above.
        self._latest_bid_size = bid_size
        self._latest_ask_size = ask_size

    # ------------------------------------------------------------------
    # Chop-gate probability (unchanged from g2l1)
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
    # Spread-gate hard test (unchanged from g2l1)
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
    # Size-asymmetry gate (NEW — third orthogonal axis)
    # ------------------------------------------------------------------

    def _size_asym_gate_skip(self, order) -> bool:
        """Return True if the contra side massively dominates this side.

        BUY OPEN skipped when ``ask_size >= ratio * bid_size`` (contra
        side thick, our side thin -> likely getting picked off into a
        top-tier liquidity-asymmetry window).
        SELL OPEN skipped when ``bid_size >= ratio * ask_size`` (symmetric).

        Warm-up: if no quote has yet been observed, defer to remaining
        gates (return False). Identical contract to ptg-isl-g1l2 and
        afg-isl-g3l2.
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
    # Deterministic pseudo-random draw (per order) — unchanged from g2l1
    # ------------------------------------------------------------------

    @staticmethod
    def _order_uniform(order_id_str: str) -> float:
        digest = hashlib.sha256(order_id_str.encode()).digest()
        val = struct.unpack(">Q", digest[:8])[0]
        return val / (2**64)

    # ------------------------------------------------------------------
    # Main order handler — compose all three gates
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
    size_asym_ratio: float = 1.5,
) -> VrsIslG3L2Algorithm:
    """Instantiate the chop + rolling-spread + size-asymmetry composed gate sizer.

    Defaults mirror vrs-isl-g2l1 (chop + spread) plus the new
    size-asymmetry gate at ratio 1.5 — directly matching island-1
    g3l2's working operating point (+21.59% PnL vs its g2l2 parent on
    the afg base).

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_ticks : int
        Rolling window length (quote ticks) for chop ratio + signed
        trend. Default 30 (verbatim from g2l1 / vrs-isl-g1l1).
    chop_neutral : float
        Baseline chop ratio at/below which chop p_submit = 1.0.
        Default 1.5 (verbatim from g2l1).
    trend_boost : float
        Multiplier on |trend| added to chop_neutral. Default 0.0 —
        collapses g1l2's trend-reinforcer to a no-op (gen-1 showed
        trend_boost > 0 added ~zero marginal EV).
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
        ``bid_size >= size_asym_ratio * ask_size``. Default 1.5 —
        directly matches island-1 g3l2's working operating point on
        the afg base.
    """
    config = VrsIslG3L2Config(
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
    return VrsIslG3L2Algorithm(config=config)
