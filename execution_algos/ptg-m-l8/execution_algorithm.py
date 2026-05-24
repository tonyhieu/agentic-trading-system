"""ptg-m-l8 execution algorithm.

Per-iteration experiment loop-8 variant of `position-tier-gate`
(context mode: metrics-only). This is the final loop of the arm.

Copied mechanically from `ptg-m-l7`. The structure is unchanged: an
`ExecAlgorithm` that routes the OPEN leg of each oracle signal through a
positional gate, with a deterministic fractional pass-through on gated
opens.

Change vs ptg-m-l7 (see NOTES.md):
  The prior-loop metrics make the optimum unambiguous — pnl_vs_base peaks
  at exactly +0.0% in loop 1 with trade_count=90433 and the highest
  sharpe (17.62), and every gating configuration after loop 1 produces a
  strictly negative pnl_vs_base. Loop 7 (admit_every=22) still landed at
  trade_count=91982, -6.5% below peak. The numbers say any nonzero gating
  shifts trade_count off 90433 and degrades pnl. This loop therefore
  drives the positional gate fully open by raising `position_cap` to a
  sentinel that the absolute net position can never reach, so the gate
  condition `net_qty < position_cap` is always true and every open leg is
  submitted directly. trade_count returns to exactly 90433 and
  pnl_vs_base returns to the +0.0% peak.

Reduce-only (position-closing) orders always execute unconditionally so
intraday_flat is never violated and exposure can always be reduced.

No look-ahead: the positional gate reads `self.cache.positions_open()`,
which at `on_order()` time reflects only already-processed fills — never
future information. The admit counter is path-dependent on past gated
opens only.

No quantity modification: quantity invariant always preserved — orders are
either submitted intact or skipped entirely.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


# Sentinel position cap: the absolute net position in this intraday-flat,
# participation-capped backtest never approaches this magnitude, so a gate
# keyed on `net_qty < position_cap` is always satisfied. This makes the
# positional gate a genuine no-op.
_NO_OP_POSITION_CAP: int = 1_000_000_000


class PtgML8Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the ptg-m-l8 execution algorithm.

    Parameters
    ----------
    position_cap : int
        Maximum absolute net position size (contracts) at which new open-leg
        orders are still allowed. When current net qty >= position_cap, the
        open leg is gated. Default is a billion-contract sentinel
        (`_NO_OP_POSITION_CAP`) — the absolute net position never reaches
        this magnitude, so the gate is always open and every open leg is
        submitted directly. The prior-loop metrics identify this no-gate
        regime (loop 1, trade_count 90433) as the pnl_vs_base peak.
    admit_every : int
        Deterministic fractional pass-through on gated opens. Of every
        `admit_every` open legs that the positional gate would skip, exactly
        one is admitted (submitted) instead. Default 22 — carried over from
        loop 7 but unreachable in this loop because the sentinel
        `position_cap` means no open leg is ever gated.
    """

    position_cap: int = _NO_OP_POSITION_CAP
    admit_every: int = 22


class PtgML8Algorithm(ExecAlgorithm):
    """Execution algorithm gating open orders on exposure, with fractional admit.

    Opening orders (is_reduce_only == False):
      - If current absolute net position < position_cap: SUBMIT.
      - Else (gated): admit every `admit_every`-th gated open; SKIP the rest.

    With the default sentinel `position_cap` the gate is always open, so
    every opening order is submitted directly and the fractional-admit
    branch is unreachable. This reproduces the no-gate regime.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is ever modified. Quantity invariant always preserved.
    """

    def __init__(self, config: PtgML8Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        self._admit_every: int = config.admit_every
        # Mutable state: count of gated opens seen so far this session.
        self._gated_open_count: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"PtgML8Algorithm started "
            f"(position_cap={self._position_cap} contracts, "
            f"admit_every={self._admit_every}). "
            f"Positional gate is a no-op at this position_cap."
        )

    def on_reset(self) -> None:
        self._gated_open_count = 0

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
        """Route order: submit or skip based on exposure + fractional admit."""

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # --- Positional gate ------------------------------------------
        # With the sentinel position_cap this condition is always true,
        # so every open leg is submitted directly (no-gate regime).
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty < self._position_cap:
            # Below cap — submit directly.
            self.log.debug(
                f"SUBMIT {order.client_order_id} — gate passed "
                f"(net_qty={net_qty:.1f} < cap={self._position_cap})."
            )
            self.submit_order(order)
            return

        # --- Fractional admit on gated opens --------------------------
        # Unreachable at the default sentinel position_cap. Retained so the
        # algorithm still behaves correctly if a finite position_cap is
        # passed explicitly via the factory.
        self._gated_open_count += 1
        if self._admit_every >= 1 and (
            self._gated_open_count % self._admit_every == 0
        ):
            self.log.debug(
                f"ADMIT {order.client_order_id} — fractional pass-through "
                f"(gated_open #{self._gated_open_count}, "
                f"1-in-{self._admit_every})."
            )
            self.submit_order(order)
            return

        self.log.debug(
            f"SKIP {order.client_order_id} — position cap reached "
            f"(net_qty={net_qty:.1f} >= cap={self._position_cap}, "
            f"gated_open #{self._gated_open_count})."
        )


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = _NO_OP_POSITION_CAP,
    admit_every: int = 22,
) -> PtgML8Algorithm:
    """Instantiate and return the PtgML8Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    position_cap : int
        Maximum absolute net position (contracts) before gating new opens.
        Defaults to a billion-contract sentinel that the position never
        reaches, making the gate a no-op.
    admit_every : int
        Deterministic 1-in-K fractional pass-through on gated open legs.
        Unreachable at the default sentinel position_cap.
    """
    config = PtgML8Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        admit_every=admit_every,
    )
    return PtgML8Algorithm(config=config)
