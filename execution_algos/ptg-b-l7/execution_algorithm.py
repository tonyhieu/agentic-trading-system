"""ptg-b-l7: position-tier-gate + adverse AND age AND tight-spread AND aggressor-flow.

Single targeted change vs ptg-b-l6: the reversal override now requires a
**fourth** condition on top of L6's three -- aggressor flow over the most
recent 1-second window of trade ticks must AGREE with the proposed NEW
direction at >= 60% same-side volume. L6 reached -1.91% vs base on the
11-date apples-to-apples train window with marginal pnl gain over L5 of
+$272 (+8.43%) on -286 trades (-0.39%), 10/11 dates improved with 1/11
exact match. The L6 brief summary identified two natural directions:
(i) one more genuinely-orthogonal structural conditioner (aggressor
flow) or (ii) tune an existing knob (relax spread to 2 ticks). It
recommended (i) -- aggressor flow -- because the residual gap to base
(-$68, -1.91%) is so small that any same-axis sweep has negligible
expected upside, while adding a truly orthogonal axis is the only
mechanism that can close or invert the gap.

The hypothesis carried into this loop:
  - The remaining money-losing admits in L6 (the 151 trades over base
    that produce -$68 aggregate) are flips where adverse-mid, age, and
    spread all pass but the FLOW direction at admit time disagrees
    with the proposed new direction. Example: a LONG position is
    5-ticks underwater after 5 seconds with a 1-tick spread, but the
    most recent 1s of trades shows aggressor BUYING dominating
    (suggesting the long should be held, not flipped to short).
  - Adding a flow-agreement filter should remove those discordant
    flips while preserving the concordant ones.
  - The expectation is a small but meaningful pnl improvement (+$10
    to +$80) on a small trade-count drop (-50 to -200), potentially
    closing or crossing the residual -$68 gap to base.

Aggressor-flow definitions:
  - Lookback window: 1 second (matches L5's age scale; balances
    signal smoothing against staleness on a 30s oracle horizon).
  - Aggregation: signed volume per trade tick. BUYER aggressor =
    +size, SELLER aggressor = -size, NO_AGGRESSOR = 0.
  - Agreement test: for a proposed BUY reversal, require
    sum(signed) > 0 AND sum(signed) / sum(abs(signed)) >= 0.60.
    For a proposed SELL reversal, require sum(signed) < 0 AND
    -sum(signed) / sum(abs(signed)) >= 0.60.
  - Defensive fall-through: if no trades in window (warm-up or
    quiet period), SKIP the override (do not admit reversal without
    flow evidence). Choice mirrors the L6 no-quote behavior --
    absence of evidence is not evidence of presence; the L6 next
    text explicitly identified the residual losers as flips lacking
    flow confirmation, so an empty window is the same failure mode
    as a discordant window.

In-flight diagnostics planned in advance:
  - If L7 pnl improves vs L6 with trade_count moving toward or
    below base, the flow axis is genuinely orthogonal to the
    (adverse, age, spread) trio -- the residual gap is closing
    via a fourth real dimension. Highest-leverage outcome.
  - If L7 pnl matches L6 closely (within +/-$20) with trade_count
    similar to L6, aggressor flow is correlated with adverse-mid
    at admit time (a position 5-ticks underwater AFTER 5 seconds
    likely had the original-side aggressor flow already turn
    against it during that 5s -- meaning flow is downstream of the
    adverse move, not orthogonal to it). The axis is exhausted at
    this conjunction depth; L8 should pivot to (ii) tune the
    spread knob to 2 ticks instead.
  - If L7 pnl regresses with trade_count dropping materially below
    L6, the 60% agreement threshold is too strict and is throwing
    out beneficial admits in addition to losers; L8 should bracket
    back to 51% (any majority).
  - If L7 pnl regresses with trade_count similar to L6, the
    flow-agreement filter is admitting different trades that lose
    more on average than the L6 trades it removed -- evidence the
    flow direction is anti-predictive on this oracle and L8
    should freeze L6 and stop adding conjunctions.

Lineage:
  L1 (age-only, 5s):                       -75.33% vs base, +13.25% trades
  L2 (adverse, 1 tick):                    -41.30% vs base,  +9.80% trades
  L3 (adverse, 3 ticks):                   -22.29% vs base,  +2.42% trades
  L4 (adverse, 5 ticks):                   -11.88% vs base,  +0.84% trades
  L5 (5 ticks AND 5s):                      -9.54% vs base,  +0.59% trades
  L6 (5 ticks AND 5s AND spread <= 1 tick): -1.91% vs base,  +0.20% trades
  L7 (... AND flow_agreement >= 60%):       ???

The fourth condition strictly tightens the predicate vs L6 (every L7
admit is also a valid L6 admit; L7 is a strict subset). So
trade_count must be <= L6's 73,953 and below base (73,802) is
plausible. Whether pnl moves up or down depends on the conditional
money-making rate of admits surviving all four filters vs admits
dropped by adding the flow-agreement guard.
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


class PtgBL7Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for ptg-b-l7.

    Parameters
    ----------
    position_cap : int
        Same semantics as base position-tier-gate. Default 1.
    adverse_threshold_ticks : float
        Minimum adverse mid-price move (in MES ticks) since entry to admit
        a reversal OPEN. Default 5.0 (inherited from L4/L5/L6).
    min_age_ns : int
        Minimum hold-age (ns) for the existing position before reversal
        override may fire. Default 5_000_000_000 (inherited from L5/L6).
    max_spread_ticks : float
        Maximum allowed spread (ticks) at admit moment for reversal
        override. Default 1.0 (inherited from L6).
    flow_window_ns : int
        Lookback window (ns) over which signed aggressor volume is summed
        to evaluate flow direction. **Default 1_000_000_000 (1 second)** --
        the new dimension added in L7 vs L6.
    flow_agreement_min : float
        Minimum fraction in [0, 1] of same-side aggressor volume required
        for the flow to AGREE with the proposed reversal direction.
        Default 0.60 (modest majority; not a supermajority that would
        collapse to ~zero admits in noisy windows).
    tick_size : float
        Price increment per tick. Default 0.25 (MES).
    """

    position_cap: int = 1
    adverse_threshold_ticks: float = 5.0
    min_age_ns: int = _DEFAULT_MIN_AGE_NS
    max_spread_ticks: float = 1.0
    flow_window_ns: int = _DEFAULT_FLOW_WINDOW_NS
    flow_agreement_min: float = 0.60
    tick_size: float = _MES_TICK_SIZE


class PtgBL7Algorithm(ExecAlgorithm):
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

    def __init__(self, config: PtgBL7Config) -> None:
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
            "PtgBL7Algorithm started "
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

        # Gate 1: adverse-mid (matches L4/L5/L6).
        if adverse < self._adverse_threshold:
            self._skipped_reversal_no_adverse += 1
            return

        # Gate 2: hold-time floor (matches L5/L6).
        age_ns = order.ts_init - position.ts_opened
        if age_ns < self._min_age_ns:
            self._skipped_reversal_fresh += 1
            return

        # Gate 3: tight-spread floor (matches L6).
        if current_spread > self._max_spread:
            self._skipped_reversal_wide_spread += 1
            return

        # Gate 4 (new in L7): aggressor-flow agreement with proposed side.
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
    max_spread_ticks: float = 1.0,
    flow_window_ns: int = _DEFAULT_FLOW_WINDOW_NS,
    flow_agreement_min: float = 0.60,
    tick_size: float = _MES_TICK_SIZE,
) -> PtgBL7Algorithm:
    """Instantiate the ptg-b-l7 four-condition position-tier-gate override."""
    config = PtgBL7Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        adverse_threshold_ticks=adverse_threshold_ticks,
        min_age_ns=min_age_ns,
        max_spread_ticks=max_spread_ticks,
        flow_window_ns=flow_window_ns,
        flow_agreement_min=flow_agreement_min,
        tick_size=tick_size,
    )
    return PtgBL7Algorithm(config=config)
