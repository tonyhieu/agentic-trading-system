"""Position-tier + EMA-imbalance + vol-regime gate execution algorithm.

Builds on `position-tier-imbalance-ema-gate` (iter-2 best, PASS, pnl=$4503.25
on 11 train dates). The ONE targeted change is the addition of a short-window
realized-vol gate on OPEN-leg orders:

  Per quote tick, compute a short-window (rolling deque, default 60 ticks) stdev
  of mid-price log returns. Maintain a long-window rolling median (default 300
  short-vol observations) of those readings as the regime baseline.

  On every OPEN-leg order: if `current_short_vol > vol_multiplier *
  baseline_median_vol`, SKIP. Otherwise hand off to the inherited
  EMA-imbalance + position-tier gates from iter-2.

Reduce-only (close) orders ALWAYS execute immediately (intraday_flat).

Why a vol-regime gate:
  The oracle has a 30 s forecast horizon. Its directional accuracy degrades
  in bursts of short-window realized volatility — regimes where the
  mid-price moves more in 30 s than the signal's noisy edge can pay for.
  Iter-4's takeaway recommended trying a structurally different axis than
  more imbalance/cap/threshold tweaks; a vol-regime filter is exactly that.

No look-ahead bias:
  `on_quote_tick(tick)` appends the new mid and recomputes both the short-
  window stdev and the baseline median in strict chronological order. By the
  time `on_order(order)` reads `_last_short_vol` / `_baseline_median`, both
  reflect only quotes the engine had already dispatched at moments
  <= order.ts_init.

No quantity modification:
  Every parent order is either submitted intact or skipped entirely.
  Quantity invariant `sum(child_fills) <= parent.quantity` always preserved.
"""

from __future__ import annotations

import math
import statistics
from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PositionTierVolRegimeGateConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the position-tier + EMA-imbalance + vol-regime gate.

    Parameters
    ----------
    position_cap : int
        Maximum absolute net position (contracts) at which new OPEN-leg
        orders are still allowed. Inherited from iter-2. Default 1.
    skip_threshold : float
        EMA-imbalance threshold for the imbalance gate. Default 0.40.
    min_total_size : float
        Minimum bid_size + ask_size for a quote to (a) seed the EMA, (b)
        update the mid-history for vol estimation, (c) fire the gate.
        Default 2.0.
    ema_alpha : float
        EMA smoothing factor in (0, 1] for the imbalance gate. Default 0.30.
    vol_window : int
        Length (in quote ticks) of the short-window mid-log-return rolling
        deque used to estimate current realized vol. Default 60.
    baseline_window : int
        Length (in short-vol snapshots) of the rolling deque whose
        MEDIAN is the regime baseline. Default 300.
    min_baseline_window : int
        Minimum baseline-deque length before the vol-regime gate fires.
        Below this the gate does NOT skip (warm-up). Default 30.
    vol_multiplier : float
        Skip OPEN orders when current short-window vol exceeds
        vol_multiplier * baseline_median_vol. Default 1.5.
    vol_sample_every : int
        Sample the short-window vol into the baseline deque every Nth
        quote tick (after warm-up). Reduces per-tick CPU on busy days
        while preserving baseline coverage. Default 10.
    """

    position_cap: int = 1
    skip_threshold: float = 0.40
    min_total_size: float = 2.0
    ema_alpha: float = 0.30
    vol_window: int = 60
    baseline_window: int = 300
    min_baseline_window: int = 30
    vol_multiplier: float = 1.5
    vol_sample_every: int = 10


class PositionTierVolRegimeGateAlgorithm(ExecAlgorithm):
    """Execution algo: position-tier + EMA-imbalance + short-window vol-regime gate.

    Opening orders (is_reduce_only == False):
      1. Vol-regime gate: if baseline is warm AND current short-vol >
         vol_multiplier * baseline_median_vol, SKIP.
      2. Positional gate: if abs(net_qty) >= position_cap, SKIP.
      3. EMA-imbalance gate: if EMA imbalance is adverse to side, SKIP.
      4. Otherwise SUBMIT.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    Quote ticks (on_quote_tick):
      - Maintain per-instrument EMA imbalance (alpha smoothing on
        bid_size/(bid_size + ask_size)).
      - Maintain per-instrument short-window mid-log-return rolling deque
        of length vol_window; compute stdev as current short-vol.
      - Append each new short-vol reading to a baseline-window rolling
        deque; the median is the regime baseline.
    """

    def __init__(self, config: PositionTierVolRegimeGateConfig) -> None:
        super().__init__(config=config)

        # Gate parameters (iter-2 inherited)
        self._position_cap: int = config.position_cap
        self._skip_threshold: float = config.skip_threshold
        self._min_total_size: float = config.min_total_size
        self._ema_alpha: float = config.ema_alpha

        # Vol-regime gate parameters (this iteration's new mechanism)
        self._vol_window: int = config.vol_window
        self._baseline_window: int = config.baseline_window
        self._min_baseline_window: int = config.min_baseline_window
        self._vol_multiplier: float = config.vol_multiplier
        self._vol_sample_every: int = max(1, int(config.vol_sample_every))

        # Subscription tracking (quote ticks required for imbalance + vol).
        self._subscribed: set[str] = set()

        # Per-instrument EMA imbalance state (iter-2 inherited).
        self._ema_imbalance: dict[str, float] = {}

        # Per-instrument vol state (incremental, O(1) per quote tick).
        # _last_mid[key]      : float | None    — last observed mid
        # _ret_history[key]   : deque[float]    — rolling log returns (vol_window)
        # _sum_r[key]         : float           — running sum of returns in deque
        # _sum_r2[key]        : float           — running sum of squared returns
        # _vol_history[key]   : deque[float]    — sampled short-vol snapshots
        # _tick_counter[key]  : int             — quote ticks seen (for sampling)
        self._last_mid: dict[str, float] = {}
        self._ret_history: dict[str, deque[float]] = {}
        self._sum_r: dict[str, float] = {}
        self._sum_r2: dict[str, float] = {}
        self._vol_history: dict[str, deque[float]] = {}
        self._tick_counter: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            "PositionTierVolRegimeGateAlgorithm started "
            f"(position_cap={self._position_cap}, "
            f"skip_threshold={self._skip_threshold:.2f}, "
            f"min_total_size={self._min_total_size:.1f}, "
            f"ema_alpha={self._ema_alpha:.2f}, "
            f"vol_window={self._vol_window}, "
            f"baseline_window={self._baseline_window}, "
            f"min_baseline_window={self._min_baseline_window}, "
            f"vol_multiplier={self._vol_multiplier:.2f})."
        )

    def on_reset(self) -> None:
        self._subscribed.clear()
        self._ema_imbalance.clear()
        self._last_mid.clear()
        self._ret_history.clear()
        self._sum_r.clear()
        self._sum_r2.clear()
        self._vol_history.clear()
        self._tick_counter.clear()

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
        """Return absolute net position quantity for the instrument."""
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        total = sum(float(str(p.quantity)) for p in open_positions)
        return total

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
            if ema < self._skip_threshold:
                return True
        else:  # SELL
            adverse_threshold = 1.0 - self._skip_threshold
            if ema > adverse_threshold:
                return True
        return False

    # ------------------------------------------------------------------
    # Vol-regime helpers (this iteration's new mechanism)
    # ------------------------------------------------------------------

    def _update_vol(
        self,
        instrument_id,
        bid_px: float,
        ask_px: float,
        bid_size: float,
        ask_size: float,
    ) -> None:
        """Update short-window vol incrementally; sample to baseline every Nth tick.

        Performance: O(1) per quote tick. Maintains running sum and sum-of-
        squares of the returns currently in the deque so that
        `pstdev = sqrt(max(0, sum_r2/n - (sum_r/n)^2))` is constant-time.
        """
        # Same thin-book guard as iter-2's imbalance gate, applied to vol too.
        total = bid_size + ask_size
        if total < self._min_total_size or total <= 0.0:
            return
        if bid_px <= 0.0 or ask_px <= 0.0:
            return

        mid = 0.5 * (bid_px + ask_px)
        key = str(instrument_id)
        prev_mid = self._last_mid.get(key)
        self._last_mid[key] = mid

        if prev_mid is None or prev_mid <= 0.0:
            return  # need two mids before the first log return

        # Compute log return.
        try:
            ret = math.log(mid / prev_mid)
        except ValueError:
            return

        # Append to per-instrument return deque (bounded to vol_window).
        rh = self._ret_history.get(key)
        if rh is None:
            rh = deque(maxlen=self._vol_window)
            self._ret_history[key] = rh
            self._sum_r[key] = 0.0
            self._sum_r2[key] = 0.0

        # Maintain running sums incrementally: when deque is full, the
        # leftmost element is about to be evicted by the append. Read it
        # FIRST, subtract its contribution, then append + add the new.
        if len(rh) == rh.maxlen:
            evicted = rh[0]
            self._sum_r[key] -= evicted
            self._sum_r2[key] -= evicted * evicted
        rh.append(ret)
        self._sum_r[key] += ret
        self._sum_r2[key] += ret * ret

        # Need at least 2 returns for a meaningful stdev.
        n = len(rh)
        if n < 2:
            return

        # Sample the short-vol into the baseline deque every Nth tick.
        self._tick_counter[key] = self._tick_counter.get(key, 0) + 1
        if self._tick_counter[key] % self._vol_sample_every != 0:
            return

        mean = self._sum_r[key] / n
        var = self._sum_r2[key] / n - mean * mean
        if var < 0.0:
            var = 0.0  # numerical guard
        short_vol = math.sqrt(var)

        vh = self._vol_history.get(key)
        if vh is None:
            vh = deque(maxlen=self._baseline_window)
            self._vol_history[key] = vh
        vh.append(short_vol)

    def _vol_regime_is_adverse(self, order) -> bool:
        """Return True if the current short-window vol exceeds the regime gate.

        Returns False (do not skip) when:
          - per-instrument baseline deque is shorter than min_baseline_window.
        """
        key = str(order.instrument_id)
        vh = self._vol_history.get(key)
        if vh is None or len(vh) < self._min_baseline_window:
            return False

        # Latest reading = current short-window vol (just appended).
        current = vh[-1]
        baseline = statistics.median(vh)
        if baseline <= 0.0:
            return False

        return current > self._vol_multiplier * baseline

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute (intraday_flat).
        if order.is_reduce_only:
            self.submit_order(order)
            return

        # --- Vol-regime gate (new this iteration) ---------------------
        if self._vol_regime_is_adverse(order):
            self.log.info(
                f"SKIP {order.client_order_id} — vol-regime gate adverse "
                f"(short_vol > {self._vol_multiplier:.2f} * baseline_median)."
            )
            return

        # --- Positional gate (iter-2 inherited) -----------------------
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty >= self._position_cap:
            return

        # --- EMA-imbalance gate (iter-2 inherited) --------------------
        if self._ema_is_adverse(order):
            return

        # All three gates pass — submit.
        self.submit_order(order)

    # ------------------------------------------------------------------
    # Quote tick handler
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        try:
            bid_size = float(str(tick.bid_size))
            ask_size = float(str(tick.ask_size))
            bid_px = float(str(tick.bid_price))
            ask_px = float(str(tick.ask_price))
        except Exception:
            return
        self._update_ema(tick.instrument_id, bid_size, ask_size)
        self._update_vol(tick.instrument_id, bid_px, ask_px, bid_size, ask_size)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    skip_threshold: float = 0.40,
    min_total_size: float = 2.0,
    ema_alpha: float = 0.30,
    vol_window: int = 60,
    baseline_window: int = 300,
    min_baseline_window: int = 30,
    vol_multiplier: float = 1.5,
    vol_sample_every: int = 10,
) -> PositionTierVolRegimeGateAlgorithm:
    """Instantiate the PositionTierVolRegimeGateAlgorithm.

    Parameters mirror the config dataclass; see PositionTierVolRegimeGateConfig.
    """
    config = PositionTierVolRegimeGateConfig(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        skip_threshold=skip_threshold,
        min_total_size=min_total_size,
        ema_alpha=ema_alpha,
        vol_window=vol_window,
        baseline_window=baseline_window,
        min_baseline_window=min_baseline_window,
        vol_multiplier=vol_multiplier,
        vol_sample_every=vol_sample_every,
    )
    return PositionTierVolRegimeGateAlgorithm(config=config)
