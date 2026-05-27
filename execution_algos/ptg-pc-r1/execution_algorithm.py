"""ptg-pc-r1 execution algorithm.

Layers a signal-consensus filter on top of position-tier-gate (cap=1).

Algorithm (per OPEN order at on_order()):
  1. If order.is_reduce_only: submit unconditionally (intraday_flat).
  2. Otherwise (it's an OPEN-leg order):
     a. Update the rolling buffer with this OPEN's direction (BUY/SELL).
        The buffer always reflects the actual oracle directional stream.
     b. Apply position-cap gate: if absolute net open quantity >=
        position_cap, SKIP (do not submit).
     c. Apply consensus gate: if buffer has at least consensus_k entries,
        compute the fraction of last consensus_k OPEN directions matching
        this OPEN's direction. If fraction < agreement_threshold, SKIP.
        During warmup (< consensus_k OPENs observed), default to SUBMIT.
     d. Otherwise SUBMIT.

No look-ahead: the buffer is populated solely from past on_order() calls.
The position cache reflects fills already processed (strictly past relative
to ts_init).

No quantity modification: quantity invariant preserved.
"""
from __future__ import annotations

from collections import deque
from typing import Deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PtgPcR1Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for ptg-pc-r1.

    Parameters
    ----------
    position_cap : int
        Maximum absolute net position size (contracts) at which new
        open-leg orders are still allowed. When current net qty >=
        position_cap, the open leg is skipped. Default 1 (matches base
        position-tier-gate).
    consensus_k : int
        Rolling window size (number of recent OPEN directions to consider).
        Default 5 (5 seconds at the 1Hz oracle cadence).
    agreement_threshold : float
        Minimum fraction of the last consensus_k OPEN directions that must
        match this OPEN's direction for it to pass the consensus gate.
        Default 0.6 (3-of-5 majority with consensus_k=5).
    """

    position_cap: int = 1
    consensus_k: int = 5
    agreement_threshold: float = 0.6


class PtgPcR1Algorithm(ExecAlgorithm):
    """Position-tier-gate (cap=1) with an additive signal-consensus filter.

    On every OPEN order (is_reduce_only=False), the algorithm:
      1. Records the order's direction (BUY/SELL) in a rolling buffer of
         the last consensus_k entries.
      2. Applies the position-cap gate: if absolute net qty >= position_cap,
         SKIP.
      3. Applies the consensus gate: if buffer has consensus_k entries and
         the fraction matching this order's direction is below
         agreement_threshold, SKIP. During warmup (< consensus_k entries
         observed), default to SUBMIT.

    Reduce-only (close) orders always SUBMIT and never enter the buffer.
    No order quantity is ever modified.
    """

    def __init__(self, config: PtgPcR1Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        self._consensus_k: int = config.consensus_k
        self._agreement_threshold: float = config.agreement_threshold
        # Rolling buffer of the last K OPEN-order sides (integer enum values).
        self._direction_buffer: Deque[int] = deque(maxlen=config.consensus_k)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"PtgPcR1Algorithm started "
            f"(position_cap={self._position_cap}, "
            f"consensus_k={self._consensus_k}, "
            f"agreement_threshold={self._agreement_threshold})."
        )

    def on_reset(self) -> None:
        # Each date runs in a fresh subprocess so this should rarely matter,
        # but reset defensively in case Nautilus reuses an instance.
        self._direction_buffer.clear()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _current_net_qty(self, instrument_id) -> float:
        """Return absolute net position quantity for the instrument.

        Uses self.cache.positions_open() which returns the list of currently
        open positions in the netting OMS (at most one per instrument).
        Returns 0.0 when flat.
        """
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        return sum(float(str(p.quantity)) for p in open_positions)

    def _consensus_allows(self, side_value: int) -> bool:
        """Apply the consensus gate.

        During warmup (fewer than consensus_k entries observed) the filter
        defaults to SUBMIT (returns True).
        Otherwise computes fraction of buffer entries matching side_value
        and returns True iff fraction >= agreement_threshold.
        """
        if len(self._direction_buffer) < self._consensus_k:
            return True
        match_count = sum(1 for s in self._direction_buffer if s == side_value)
        fraction = match_count / len(self._direction_buffer)
        return fraction >= self._agreement_threshold

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on position cap and consensus filter."""

        # Reduce-only (CLOSE) orders always execute - intraday_flat compliance.
        # They are not entered into the consensus buffer.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # OPEN order: record its direction in the rolling buffer FIRST.
        # The buffer tracks the raw oracle directional stream regardless of
        # whether downstream gates pass.
        side_value = int(order.side)
        self._direction_buffer.append(side_value)

        # Apply the position-cap gate (preserve base position-tier-gate behavior).
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty >= self._position_cap:
            self.log.debug(
                f"SKIP {order.client_order_id} - position cap reached "
                f"(net_qty={net_qty:.1f} >= cap={self._position_cap})."
            )
            return

        # Apply the consensus gate.
        if not self._consensus_allows(side_value):
            match_count = sum(1 for s in self._direction_buffer if s == side_value)
            self.log.debug(
                f"SKIP {order.client_order_id} - consensus below threshold "
                f"(match={match_count}/{len(self._direction_buffer)}, "
                f"thr={self._agreement_threshold})."
            )
            return

        # Both gates pass.
        self.log.debug(
            f"SUBMIT {order.client_order_id} (side={side_value}, net_qty={net_qty:.1f})."
        )
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    consensus_k: int = 5,
    agreement_threshold: float = 0.6,
) -> PtgPcR1Algorithm:
    """Instantiate the ptg-pc-r1 execution algorithm."""
    config = PtgPcR1Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        consensus_k=consensus_k,
        agreement_threshold=agreement_threshold,
    )
    return PtgPcR1Algorithm(config=config)
