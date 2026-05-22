"""ptg-m-l3 execution algorithm.

Per-iteration experiment loop-3 variant of `position-tier-gate`
(context mode: metrics-only).

Copied mechanically from `ptg-m-l2`. Conditions the OPEN leg of each
oracle signal on TWO gates:

  1. Positional gate (inherited from `position-tier-gate`):
     skip the open leg when the current absolute net position is at or
     above `position_cap` contracts.

  2. Post-open cooldown gate:
     skip the open leg when fewer than `cooldown_seconds` have elapsed
     since the most recently submitted open order.

Reduce-only (position-closing) orders always execute unconditionally so
intraday_flat is never violated and exposure can always be reduced.

Change vs ptg-m-l2 (see NOTES.md):
  The loop-2 cooldown (10.0 s) cut trade_count 47% below base and lost
  23.1% P&L — too aggressive. The loop-1 setting (2.0 s) was inert. This
  loop sets the cooldown to 3.0 s — a mild throttle that fires only
  occasionally, trimming a thin slice of opens rather than half of them.

No look-ahead: the cooldown compares `order.ts_init` (the order's own
initialization timestamp) against the `ts_init` of the previously submitted
open order — both are strictly in the past or present, never future.
`self.cache` at `on_order()` time reflects only already-processed fills.

No quantity modification: quantity invariant always preserved — orders are
either submitted intact or skipped entirely.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PtgML3Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the ptg-m-l3 execution algorithm.

    Parameters
    ----------
    position_cap : int
        Maximum absolute net position size (contracts) at which new open-leg
        orders are still allowed. When current net qty >= position_cap, the
        open leg is skipped. Default 1 (serialized entry).
    cooldown_seconds : float
        Minimum elapsed time (seconds) between two submitted open orders.
        When fewer than this many seconds have passed since the last
        submitted open, a new open leg is skipped. Default 3.0 s — a mild
        throttle relative to the 1.0 s oracle signal cadence.
    """

    position_cap: int = 1
    cooldown_seconds: float = 3.0


class PtgML3Algorithm(ExecAlgorithm):
    """Execution algorithm gating open orders on exposure AND a post-open cooldown.

    Opening orders (is_reduce_only == False):
      - If current absolute net position >= position_cap: SKIP.
      - Else if (order.ts_init - last_open_ts_init) < cooldown: SKIP.
      - Else: SUBMIT and record this order's ts_init as the new last-open time.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is ever modified. Quantity invariant always preserved.
    """

    def __init__(self, config: PtgML3Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        self._cooldown_ns: int = int(config.cooldown_seconds * 1_000_000_000)
        # ts_init (ns) of the most recently SUBMITTED open order; None until
        # the first open is submitted.
        self._last_open_ts_init: int | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"PtgML3Algorithm started "
            f"(position_cap={self._position_cap} contracts, "
            f"cooldown={self._cooldown_ns / 1e9:.1f}s)."
        )

    def on_reset(self) -> None:
        self._last_open_ts_init = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _current_net_qty(self, instrument_id) -> float:
        """Return absolute net position quantity for the instrument.

        Uses self.cache.positions_open() which returns the list of currently
        open positions in the netting OMS. Returns 0.0 when flat.
        """
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        total = sum(float(str(p.quantity)) for p in open_positions)
        return total

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on exposure and post-open cooldown."""

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # --- Gate 1: positional cap -----------------------------------
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty >= self._position_cap:
            self.log.debug(
                f"SKIP {order.client_order_id} — position cap reached "
                f"(net_qty={net_qty:.1f} >= cap={self._position_cap})."
            )
            return

        # --- Gate 2: post-open cooldown -------------------------------
        # order.ts_init is the order's own initialization timestamp (ns).
        # Comparing it against the previously submitted open's ts_init uses
        # only past/present information — no look-ahead.
        if self._last_open_ts_init is not None:
            elapsed_ns = order.ts_init - self._last_open_ts_init
            if 0 <= elapsed_ns < self._cooldown_ns:
                self.log.debug(
                    f"SKIP {order.client_order_id} — cooldown active "
                    f"(elapsed={elapsed_ns / 1e9:.2f}s < "
                    f"{self._cooldown_ns / 1e9:.1f}s)."
                )
                return

        # Both gates passed — submit and record the open timestamp.
        self.log.debug(
            f"SUBMIT {order.client_order_id} — gates passed "
            f"(net_qty={net_qty:.1f} < cap={self._position_cap})."
        )
        self._last_open_ts_init = order.ts_init
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    cooldown_seconds: float = 3.0,
) -> PtgML3Algorithm:
    """Instantiate and return the PtgML3Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    position_cap : int
        Maximum absolute net position (contracts) before skipping new opens.
    cooldown_seconds : float
        Minimum elapsed time between two submitted open orders.
    """
    config = PtgML3Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        cooldown_seconds=cooldown_seconds,
    )
    return PtgML3Algorithm(config=config)
