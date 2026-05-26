"""ptg-b-l6: position-tier-gate + adverse-move AND hold-time AND tight-spread.

Single targeted change vs ptg-b-l5: the reversal override now requires a
third condition on top of L5's two -- the **current top-of-book spread
must be tight** (<= 1 MES tick) at the admit moment. L5 used the
conjunction `adverse_mid >= 5 ticks AND age >= 5s` and reached -9.54%
vs base on the 11-date apples-to-apples train window, with marginal
pnl gain over L4 of only $83.50 (~25% of predicted). The L5 brief
summary identified this as the same diminishing-returns shape as the
single-axis adverse-mid sweep, with the same underlying cause: the
two filter dimensions (adverse-mid magnitude and position age) are
strongly positively correlated, so the L5 conjunction often does not
bind.

The L5 next text explicitly proposed pivoting to a genuinely
orthogonal conditioning variable, ranking the spread-not-widened
guard at the admit moment as the highest-leverage candidate. The
reasoning given there:
  - Spread is a fill-cost axis, not a signal-direction axis -- it
    should bind on admits that adverse-mid AND age both pass.
  - An adverse-rich aged reversal can still be expensive to enter if
    the book is thin right then. Crossing a wide spread to flip pays
    the mid-edge away to the spread-crossing cost.
  - A simple 1-tick threshold (skip override if ask - bid > 1 tick)
    is the natural single-step probe.

The hypothesis carried into this loop:
  - L5's residual money-losing admits (+437 vs base, -$340 aggregate)
    are concentrated on flips that happen during wide-spread micro-
    regimes where the mid-edge gets paid to the spread crossing cost.
  - Adding a third orthogonal condition `current_spread <= 1 tick`
    should filter those out, in a way the two correlated dimensions
    (adverse-mid, age) cannot.
  - The expectation is a modest but meaningful pnl improvement (+$50
    to +$150) on a small trade_count drop (-50 to -250 trades),
    closing the residual gap to base from -9.54% toward -5% or
    better.

In-flight diagnostics planned in advance:
  - If L6 pnl improves vs L5 with trade_count moving toward or
    slightly below base, the spread axis is truly orthogonal and
    filtering on the right variable.
  - If L6 pnl is approximately flat vs L5 with trade_count similar
    to L5, spread at admit time is also correlated with adverse-mid
    (a position 5-ticks underwater after 5s tends to sit in a
    thin-book regime by default), and L7 should pivot to signed
    aggressor imbalance on the most recent N trades.
  - If L6 pnl regresses with trade_count dropping materially below
    base, the 1-tick threshold is too strict and is throwing out
    beneficial admits in addition to losers; L7 should bracket back
    to 2 ticks.

Lineage:
  L1 (age-only, 5s):                       -75.33% vs base, +13.25% trades
  L2 (adverse, 1 tick):                    -41.30% vs base,  +9.80% trades
  L3 (adverse, 3 ticks):                   -22.29% vs base,  +2.42% trades
  L4 (adverse, 5 ticks):                   -11.88% vs base,  +0.84% trades
  L5 (5 ticks AND 5s):                      -9.54% vs base,  +0.59% trades
  L6 (5 ticks AND 5s AND spread <= 1 tick): ???

The third condition strictly tightens the predicate vs L5 (every L6
admit is also a valid L5 admit; L6 is a strict subset). So
trade_count must be <= L5's trade_count and below or close to base's
trade_count is likely. Whether the pnl moves up or down depends on
the conditional money-making rate of admits that survive all three
filters vs admits dropped by adding the spread guard.
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


class PtgBL6Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for ptg-b-l6.

    Parameters
    ----------
    position_cap : int
        Same semantics as base position-tier-gate. Default 1.
    adverse_threshold_ticks : float
        Minimum adverse mid-price move (in MES ticks of 0.25) since the
        existing position was opened, required to admit a reversal OPEN
        through the cap. Default 5.0 ticks (= $1.25 in price), inherited
        unchanged from L5.
    min_age_ns : int
        Minimum hold-age in nanoseconds for the currently-held position
        before a reversal override may fire. Default 5_000_000_000
        (5 seconds), inherited unchanged from L5.
    max_spread_ticks : float
        Maximum allowed spread (ask - bid) in MES ticks at the admit
        moment for the reversal override to fire. **Default 1.0 ticks
        (= $0.25 in price)** -- the new dimension added in L6 vs L5.
        One tick is the tightest possible spread for MES; this enforces
        the override only fires when the book is at its tightest.
    tick_size : float
        Price increment per tick. Default 0.25 (MES).
    """

    position_cap: int = 1
    adverse_threshold_ticks: float = 5.0
    min_age_ns: int = _DEFAULT_MIN_AGE_NS
    max_spread_ticks: float = 1.0
    tick_size: float = _MES_TICK_SIZE


class PtgBL6Algorithm(ExecAlgorithm):
    """position-tier-gate with adverse-move AND hold-time AND tight-spread.

    For each incoming order:
      * Reduce-only:                                  SUBMIT.
      * Open, below cap:                              SUBMIT.
      * Open, at/above cap, SAME direction:           SKIP (matches base).
      * Open, at/above cap, REVERSAL:
          - If adverse_mid >= threshold
            AND age >= min_age
            AND spread <= max_spread:                 SUBMIT (override).
          - Else:                                     SKIP (matches base on
                                                            noise/fresh/wide).

    Adverse-move convention:
      - LONG  position: adverse = entry_mid - current_mid  (price fell).
      - SHORT position: adverse = current_mid - entry_mid  (price rose).
      Adverse >= 0 means the position is sitting on (or near) a loss.

    Age convention: order.ts_init - position.ts_opened, in nanoseconds.
    Both attributes are general Nautilus API and strictly past at the
    moment on_order() fires (the new order has not been submitted yet).

    Spread convention: best ask - best bid from the cached quote tick.
    Skip override if spread > max_spread (the wide-spread regime).

    Diagnostic counters: submitted_normal, submitted_reversal_override,
    skipped_same_dir, skipped_reversal_no_adverse,
    skipped_reversal_fresh, skipped_reversal_wide_spread,
    skipped_reversal_no_quote.

    Gate order inside the reversal branch: no-quote -> adverse -> age ->
    spread -> submit. Adverse and age first to preserve direct
    comparability with L4's and L5's counter buckets; spread is the
    last and newest gate so its counter cleanly isolates the L6
    incremental filter effect.
    """

    def __init__(self, config: PtgBL6Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        self._adverse_threshold: float = (
            config.adverse_threshold_ticks * config.tick_size
        )
        self._min_age_ns: int = config.min_age_ns
        self._max_spread: float = config.max_spread_ticks * config.tick_size
        self._tick_size: float = config.tick_size

        # Diagnostic counters
        self._submitted_normal: int = 0
        self._submitted_reversal_override: int = 0
        self._skipped_same_dir: int = 0
        self._skipped_reversal_no_adverse: int = 0
        self._skipped_reversal_fresh: int = 0
        self._skipped_reversal_wide_spread: int = 0
        self._skipped_reversal_no_quote: int = 0

        # Idempotent quote subscription guard
        self._subscribed_instruments: set = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            "PtgBL6Algorithm started "
            f"(position_cap={self._position_cap} contracts, "
            f"adverse_threshold={self._adverse_threshold:.4f} "
            f"= {self._adverse_threshold / self._tick_size:.2f} ticks, "
            f"min_age={self._min_age_ns / 1e9:.2f}s, "
            f"max_spread={self._max_spread:.4f} "
            f"= {self._max_spread / self._tick_size:.2f} ticks)."
        )

    def on_reset(self) -> None:
        self._submitted_normal = 0
        self._submitted_reversal_override = 0
        self._skipped_same_dir = 0
        self._skipped_reversal_no_adverse = 0
        self._skipped_reversal_fresh = 0
        self._skipped_reversal_wide_spread = 0
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

    def _current_quote_components(self, instrument_id):
        """Return (bid, ask, mid, spread) or None tuple if unavailable.

        Returns:
            tuple[float, float, float, float] | None
        """
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

        # Reversal at/above cap. Apply adverse-move AND age AND tight-spread.
        quote_components = self._current_quote_components(order.instrument_id)
        if quote_components is None:
            # Defensive: no quote means we cannot evaluate adverse-move
            # or spread. Fall back to base behavior (skip) -- do NOT admit
            # the reversal without evidence.
            self._skipped_reversal_no_quote += 1
            return
        _bid, _ask, current_mid, current_spread = quote_components

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

        # First check: adverse-mid threshold (matches L4/L5).
        if adverse < self._adverse_threshold:
            self._skipped_reversal_no_adverse += 1
            self.log.debug(
                f"SKIP {order.client_order_id} (reversal w/o adverse: "
                f"adverse={adverse:.4f} < {self._adverse_threshold:.4f}, "
                f"pos={pos_side.name}@{entry_price:.4f}, mid={current_mid:.4f})."
            )
            return

        # Second check: hold-time floor on the existing position (matches L5).
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

        # Third check (new in L6): tight-spread floor at the admit moment.
        if current_spread > self._max_spread:
            self._skipped_reversal_wide_spread += 1
            self.log.debug(
                f"SKIP {order.client_order_id} (reversal wide spread: "
                f"spread={current_spread:.4f} > {self._max_spread:.4f}, "
                f"adverse={adverse:.4f} >= {self._adverse_threshold:.4f}, "
                f"age={age_ns / 1e9:.2f}s >= {self._min_age_ns / 1e9:.2f}s, "
                f"pos={pos_side.name})."
            )
            return

        # All three conditions hold: adverse mid AND matured position AND
        # tight spread. Submit the reversal override.
        self._submitted_reversal_override += 1
        self.log.debug(
            f"SUBMIT {order.client_order_id} (reversal override: "
            f"adverse={adverse:.4f} = {adverse / self._tick_size:.2f} ticks "
            f">= {self._adverse_threshold:.4f}, "
            f"age={age_ns / 1e9:.2f}s >= {self._min_age_ns / 1e9:.2f}s, "
            f"spread={current_spread:.4f} <= {self._max_spread:.4f}, "
            f"pos={pos_side.name}@{entry_price:.4f}, mid={current_mid:.4f}). "
            f"counts: norm={self._submitted_normal} "
            f"rev_ovr={self._submitted_reversal_override} "
            f"skip_same={self._skipped_same_dir} "
            f"skip_rev_no_adv={self._skipped_reversal_no_adverse} "
            f"skip_rev_fresh={self._skipped_reversal_fresh} "
            f"skip_rev_wide={self._skipped_reversal_wide_spread} "
            f"skip_rev_no_q={self._skipped_reversal_no_quote}"
        )
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    adverse_threshold_ticks: float = 5.0,
    min_age_ns: int = _DEFAULT_MIN_AGE_NS,
    max_spread_ticks: float = 1.0,
    tick_size: float = _MES_TICK_SIZE,
) -> PtgBL6Algorithm:
    """Instantiate the ptg-b-l6 position-tier-gate + adverse-AND-age-AND-spread override."""
    config = PtgBL6Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        adverse_threshold_ticks=adverse_threshold_ticks,
        min_age_ns=min_age_ns,
        max_spread_ticks=max_spread_ticks,
        tick_size=tick_size,
    )
    return PtgBL6Algorithm(config=config)
