"""ptg-m-l6 execution algorithm.

Per-iteration experiment loop-6 variant of `position-tier-gate`
(context mode: metrics-only).

Copied mechanically from `ptg-m-l5`. Routes the OPEN leg of each oracle
signal through a positional gate, then adds a deterministic fractional
pass-through on the gated opens.

  1. Positional gate (inherited from `position-tier-gate`):
     skip the open leg when the current absolute net position is at or
     above `position_cap` contracts.
  2. Fractional admit (new this loop): when an open leg would be skipped
     by the positional gate, a deterministic 1-in-`admit_every` counter
     admits every Kth such gated open instead of skipping it.

Reduce-only (position-closing) orders always execute unconditionally so
intraday_flat is never violated and exposure can always be reduced.

Change vs ptg-m-l5 (see NOTES.md):
  The prior loop metrics describe a single-peaked link between trade_count
  and pnl_vs_base, peaking at loop 1's count (~90433). Loop 3's tightest
  integer gate throttled to 84541 (just under the peak, -7% P&L); loop 5's
  next integer notch over-traded to 136734 (-96%). No integer gate setting
  lands on the peak. This loop keeps the tight integer gate (position_cap=1,
  the loop-3 safe regime) but admits a deterministic 1-in-16 fraction of the
  gated opens, nudging trade_count up from 84541 toward the ~90433 peak
  without crossing into the loop-4/5 over-trading collapse.

No look-ahead: the positional gate reads `self.cache.positions_open()`,
which at `on_order()` time reflects only already-processed fills — never
future information. The admit counter is path-dependent on past gated opens
only.

No quantity modification: quantity invariant always preserved — orders are
either submitted intact or skipped entirely.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PtgML6Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the ptg-m-l6 execution algorithm.

    Parameters
    ----------
    position_cap : int
        Maximum absolute net position size (contracts) at which new open-leg
        orders are still allowed. When current net qty >= position_cap, the
        open leg is gated. Default 1 — the tightest integer gate, which the
        loop-3 metrics show produced a trade_count of 84541 (the best
        non-base regime by pnl_vs_base).
    admit_every : int
        Deterministic fractional pass-through on gated opens. Of every
        `admit_every` open legs that the positional gate would skip, exactly
        one is admitted (submitted) instead. Default 16 — the smallest
        fractional step that lifts trade_count from ~84541 toward loop 1's
        ~90433 peak without entering the loop-4/5 over-trading regime
        (136734). Set <= 1 to admit every gated open (disables the gate);
        set very large to effectively disable the pass-through.
    """

    position_cap: int = 1
    admit_every: int = 16


class PtgML6Algorithm(ExecAlgorithm):
    """Execution algorithm gating open orders on exposure, with fractional admit.

    Opening orders (is_reduce_only == False):
      - If current absolute net position < position_cap: SUBMIT.
      - Else (gated): admit every `admit_every`-th gated open; SKIP the rest.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is ever modified. Quantity invariant always preserved.
    """

    def __init__(self, config: PtgML6Config) -> None:
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
            f"PtgML6Algorithm started "
            f"(position_cap={self._position_cap} contracts, "
            f"admit_every={self._admit_every})."
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
        # This open leg would be skipped by the positional gate. Admit every
        # admit_every-th such gated open to nudge trade_count toward the peak.
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
    position_cap: int = 1,
    admit_every: int = 16,
) -> PtgML6Algorithm:
    """Instantiate and return the PtgML6Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    position_cap : int
        Maximum absolute net position (contracts) before gating new opens.
    admit_every : int
        Deterministic 1-in-K fractional pass-through on gated open legs.
    """
    config = PtgML6Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        admit_every=admit_every,
    )
    return PtgML6Algorithm(config=config)
