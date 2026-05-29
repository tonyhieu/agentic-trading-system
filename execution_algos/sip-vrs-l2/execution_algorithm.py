"""Session-close-suppress vol-regime sizer (sip-vrs-l2).

Hypothesis (loop 2, propose-falsify-commit method):
-----------------------------------------------------------------
The parent `vol-regime-sizer` has no time-of-day component. On the two
worst-loss train dates (20260317, 20260313) the last 15 minutes of the
regular trading hour (RTH close, 21:00 UTC = 16:00 CT) had aggregate
mean realized_pnl = -$0.067 / contract, versus an all-day mean of
-$0.022 / contract — a -$0.045 / contract deficit. The parent's
unsigned vol-ratio gate does NOT preferentially skip these
late-session trades because vol-ratio is not elevated during them.

This algorithm layers a session-close gate on TOP of the parent's
existing vol-regime probability:

    minutes_to_close = (SESSION_END_UTC - current_market_time).total_seconds()
    if 0 <= minutes_to_close < close_window:
        p_submit = parent_p_submit * close_suppress
    else:
        p_submit = parent_p_submit

With `close_suppress = 0.0`, the close window becomes a hard skip — every
open-leg order in the last `close_window` seconds is suppressed,
regardless of vol regime. Reduce-only orders are submitted unconditionally
(intraday_flat compliance, identical to parent). Quantity invariant is
preserved (the algorithm never inflates qty).

Parameter derivations (NOTES.md, step 6):
- close_window = 900 (15 min): selected from step-4 statistic — the
  15-min pre-close bucket had n=145 across the two test dates, large
  enough to commit to and with mean_pnl materially below the all-day
  baseline. The 5-min window had a larger delta but only n=51.
- close_suppress = 0.0 (hard skip): principled rule — when expected
  pnl in a regime is negative (-$0.067/contract here), the rational
  participation rate is 0.
- All other parameters inherit from parent vol-regime-sizer: fast_halflife=20,
  slow_halflife=120, sensitivity=2.0, min_prob=0.05, min_ticks=30,
  max_vol_ratio=5.0.
- SESSION_END_UTC = 21:00:00 UTC: CME equity-index futures RTH close
  (16:00 CT), a fixed market-convention timestamp, not an inherited or
  intuited parameter.

Inherited mechanics from parent: EWM fast/slow on |Δmid|, vol_ratio,
exp-decay probability, deterministic SHA-256(client_order_id) draw,
reduce-only exemption.
"""
from __future__ import annotations

import hashlib
import math
import struct
from datetime import time as dt_time

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


# CME equity-index RTH close, 21:00 UTC (16:00 CT).
SESSION_END_HOUR_UTC: int = 21
SESSION_END_MINUTE_UTC: int = 0


class SipVrsL2Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for session-close-suppress vol-regime sizer.

    Parameters inherit from parent vol-regime-sizer; new parameters
    introduce the close-window gate.
    """

    fast_halflife: int = 20
    slow_halflife: int = 120
    sensitivity: float = 2.0
    min_prob: float = 0.05
    min_ticks: int = 30
    max_vol_ratio: float = 5.0
    close_window: int = 900       # seconds before SESSION_END_UTC; 15 min
    close_suppress: float = 0.0   # multiplier on parent_p_submit in window


class SipVrsL2Algorithm(ExecAlgorithm):
    """Session-close-suppress wrapper on vol-regime sizer.

    For each incoming OPEN order:
      1. Update EWM fast/slow on |Δmid| from recent quote ticks.
      2. Compute parent_p_submit = max(min_prob, exp(-sensitivity * max(0, vol_ratio - 1))).
      3. If current market time is within `close_window` seconds before
         SESSION_END_UTC (21:00 UTC), multiply by `close_suppress`.
      4. Accept or skip via deterministic SHA-256(client_order_id) draw.

    For reduce-only (CLOSE) orders: always submit unconditionally.
    """

    def __init__(self, config: SipVrsL2Config) -> None:
        super().__init__(config=config)

        # Parent (vol-regime-sizer) parameters
        self._fast_alpha: float = 1.0 - math.exp(-math.log(2) / config.fast_halflife)
        self._slow_alpha: float = 1.0 - math.exp(-math.log(2) / config.slow_halflife)
        self._sensitivity: float = config.sensitivity
        self._min_prob: float = config.min_prob
        self._min_ticks: int = config.min_ticks
        self._max_vol_ratio: float = config.max_vol_ratio

        # Loop-2 close-window parameters
        self._close_window: int = config.close_window
        self._close_suppress: float = config.close_suppress

        # EWM state
        self._fast_vol: float | None = None
        self._slow_vol: float | None = None
        self._prev_mid: float | None = None
        self._tick_count: int = 0
        self._last_tick_ts_ns: int | None = None

        # Subscription tracking
        self._subscribed: set[str] = set()

        # Diagnostic counters
        self._submitted: int = 0
        self._skipped_vol: int = 0
        self._skipped_close: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"SipVrsL2Algorithm started "
            f"(fast_alpha={self._fast_alpha:.4f}, slow_alpha={self._slow_alpha:.4f}, "
            f"sensitivity={self._sensitivity}, min_prob={self._min_prob}, "
            f"min_ticks={self._min_ticks}, close_window={self._close_window}s, "
            f"close_suppress={self._close_suppress}, "
            f"session_end={SESSION_END_HOUR_UTC:02d}:{SESSION_END_MINUTE_UTC:02d} UTC)."
        )

    def on_reset(self) -> None:
        self._fast_vol = None
        self._slow_vol = None
        self._prev_mid = None
        self._tick_count = 0
        self._last_tick_ts_ns = None
        self._subscribed.clear()
        self._submitted = 0
        self._skipped_vol = 0
        self._skipped_close = 0

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Quote tick handler — update EWM vol estimates AND market clock
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        """Update EWM vol estimates and latest market timestamp."""
        # Update latest market timestamp (used for close-window gate)
        try:
            self._last_tick_ts_ns = int(tick.ts_event)
        except Exception:
            pass

        try:
            bid = float(str(tick.bid_price))
            ask = float(str(tick.ask_price))
            mid = (bid + ask) / 2.0
        except Exception:
            return

        if self._prev_mid is not None:
            abs_delta = abs(mid - self._prev_mid)
            if self._fast_vol is None:
                self._fast_vol = abs_delta
                self._slow_vol = abs_delta
            else:
                self._fast_vol = (
                    self._fast_alpha * abs_delta + (1.0 - self._fast_alpha) * self._fast_vol
                )
                self._slow_vol = (
                    self._slow_alpha * abs_delta + (1.0 - self._slow_alpha) * self._slow_vol
                )

        self._prev_mid = mid
        self._tick_count += 1

    # ------------------------------------------------------------------
    # Parent's vol-regime probability (inherited unchanged)
    # ------------------------------------------------------------------

    def _compute_parent_prob(self) -> float:
        """Return parent vol-regime-sizer's p_submit (no close-window gate)."""
        if self._tick_count < self._min_ticks:
            return 1.0
        if self._fast_vol is None or self._slow_vol is None:
            return 1.0
        if self._slow_vol < 1e-12:
            return 1.0
        vol_ratio = min(self._fast_vol / self._slow_vol, self._max_vol_ratio)
        excess = max(0.0, vol_ratio - 1.0)
        prob = math.exp(-self._sensitivity * excess)
        prob = max(self._min_prob, prob)
        return prob

    # ------------------------------------------------------------------
    # Close-window detection
    # ------------------------------------------------------------------

    def _in_close_window(self) -> bool:
        """Return True if latest market time is within `close_window` of 21:00 UTC.

        Uses the most-recent quote tick's `ts_event` (nanoseconds since
        epoch). If no quote tick has arrived yet (cold start), returns
        False — i.e., do not suppress; the parent's cold-start behavior
        is preserved.
        """
        if self._last_tick_ts_ns is None:
            return False
        # Convert ns since epoch to (hour, minute, second) UTC time-of-day.
        # We do this by hand to avoid datetime allocation on every order.
        secs_total = self._last_tick_ts_ns // 1_000_000_000
        secs_of_day = int(secs_total % 86_400)  # 0..86399
        session_end_secs = SESSION_END_HOUR_UTC * 3600 + SESSION_END_MINUTE_UTC * 60
        # Distance to session-end (positive if still before close, 0 at close).
        # Negative values mean we are AFTER the RTH close (post-close session) —
        # do NOT suppress in that regime (post-close is a separate liquidity
        # condition; the falsification test only spoke to pre-close).
        seconds_to_close = session_end_secs - secs_of_day
        return 0 <= seconds_to_close < self._close_window

    # ------------------------------------------------------------------
    # Deterministic pseudo-random draw (inherited unchanged from parent)
    # ------------------------------------------------------------------

    @staticmethod
    def _order_uniform(order_id_str: str) -> float:
        digest = hashlib.sha256(order_id_str.encode()).digest()
        val = struct.unpack(">Q", digest[:8])[0]
        return val / (2**64)

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip via parent_p * (close_suppress if in window)."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders: always submit — intraday_flat compliance.
        if order.is_reduce_only:
            self.submit_order(order)
            return

        parent_prob = self._compute_parent_prob()
        in_close = self._in_close_window()

        if in_close:
            p = parent_prob * self._close_suppress
        else:
            p = parent_prob

        # Full participation shortcut
        if p >= 1.0 - 1e-9:
            self._submitted += 1
            self.submit_order(order)
            return

        # Hard-skip shortcut: avoid hashing if p is effectively 0
        if p <= 1e-12:
            if in_close:
                self._skipped_close += 1
            else:
                self._skipped_vol += 1
            return

        # Deterministic draw from order ID
        u = self._order_uniform(str(order.client_order_id))
        if u < p:
            self._submitted += 1
            self.submit_order(order)
        else:
            if in_close:
                self._skipped_close += 1
                self.log.debug(
                    f"SKIP-CLOSE {order.client_order_id} (p={p:.4f}, u={u:.4f}). "
                    f"submitted={self._submitted} skipped_vol={self._skipped_vol} "
                    f"skipped_close={self._skipped_close}."
                )
            else:
                self._skipped_vol += 1


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    fast_halflife: int = 20,
    slow_halflife: int = 120,
    sensitivity: float = 2.0,
    min_prob: float = 0.05,
    min_ticks: int = 30,
    max_vol_ratio: float = 5.0,
    close_window: int = 900,
    close_suppress: float = 0.0,
) -> SipVrsL2Algorithm:
    """Instantiate and return the SipVrsL2Algorithm."""
    config = SipVrsL2Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        fast_halflife=fast_halflife,
        slow_halflife=slow_halflife,
        sensitivity=sensitivity,
        min_prob=min_prob,
        min_ticks=min_ticks,
        max_vol_ratio=max_vol_ratio,
        close_window=close_window,
        close_suppress=close_suppress,
    )
    return SipVrsL2Algorithm(config=config)
