"""Session-clock-gate execution algorithm.

Conditions the open leg of each oracle signal on the intraday wall-clock
time mapped to the CME RTH session. Skips entries during structurally
low-quality session windows; executes normally during stable mid-session.
Reduce-only orders always execute.

Session-phase windows skipped (configurable, in minutes-since-midnight UTC):
  - Open turbulence:   first 30 min of RTH (default 08:30-09:00 CT / 13:30-14:00 UTC CDT)
  - Midday lull:       11:45-12:15 CT / 16:45-17:15 UTC CDT
  - Pre-close ramp:    last 15 min of RTH (default 15:00-15:15 CT / 20:00-20:15 UTC CDT)

The algorithm is purely temporal — it reads only order.ts_init (nanosecond
UTC timestamp) and computes the intraday minute offset. No microstructure
signals, no book data, no P&L history.

There is no look-ahead bias: the timestamp is set when the order is initialized,
before any fill occurs.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId

# Seconds per minute, for clarity
_S_PER_MIN = 60
# Nanoseconds per second
_NS_PER_S = 1_000_000_000


def _utc_minute_of_day(ts_init_ns: int, utc_offset_hours: float) -> int:
    """Return the minute-of-day (0-1439) in the configured local timezone.

    Parameters
    ----------
    ts_init_ns : int
        UNIX nanosecond timestamp (UTC).
    utc_offset_hours : float
        Hours to ADD to UTC to get local time (e.g., -5 for CDT, -6 for CST).

    Returns
    -------
    int
        Minutes since midnight in local time, in range [0, 1439].
    """
    ts_s = ts_init_ns / _NS_PER_S
    # Offset in seconds
    offset_s = int(utc_offset_hours * 3600)
    local_s = ts_s + offset_s
    # Seconds since midnight in local time
    secs_since_midnight = int(local_s) % 86400
    return secs_since_midnight // _S_PER_MIN


class SessionClockGateConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the session-clock-gate execution algorithm.

    Parameters
    ----------
    utc_offset_hours : float
        Timezone offset from UTC in hours. Use -5 for CDT (2026 DST active),
        -6 for CST (standard time). Default -5 (CDT).
    open_turbulence_start : int
        Start minute-of-day (local) for the open-turbulence skip window.
        Default 510 = 08:30 CT.
    open_turbulence_end : int
        End minute-of-day (local, exclusive) for open-turbulence window.
        Default 540 = 09:00 CT.
    midday_lull_start : int
        Start minute-of-day (local) for the midday-lull skip window.
        Default 705 = 11:45 CT.
    midday_lull_end : int
        End minute-of-day (local, exclusive) for midday-lull window.
        Default 735 = 12:15 CT.
    preclose_ramp_start : int
        Start minute-of-day (local) for the pre-close-ramp skip window.
        Default 900 = 15:00 CT.
    preclose_ramp_end : int
        End minute-of-day (local, exclusive) for pre-close-ramp window.
        Default 915 = 15:15 CT.
    """

    utc_offset_hours: float = -5.0          # CDT (UTC-5), valid for train window
    open_turbulence_start: int = 510        # 08:30 CT
    open_turbulence_end: int = 540          # 09:00 CT
    midday_lull_start: int = 705            # 11:45 CT
    midday_lull_end: int = 735              # 12:15 CT
    preclose_ramp_start: int = 900          # 15:00 CT
    preclose_ramp_end: int = 915            # 15:15 CT


class SessionClockGateAlgorithm(ExecAlgorithm):
    """Execution algorithm that gates open-leg entries by session phase.

    Opening orders (is_reduce_only == False):
      - Compute intraday minute-of-day from order.ts_init.
      - Skip if the minute falls in any configured skip window.
      - After any skip, _position_flat = True: the NEXT open is always submitted
        regardless of clock to prevent cascade (same safety guard as
        streak-spread-tight).

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    No order quantity is ever modified. Quantity invariant always preserved.
    """

    def __init__(self, config: SessionClockGateConfig) -> None:
        super().__init__(config=config)
        self._utc_offset_hours: float = config.utc_offset_hours
        # Skip windows: list of (start_minute_inclusive, end_minute_exclusive)
        self._skip_windows: list[tuple[int, int]] = [
            (config.open_turbulence_start, config.open_turbulence_end),
            (config.midday_lull_start, config.midday_lull_end),
            (config.preclose_ramp_start, config.preclose_ramp_end),
        ]
        # Safety: forced re-entry after any skip to prevent cascade
        self._position_flat: bool = True

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        windows_str = ", ".join(
            f"{s//60:02d}:{s%60:02d}-{e//60:02d}:{e%60:02d}"
            for s, e in self._skip_windows
        )
        self.log.info(
            f"SessionClockGateAlgorithm started "
            f"(utc_offset={self._utc_offset_hours:+.1f}h, "
            f"skip_windows_CT=[{windows_str}])."
        )

    def on_reset(self) -> None:
        self._position_flat = True

    # ------------------------------------------------------------------
    # Skip-window evaluation
    # ------------------------------------------------------------------

    def _in_skip_window(self, ts_init_ns: int) -> bool:
        """Return True if the order's timestamp falls in any skip window."""
        minute = _utc_minute_of_day(ts_init_ns, self._utc_offset_hours)
        for start, end in self._skip_windows:
            if start <= minute < end:
                return True
        return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route the order: submit or skip based on session-clock windows."""

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Forced re-entry after a skip — always submit to prevent cascade.
        if self._position_flat:
            self.log.debug(
                f"Re-entry after skip (or first trade); submitting "
                f"{order.client_order_id}."
            )
            self._position_flat = False
            self.submit_order(order)
            return

        # Evaluate session-clock condition.
        skip = self._in_skip_window(order.ts_init)

        if skip:
            minute = _utc_minute_of_day(order.ts_init, self._utc_offset_hours)
            self.log.info(
                f"SKIP order {order.client_order_id} "
                f"(minute_of_day={minute}, adverse session window)."
            )
            self._position_flat = True
            # Do NOT call submit_order — quantity invariant preserved.
        else:
            self.log.debug(
                f"SUBMIT order {order.client_order_id} "
                f"(minute={_utc_minute_of_day(order.ts_init, self._utc_offset_hours)}, "
                f"mid-session)."
            )
            self._position_flat = False
            self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    utc_offset_hours: float = -5.0,
    open_turbulence_start: int = 510,
    open_turbulence_end: int = 540,
    midday_lull_start: int = 705,
    midday_lull_end: int = 735,
    preclose_ramp_start: int = 900,
    preclose_ramp_end: int = 915,
) -> SessionClockGateAlgorithm:
    """Instantiate and return the SessionClockGateAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    utc_offset_hours : float
        Timezone offset from UTC. Default -5.0 (CDT, valid for 2026-03-08 to
        2026-03-21 train window).
    open_turbulence_start, open_turbulence_end : int
        Skip window in minutes-since-midnight local time. Default 510-540
        (08:30-09:00 CT).
    midday_lull_start, midday_lull_end : int
        Midday lull window. Default 705-735 (11:45-12:15 CT).
    preclose_ramp_start, preclose_ramp_end : int
        Pre-close ramp window. Default 900-915 (15:00-15:15 CT).
    """
    config = SessionClockGateConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),  # noqa: intentionally "MY_GENERIC_ALGO" to match strategy routing
        utc_offset_hours=utc_offset_hours,
        open_turbulence_start=open_turbulence_start,
        open_turbulence_end=open_turbulence_end,
        midday_lull_start=midday_lull_start,
        midday_lull_end=midday_lull_end,
        preclose_ramp_start=preclose_ramp_start,
        preclose_ramp_end=preclose_ramp_end,
    )
    return SessionClockGateAlgorithm(config=config)
