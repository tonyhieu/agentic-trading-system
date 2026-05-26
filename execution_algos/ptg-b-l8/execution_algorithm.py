"""ptg-b-l8: position-tier-gate + adverse AND age AND spread<=2 AND aggressor-flow.

FINAL loop of the brief-summary arm. Single targeted KNOB change vs
ptg-b-l7: relax the spread guard from 1 tick (MES minimum) to 2 ticks.
Predicate becomes
  `adverse_mid >= 5 ticks AND age >= 5s AND spread <= 2 ticks AND flow_agreement >= 60%`.
Everything else (adverse 5-tick threshold, 5s age, 60% / 1s flow
agreement, on_trade_tick handler, defensive skips, counters) is
byte-identical to L7.

Why this knob, why this direction, why now (per L7's brief-summary next
text):

  L7 was the smallest gap of the 7-loop lineage (-0.72% vs base,
  -$25.50 aggregate) -- decisively short of base but within the
  noise floor of a single bad date. The L7 brief summary identified
  two natural directions for L8:
    (i) add a sixth orthogonal axis on top of the 4-axis predicate.
        The L1-L7 marginal-pnl shape ($1213, $677, $371, $83.50,
        $272, $42.50) shows clear exhaustion; a sixth axis is most
        likely to drift pnl +/-$20 with no clear theoretical
        mechanism for crossover. Low expected upside.
    (ii) TUNE the spread knob from 1 tick to 2 ticks.

  L7 recommended (ii). Mechanism:
    - L5->L6 was -$272 pnl on -286 trades = -$0.95/trade for the
      wide-spread admits L6 removed at the 1-tick threshold.
    - Relaxing to 2 ticks would re-admit ~150-250 of those trades
      (some are 1.25-1.5 tick spreads, some are 1.75-2.0).
    - The flow-agreement filter (now in place since L7) is
      hypothesized to screen the worst flow-disagree admits among
      the re-admitted batch.
    - Hypothetical gain: ~+$143 if half of L6's -$272 batch is
      re-admitted at zero net pnl (the flow guard screens the
      losers but not the negative-EV-by-spread admits). $143
      hypothetical > $25.50 residual gap, so the theoretical
      mechanism for crossing base exists.

  The bet: at the L6/L7 conjunction depth, the 1-tick spread guard
  was over-tightened to compensate for the missing flow filter.
  With the flow filter now in place, a wider spread tolerance
  becomes safe because the worst wide-spread admits (those with
  flow disagreement) are screened by gate 4 rather than gate 3.

In-flight diagnostics planned in advance (for the post-hoc note
since this is the final loop -- no L9):

  - If L8 pnl crosses base (>= $3,565), the relaxed-spread + flow
    combination is the right structure. The L6 spread-guard
    tightness was over-fitted to the absence of the flow filter.
    The arm BEAT base. Highest-leverage outcome.
  - If L8 pnl is in the band ($3,520, $3,565) -- between L7 and
    base -- the relaxation is partially compensating. The flow
    filter is screening some but not all wide-spread admit losers.
    The arm matched base within noise.
  - If L8 pnl is flat with L7 (within +/-$30 of $3,538.75) and
    trade_count climbs modestly (+50 to +200 vs L7), the flow
    filter is doing exactly the work the spread guard was doing,
    and relaxation neither helps nor hurts. The arm saturated
    at L6/L7 level.
  - If L8 pnl drops below L7 ($3,480 or lower) with trade_count
    climbing >+0.5% vs base, the flow filter cannot rescue the
    wide-spread admits. The 1-tick guard was right; L7 is the
    arm's best result. Regression of -$60 or more would suggest
    the flow filter is anti-correlated with the wide-spread
    losers (i.e. wide-spread reversals tend to coincide with
    flow agreement, masking their bad expected value).

Lineage:
  L1 (age-only, 5s):                              -75.33% vs base, +13.25% trades
  L2 (adverse, 1 tick):                           -41.30% vs base,  +9.80% trades
  L3 (adverse, 3 ticks):                          -22.29% vs base,  +2.42% trades
  L4 (adverse, 5 ticks):                          -11.88% vs base,  +0.84% trades
  L5 (5 ticks AND 5s):                             -9.54% vs base,  +0.59% trades
  L6 (5 ticks AND 5s AND spread <= 1 tick):        -1.91% vs base,  +0.20% trades
  L7 (... AND flow_agreement >= 60%):              -0.72% vs base,  +0.08% trades
  L8 (... AND spread <= 2 ticks instead of 1):     ???

Subset/superset structure vs L6 and L7 (mechanistic clarity):
  - Strict subset of L4's admit set: every L8 admit is an L4 admit
    (adverse and age both hold), and L4 is the union of L5/L6/L7/L8.
  - Strict SUPERSET of L7's admit set: every L7 admit is an L8 admit
    (flow agree holds; spread <= 1 implies spread <= 2). So
    trade_count(L8) >= trade_count(L7) = 73,861. Whether trade_count
    crosses base (73,802) is determined by L7 already being above.
  - The set of admits in L8 but not L7 is exactly:
    {flow agrees AND adverse >= 5 AND age >= 5 AND 1 < spread <= 2}.
    These are the "newly re-admitted" trades the hypothesis bets on.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide, PositionSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


# MES tick size in price units.
_MES_TICK_SIZE: float = 0.25

# Default min age in nanoseconds (5 seconds).
_DEFAULT_MIN_AGE_NS: int = 5 * 1_000_000_000

# Default flow lookback in nanoseconds (1 second).
_DEFAULT_FLOW_WINDOW_NS: int = 1 * 1_000_000_000


class PtgBL8Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for ptg-b-l8.

    Parameters
    ----------
    position_cap : int
        Same semantics as base position-tier-gate. Default 1.
    adverse_threshold_ticks : float
        Minimum adverse mid-price move (in MES ticks) since entry to admit
        a reversal OPEN. Default 5.0 (inherited from L4/L5/L6/L7).
    min_age_ns : int
        Minimum hold-age (ns) for the existing position before reversal
        override may fire. Default 5_000_000_000 (inherited from L5/L6/L7).
    max_spread_ticks : float
        Maximum allowed spread (ticks) at admit moment for reversal
        override. **Default 2.0** -- the SINGLE knob change vs L7 (was
        1.0 in L6/L7). Relaxes the spread guard to admit reversals with
        1.25-2.0-tick spreads that L7 was screening out.
    flow_window_ns : int
        Lookback window (ns) over which signed aggressor volume is summed
        to evaluate flow direction. Default 1_000_000_000 (1 second),
        inherited from L7.
    flow_agreement_min : float
        Minimum fraction in [0, 1] of same-side aggressor volume required
        for the flow to AGREE with the proposed reversal direction.
        Default 0.60 (inherited from L7; modest majority).
    tick_size : float
        Price increment per tick. Default 0.25 (MES).
    """

    position_cap: int = 1
    adverse_threshold_ticks: float = 5.0
    min_age_ns: int = _DEFAULT_MIN_AGE_NS
    max_spread_ticks: float = 2.0
    flow_window_ns: int = _DEFAULT_FLOW_WINDOW_NS
    flow_agreement_min: float = 0.60
    tick_size: float = _MES_TICK_SIZE


class PtgBL8Algorithm(ExecAlgorithm):
    """position-tier-gate with adverse AND age AND tight-spread AND flow-agreement.

    For each incoming order:
      * Reduce-only:                              SUBMIT.
      * Open, below cap:                          SUBMIT.
      * Open, at/above cap, SAME direction:       SKIP (matches base).
      * Open, at/above cap, REVERSAL:
          - If adverse_mid   >= threshold
            AND age          >= min_age
            AND spread       <= max_spread
            AND flow_agree   >= flow_agreement_min:  SUBMIT (override).
          - Else:                                    SKIP.

    Reversal-direction flow agreement (for the proposed NEW direction):
      * BUY  reversal (flipping from SHORT->LONG):
          require sum(signed_vol) > 0
          AND   sum(signed_vol) / sum(abs(signed_vol)) >= flow_agreement_min
      * SELL reversal (flipping from LONG->SHORT):
          require sum(signed_vol) < 0
          AND  -sum(signed_vol) / sum(abs(signed_vol)) >= flow_agreement_min

    Empty / no-flow window  -> SKIP (no evidence -> default to base skip).

    Maintains a deque of (ts_event_ns, signed_vol) over a rolling window
    pruned at each evaluation against (order.ts_init - flow_window_ns).
    No look-ahead: only trade ticks with ts_event <= order.ts_init are in
    the deque at decision time (replay is strictly chronological).
    """

    def __init__(self, config: PtgBL8Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        self._adverse_threshold: float = (
            config.adverse_threshold_ticks * config.tick_size
        )
        self._min_age_ns: int = config.min_age_ns
        self._max_spread: float = config.max_spread_ticks * config.tick_size
        self._flow_window_ns: int = config.flow_window_ns
        self._flow_agreement_min: float = config.flow_agreement_min
        self._tick_size: float = config.tick_size

        # Rolling signed-flow deque: (ts_event_ns, signed_vol)
        self._flow_deque: deque[tuple[int, float]] = deque()

        # Diagnostic counters
        self._submitted_normal: int = 0
        self._submitted_reversal_override: int = 0
        self._skipped_same_dir: int = 0
        self._skipped_reversal_no_adverse: int = 0
        self._skipped_reversal_fresh: int = 0
        self._skipped_reversal_wide_spread: int = 0
        self._skipped_reversal_no_flow: int = 0
        self._skipped_reversal_flow_disagree: int = 0
        self._skipped_reversal_no_quote: int = 0

        # Idempotent subscription guard
        self._subscribed_instruments: set = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            "PtgBL8Algorithm started "
            f"(position_cap={self._position_cap} contracts, "
            f"adverse_threshold={self._adverse_threshold:.4f} "
            f"= {self._adverse_threshold / self._tick_size:.2f} ticks, "
            f"min_age={self._min_age_ns / 1e9:.2f}s, "
            f"max_spread={self._max_spread:.4f} "
            f"= {self._max_spread / self._tick_size:.2f} ticks, "
            f"flow_window={self._flow_window_ns / 1e9:.2f}s, "
            f"flow_agreement_min={self._flow_agreement_min:.2f})."
        )

    def on_reset(self) -> None:
        self._flow_deque.clear()
        self._submitted_normal = 0
        self._submitted_reversal_override = 0
        self._skipped_same_dir = 0
        self._skipped_reversal_no_adverse = 0
        self._skipped_reversal_fresh = 0
        self._skipped_reversal_wide_spread = 0
        self._skipped_reversal_no_flow = 0
        self._skipped_reversal_flow_disagree = 0
        self._skipped_reversal_no_quote = 0
        self._subscribed_instruments = set()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        """Subscribe to quote and trade ticks once per instrument."""
        if instrument_id in self._subscribed_instruments:
            return
        try:
            self.subscribe_quote_ticks(instrument_id)
        except Exception as exc:  # noqa: BLE001
            self.log.warning(
                f"Quote subscription failed for {instrument_id}: {exc}"
            )
        try:
            self.subscribe_trade_ticks(instrument_id)
        except Exception as exc:  # noqa: BLE001
            self.log.warning(
                f"Trade subscription failed for {instrument_id}: {exc}"
            )
        self._subscribed_instruments.add(instrument_id)

    def _current_open_position(self, instrument_id):
        """Return the single open position for this instrument, or None."""
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return None
        return open_positions[0]

    def _current_quote_components(self, instrument_id):
        """Return (bid, ask, mid, spread) or None tuple if unavailable."""
        quote = self.cache.quote_tick(instrument_id)
        if quote is None:
            return None
        try:
            bid = float(str(quote.bid_price))
            ask = float(str(quote.ask_price))
        except Exception:  # noqa: BLE001
            return None
        mid = 0.5 * (bid + ask)
        spread = ask - bid
        return (bid, ask, mid, spread)

    def _prune_flow_window(self, cutoff_ns: int) -> None:
        """Drop deque entries with ts_event < cutoff_ns. O(k) where k=expired."""
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            self._flow_deque.popleft()

    def _flow_agreement(self, proposed_side: OrderSide, now_ns: int):
        """Return (agreed: bool, has_flow: bool, frac: float).

        agreed: True iff there is at least some signed volume in window AND
                same-side fraction >= flow_agreement_min.
        has_flow: True iff sum(abs(signed_vol)) > 0 (warm-up / quiet check).
        frac:   Same-side volume fraction (0..1). Defined as 0 when no flow.
        """
        cutoff_ns = now_ns - self._flow_window_ns
        self._prune_flow_window(cutoff_ns)

        if not self._flow_deque:
            return (False, False, 0.0)

        net = 0.0
        total_abs = 0.0
        for _ts, signed in self._flow_deque:
            net += signed
            total_abs += abs(signed)

        if total_abs <= 0.0:
            # All NO_AGGRESSOR ticks -- treat as no flow evidence.
            return (False, False, 0.0)

        if proposed_side == OrderSide.BUY:
            # Want net > 0 (buying aggression dominates).
            if net <= 0.0:
                return (False, True, 0.0)
            frac = net / total_abs
        else:  # SELL
            if net >= 0.0:
                return (False, True, 0.0)
            frac = (-net) / total_abs

        return (frac >= self._flow_agreement_min, True, frac)

    # ------------------------------------------------------------------
    # Trade tick handler -- update rolling signed-flow deque
    # ------------------------------------------------------------------

    def on_trade_tick(self, tick) -> None:
        try:
            size = float(str(tick.size))
        except Exception:  # noqa: BLE001
            return
        aggressor = tick.aggressor_side
        if aggressor == AggressorSide.BUYER:
            signed_vol = size
        elif aggressor == AggressorSide.SELLER:
            signed_vol = -size
        else:
            signed_vol = 0.0
        self._flow_deque.append((tick.ts_event, signed_vol))

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        # Reduce-only (close) orders always execute -- intraday_flat.
        if order.is_reduce_only:
            self.submit_order(order)
            return

        self._ensure_subscribed(order.instrument_id)

        position = self._current_open_position(order.instrument_id)

        if position is None:
            self._submitted_normal += 1
            self.submit_order(order)
            return

        net_qty = float(str(position.quantity))
        if net_qty < self._position_cap:
            self._submitted_normal += 1
            self.submit_order(order)
            return

        # Cap hit. Classify reversal vs same-direction add.
        pos_side = position.side
        order_side = order.side
        is_reversal = (
            (order_side == OrderSide.SELL and pos_side == PositionSide.LONG)
            or (order_side == OrderSide.BUY and pos_side == PositionSide.SHORT)
        )

        if not is_reversal:
            self._skipped_same_dir += 1
            return

        # Reversal at/above cap. Four gates: adverse, age, spread, flow.
        quote_components = self._current_quote_components(order.instrument_id)
        if quote_components is None:
            self._skipped_reversal_no_quote += 1
            return
        _bid, _ask, current_mid, current_spread = quote_components

        try:
            entry_price = float(str(position.avg_px_open))
        except Exception:  # noqa: BLE001
            self._skipped_reversal_no_quote += 1
            return

        if pos_side == PositionSide.LONG:
            adverse = entry_price - current_mid
        else:
            adverse = current_mid - entry_price

        # Gate 1: adverse-mid (matches L4/L5/L6/L7).
        if adverse < self._adverse_threshold:
            self._skipped_reversal_no_adverse += 1
            return

        # Gate 2: hold-time floor (matches L5/L6/L7).
        age_ns = order.ts_init - position.ts_opened
        if age_ns < self._min_age_ns:
            self._skipped_reversal_fresh += 1
            return

        # Gate 3: spread guard (RELAXED in L8 from 1 tick -> 2 ticks).
        if current_spread > self._max_spread:
            self._skipped_reversal_wide_spread += 1
            return

        # Gate 4 (inherited from L7): aggressor-flow agreement with proposed side.
        agreed, has_flow, frac = self._flow_agreement(order_side, order.ts_init)
        if not has_flow:
            self._skipped_reversal_no_flow += 1
            self.log.debug(
                f"SKIP {order.client_order_id} (reversal no-flow window; "
                f"deque_len={len(self._flow_deque)})."
            )
            return
        if not agreed:
            self._skipped_reversal_flow_disagree += 1
            self.log.debug(
                f"SKIP {order.client_order_id} (reversal flow disagree: "
                f"frac={frac:.3f} < {self._flow_agreement_min:.3f}, "
                f"side={order_side.name})."
            )
            return

        # All four conditions hold: submit the reversal override.
        self._submitted_reversal_override += 1
        self.log.debug(
            f"SUBMIT {order.client_order_id} (reversal override: "
            f"adverse={adverse:.4f} = {adverse / self._tick_size:.2f} ticks, "
            f"age={age_ns / 1e9:.2f}s, "
            f"spread={current_spread:.4f}, "
            f"flow_frac={frac:.3f} >= {self._flow_agreement_min:.3f}). "
            f"counts: norm={self._submitted_normal} "
            f"rev_ovr={self._submitted_reversal_override} "
            f"skip_same={self._skipped_same_dir} "
            f"skip_rev_no_adv={self._skipped_reversal_no_adverse} "
            f"skip_rev_fresh={self._skipped_reversal_fresh} "
            f"skip_rev_wide={self._skipped_reversal_wide_spread} "
            f"skip_rev_no_flow={self._skipped_reversal_no_flow} "
            f"skip_rev_flow_dis={self._skipped_reversal_flow_disagree} "
            f"skip_rev_no_q={self._skipped_reversal_no_quote}"
        )
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    adverse_threshold_ticks: float = 5.0,
    min_age_ns: int = _DEFAULT_MIN_AGE_NS,
    max_spread_ticks: float = 2.0,
    flow_window_ns: int = _DEFAULT_FLOW_WINDOW_NS,
    flow_agreement_min: float = 0.60,
    tick_size: float = _MES_TICK_SIZE,
) -> PtgBL8Algorithm:
    """Instantiate the ptg-b-l8 four-condition position-tier-gate override
    (L7 with the spread guard relaxed from 1 tick to 2 ticks)."""
    config = PtgBL8Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        adverse_threshold_ticks=adverse_threshold_ticks,
        min_age_ns=min_age_ns,
        max_spread_ticks=max_spread_ticks,
        flow_window_ns=flow_window_ns,
        flow_agreement_min=flow_agreement_min,
        tick_size=tick_size,
    )
    return PtgBL8Algorithm(config=config)
