"""ptg-pc-r2 execution algorithm.

Layers a LOSS-COOLDOWN gate on top of position-tier-gate (cap=1).

Mechanism:
  Hooks on_position_closed(event) to read event.realized_pnl after each
  round trip. If the position was a loser (realized_pnl < 0), arm a
  cooldown by setting cooldown_until_ts = now + cooldown_ns. Subsequent
  OPEN orders that pass the position-cap=1 gate are SKIPPED while the
  cooldown is active. CLOSE orders (is_reduce_only=True) always submit
  unchanged - exits are never blocked.

Algorithm (per on_order()):
  1. If order.is_reduce_only: submit unconditionally (intraday_flat).
  2. Otherwise (OPEN-leg order):
     a. Apply position-cap gate: if absolute net open quantity >=
        position_cap, SKIP (do not submit).
     b. Apply loss-cooldown gate: if clock.timestamp_ns() <
        cooldown_until_ts, SKIP.
     c. Otherwise SUBMIT.

Algorithm (per on_position_closed(event)):
  - If event.realized_pnl.as_double() < 0:
        cooldown_until_ts = clock.timestamp_ns() + cooldown_ns

No look-ahead: cooldown_until_ts is set strictly from past PositionClosed
events. on_order() reads the current clock timestamp, which is the order's
arrival time - strictly in the past relative to any subsequent fill.

No quantity modification: quantity invariant always preserved.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.events import PositionClosed
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PtgPcR2Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for ptg-pc-r2.

    Parameters
    ----------
    position_cap : int
        Maximum absolute net position size (contracts) at which new open-leg
        orders are still allowed. When current net qty >= position_cap, the
        open leg is skipped. Default 1 (matches base position-tier-gate).
    cooldown_ns : int
        Cooldown duration in nanoseconds after a losing position close.
        Default 2_000_000_000 (2 seconds). The oracle's nominal signal cadence
        is 1 second per research/config.yaml, but empirically the inter-OPEN
        gap (measured via instrumentation on 20260312) is typically 1.1-1.5
        seconds due to scheduling on actual market ticks. A 1.0s cooldown
        consistently expires before the next OPEN arrives and never bites;
        2.0s gives the smallest reliable margin to block exactly one
        subsequent OPEN signal in the dense regime, while leaving the rare
        wider gaps (>2s) alone.
    """

    position_cap: int = 1
    cooldown_ns: int = 2_000_000_000


class PtgPcR2Algorithm(ExecAlgorithm):
    """Position-tier-gate (cap=1) with an additive loss-cooldown filter.

    Maintains a single mutable scalar `_cooldown_until_ts`. Hooks
    on_position_closed to arm the cooldown after a losing round trip. On
    every OPEN order (is_reduce_only=False), applies the position-cap gate
    first; if that passes, applies the cooldown gate.
    """

    def __init__(self, config: PtgPcR2Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        self._cooldown_ns: int = config.cooldown_ns
        self._cooldown_until_ts: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"PtgPcR2Algorithm started "
            f"(position_cap={self._position_cap}, "
            f"cooldown_ns={self._cooldown_ns})."
        )

    def on_reset(self) -> None:
        # Each date runs in a fresh subprocess, but reset defensively
        # in case Nautilus reuses an instance.
        self._cooldown_until_ts = 0

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

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_position_closed(self, event: PositionClosed) -> None:
        """Arm cooldown if the just-closed position was a loser."""
        try:
            pnl_value = event.realized_pnl.as_double()
        except AttributeError:
            # Defensive: if realized_pnl is None or a different type, fall
            # back to float() and treat unparseable as zero (no cooldown).
            try:
                pnl_value = float(event.realized_pnl)
            except (TypeError, ValueError):
                pnl_value = 0.0

        if pnl_value < 0.0:
            self._cooldown_until_ts = self.clock.timestamp_ns() + self._cooldown_ns
            self.log.debug(
                f"Loss-cooldown armed: realized_pnl={pnl_value:.4f}, "
                f"cooldown_until_ts={self._cooldown_until_ts}."
            )

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on cap and loss-cooldown gates."""

        # Reduce-only (CLOSE) orders always execute - intraday_flat compliance,
        # exits are never blocked.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Position-cap gate (preserve base position-tier-gate behavior).
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty >= self._position_cap:
            self.log.debug(
                f"SKIP {order.client_order_id} - position cap reached "
                f"(net_qty={net_qty:.1f} >= cap={self._position_cap})."
            )
            return

        # Loss-cooldown gate.
        now_ns = self.clock.timestamp_ns()
        if now_ns < self._cooldown_until_ts:
            self.log.debug(
                f"SKIP {order.client_order_id} - loss-cooldown active "
                f"(now={now_ns}, until={self._cooldown_until_ts})."
            )
            return

        self.log.debug(
            f"SUBMIT {order.client_order_id} (net_qty={net_qty:.1f}, no cooldown)."
        )
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    cooldown_ns: int = 2_000_000_000,
) -> PtgPcR2Algorithm:
    """Instantiate the ptg-pc-r2 execution algorithm."""
    config = PtgPcR2Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        cooldown_ns=cooldown_ns,
    )
    return PtgPcR2Algorithm(config=config)
