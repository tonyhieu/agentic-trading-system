"""Position-tier-gate-b-l1 execution algorithm.

Per-iteration experiment — arm: base_algo=position-tier-gate,
mode=brief-summary, loop 1. Starting point: `position-tier-gate`.

Conditions the OPEN leg of each oracle signal on the strategy's realized-P&L
drawdown — a portfolio-equity circuit breaker. This replaces the base algo's
unconditional "skip OPEN while a position is in-flight" serialize gate, which
destroys value under the current high-noise (sigma=200) oracle config.

Hypothesis:
  Under sigma=200 the oracle signal is near-random. The base algo skips opens
  whenever a position shows in the cache — a blanket throttle that locks the
  algo into bad entries and prevents re-entry on a no-worse signal. That
  skipped subset is net-negative (base realized_pnl=-5892 vs simple +156).

  Instead, only throttle new opens when the strategy is actually losing:
    - Track cumulative realized P&L of closed positions and its running peak.
    - If realized P&L is within `drawdown_halt` of its peak: SUBMIT the open
      (let every signal through — capture the upside the base algo discards).
    - If realized P&L is more than `drawdown_halt` below its peak: SKIP the
      open (cut fresh exposure during a losing streak).
  Reduce-only / closing orders always submit (intraday_flat compliance).

No look-ahead: `on_position_closed` reflects only closes already processed by
the engine; the running tally read in `on_order` is strictly in the past
relative to the current order's ts_init.

No quantity modification: orders are submitted or skipped, never modified.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PositionTierGateBL1Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the position-tier-gate-b-l1 execution algorithm.

    Parameters
    ----------
    drawdown_halt : float
        Realized-P&L drawdown (USD, from the running peak) at or beyond which
        new open-leg orders are skipped. While realized P&L is within this
        distance of its peak, all open legs are submitted. Default 150.0.
    """

    drawdown_halt: float = 150.0


class PositionTierGateBL1Algorithm(ExecAlgorithm):
    """Execution algorithm that gates open orders on realized-P&L drawdown.

    Opening orders (is_reduce_only == False):
      - Compute drawdown = running realized-P&L peak - current realized P&L.
      - If drawdown <= drawdown_halt: SUBMIT.
      - Else: SKIP.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance; exposure
        reduction is always allowed).

    No order quantity is ever modified. Quantity invariant always preserved.
    """

    def __init__(self, config: PositionTierGateBL1Config) -> None:
        super().__init__(config=config)
        self._drawdown_halt: float = config.drawdown_halt
        # Per-session running state.
        self._realized_pnl: float = 0.0
        self._pnl_peak: float = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self._realized_pnl = 0.0
        self._pnl_peak = 0.0
        self.log.info(
            f"PositionTierGateBL1Algorithm started "
            f"(drawdown_halt={self._drawdown_halt} USD)."
        )

    def on_reset(self) -> None:
        self._realized_pnl = 0.0
        self._pnl_peak = 0.0

    # ------------------------------------------------------------------
    # Position event handler — maintains the running realized-P&L tally
    # ------------------------------------------------------------------

    def on_position_closed(self, position) -> None:
        """Accumulate realized P&L of a just-closed position and track peak.

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
        if self._realized_pnl > self._pnl_peak:
            self._pnl_peak = self._realized_pnl

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on realized-P&L drawdown."""

        # Reduce-only (close) orders always execute — intraday_flat compliance,
        # and they reduce exposure rather than adding to it.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Portfolio-equity circuit breaker.
        drawdown = self._pnl_peak - self._realized_pnl

        if drawdown > self._drawdown_halt:
            self.log.debug(
                f"SKIP {order.client_order_id} — realized-P&L drawdown "
                f"({drawdown:.2f} > halt={self._drawdown_halt})."
            )
            # Do NOT call submit_order — quantity invariant preserved.
            return

        # Strategy at/near its high-water mark — submit.
        self.log.debug(
            f"SUBMIT {order.client_order_id} — drawdown within tolerance "
            f"({drawdown:.2f} <= halt={self._drawdown_halt})."
        )
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    drawdown_halt: float = 150.0,
) -> PositionTierGateBL1Algorithm:
    """Instantiate and return the PositionTierGateBL1Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    drawdown_halt : float
        Realized-P&L drawdown (USD) at or beyond which new open legs are
        skipped. Default 150.0.
    """
    config = PositionTierGateBL1Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        drawdown_halt=drawdown_halt,
    )
    return PositionTierGateBL1Algorithm(config=config)
