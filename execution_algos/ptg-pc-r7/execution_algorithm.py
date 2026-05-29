"""ptg-pc-r7 execution algorithm.

FEEDBACK-BOUNDED ROLLING-PNL COOLDOWN, layered on position-tier-gate (cap=1).

Hypothesis (see NOTES.md):
  The noisy oracle (sigma=6.0, R^2 ~14%) exhibits time-varying regime quality.
  When the most recent N=225 closed positions have aggregated to a sum <= -$8
  (about -$0.036/trade vs the global mean +$0.047/trade), the algorithm is in
  a loser-cluster regime. Skipping the next OPEN in that regime — bounded by
  a 65% hard ceiling on rolling skip-rate to prevent r6's feedback freeze —
  yields +6.68% offline delta over base PTG, with Sharpe improving 17.62 -> 20.06.

Decision rule (in order, applied at each cap-passing OPEN):
  1. WARMUP: if len(kept_pnl_buf) < N -> SUBMIT.
  2. ROLLING-SUM-OK: if kept_sum >= thresh -> SUBMIT.
  3. CEILING-BIND: if action_skip_rate >= max_skip -> FORCE-SUBMIT
     (this is the feedback-defense path that protects against r6's freeze).
  4. SKIP: otherwise.

Defense against r6's failure mode:
  - SUM-of-PnL signal (linear sensitivity to outcome magnitude; recovers fast
    after big winners) instead of WIN-RATE (0/1-quantized, slow recovery).
  - HARD 65% ceiling on action-history skip-rate prevents the catastrophic
    92% skip rate r6 exhibited live.

Signal source: on_position_closed events (Nautilus standard hook, verified
working on ExecAlgorithm via r2 and r6). The action-history is the algo's
own decision log. Both are intrinsically reliable — no simulator-delivered
sub-second market data dependency.

No look-ahead: deque is updated only from past close events. At on_order()
time it reflects only positions that have already closed.

No quantity modification: SKIP or SUBMIT, quantity invariant preserved.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.events import PositionClosed
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PtgPcR7Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for ptg-pc-r7.

    Parameters
    ----------
    position_cap : int
        Maximum absolute net position size (contracts) at which new OPEN
        orders are still allowed. When current net qty >= position_cap, the
        open leg is skipped. Default 1 (matches base position-tier-gate).
    pnl_window : int
        Length of the rolling kept-position-PnL deque (N). Default 225.
        Until the deque has pnl_window entries, the cooldown is inactive
        (warmup -> always SUBMIT).
    pnl_threshold : float
        Rolling-sum threshold (USD). When sum-of-last-N kept-position PnLs
        is BELOW this threshold, the algorithm enters cooldown mode and
        will SKIP new OPENs (subject to the ceiling defense). Default -8.0.
    action_window : int
        Length of the rolling action-history deque (W). Tracks the last W
        OPEN decisions to compute the recent skip rate. Default 200.
    max_skip_rate : float
        Hard ceiling on the rolling skip-rate. When cur_skip_rate >=
        max_skip_rate, FORCE-SUBMIT instead of skipping. Default 0.65.
        This bound protects against r6's feedback-loop freeze.
    """

    position_cap: int = 1
    pnl_window: int = 225
    pnl_threshold: float = -8.0
    action_window: int = 200
    max_skip_rate: float = 0.65


class PtgPcR7Algorithm(ExecAlgorithm):
    """Position-tier-gate (cap=1) + bounded rolling-PnL cooldown."""

    def __init__(self, config: PtgPcR7Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = int(config.position_cap)
        self._pnl_window: int = int(config.pnl_window)
        self._pnl_threshold: float = float(config.pnl_threshold)
        self._action_window: int = int(config.action_window)
        self._max_skip_rate: float = float(config.max_skip_rate)

        # Rolling deque of the last N closed-position PnLs.
        # Use maxlen so push past the limit drops the oldest entry automatically;
        # eviction-bookkeeping is handled in _push_pnl for O(1) sum maintenance.
        self._kept_buf: deque[float] = deque(maxlen=self._pnl_window)
        self._kept_sum: float = 0.0

        # Rolling deque of the last W OPEN decisions (1 = skipped, 0 = submitted).
        # CLOSE orders do NOT enter this deque (only OPEN decisions count).
        self._action_buf: deque[int] = deque(maxlen=self._action_window)
        self._action_skip_count: int = 0

        # Diagnostic counters (logged at on_stop for falsifiability).
        self._n_orders_seen: int = 0
        self._n_closes_seen: int = 0
        self._n_opens_seen: int = 0
        self._n_skips_cap: int = 0
        self._n_skips_pnl: int = 0
        self._n_force_submits: int = 0
        self._n_submits: int = 0
        self._n_warmup_submits: int = 0
        self._n_position_closed_events: int = 0
        self._max_observed_skip_rate: float = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"PtgPcR7Algorithm started "
            f"(position_cap={self._position_cap}, "
            f"pnl_window={self._pnl_window}, "
            f"pnl_threshold={self._pnl_threshold:.4f}, "
            f"action_window={self._action_window}, "
            f"max_skip_rate={self._max_skip_rate:.3f})."
        )

    def on_stop(self) -> None:
        # Emit diagnostics line so future iterations can read activation rates
        # and confirm the feedback-defense bound was respected.
        self.log.info(
            "PtgPcR7Algorithm diagnostics: "
            f"n_orders_seen={self._n_orders_seen} "
            f"n_closes_seen={self._n_closes_seen} "
            f"n_opens_seen={self._n_opens_seen} "
            f"n_skips_cap={self._n_skips_cap} "
            f"n_skips_pnl={self._n_skips_pnl} "
            f"n_force_submits={self._n_force_submits} "
            f"n_submits={self._n_submits} "
            f"n_warmup_submits={self._n_warmup_submits} "
            f"n_position_closed_events={self._n_position_closed_events} "
            f"kept_buf_len_at_stop={len(self._kept_buf)} "
            f"kept_sum_at_stop={self._kept_sum:.4f} "
            f"max_observed_skip_rate={self._max_observed_skip_rate:.4f}"
        )

    def on_reset(self) -> None:
        # Each backtest date runs in a fresh subprocess, but reset defensively
        # in case Nautilus reuses an instance.
        self._kept_buf.clear()
        self._kept_sum = 0.0
        self._action_buf.clear()
        self._action_skip_count = 0
        self._n_orders_seen = 0
        self._n_closes_seen = 0
        self._n_opens_seen = 0
        self._n_skips_cap = 0
        self._n_skips_pnl = 0
        self._n_force_submits = 0
        self._n_submits = 0
        self._n_warmup_submits = 0
        self._n_position_closed_events = 0
        self._max_observed_skip_rate = 0.0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _current_net_qty(self, instrument_id) -> float:
        """Return absolute net position quantity for the instrument."""
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        return sum(float(str(p.quantity)) for p in open_positions)

    def _push_pnl(self, pnl: float) -> None:
        """Push a closed-position PnL into the rolling deque.

        Maintains the running sum. Because the deque has a maxlen, appending
        when full drops the oldest entry — subtract its value from the sum
        before appending the new one.
        """
        if len(self._kept_buf) == self._pnl_window:
            evicted = self._kept_buf[0]
            self._kept_sum -= evicted
        self._kept_buf.append(pnl)
        self._kept_sum += pnl

    def _push_action(self, is_skip: bool) -> None:
        """Push an OPEN-decision action (1=skip, 0=submit) into the action history.

        Maintains the running skip count.
        """
        action = 1 if is_skip else 0
        if len(self._action_buf) == self._action_window:
            evicted = self._action_buf[0]
            if evicted == 1:
                self._action_skip_count -= 1
        self._action_buf.append(action)
        if action == 1:
            self._action_skip_count += 1

    # ------------------------------------------------------------------
    # Position event handler
    # ------------------------------------------------------------------

    def on_position_closed(self, event: PositionClosed) -> None:
        """Update the rolling-PnL deque on each close event."""
        self._n_position_closed_events += 1
        # Defensive extraction of realized PnL (event.realized_pnl may be a
        # Nautilus Money object with as_double(), or occasionally a raw float).
        try:
            pnl_value = event.realized_pnl.as_double()
        except AttributeError:
            try:
                pnl_value = float(event.realized_pnl)
            except (TypeError, ValueError):
                pnl_value = 0.0
        self._push_pnl(pnl_value)

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: cap=1 gate, then bounded-PnL-cooldown gate, on OPENs."""
        self._n_orders_seen += 1

        # CLOSE leg: always submit (intraday_flat compliance, exits never blocked).
        # CLOSE orders do NOT enter the action history.
        if order.is_reduce_only:
            self._n_closes_seen += 1
            self.submit_order(order)
            return

        self._n_opens_seen += 1

        # GATE 1: cap=1 (verbatim from base position-tier-gate).
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty >= self._position_cap:
            self._n_skips_cap += 1
            # cap-skipped OPENs do NOT enter the action history — the action
            # window tracks only the decisions made by the second (PnL) gate.
            # This is intentional: cap is a deterministic state filter, the
            # cooldown is the regime filter we are measuring.
            return

        # GATE 2: bounded rolling-PnL cooldown.
        # Branch (a) WARMUP: deque not yet full -> SUBMIT.
        if len(self._kept_buf) < self._pnl_window:
            self._n_warmup_submits += 1
            self._n_submits += 1
            self._push_action(is_skip=False)
            self.submit_order(order)
            return

        # Branch (b) ROLLING-SUM-OK: kept_sum >= threshold -> SUBMIT.
        if self._kept_sum >= self._pnl_threshold:
            self._n_submits += 1
            self._push_action(is_skip=False)
            self.submit_order(order)
            return

        # Branch (c) CEILING-BIND: cur_skip_rate >= max_skip -> FORCE-SUBMIT.
        # This is the feedback-defense path that prevents r6's freeze.
        action_buf_len = len(self._action_buf)
        if action_buf_len > 0:
            cur_skip_rate = self._action_skip_count / action_buf_len
        else:
            cur_skip_rate = 0.0
        if cur_skip_rate > self._max_observed_skip_rate:
            self._max_observed_skip_rate = cur_skip_rate

        if cur_skip_rate >= self._max_skip_rate:
            self._n_force_submits += 1
            self._n_submits += 1
            self._push_action(is_skip=False)
            self.submit_order(order)
            return

        # Branch (d) SKIP — cooldown active and ceiling not yet binding.
        self._n_skips_pnl += 1
        self._push_action(is_skip=True)
        # Do NOT call submit_order — quantity invariant preserved.


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    pnl_window: int = 225,
    pnl_threshold: float = -8.0,
    action_window: int = 200,
    max_skip_rate: float = 0.65,
) -> PtgPcR7Algorithm:
    """Instantiate the ptg-pc-r7 execution algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    position_cap : int
        Position-cap gate threshold (contracts). Default 1.
    pnl_window : int
        Rolling kept-PnL deque length (N). Default 225.
    pnl_threshold : float
        Rolling-sum threshold below which cooldown activates. Default -8.0.
    action_window : int
        Rolling action-history deque length (W). Default 200.
    max_skip_rate : float
        Hard ceiling on rolling skip-rate (feedback defense). Default 0.65.
    """
    config = PtgPcR7Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        pnl_window=pnl_window,
        pnl_threshold=pnl_threshold,
        action_window=action_window,
        max_skip_rate=max_skip_rate,
    )
    return PtgPcR7Algorithm(config=config)
