"""ptg-b-l3: position-tier-gate + adverse-move override at 3-tick threshold.

Single mechanical change vs ptg-b-l2: `adverse_threshold_ticks` default
raised from 1.0 to 3.0 ($0.25 -> $0.75 of adverse mid-move required to
admit a reversal OPEN through the position cap). All other logic
(reversal detection, same-direction-add skip, quote subscription, reduce-
only short-circuit) is preserved unchanged.

L2 used a 1-tick adverse threshold and was -41.30% vs base_algo on the
same 11 dates. L2's own hypothesis section flagged that 1 tick admits
bid-ask oscillation as if it were a real reversal signal, and that
prediction matched the data: 7,232 extra admitted reversals were net
money-losing across all 11 dates. L3 raises the bar to 3 full-spread
displacements ($0.75), which represents an adverse mid regime rather
than intra-spread noise. The expected outcome is fewer admitted
reversals (closer to base's trade count of 73,802) with better per-admit
pnl, which should narrow or reverse the vs-base gap. If 3 ticks
collapses to base behavior (no admitted reversals), a later loop will
probe 2 ticks; if 3 ticks still underperforms base, the adverse-mid
proxy is exhausted and a later loop should pivot to a different
conditioning variable.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide, PositionSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


# MES tick size in price units.
_MES_TICK_SIZE: float = 0.25


class PtgBL3Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for ptg-b-l3.

    Parameters
    ----------
    position_cap : int
        Same semantics as base position-tier-gate. Default 1.
    adverse_threshold_ticks : float
        Minimum adverse mid-price move (in MES ticks of 0.25) since the
        existing position was opened, required to admit a reversal OPEN
        through the cap. **Default 3.0 ticks (= $0.75 in price)** -- the
        single mechanical change vs L2, which used 1.0. Three ticks
        require a meaningful adverse regime rather than bid-ask
        oscillation.
    tick_size : float
        Price increment per tick. Default 0.25 (MES).
    """

    position_cap: int = 1
    adverse_threshold_ticks: float = 3.0
    tick_size: float = _MES_TICK_SIZE


class PtgBL3Algorithm(ExecAlgorithm):
    """position-tier-gate with adverse-move override (3-tick threshold).

    For each incoming order:
      * Reduce-only:                          SUBMIT.
      * Open, below cap:                      SUBMIT.
      * Open, at/above cap, SAME direction:   SKIP (matches base).
      * Open, at/above cap, REVERSAL:
          - If adverse mid-move >= threshold: SUBMIT (override).
          - Else:                             SKIP (matches base on noise).

    Adverse-move convention:
      - LONG  position: adverse = entry_mid - current_mid  (price fell).
      - SHORT position: adverse = current_mid - entry_mid  (price rose).
      Adverse >= 0 means the position is sitting on (or near) a loss.

    Diagnostic counters: submitted_normal, submitted_reversal_override,
    skipped_same_dir, skipped_reversal_no_adverse,
    skipped_reversal_no_quote.
    """

    def __init__(self, config: PtgBL3Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        self._adverse_threshold: float = (
            config.adverse_threshold_ticks * config.tick_size
        )
        self._tick_size: float = config.tick_size

        # Diagnostic counters
        self._submitted_normal: int = 0
        self._submitted_reversal_override: int = 0
        self._skipped_same_dir: int = 0
        self._skipped_reversal_no_adverse: int = 0
        self._skipped_reversal_no_quote: int = 0

        # Idempotent quote subscription guard
        self._subscribed_instruments: set = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            "PtgBL3Algorithm started "
            f"(position_cap={self._position_cap} contracts, "
            f"adverse_threshold={self._adverse_threshold:.4f} "
            f"= {self._adverse_threshold / self._tick_size:.2f} ticks)."
        )

    def on_reset(self) -> None:
        self._submitted_normal = 0
        self._submitted_reversal_override = 0
        self._skipped_same_dir = 0
        self._skipped_reversal_no_adverse = 0
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

        # Reversal at/above cap. Apply adverse-move override.
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

        if adverse >= self._adverse_threshold:
            # Mid has moved against the existing position by >= threshold
            # (3 ticks default). Reversal is justified -- override skip.
            self._submitted_reversal_override += 1
            self.log.debug(
                f"SUBMIT {order.client_order_id} (reversal override: "
                f"adverse={adverse:.4f} = {adverse / self._tick_size:.2f} ticks "
                f">= {self._adverse_threshold:.4f}, "
                f"pos={pos_side.name}@{entry_price:.4f}, mid={current_mid:.4f}). "
                f"counts: norm={self._submitted_normal} "
                f"rev_ovr={self._submitted_reversal_override} "
                f"skip_same={self._skipped_same_dir} "
                f"skip_rev_no_adv={self._skipped_reversal_no_adverse} "
                f"skip_rev_no_q={self._skipped_reversal_no_quote}"
            )
            self.submit_order(order)
            return

        # Reversal but no adverse evidence -- treat as noise flip, skip.
        self._skipped_reversal_no_adverse += 1
        self.log.debug(
            f"SKIP {order.client_order_id} (reversal w/o adverse: "
            f"adverse={adverse:.4f} < {self._adverse_threshold:.4f}, "
            f"pos={pos_side.name}@{entry_price:.4f}, mid={current_mid:.4f})."
        )
        # Do NOT call submit_order -- quantity invariant preserved.


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    adverse_threshold_ticks: float = 3.0,
    tick_size: float = _MES_TICK_SIZE,
) -> PtgBL3Algorithm:
    """Instantiate the ptg-b-l3 position-tier-gate + 3-tick adverse-move override."""
    config = PtgBL3Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        adverse_threshold_ticks=adverse_threshold_ticks,
        tick_size=tick_size,
    )
    return PtgBL3Algorithm(config=config)
