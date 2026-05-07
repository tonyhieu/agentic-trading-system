"""Oracle signal consensus filter execution algorithm.

For each incoming parent order:
  1. Record its direction (BUY or SELL) in a rolling window of recent signals.
  2. If fewer than min_window orders have been seen, submit immediately
     (no-history baseline fallback).
  3. Compute agreement = fraction of the window matching the current direction.
  4. If agreement >= min_agreement_frac, submit the order.
  5. Otherwise skip the order — the oracle is oscillating, indicating low
     signal quality.

Reduce-only (close) orders are always submitted to maintain intraday_flat.

Quantity invariant: no order quantities are ever modified.  Skipped orders
result in sum(child_fills) < parent.quantity, which is permitted by
OBJECTIVE.md §3.

See execution_algos/signal-consensus/NOTES.md for the full hypothesis.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class SignalConsensusConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the oracle signal consensus filter.

    Parameters
    ----------
    window_size : int
        Number of recent oracle signal directions to track.
        Default 5 — covers ~5 seconds of oracle signals at 1 Hz.
    min_window : int
        Minimum number of signals required before the consensus logic
        activates.  If fewer samples are available, submit immediately.
        Default 3.
    min_agreement_frac : float
        Minimum fraction of the window that must match the current order
        direction to submit.  Range [0, 1].  Default 0.6 (3-of-5 must agree).
        At 0.6 with window_size=5: requires 3+ matching signals.
        - High-conviction oracle run (p_correct ≈ 0.84): P(≥3 agree) ≈ 0.999.
        - Noisy oracle (p_correct = 0.50): P(≥3 agree) ≈ 0.50 — skips ~50%.
    """

    window_size: int = 5
    min_window: int = 3
    min_agreement_frac: float = 0.6


class SignalConsensusAlgorithm(ExecAlgorithm):
    """Execution algorithm that filters oracle signals by directional consensus.

    Opening orders (is_reduce_only == False):
      - Record direction in the rolling history window.
      - Compute agreement = fraction of window matching current direction.
      - Submit if agreement >= min_agreement_frac; skip otherwise.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is modified.  Quantity invariant always preserved.
    """

    def __init__(self, config: SignalConsensusConfig) -> None:
        super().__init__(config=config)
        self._window_size: int = config.window_size
        self._min_window: int = config.min_window
        self._min_agreement_frac: float = config.min_agreement_frac
        # Rolling window of recent order sides: True = BUY, False = SELL.
        self._history: deque[bool] = deque(maxlen=self._window_size)

    def on_start(self) -> None:
        self.log.info(
            f"SignalConsensusAlgorithm started "
            f"(window_size={self._window_size}, "
            f"min_window={self._min_window}, "
            f"min_agreement_frac={self._min_agreement_frac:.2f})."
        )

    def on_reset(self) -> None:
        self._history.clear()

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route the order: submit if directional consensus is sufficient."""
        # Reduce-only orders are always submitted — required for intraday_flat.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        is_buy = order.side == OrderSide.BUY

        # Record this signal's direction BEFORE the consensus check so that
        # even skipped orders inform the history (we want to track oracle
        # direction, not execution outcomes).
        self._history.append(is_buy)

        n = len(self._history)
        if n < self._min_window:
            # Not enough history — submit immediately (baseline fallback).
            self.log.info(
                f"Insufficient history ({n}/{self._min_window}) for "
                f"{order.instrument_id}; submitting {order.client_order_id} "
                f"immediately (no-history fallback)."
            )
            self.submit_order(order)
            return

        # Compute agreement: fraction of window matching current direction.
        matching = sum(1 for side in self._history if side == is_buy)
        agreement = matching / n

        if agreement >= self._min_agreement_frac:
            self.log.debug(
                f"SUBMIT order {order.client_order_id} "
                f"(side={'BUY' if is_buy else 'SELL'}, "
                f"agreement={agreement:.2f} >= {self._min_agreement_frac:.2f})."
            )
            self.submit_order(order)
        else:
            self.log.info(
                f"SKIP order {order.client_order_id} "
                f"(side={'BUY' if is_buy else 'SELL'}, "
                f"agreement={agreement:.2f} < {self._min_agreement_frac:.2f}) "
                f"— low oracle consensus."
            )
            # Do NOT call submit_order — order is intentionally not executed.


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    window_size: int = 5,
    min_window: int = 3,
    min_agreement_frac: float = 0.6,
) -> SignalConsensusAlgorithm:
    """Instantiate and return a SignalConsensusAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    window_size : int
        Rolling window length for signal direction history. Default 5.
    min_window : int
        Minimum samples before the filter activates. Default 3.
    min_agreement_frac : float
        Minimum agreement fraction to submit. Default 0.6.
    """
    config = SignalConsensusConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        window_size=window_size,
        min_window=min_window,
        min_agreement_frac=min_agreement_frac,
    )
    return SignalConsensusAlgorithm(config=config)
