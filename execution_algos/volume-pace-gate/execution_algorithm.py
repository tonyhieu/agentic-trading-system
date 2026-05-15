"""Volume-pace-gate execution algorithm.

Conditions the OPEN leg of each oracle signal on event-time progress:
the cumulative volume (total contracts traded) observed since the most
recent executed open-leg order.

Algorithm:
  - Maintain a running counter `_vol_since_last_open` that accumulates
    the size of every TradeTick delivered via on_trade_tick().
  - At each new open-leg order event:
    - If no prior open has been executed this session, submit unconditionally
      (initialization / warm-up).
    - If `_vol_since_last_open` >= `volume_threshold`, execute and reset
      the counter to 0.
    - Otherwise (counter < threshold), skip — insufficient market activity
      since the last entry.
  - Reduce-only / position-closing orders always execute and do NOT reset
    the counter.
  - Counter increments on every trade tick (both sides, unsigned size).

Distinctions from prior algorithms:
  - cooldown-entry-gate: wall-clock time between entries (not event-time)
  - aggressor-flow-gate: signed NET directional flow (not total volume)
  - This algorithm: total unsigned contracts traded = event-time progress,
    independent of direction, independent of clock.

No look-ahead bias: on_trade_tick() fires in strict chronological order
before on_order() for any event with the same or earlier ts_event; the
counter at decision time includes only trades strictly before the order.

Volume threshold calibration (from EDA on 20260308):
  Average ~21 contracts/second, median inter-trade time ~0.002s.
  Default V=50 contracts ≈ ~2.4 seconds of typical activity.
  During thin periods, V contracts take much longer to accumulate,
  effectively deferring entries until the market is active.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class VolumePaceGateConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the volume-pace-gate execution algorithm.

    Parameters
    ----------
    volume_threshold : int
        Minimum total contracts that must trade since the last executed
        open-leg order before the next open is eligible.
        Default 50 contracts ≈ ~2.4 seconds of average activity.
    """

    volume_threshold: int = 50


class VolumePaceGateAlgorithm(ExecAlgorithm):
    """Execution algorithm that gates open orders on event-time volume progress.

    Opening orders (is_reduce_only == False):
      - If no prior open executed this session: submit unconditionally.
      - If _vol_since_last_open >= volume_threshold: submit and reset counter.
      - Otherwise: skip (insufficient activity since last entry).

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).
      - Do NOT reset the volume counter.

    Order quantity is never modified — quantity invariant always preserved.
    """

    def __init__(self, config: VolumePaceGateConfig) -> None:
        super().__init__(config=config)
        self._volume_threshold: int = config.volume_threshold

        # Cumulative unsigned contracts traded since the last executed open-leg.
        self._vol_since_last_open: int = 0

        # True until the first open of the session executes.
        self._first_open_pending: bool = True

        # Subscription tracking (subscribe once per instrument)
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"VolumePaceGateAlgorithm started "
            f"(volume_threshold={self._volume_threshold} contracts)."
        )

    def on_reset(self) -> None:
        self._vol_since_last_open = 0
        self._first_open_pending = True
        self._subscribed.clear()

    # ------------------------------------------------------------------
    # Subscription helper
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_trade_ticks(instrument_id)
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Trade tick handler — accumulate unsigned volume
    # ------------------------------------------------------------------

    def on_trade_tick(self, tick) -> None:
        """Receive a trade tick and accumulate volume in the event-time counter."""
        size = int(str(tick.size))
        self._vol_since_last_open += size

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on event-time volume since last open."""
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        # Closes do NOT reset the volume counter.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # First open of the session — always submit unconditionally.
        if self._first_open_pending:
            self.log.debug(
                f"First open {order.client_order_id}; submitting unconditionally."
            )
            self._first_open_pending = False
            self._vol_since_last_open = 0  # reset counter from this point
            self.submit_order(order)
            return

        # Check volume threshold.
        if self._vol_since_last_open >= self._volume_threshold:
            self.log.debug(
                f"SUBMIT {order.client_order_id} — volume threshold met "
                f"(vol_since_open={self._vol_since_last_open} >= "
                f"threshold={self._volume_threshold})."
            )
            self._vol_since_last_open = 0  # reset counter
            self.submit_order(order)
        else:
            self.log.debug(
                f"SKIP {order.client_order_id} — insufficient volume "
                f"(vol_since_open={self._vol_since_last_open} < "
                f"threshold={self._volume_threshold})."
            )
            # Do NOT call submit_order — quantity invariant preserved.
            # Do NOT reset the counter — it keeps accumulating.


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    volume_threshold: int = 50,
) -> VolumePaceGateAlgorithm:
    """Instantiate and return the VolumePaceGateAlgorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    volume_threshold : int
        Minimum total contracts traded since the last executed open-leg order
        before the next open-leg is eligible.
        Default 50 contracts.
    """
    config = VolumePaceGateConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        volume_threshold=volume_threshold,
    )
    return VolumePaceGateAlgorithm(config=config)
