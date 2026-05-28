"""ptg-pc-r6 execution algorithm.

ROLLING-WINDOW WIN-RATE COOLDOWN, layered on position-tier-gate (cap=1).

Hypothesis (see NOTES.md):
  The oracle (sigma=6.0, R^2 ~14%) exhibits time-varying realized accuracy.
  Empirical pre-validation on the 12-date train window (90,433 positions):
  the subset of OPENs preceded by a 100-position rolling window with
  win-rate < 0.32 has concretely negative aggregate PnL (-$188.75 over
  23,019 trades). Skipping that subset yields +4.43% vs base PTG. The
  signal aggregates 100 i.i.d. trial outcomes, making it regime-sensitive
  even though individual losses are i.i.d.

Decision rule:
  - cap=1 gate (verbatim from base position-tier-gate): SKIP the OPEN
    if current absolute net qty >= 1. CLOSE always submits.
  - Rolling-WR cooldown (NEW): on each OPEN that survives cap=1, if the
    rolling 100-position win-rate is below 0.32, SKIP the OPEN.
    Warmup (deque not yet full): cooldown inactive, always SUBMIT.

Signal source: on_position_closed events (Nautilus standard hook, verified
working on ExecAlgorithm via r2). Each close pushes a boolean (is_win =
realized_pnl > 0) into a fixed-length deque. A running win count is
maintained for O(1) win-rate computation.

No look-ahead: deque contains only events from on_position_closed which
fire after fills are processed - strictly past information.

No quantity modification: SKIP or SUBMIT, quantity invariant preserved.

No market-data subscription: signal source is the algo's own internal
position-outcome accounting, NOT quote/trade ticks. Sidesteps the
delivery-channel failure mode that broke r4 (-3.1%) and r5 (0.0%).
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.events import PositionClosed
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PtgPcR6Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for ptg-pc-r6.

    Parameters
    ----------
    position_cap : int
        Maximum absolute net position size (contracts) at which new OPEN
        orders are still allowed. When current net qty >= position_cap, the
        open leg is skipped. Default 1 (matches base position-tier-gate).
    wr_window : int
        Length of the rolling win-rate deque. Default 100. Until the deque
        has wr_window entries, the rolling-WR cooldown is inactive (warmup).
    wr_threshold : float
        Rolling-WR threshold below which the OPEN is skipped (cooldown
        active). Default 0.32 — empirically calibrated on the 12-date train
        window as the sweet spot with 7/2 help/hurt ratio.
    """

    position_cap: int = 1
    wr_window: int = 100
    wr_threshold: float = 0.32


class PtgPcR6Algorithm(ExecAlgorithm):
    """Position-tier-gate (cap=1) + rolling-window win-rate cooldown."""

    def __init__(self, config: PtgPcR6Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        self._wr_window: int = int(config.wr_window)
        self._wr_threshold: float = float(config.wr_threshold)

        # Rolling deque of bools (True = win, False = loss) for the last
        # `wr_window` closed positions. Use maxlen so push past the limit
        # drops the oldest entry automatically.
        self._wr_buf: deque[bool] = deque(maxlen=self._wr_window)
        # Maintained running count of True (win) entries in the deque.
        # Avoids O(N) sum() on every OPEN.
        self._n_wins_in_buf: int = 0

        # Diagnostic counters (logged at on_stop for falsifiability).
        self._n_orders_seen: int = 0
        self._n_closes_seen: int = 0
        self._n_opens_seen: int = 0
        self._n_skips_cap: int = 0
        self._n_skips_wr: int = 0
        self._n_submits: int = 0
        self._n_position_closed_events: int = 0
        self._n_warmup_submits: int = 0  # OPENs that submitted because deque < window
        self._n_wr_checks_active: int = 0  # OPENs where the WR check was actually consulted

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"PtgPcR6Algorithm started "
            f"(position_cap={self._position_cap}, "
            f"wr_window={self._wr_window}, "
            f"wr_threshold={self._wr_threshold:.3f})."
        )

    def on_stop(self) -> None:
        # Emit diagnostics line so future iterations can read activation
        # rates and feedback-loop impact.
        wr_at_stop = (
            self._n_wins_in_buf / len(self._wr_buf)
            if self._wr_buf
            else float("nan")
        )
        self.log.info(
            "PtgPcR6Algorithm diagnostics: "
            f"n_orders_seen={self._n_orders_seen} "
            f"n_closes_seen={self._n_closes_seen} "
            f"n_opens_seen={self._n_opens_seen} "
            f"n_skips_cap={self._n_skips_cap} "
            f"n_skips_wr={self._n_skips_wr} "
            f"n_submits={self._n_submits} "
            f"n_warmup_submits={self._n_warmup_submits} "
            f"n_wr_checks_active={self._n_wr_checks_active} "
            f"n_position_closed_events={self._n_position_closed_events} "
            f"buffer_len_at_stop={len(self._wr_buf)} "
            f"wins_in_buf_at_stop={self._n_wins_in_buf} "
            f"wr_at_stop={wr_at_stop:.4f}"
        )

    def on_reset(self) -> None:
        # Each backtest date runs in a fresh subprocess, but reset
        # defensively in case Nautilus reuses an instance.
        self._wr_buf.clear()
        self._n_wins_in_buf = 0
        self._n_orders_seen = 0
        self._n_closes_seen = 0
        self._n_opens_seen = 0
        self._n_skips_cap = 0
        self._n_skips_wr = 0
        self._n_submits = 0
        self._n_position_closed_events = 0
        self._n_warmup_submits = 0
        self._n_wr_checks_active = 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _current_net_qty(self, instrument_id) -> float:
        """Return absolute net position quantity for the instrument."""
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        return sum(float(str(p.quantity)) for p in open_positions)

    def _push_outcome(self, is_win: bool) -> None:
        """Push a closed-position outcome into the rolling deque.

        Maintains the running win count. Because the deque has a maxlen,
        appending when the deque is full drops the oldest entry — we must
        decrement the win count if that entry was a win.
        """
        # If at capacity, the leftmost entry is about to be dropped.
        if len(self._wr_buf) == self._wr_window:
            evicted = self._wr_buf[0]
            if evicted:
                self._n_wins_in_buf -= 1
        self._wr_buf.append(is_win)
        if is_win:
            self._n_wins_in_buf += 1

    # ------------------------------------------------------------------
    # Position event handler
    # ------------------------------------------------------------------

    def on_position_closed(self, event: PositionClosed) -> None:
        """Update the rolling win-rate deque on each close event."""
        self._n_position_closed_events += 1
        try:
            pnl_value = event.realized_pnl.as_double()
        except AttributeError:
            # Defensive: if realized_pnl is None or a different type, treat
            # as 0 (a non-win, non-loss outcome — neutral).
            try:
                pnl_value = float(event.realized_pnl)
            except (TypeError, ValueError):
                pnl_value = 0.0

        is_win = pnl_value > 0.0
        self._push_outcome(is_win)

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: cap=1 gate, then rolling-WR cooldown gate, on OPENs."""
        self._n_orders_seen += 1

        # CLOSE leg: always submit (intraday_flat compliance, exits never
        # blocked).
        if order.is_reduce_only:
            self._n_closes_seen += 1
            self.submit_order(order)
            return

        self._n_opens_seen += 1

        # OPEN leg: cap=1 gate (verbatim from base position-tier-gate).
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty >= self._position_cap:
            self._n_skips_cap += 1
            return

        # OPEN leg: rolling-WR cooldown gate.
        # Warmup: while the deque isn't full, the cooldown is inactive.
        if len(self._wr_buf) < self._wr_window:
            self._n_warmup_submits += 1
            self._n_submits += 1
            self.submit_order(order)
            return

        # Deque is full — consult the rolling win-rate.
        self._n_wr_checks_active += 1
        rolling_wr = self._n_wins_in_buf / self._wr_window
        if rolling_wr < self._wr_threshold:
            self._n_skips_wr += 1
            return

        self._n_submits += 1
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    wr_window: int = 100,
    wr_threshold: float = 0.32,
) -> PtgPcR6Algorithm:
    """Instantiate the ptg-pc-r6 execution algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    position_cap : int
        Position-cap gate threshold (contracts). Default 1.
    wr_window : int
        Rolling win-rate deque length. Default 100.
    wr_threshold : float
        Win-rate cutoff for the cooldown filter. Default 0.32.
    """
    config = PtgPcR6Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        wr_window=wr_window,
        wr_threshold=wr_threshold,
    )
    return PtgPcR6Algorithm(config=config)
