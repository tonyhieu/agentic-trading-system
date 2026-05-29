"""ptg-f-l2 execution algorithm.

Per-iteration experiment, base_algo `position-tier-gate`, context mode
`full-trace`, loop 2. Starting point: `position-tier-gate` base algo.

Loop 1 finding: position_cap is binary for this oracle+MES combination.
cap=1 = serialized entry = best. cap>=2 = simple baseline = worst.
The cap lever cannot be tuned — cap=1 must be preserved.

Loop 2 adds a **consecutive-loss streak gate** on top of cap=1:
After N consecutive losing closed positions (realized_pnl < 0), the
next open-leg order is skipped (one skip). The skip resets the streak
counter, allowing normal operation immediately after.

Mechanism: losing streaks may correlate with adverse oracle signal quality
phases. Blocking one re-entry after N consecutive losses filters the
highest-adverse-selection re-entry moments.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PositionTierGateL2Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for ptg-f-l2.

    Parameters
    ----------
    position_cap : int
        Maximum net position before gating opens. Default 1 (preserved from base).
    streak_threshold : int
        Number of consecutive losing closes before the next open is skipped.
        Default 2: skip the next open after 2 consecutive losing closes.
    """

    position_cap: int = 1
    streak_threshold: int = 2


class PositionTierGateL2Algorithm(ExecAlgorithm):
    """Position-tier gate (cap=1) + consecutive-loss streak gate.

    Opening orders (is_reduce_only == False):
      - If skip_next_open: SKIP this open (reset flag after skip).
      - If net_qty >= position_cap: SKIP (base behavior).
      - Else: SUBMIT.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately.
      - After submission: read last closed position P&L; update streak counter.
      - If streak reaches threshold: set skip_next_open flag.

    No order quantity is ever modified.
    """

    def __init__(self, config: PositionTierGateL2Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        self._streak_threshold: int = config.streak_threshold
        self._loss_streak: int = 0
        self._skip_next_open: bool = False
        self._n_closed_seen: int = 0  # track how many closes we've processed

    def on_start(self) -> None:
        self.log.info(
            f"PositionTierGateL2Algorithm started "
            f"(position_cap={self._position_cap}, "
            f"streak_threshold={self._streak_threshold})."
        )

    def on_reset(self) -> None:
        self._loss_streak = 0
        self._skip_next_open = False
        self._n_closed_seen = 0

    def _current_net_qty(self, instrument_id) -> float:
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        return sum(float(str(p.quantity)) for p in open_positions)

    def _update_streak_from_closes(self, instrument_id) -> None:
        """Check newly closed positions and update loss streak counter."""
        closed_positions = self.cache.positions_closed(instrument_id=instrument_id)
        n_closed = len(closed_positions)
        if n_closed <= self._n_closed_seen:
            return  # no new closes

        # Process newly closed positions (those beyond what we've seen before)
        new_closes = closed_positions[self._n_closed_seen:]
        self._n_closed_seen = n_closed

        for pos in new_closes:
            realized = float(str(pos.realized_pnl))
            if realized < 0:
                self._loss_streak += 1
                self.log.debug(
                    f"Closed position P&L={realized:.2f} < 0; "
                    f"loss_streak now {self._loss_streak}."
                )
                if self._loss_streak >= self._streak_threshold:
                    self._skip_next_open = True
                    self.log.info(
                        f"Loss streak reached {self._loss_streak} >= "
                        f"threshold {self._streak_threshold}; "
                        f"setting skip_next_open."
                    )
            else:
                self._loss_streak = 0
                self.log.debug(
                    f"Closed position P&L={realized:.2f} >= 0; "
                    f"loss_streak reset to 0."
                )

    def on_order(self, order) -> None:
        """Route order: submit or skip based on position cap + streak gate."""
        instrument_id = order.instrument_id

        if order.is_reduce_only:
            self.submit_order(order)
            # After close, update streak
            self._update_streak_from_closes(instrument_id)
            return

        # Check streak gate first (before position cap)
        if self._skip_next_open:
            self.log.info(
                f"SKIP {order.client_order_id} — loss streak gate "
                f"(skip_next_open=True; streak was {self._loss_streak})."
            )
            self._skip_next_open = False
            self._loss_streak = 0  # reset after skip
            return

        # Position cap gate (base behavior)
        net_qty = self._current_net_qty(instrument_id)
        if net_qty >= self._position_cap:
            self.log.debug(
                f"SKIP {order.client_order_id} — position cap "
                f"(net_qty={net_qty:.1f} >= cap={self._position_cap})."
            )
            return

        self.log.debug(
            f"SUBMIT {order.client_order_id} "
            f"(net_qty={net_qty:.1f} < cap={self._position_cap}, "
            f"streak={self._loss_streak}, skip_next={self._skip_next_open})."
        )
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    streak_threshold: int = 2,
) -> PositionTierGateL2Algorithm:
    """Instantiate and return the PositionTierGateL2Algorithm."""
    config = PositionTierGateL2Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        streak_threshold=streak_threshold,
    )
    return PositionTierGateL2Algorithm(config=config)
