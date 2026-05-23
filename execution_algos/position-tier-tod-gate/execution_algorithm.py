"""Position-tier + EMA-imbalance + TIME-OF-DAY gate execution algorithm.

Iter-7 STRUCTURAL axis change. Builds on iter-2 best
`position-tier-imbalance-ema-gate` (pnl=4503.25, sharpe=20.79 on N=11).
Adds ONE new mechanism orthogonal to the inherited gate stack:

  * Time-of-day (TOD) gate on OPEN orders only:
      SKIP every OPEN-leg order whose ts_init falls inside either
      `open_window_minutes` after the cash-equity session open
      (13:30 UTC, i.e. 09:30 ET) or `close_window_minutes` before the
      cash-equity session close (20:00 UTC, i.e. 16:00 ET).
      Reduce-only orders are NEVER touched by this gate (intraday_flat
      compliance).

Why this axis (per iter-6 NOTES.md):
  Iters 2-6 cluster pnl in $4377-$4503 (a 2.9% spread on N=11), with
  five PASS algos all sitting in this narrow band irrespective of which
  upstream signal (single-tick imbalance / EMA imbalance / OFI / sym-vol
  / dir-vol) is layered on the inherited `position_cap=1` +
  reduce-only-fast-path stack. The family-internal gradient on
  GATE-AXIS tweaks (different microstructure signals at the same
  trade-time decision point) is exhausted. The remaining improvement
  gradient must be on a STRUCTURALLY DIFFERENT mechanism. Iter-6 listed
  two candidates: (a) time-of-day filter, (b) reduce-only ladder. This
  iteration probes (a) — the cheaper of the two — because it can be
  tested with a tiny code delta and gives a clean answer to a load-
  bearing structural question: "is the binding constraint actually
  intraday-uniform, or is there a session-time axis of unrealised edge?"

Hypothesis:
  ES-family microstructure literature (Bouchaud/Bonart/Donier;
  Easley/Lopez-de-Prado/O'Hara) consistently documents two intraday
  liquidity / volatility regimes that depress short-horizon
  directional-signal edge:
    (1) Cash-equity OPEN (13:30 UTC for ET) -> microstructure noise
        burst, wide effective spread, fastest mid drift; price-discovery
        regime where the oracle's 30s forecast horizon is largely
        absorbed in the first few minutes of price action.
    (2) Cash-equity CLOSE (20:00 UTC for ET) -> inventory unwind,
        volume spike, settlement / hedging flow; directional persistence
        of intra-day signals collapses near the close.
  If the position-tier gate's binding pnl ceiling is partly the
  *accumulation of small adverse OPEN-side decisions during these two
  high-noise intervals*, an open/close time skip should lift pnl
  monotonically by removing exactly those adverse decisions.

  Falsification path: if pnl falls (or is unchanged) after the time
  filter is added, the binding constraint is genuinely intraday-uniform
  and the position_cap=1 + reduce-only fast-path family has no
  session-time edge to recover. That is itself a useful structural
  takeaway for iter-8.

Defaults (held-out justification):
  open_window_minutes=30  : standard ES "first 30 minutes" microstructure
                            window used in Easley/Lopez-de-Prado VPIN
                            studies; also the window over which futures
                            volume profile is U-shaped at its left peak.
  close_window_minutes=30 : symmetric right peak of the volume U-shape;
                            also overlaps the cash-equity close auction
                            inventory unwind.
  cash_open_utc_hour=13   : NYSE 09:30 ET in UTC during DST (the train
  cash_open_utc_minute=30   window 2026-03-08 .. 2026-03-21 is fully in
  cash_close_utc_hour=20    US DST; DST started 2026-03-08, so 09:30 ET
  cash_close_utc_minute=0   == 13:30 UTC and 16:00 ET == 20:00 UTC).
  Held-out: I am NOT optimising the window length on the train set; 30
  minutes is a literature-standard default for the ES family and is
  picked once.

No look-ahead:
  `order.ts_init` is the timestamp the engine attaches when the order is
  created upstream of the execution algorithm; it reflects strictly
  past wall-clock time relative to the on_order callback. The TOD gate
  compares this timestamp to fixed UTC session boundaries; no future
  information is used.

No quantity modification:
  Every parent order is either submitted intact (after all gates pass)
  or skipped entirely. Quantity invariant `sum(child_fills) <=
  parent.quantity` always preserved.

Inherited components (verbatim from iter-2):
  - position_cap=1 (cascade-prevention positional gate)
  - reduce-only fast-path (intraday_flat compliance; ALSO bypasses TOD)
  - EMA-imbalance gate (alpha=0.30, skip_threshold=0.40, min_total_size=2.0)
"""

from __future__ import annotations

from datetime import datetime, timezone

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PositionTierTodGateConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the position-tier + EMA-imbalance + TOD gate algorithm.

    Parameters
    ----------
    position_cap : int
        Max absolute net position (contracts) at which new OPEN-leg
        orders are still allowed. Default 1.
    skip_threshold : float
        EMA-imbalance threshold for the imbalance gate. Default 0.40.
    min_total_size : float
        Minimum bid_size + ask_size for a quote to seed/update the EMA.
        Default 2.0.
    ema_alpha : float
        EMA smoothing factor in (0, 1]. Default 0.30.
    open_window_minutes : int
        Minutes after the cash-equity open during which OPEN-leg orders
        are skipped. Default 30.
    close_window_minutes : int
        Minutes before the cash-equity close during which OPEN-leg
        orders are skipped. Default 30.
    cash_open_utc_hour : int
        UTC hour of the cash-equity open. Default 13 (09:30 ET DST).
    cash_open_utc_minute : int
        UTC minute of the cash-equity open. Default 30.
    cash_close_utc_hour : int
        UTC hour of the cash-equity close. Default 20 (16:00 ET DST).
    cash_close_utc_minute : int
        UTC minute of the cash-equity close. Default 0.
    """

    position_cap: int = 1
    skip_threshold: float = 0.40
    min_total_size: float = 2.0
    ema_alpha: float = 0.30
    open_window_minutes: int = 30
    close_window_minutes: int = 30
    cash_open_utc_hour: int = 13
    cash_open_utc_minute: int = 30
    cash_close_utc_hour: int = 20
    cash_close_utc_minute: int = 0


class PositionTierTodGateAlgorithm(ExecAlgorithm):
    """Execution algo: position-tier + EMA-imbalance + TOD gate.

    Opening orders (is_reduce_only == False):
      1. TOD gate: if order ts_init is in [open, open+open_window) or
         [close-close_window, close), SKIP.
      2. Positional gate: if abs(net_qty) >= position_cap, SKIP.
      3. EMA-imbalance gate: if EMA imbalance is adverse to side, SKIP.
      4. Otherwise SUBMIT.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance, TOD
        gate intentionally bypassed).

    Quote ticks (on_quote_tick):
      - Maintain per-instrument EMA imbalance (alpha smoothing).
    """

    _NS_PER_MIN: int = 60 * 1_000_000_000

    def __init__(self, config: PositionTierTodGateConfig) -> None:
        super().__init__(config=config)

        # Inherited iter-2 params
        self._position_cap: int = int(config.position_cap)
        self._skip_threshold: float = float(config.skip_threshold)
        self._min_total_size: float = float(config.min_total_size)
        self._ema_alpha: float = float(config.ema_alpha)

        # TOD params (iter-7 new)
        self._open_window_minutes: int = max(0, int(config.open_window_minutes))
        self._close_window_minutes: int = max(0, int(config.close_window_minutes))
        self._cash_open_hour: int = int(config.cash_open_utc_hour)
        self._cash_open_minute: int = int(config.cash_open_utc_minute)
        self._cash_close_hour: int = int(config.cash_close_utc_hour)
        self._cash_close_minute: int = int(config.cash_close_utc_minute)

        # Subscription tracking
        self._subscribed: set[str] = set()

        # Per-instrument EMA imbalance
        self._ema_imbalance: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            "PositionTierTodGateAlgorithm started "
            f"(position_cap={self._position_cap}, "
            f"skip_threshold={self._skip_threshold:.2f}, "
            f"min_total_size={self._min_total_size:.1f}, "
            f"ema_alpha={self._ema_alpha:.2f}, "
            f"open_window_minutes={self._open_window_minutes}, "
            f"close_window_minutes={self._close_window_minutes}, "
            f"cash_open_utc={self._cash_open_hour:02d}:{self._cash_open_minute:02d}, "
            f"cash_close_utc={self._cash_close_hour:02d}:{self._cash_close_minute:02d})."
        )

    def on_reset(self) -> None:
        self._subscribed.clear()
        self._ema_imbalance.clear()

    # ------------------------------------------------------------------
    # Subscription helper
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Position helper
    # ------------------------------------------------------------------

    def _current_net_qty(self, instrument_id) -> float:
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        return sum(float(str(p.quantity)) for p in open_positions)

    # ------------------------------------------------------------------
    # EMA imbalance helpers (iter-2 inherited)
    # ------------------------------------------------------------------

    def _update_ema(self, instrument_id, bid_size: float, ask_size: float) -> None:
        total = bid_size + ask_size
        if total < self._min_total_size or total <= 0.0:
            return
        imbalance = bid_size / total
        key = str(instrument_id)
        prev = self._ema_imbalance.get(key)
        if prev is None:
            self._ema_imbalance[key] = imbalance
        else:
            self._ema_imbalance[key] = (
                self._ema_alpha * imbalance + (1.0 - self._ema_alpha) * prev
            )

    def _ema_is_adverse(self, order) -> bool:
        key = str(order.instrument_id)
        ema = self._ema_imbalance.get(key)
        if ema is None:
            return False
        if order.side == OrderSide.BUY:
            return ema < self._skip_threshold
        else:  # SELL
            return ema > 1.0 - self._skip_threshold

    # ------------------------------------------------------------------
    # TOD gate (iter-7 new)
    # ------------------------------------------------------------------

    def _tod_is_adverse(self, order) -> bool:
        """Return True iff the order's ts_init falls inside the open- or
        close-window skip regions.

        Implementation note: `order.ts_init` is nanoseconds since the
        UNIX epoch. We construct a UTC datetime and compare HH:MM to the
        configured session boundaries. The DST transition for 2026
        train dates (March 8 .. March 21) is uniform: NYSE is on EDT
        for the entire window, so the cash open is 13:30 UTC for every
        date here. No DST mid-window transition to worry about.
        """
        ts_ns = int(order.ts_init)
        if ts_ns <= 0:
            return False  # missing timestamp -> do not gate
        try:
            dt = datetime.fromtimestamp(ts_ns / 1_000_000_000, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return False

        minute_of_day = dt.hour * 60 + dt.minute
        open_min = self._cash_open_hour * 60 + self._cash_open_minute
        close_min = self._cash_close_hour * 60 + self._cash_close_minute

        # Open window: [open_min, open_min + open_window_minutes)
        if (
            self._open_window_minutes > 0
            and open_min <= minute_of_day < open_min + self._open_window_minutes
        ):
            return True

        # Close window: [close_min - close_window_minutes, close_min)
        if (
            self._close_window_minutes > 0
            and close_min - self._close_window_minutes <= minute_of_day < close_min
        ):
            return True

        return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only fast-path: ALWAYS submit (intraday_flat). The TOD
        # gate is intentionally bypassed for reduce-only orders so the
        # algorithm never refuses to close a position.
        if order.is_reduce_only:
            self.submit_order(order)
            return

        # --- TOD gate (iter-7 new) -----------------------------------
        if self._tod_is_adverse(order):
            return

        # --- Positional gate (iter-2 inherited) ----------------------
        net_qty = self._current_net_qty(order.instrument_id)
        if abs(net_qty) >= self._position_cap:
            return

        # --- EMA-imbalance gate (iter-2 inherited) -------------------
        if self._ema_is_adverse(order):
            return

        self.submit_order(order)

    # ------------------------------------------------------------------
    # Quote tick handler
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        try:
            bid_size = float(str(tick.bid_size))
            ask_size = float(str(tick.ask_size))
        except Exception:
            return
        self._update_ema(tick.instrument_id, bid_size, ask_size)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    skip_threshold: float = 0.40,
    min_total_size: float = 2.0,
    ema_alpha: float = 0.30,
    open_window_minutes: int = 30,
    close_window_minutes: int = 30,
    cash_open_utc_hour: int = 13,
    cash_open_utc_minute: int = 30,
    cash_close_utc_hour: int = 20,
    cash_close_utc_minute: int = 0,
) -> PositionTierTodGateAlgorithm:
    """Instantiate the PositionTierTodGateAlgorithm.

    Parameters mirror the config dataclass; see
    PositionTierTodGateConfig for definitions.
    """
    config = PositionTierTodGateConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        skip_threshold=skip_threshold,
        min_total_size=min_total_size,
        ema_alpha=ema_alpha,
        open_window_minutes=open_window_minutes,
        close_window_minutes=close_window_minutes,
        cash_open_utc_hour=cash_open_utc_hour,
        cash_open_utc_minute=cash_open_utc_minute,
        cash_close_utc_hour=cash_close_utc_hour,
        cash_close_utc_minute=cash_close_utc_minute,
    )
    return PositionTierTodGateAlgorithm(config=config)
