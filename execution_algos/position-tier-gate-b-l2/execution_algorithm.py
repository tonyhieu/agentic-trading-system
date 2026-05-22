"""Position-tier-gate-b-l2 execution algorithm.

Per-iteration experiment — arm: base_algo=position-tier-gate,
mode=brief-summary, loop 2. Starting point: `position-tier-gate-b-l1`.

Loop 1 conditioned new OPEN legs on a portfolio-equity circuit breaker:
realized P&L vs an *all-time* session peak; opens were skipped while the
drawdown from that peak exceeded `drawdown_halt`. The loop-1 summary flagged
that this breaker latches one-way — under sigma=200 realized P&L almost never
climbs back above an all-time high, so once tripped the gate stays shut for
the rest of the session. trade_count collapsed to 32,475 (76% below simple),
which distorted Sharpe to -106.

Loop 2 makes the breaker re-arm. Two coupled changes:

  1. Decaying peak reference.
     The peak is no longer a hard all-time maximum. Each closed position pulls
     the reference toward the current realized P&L by a fraction
     `peak_decay` (0.0 = old all-time-peak behaviour; 1.0 = peak always equals
     current P&L, breaker never trips). With peak_decay > 0 a flat losing
     stretch slowly lowers the reference, so the measured drawdown shrinks over
     time and the gate eventually re-arms even without a P&L recovery.

  2. Recovery hysteresis band.
     A latched-skip state with a separate re-arm threshold. Once drawdown
     exceeds `drawdown_halt` the gate latches SKIP; it only unlatches once
     drawdown falls back below `drawdown_rearm` (< drawdown_halt). This
     prevents the gate chattering open/shut tick-by-tick around a single
     threshold while still guaranteeing it reopens after a partial recovery.

Both mechanisms attack the same loop-1 failure: a breaker that, once tripped,
never samples a fresh signal again. drawdown_halt is also relaxed from 150 to
220 USD per the loop-1 note that 150 may engage too early.

Reduce-only / closing orders always submit (intraday_flat compliance).
No order quantity is ever modified — orders are submitted or skipped only.

No look-ahead: `on_position_closed` reflects only closes already processed by
the engine; the running tally read in `on_order` is strictly in the past
relative to the current order's ts_init.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PositionTierGateBL2Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the position-tier-gate-b-l2 execution algorithm.

    Parameters
    ----------
    drawdown_halt : float
        Realized-P&L drawdown (USD, from the decaying peak reference) at or
        beyond which the open-leg gate latches into a SKIP state. Default 220.0.
    drawdown_rearm : float
        Drawdown (USD) at or below which a latched SKIP state unlatches and new
        open legs resume. Must be < drawdown_halt to give hysteresis.
        Default 80.0.
    peak_decay : float
        Fraction (0..1) by which the peak reference is pulled toward the
        current realized P&L on each position close. 0.0 reproduces the loop-1
        all-time-peak behaviour; higher values let the breaker re-arm faster
        on flat/losing stretches. Default 0.10.
    """

    drawdown_halt: float = 220.0
    drawdown_rearm: float = 80.0
    peak_decay: float = 0.10


class PositionTierGateBL2Algorithm(ExecAlgorithm):
    """Execution algorithm that gates open orders on a re-arming equity breaker.

    Opening orders (is_reduce_only == False):
      - drawdown = decaying peak reference - current realized P&L.
      - Gate is a latched state with hysteresis:
          * if currently OPEN  and drawdown >  drawdown_halt  -> latch SKIP.
          * if currently SKIP  and drawdown <= drawdown_rearm -> unlatch OPEN.
      - SUBMIT when the gate state is OPEN, SKIP otherwise.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance; exposure
        reduction is always allowed).

    No order quantity is ever modified. Quantity invariant always preserved.
    """

    def __init__(self, config: PositionTierGateBL2Config) -> None:
        super().__init__(config=config)
        self._drawdown_halt: float = config.drawdown_halt
        self._drawdown_rearm: float = config.drawdown_rearm
        self._peak_decay: float = config.peak_decay
        # Per-session running state.
        self._realized_pnl: float = 0.0
        self._peak_ref: float = 0.0
        # Gate latch: False = OPEN (submit), True = SKIP (latched closed).
        self._gate_skip: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self._realized_pnl = 0.0
        self._peak_ref = 0.0
        self._gate_skip = False
        self.log.info(
            f"PositionTierGateBL2Algorithm started "
            f"(drawdown_halt={self._drawdown_halt} USD, "
            f"drawdown_rearm={self._drawdown_rearm} USD, "
            f"peak_decay={self._peak_decay})."
        )

    def on_reset(self) -> None:
        self._realized_pnl = 0.0
        self._peak_ref = 0.0
        self._gate_skip = False

    # ------------------------------------------------------------------
    # Position event handler — maintains the running realized-P&L tally
    # ------------------------------------------------------------------

    def on_position_closed(self, position) -> None:
        """Accumulate realized P&L of a just-closed position and decay the peak.

        `on_position_closed` fires after the close fill is processed — strictly
        in the past relative to any subsequent `on_order` call. No look-ahead.
        """
        try:
            pnl = float(position.realized_pnl)
        except (TypeError, ValueError):
            # realized_pnl may be a Money object — fall back to its string form.
            try:
                pnl = float(str(position.realized_pnl).split(" ")[0])
            except (TypeError, ValueError, IndexError):
                pnl = 0.0
        self._realized_pnl += pnl

        # Decaying peak reference. A new high snaps the peak up immediately;
        # otherwise the peak is pulled a fraction of the way toward the
        # current P&L, so a flat/losing stretch slowly lowers the bar and
        # re-arms the breaker even without a P&L recovery.
        if self._realized_pnl > self._peak_ref:
            self._peak_ref = self._realized_pnl
        else:
            self._peak_ref += self._peak_decay * (
                self._realized_pnl - self._peak_ref
            )

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on the re-arming equity breaker."""

        # Reduce-only (close) orders always execute — intraday_flat compliance,
        # and they reduce exposure rather than adding to it.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Re-arming circuit breaker with hysteresis.
        drawdown = self._peak_ref - self._realized_pnl

        if self._gate_skip:
            # Latched closed — only unlatch once recovered past the re-arm band.
            if drawdown <= self._drawdown_rearm:
                self._gate_skip = False
        else:
            # Currently open — latch closed if drawdown breaches the halt.
            if drawdown > self._drawdown_halt:
                self._gate_skip = True

        if self._gate_skip:
            self.log.debug(
                f"SKIP {order.client_order_id} — gate latched "
                f"(drawdown={drawdown:.2f}, halt={self._drawdown_halt}, "
                f"rearm={self._drawdown_rearm})."
            )
            # Do NOT call submit_order — quantity invariant preserved.
            return

        self.log.debug(
            f"SUBMIT {order.client_order_id} — gate open "
            f"(drawdown={drawdown:.2f})."
        )
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    drawdown_halt: float = 220.0,
    drawdown_rearm: float = 80.0,
    peak_decay: float = 0.10,
) -> PositionTierGateBL2Algorithm:
    """Instantiate and return the PositionTierGateBL2Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    drawdown_halt : float
        Realized-P&L drawdown (USD) at or beyond which the open-leg gate
        latches SKIP. Default 220.0.
    drawdown_rearm : float
        Drawdown (USD) at or below which a latched gate unlatches. Default 80.0.
    peak_decay : float
        Fraction (0..1) the peak reference decays toward current P&L per close.
        Default 0.10.
    """
    config = PositionTierGateBL2Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        drawdown_halt=drawdown_halt,
        drawdown_rearm=drawdown_rearm,
        peak_decay=peak_decay,
    )
    return PositionTierGateBL2Algorithm(config=config)
