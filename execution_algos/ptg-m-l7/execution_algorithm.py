"""ptg-m-l7 execution algorithm.

Per-iteration experiment loop-7 variant of `position-tier-gate`
(context mode: metrics-only).

Copied mechanically from `ptg-m-l6`. Routes the OPEN leg of each oracle
signal through a positional gate, then adds a deterministic fractional
pass-through on the gated opens.

  1. Positional gate (inherited from `position-tier-gate`):
     skip the open leg when the current absolute net position is at or
     above `position_cap` contracts.
  2. Fractional admit: when an open leg would be skipped by the positional
     gate, a deterministic 1-in-`admit_every` counter admits every Kth such
     gated open instead of skipping it.

Reduce-only (position-closing) orders always execute unconditionally so
intraday_flat is never violated and exposure can always be reduced.

Change vs ptg-m-l6 (see NOTES.md):
  The prior loop metrics describe a single-peaked link between trade_count
  and pnl_vs_base, peaking at trade_count ~= 90433 (loop 1, pnl_vs_base=0%).
  Loop 6 (admit_every=16) overshot to 92461 (-8.4%); loop 3's tight integer
  gate undershot to 84541 (-7.0%). The peak lies between them. This loop
  keeps everything identical and only raises admit_every from 16 to 22,
  throttling the fractional pass-through so trade_count falls from 92461
  toward the ~90433 peak.

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


class PtgML7Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the ptg-m-l7 execution algorithm.

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
        one is admitted (submitted) instead. Default 22 — raised from
        loop 6's 16 to throttle the pass-through so trade_count falls from
        loop 6's 92461 toward loop 1's ~90433 peak. Set <= 1 to admit every
        gated open (disables the gate); set very large to effectively
        disable the pass-through.
    """

    position_cap: int = 1
    admit_every: int = 22


class PtgML7Algorithm(ExecAlgorithm):
    """Execution algorithm gating open orders on exposure, with fractional admit.

    Opening orders (is_reduce_only == False):
      - If current absolute net position < position_cap: SUBMIT.
      - Else (gated): admit every `admit_every`-th gated open; SKIP the rest.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is ever modified. Quantity invariant always preserved.
    """

    def __init__(self, config: PtgML7Config) -> None:
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
            f"PtgML7Algorithm started "
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
    admit_every: int = 22,
) -> PtgML7Algorithm:
    """Instantiate and return the PtgML7Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    position_cap : int
        Maximum absolute net position (contracts) before gating new opens.
    admit_every : int
        Deterministic 1-in-K fractional pass-through on gated open legs.
    """
    config = PtgML7Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        admit_every=admit_every,
    )
    return PtgML7Algorithm(config=config)
