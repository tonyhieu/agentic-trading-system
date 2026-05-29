"""sip-ptg-l1: directional-continuation gate on top of position-tier-gate.

Hypothesis:
  The baseline position-tier-gate (cap=1) skips every new OPEN whenever the
  cache still shows the prior position (i.e., whenever the oracle fires a
  same-timestamp CLOSE+OPEN sequence). It treats two distinct situations
  identically:

    (a) Flip re-entry: the oracle changes its sign. The old position was
        long, the new OPEN is a SELL (or vice versa). High-frequency flips
        are the dominant noise mode in a 1-second-cadence oracle with sigma
        in the signal — many flips are mean-reverting noise that the gate
        is right to filter.

    (b) Continuation re-entry: the oracle keeps the same sign. The old
        position was long, the new OPEN is also a BUY. A repeated same-side
        signal carries persistence information — the oracle's posterior on
        direction did not move, only the position lifecycle forced a
        round-trip.

  By treating (a) and (b) the same, the baseline throws away a real source
  of edge: continuation signals are conditionally more likely to be right
  than flip signals (the oracle just confirmed its prior). Allowing
  continuation OPENs through while still skipping flip OPENs should add
  trades that on average carry positive expectation, without re-introducing
  the runaway concurrent-exposure failure mode the base algo was designed
  to prevent (we never exceed cap=1 net contracts because the CLOSE has
  already been submitted alongside this OPEN, so the position will round
  trip to flat before the next signal).

Mechanism:
  At on_order():
    - Reduce-only: submit unconditionally (intraday_flat compliance).
    - Otherwise: read net qty from cache.
        - If net_qty == 0: submit (no in-flight position to compare).
        - If net_qty >= cap and the existing open position has the SAME
          signed direction as this incoming order: SUBMIT (continuation
          pass-through).
        - If net_qty >= cap and the existing open position has the OPPOSITE
          signed direction to this incoming order: SKIP (flip filter).

  Quantity invariant: no order quantity is ever modified. Top-of-book and
  participation_cap constraints are upstream of this algorithm (it neither
  inflates nor walks the book — it only chooses submit vs skip).

Expected direction:
  - trade_count: increases vs base (cap=1 ungated continuations are added
    back in). Still well below the baseline `simple` algo.
  - realized_pnl: increases vs base if continuation re-entries carry
    positive expectation on average; could decrease if the entire cap=1
    benefit came from filtering ALL re-entries indiscriminately. The
    directional cut is the empirical test.
  - mean_slippage: unchanged (still top-of-book; no book walking).

No look-ahead: cache.positions_open() at on_order() time reflects only
fills processed prior to the current order's ts_init. The same-timestamp
CLOSE has been submitted but not yet filled, so the cache still shows
the prior position's signed direction — which is exactly what we want to
classify the incoming OPEN as flip vs continuation.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class SipPtgL1Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for sip-ptg-l1.

    Parameters
    ----------
    position_cap : int
        Maximum absolute net position size at which a new OPEN is still
        allowed unconditionally. When net_qty >= cap, the directional-
        continuation rule decides submit vs skip.
        Default 1 — matches the baseline position-tier-gate behavior so
        the gate fires on every same-timestamp CLOSE+OPEN sequence.
    """

    position_cap: int = 1


class SipPtgL1Algorithm(ExecAlgorithm):
    """Directional-continuation gate on top of position-tier-gate."""

    def __init__(self, config: SipPtgL1Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"SipPtgL1Algorithm started "
            f"(position_cap={self._position_cap}; continuation pass-through enabled)."
        )

    def on_reset(self) -> None:
        # No mutable state — direction comes from the live cache.
        pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _net_qty_and_direction(self, instrument_id):
        """Return (abs_net_qty, signed_direction) for the instrument.

        signed_direction is:
            +1 if the open position is long,
            -1 if the open position is short,
             0 if flat.

        In a netting OMS there is at most one open position per instrument.
        Defensive sum over the list still works for the single-position
        case and yields 0 when flat.
        """
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0, 0

        # Netting OMS — single position per instrument in practice. Take
        # the first; if multiple appear we sum signed quantities and
        # derive a single direction from the sign.
        signed = 0.0
        abs_total = 0.0
        for p in open_positions:
            # Use is_long / is_short flags + absolute quantity. The
            # signed_decimal_qty accessor is a method in this Nautilus
            # build and is_long/is_short are well-defined boolean
            # attributes on Position.
            abs_qty = float(str(p.quantity))
            if p.is_long:
                signed += abs_qty
            elif p.is_short:
                signed -= abs_qty
            abs_total += abs_qty

        if signed > 0:
            direction = 1
        elif signed < 0:
            direction = -1
        else:
            direction = 0
        return abs_total, direction

    @staticmethod
    def _order_direction(order) -> int:
        """Return +1 for BUY, -1 for SELL."""
        return 1 if order.side == OrderSide.BUY else -1

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Decide submit vs skip based on portfolio direction vs order side."""

        # Reduce-only orders always pass — intraday_flat compliance.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        abs_net_qty, position_dir = self._net_qty_and_direction(order.instrument_id)

        # Flat — no in-flight position; always submit.
        if position_dir == 0 or abs_net_qty < self._position_cap:
            self.log.debug(
                f"SUBMIT {order.client_order_id} — flat or below cap "
                f"(abs_net_qty={abs_net_qty:.1f}, dir={position_dir})."
            )
            self.submit_order(order)
            return

        # At or above cap: directional-continuation rule.
        order_dir = self._order_direction(order)
        if order_dir == position_dir:
            # Continuation — same-side re-entry: pass through.
            self.log.debug(
                f"SUBMIT {order.client_order_id} — continuation "
                f"(position_dir={position_dir}, order_dir={order_dir})."
            )
            self.submit_order(order)
            return

        # Flip — opposite side: skip.
        self.log.debug(
            f"SKIP {order.client_order_id} — flip "
            f"(position_dir={position_dir}, order_dir={order_dir}, "
            f"abs_net_qty={abs_net_qty:.1f}, cap={self._position_cap})."
        )
        # Do NOT call submit_order — quantity invariant preserved.


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
) -> SipPtgL1Algorithm:
    """Instantiate and return the SipPtgL1Algorithm."""
    config = SipPtgL1Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
    )
    return SipPtgL1Algorithm(config=config)
