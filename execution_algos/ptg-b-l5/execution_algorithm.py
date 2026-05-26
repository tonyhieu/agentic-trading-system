"""ptg-b-l5: position-tier-gate + adverse-move AND hold-time conjunction.

Single targeted change vs ptg-b-l4: the reversal override now requires
**both** an adverse mid-move of at least 5 ticks AND a position age of
at least 5 seconds. L4 used the adverse-mid axis alone (5-tick floor)
and reached -11.88% vs base on the 11-date apples-to-apples train
window, with trade_count within +/-1% of base (+0.84%, +618 trades).
The L4 brief summary identified that the adverse-mid axis is
approaching exhaustion: each single-step tightening of the threshold
returns diminishing pnl gains ($677 L2->L3 -> $371 L3->L4), and the
residual +618 admitted reversals are still on average money-losing,
so eliminating them via another tick raise would risk dropping
trade_count below base before fully closing the residual gap.

The hypothesis carried into this loop:
  - The age dimension was insufficient on its own (L1, -75.33% vs base
    with +13.25% trades).
  - The adverse-mid dimension is asymptoting (L4, -11.88% with +0.84%
    trades).
  - The CONJUNCTION should filter precisely the admits L4 still gets
    wrong: a 5-tick adverse move with a position that is also at least
    5 seconds old means the position has BOTH matured (so the oracle
    has had time to confirm or disconfirm the original signal) AND
    been wrong by a material amount.
  - The expectation is that this conjunction removes the residual
    money-losing admits while preserving the beneficial ones.

In-flight diagnostics planned in advance:
  - If L5 pnl improves vs L4 with trade_count moving toward or
    slightly below base (-1% to +0.5% delta), the conjunction is
    correctly tightening on the residual losers.
  - If L5 pnl matches L4 closely with trade_count dropping materially
    below base, the hold-time floor is throwing out beneficial admits
    in addition to the losers (age is too long).
  - If L5 pnl regresses vs L4 with trade_count similar to L4, the
    hold-time AND condition is somehow not filtering meaningfully
    (most 5-tick-adverse reversals have already been alive >= 5s by
    the time the adverse move accumulates), and L6 should test the
    other structural conditioners (spread guard, aggressor imbalance).

Lineage:
  L1 (age-only, 5s):     -75.33% vs base, +13.25% trades
  L2 (adverse, 1 tick):  -41.30% vs base,  +9.80% trades
  L3 (adverse, 3 ticks): -22.29% vs base,  +2.42% trades
  L4 (adverse, 5 ticks): -11.88% vs base,  +0.84% trades
  L5 (5 ticks AND 5s):   ???

The conjunction strictly tightens the predicate vs L4 (every L5 admit
is also a valid L4 admit; L5 is a strict subset). So trade_count must
be <= L4's trade_count and < base's trade_count is plausible. Whether
the pnl moves up or down depends on the conditional money-making rate
of admits that survive both filters vs admits dropped by adding the
age conjunction. The base case for the prediction is: the marginal
admit removed is the L4 admit that is adverse-rich but fresh, which
is the case most likely to be a same-tick-flip noise event the oracle
just emitted at the position open. Removing those should raise the
admit win-rate and so the conjunction should improve pnl.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide, PositionSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


# MES tick size in price units.
_MES_TICK_SIZE: float = 0.25

# Default min age in nanoseconds (5 seconds).
_DEFAULT_MIN_AGE_NS: int = 5 * 1_000_000_000


class PtgBL5Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for ptg-b-l5.

    Parameters
    ----------
    position_cap : int
        Same semantics as base position-tier-gate. Default 1.
    adverse_threshold_ticks : float
        Minimum adverse mid-price move (in MES ticks of 0.25) since the
        existing position was opened, required to admit a reversal OPEN
        through the cap. Default 5.0 ticks (= $1.25 in price), inherited
        from L4.
    min_age_ns : int
        Minimum hold-age in nanoseconds for the currently-held position
        before a reversal override may fire. **Default 5_000_000_000
        (5 seconds)** -- the new dimension added in L5 vs L4. Five
        seconds matches L1's age-only choice and gives the strategy's
        30s-horizon oracle enough time (~1/6 of forecast) to either
        confirm or begin disconfirming the original signal.
    tick_size : float
        Price increment per tick. Default 0.25 (MES).
    """

    position_cap: int = 1
    adverse_threshold_ticks: float = 5.0
    min_age_ns: int = _DEFAULT_MIN_AGE_NS
    tick_size: float = _MES_TICK_SIZE


class PtgBL5Algorithm(ExecAlgorithm):
    """position-tier-gate with adverse-move AND hold-time conjunction.

    For each incoming order:
      * Reduce-only:                                  SUBMIT.
      * Open, below cap:                              SUBMIT.
      * Open, at/above cap, SAME direction:           SKIP (matches base).
      * Open, at/above cap, REVERSAL:
          - If adverse_mid >= threshold AND age >= min_age: SUBMIT (override).
          - Else:                                     SKIP (matches base on
                                                            noise/fresh).

    Adverse-move convention:
      - LONG  position: adverse = entry_mid - current_mid  (price fell).
      - SHORT position: adverse = current_mid - entry_mid  (price rose).
      Adverse >= 0 means the position is sitting on (or near) a loss.

    Age convention: order.ts_init - position.ts_opened, in nanoseconds.
    Both attributes are general Nautilus API and strictly past at the
    moment on_order() fires (the new order has not been submitted yet).

    Diagnostic counters: submitted_normal, submitted_reversal_override,
    skipped_same_dir, skipped_reversal_no_adverse,
    skipped_reversal_fresh, skipped_reversal_no_quote.

    The age and adverse filters are tracked separately when they cause a
    skip so the diagnostic mix can be read off the logs after a run.
    When BOTH conditions fail, the adverse-failure counter is incremented
    (higher in the gate order, matching L4's exit order).
    """

    def __init__(self, config: PtgBL5Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        self._adverse_threshold: float = (
            config.adverse_threshold_ticks * config.tick_size
        )
        self._min_age_ns: int = config.min_age_ns
        self._tick_size: float = config.tick_size

        # Diagnostic counters
        self._submitted_normal: int = 0
        self._submitted_reversal_override: int = 0
        self._skipped_same_dir: int = 0
        self._skipped_reversal_no_adverse: int = 0
        self._skipped_reversal_fresh: int = 0
        self._skipped_reversal_no_quote: int = 0

        # Idempotent quote subscription guard
        self._subscribed_instruments: set = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            "PtgBL5Algorithm started "
            f"(position_cap={self._position_cap} contracts, "
            f"adverse_threshold={self._adverse_threshold:.4f} "
            f"= {self._adverse_threshold / self._tick_size:.2f} ticks, "
            f"min_age={self._min_age_ns / 1e9:.2f}s)."
        )

    def on_reset(self) -> None:
        self._submitted_normal = 0
        self._submitted_reversal_override = 0
        self._skipped_same_dir = 0
        self._skipped_reversal_no_adverse = 0
        self._skipped_reversal_fresh = 0
        self._skipped_reversal_no_quote = 0
        self._subscribed_instruments = set()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        """Subscribe to quote ticks once per instrument."""
        if instrument_id in self._subscribed_instruments:
            return
        try:
            self.subscribe_quote_ticks(instrument_id)
        except Exception as exc:  # noqa: BLE001 -- defensive: never block submit
            self.log.warning(
                f"Quote subscription failed for {instrument_id}: {exc}"
            )
        self._subscribed_instruments.add(instrument_id)

    def _current_open_position(self, instrument_id):
        """Return the single open position for this instrument, or None."""
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return None
        # Netting OMS: at most one open position per instrument.
        return open_positions[0]

    def _current_mid(self, instrument_id) -> float | None:
        """Return the current best mid price, or None if no quote available."""
        quote = self.cache.quote_tick(instrument_id)
        if quote is None:
            return None
        try:
            bid = float(str(quote.bid_price))
            ask = float(str(quote.ask_price))
        except Exception:  # noqa: BLE001
            return None
        return 0.5 * (bid + ask)

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

        # No open position OR cap not yet reached -- submit (same as base).
        if position is None:
            self._submitted_normal += 1
            self.submit_order(order)
            return

        net_qty = float(str(position.quantity))
        if net_qty < self._position_cap:
            self._submitted_normal += 1
            self.submit_order(order)
            return

        # Cap hit. Determine whether the incoming order is a reversal
        # (opposite side of the current position) or a same-direction add.
        pos_side = position.side
        order_side = order.side
        is_reversal = (
            (order_side == OrderSide.SELL and pos_side == PositionSide.LONG)
            or (order_side == OrderSide.BUY and pos_side == PositionSide.SHORT)
        )

        if not is_reversal:
            # Same-direction add at/above cap -- preserve base skip.
            self._skipped_same_dir += 1
            return

        # Reversal at/above cap. Apply adverse-move AND hold-time conjunction.
        current_mid = self._current_mid(order.instrument_id)
        if current_mid is None:
            # Defensive: no quote means we cannot evaluate adverse-move.
            # Fall back to base behavior (skip) -- do NOT admit the
            # reversal without evidence.
            self._skipped_reversal_no_quote += 1
            return

        try:
            entry_price = float(str(position.avg_px_open))
        except Exception:  # noqa: BLE001
            # Defensive: missing entry price -> fall back to base skip.
            self._skipped_reversal_no_quote += 1
            return

        if pos_side == PositionSide.LONG:
            adverse = entry_price - current_mid
        else:  # SHORT
            adverse = current_mid - entry_price

        # First check: adverse-mid threshold (matches L4).
        if adverse < self._adverse_threshold:
            self._skipped_reversal_no_adverse += 1
            self.log.debug(
                f"SKIP {order.client_order_id} (reversal w/o adverse: "
                f"adverse={adverse:.4f} < {self._adverse_threshold:.4f}, "
                f"pos={pos_side.name}@{entry_price:.4f}, mid={current_mid:.4f})."
            )
            return

        # Second check (new in L5): hold-time floor on the existing position.
        position_ts_opened = position.ts_opened
        age_ns = order.ts_init - position_ts_opened
        if age_ns < self._min_age_ns:
            self._skipped_reversal_fresh += 1
            self.log.debug(
                f"SKIP {order.client_order_id} (reversal fresh: "
                f"age={age_ns / 1e9:.2f}s < {self._min_age_ns / 1e9:.2f}s, "
                f"adverse={adverse:.4f} >= {self._adverse_threshold:.4f}, "
                f"pos={pos_side.name})."
            )
            return

        # Both conditions hold: adverse mid AND matured position.
        self._submitted_reversal_override += 1
        self.log.debug(
            f"SUBMIT {order.client_order_id} (reversal override: "
            f"adverse={adverse:.4f} = {adverse / self._tick_size:.2f} ticks "
            f">= {self._adverse_threshold:.4f}, "
            f"age={age_ns / 1e9:.2f}s >= {self._min_age_ns / 1e9:.2f}s, "
            f"pos={pos_side.name}@{entry_price:.4f}, mid={current_mid:.4f}). "
            f"counts: norm={self._submitted_normal} "
            f"rev_ovr={self._submitted_reversal_override} "
            f"skip_same={self._skipped_same_dir} "
            f"skip_rev_no_adv={self._skipped_reversal_no_adverse} "
            f"skip_rev_fresh={self._skipped_reversal_fresh} "
            f"skip_rev_no_q={self._skipped_reversal_no_quote}"
        )
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    adverse_threshold_ticks: float = 5.0,
    min_age_ns: int = _DEFAULT_MIN_AGE_NS,
    tick_size: float = _MES_TICK_SIZE,
) -> PtgBL5Algorithm:
    """Instantiate the ptg-b-l5 position-tier-gate + adverse-AND-age override."""
    config = PtgBL5Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        adverse_threshold_ticks=adverse_threshold_ticks,
        min_age_ns=min_age_ns,
        tick_size=tick_size,
    )
    return PtgBL5Algorithm(config=config)
