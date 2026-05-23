"""Position-tier + EMA-imbalance + DIRECTIONAL vol-regime gate execution algorithm.

Builds on `position-tier-vol-regime-gate` (iter-5). The ONE targeted change is
making the vol-regime gate DIRECTIONAL (asymmetric on side x mid-direction)
instead of symmetric:

  Iter-5 symmetric rule: SKIP every OPEN order when short_vol > k * baseline.
  This iteration (iter-6) asymmetric rule:
    - SKIP a BUY only when (short_vol > k * baseline) AND (mid_trend < 0)
      i.e. high vol AND mid falling — buying into a downward burst is the
      adverse-direction case the oracle most often misses.
    - SKIP a SELL only when (short_vol > k * baseline) AND (mid_trend > 0)
      i.e. high vol AND mid rising — selling into an upward burst.
    - Same-direction vol bursts (BUY into rising mid, SELL into falling
      mid) are admitted: they are the favourable cases the symmetric gate
      threw away.

Everything else (position_cap=1, reduce-only fast-path, EMA-imbalance gate,
short-window stdev of mid log-returns, baseline median deque, sampling
cadence, thin-book guard) is inherited verbatim from iter-5.

Why this change:
  Iter-5 noted that the symmetric vol gate filters approximately the same
  marginal slice of entries as the EMA-imbalance gate, with diminishing
  returns when both stack inside position_cap=1. The explicit
  recommendation was to try an asymmetric/directional vol gate: skip only
  the bad-direction half of the high-vol bursts and let the good-direction
  half through. That is exactly this iteration.

  Conceptually: short-window realized vol is a regime indicator (HOW MUCH
  the mid is moving); short-window mid trend is a direction indicator
  (WHICH WAY it is moving). Together they form an adverse-direction
  classifier. The oracle's directional accuracy degrades in vol bursts
  *especially* when the mid has already rolled in the opposite direction
  from the prospective entry.

No look-ahead bias:
  Both the short-vol stdev and the mid_trend are computed strictly from
  quote ticks the engine has already dispatched. `on_quote_tick(tick)`
  appends to per-instrument deques in chronological order; `on_order()`
  reads only the latest values.

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


class PositionTierDirectionalVolGateConfig(ExecAlgorithmConfig, frozen=True):
    """Configuration for the position-tier + EMA-imbalance + DIRECTIONAL vol gate.

    Parameters
    ----------
    position_cap : int
        Max absolute net position (contracts) at which new OPEN-leg orders
        are still allowed. Inherited from iter-2/iter-5. Default 1.
    skip_threshold : float
        EMA-imbalance threshold for the imbalance gate. Default 0.40.
    min_total_size : float
        Min bid_size + ask_size for a quote to (a) seed the EMA, (b) update
        the mid-history for vol/trend, (c) fire the gate. Default 2.0.
    ema_alpha : float
        EMA smoothing factor in (0, 1] for the imbalance gate. Default 0.30.
    vol_window : int
        Length (in quote ticks) of the short-window mid-log-return rolling
        deque used to estimate current realized vol. Default 60.
    baseline_window : int
        Length (in short-vol snapshots) of the rolling deque whose MEDIAN
        is the regime baseline. Default 300.
    min_baseline_window : int
        Minimum baseline-deque length before the vol-regime gate fires.
        Default 30.
    vol_multiplier : float
        Vol regime is adverse when short_vol > vol_multiplier * baseline.
        Default 1.5.
    vol_sample_every : int
        Sample short-window vol into the baseline deque every Nth quote
        tick. Default 10.
    mid_trend_window : int
        Number of ticks back for the trend comparison: trend sign is
        sign(latest_mid - mid_at_(now - mid_trend_window)). Implemented as
        a separate bounded deque of recent mids (length mid_trend_window +
        1) so the lookback is O(1). Default 20.
    mid_trend_eps : float
        Absolute price threshold under which trend is considered NEUTRAL
        (no directional signal). Prevents tick-level rounding from
        flipping signs. In MES point units (1 point = 1.0). Default 0.25.
        With MES at ~5000, 0.25 corresponds to ~0.5 bps; large enough to
        ignore single-tick flicker, small enough to register a real burst.
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
    mid_trend_window: int = 20
    mid_trend_eps: float = 0.25


class PositionTierDirectionalVolGateAlgorithm(ExecAlgorithm):
    """Execution algo: position-tier + EMA-imbalance + DIRECTIONAL vol-regime gate.

    Opening orders (is_reduce_only == False):
      1. Directional vol-regime gate:
           If baseline warm AND short_vol > vol_multiplier * baseline:
             BUY  and mid_trend  < 0 -> SKIP
             SELL and mid_trend  > 0 -> SKIP
           Same-direction or neutral-trend bursts -> NOT skipped.
      2. Positional gate: if abs(net_qty) >= position_cap, SKIP.
      3. EMA-imbalance gate: if EMA imbalance is adverse to side, SKIP.
      4. Otherwise SUBMIT.

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance).

    Quote ticks (on_quote_tick):
      - Maintain per-instrument EMA imbalance (alpha smoothing).
      - Maintain per-instrument short-window mid-log-return deque
        (vol_window) -> running pstdev = current short-vol.
      - Sample short-vol into baseline-window rolling deque -> median = baseline.
      - Maintain per-instrument deque of recent mids (mid_trend_window + 1)
        -> trend sign = sign(mid[-1] - mid[0]) with eps deadzone.
    """

    def __init__(self, config: PositionTierDirectionalVolGateConfig) -> None:
        super().__init__(config=config)

        # Inherited iter-2/5 params
        self._position_cap: int = config.position_cap
        self._skip_threshold: float = config.skip_threshold
        self._min_total_size: float = config.min_total_size
        self._ema_alpha: float = config.ema_alpha

        # Vol-regime params (iter-5 inherited)
        self._vol_window: int = config.vol_window
        self._baseline_window: int = config.baseline_window
        self._min_baseline_window: int = config.min_baseline_window
        self._vol_multiplier: float = config.vol_multiplier
        self._vol_sample_every: int = max(1, int(config.vol_sample_every))

        # New: directional trend params (iter-6)
        self._mid_trend_window: int = max(2, int(config.mid_trend_window))
        self._mid_trend_eps: float = float(config.mid_trend_eps)

        # Subscription tracking
        self._subscribed: set[str] = set()

        # Per-instrument EMA imbalance
        self._ema_imbalance: dict[str, float] = {}

        # Per-instrument vol state (O(1) per tick)
        self._last_mid: dict[str, float] = {}
        self._ret_history: dict[str, deque[float]] = {}
        self._sum_r: dict[str, float] = {}
        self._sum_r2: dict[str, float] = {}
        self._vol_history: dict[str, deque[float]] = {}
        self._tick_counter: dict[str, int] = {}

        # New: per-instrument mid-trend deque (length mid_trend_window + 1)
        self._mid_history: dict[str, deque[float]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            "PositionTierDirectionalVolGateAlgorithm started "
            f"(position_cap={self._position_cap}, "
            f"skip_threshold={self._skip_threshold:.2f}, "
            f"min_total_size={self._min_total_size:.1f}, "
            f"ema_alpha={self._ema_alpha:.2f}, "
            f"vol_window={self._vol_window}, "
            f"baseline_window={self._baseline_window}, "
            f"min_baseline_window={self._min_baseline_window}, "
            f"vol_multiplier={self._vol_multiplier:.2f}, "
            f"mid_trend_window={self._mid_trend_window}, "
            f"mid_trend_eps={self._mid_trend_eps:.3f})."
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
        self._mid_history.clear()

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
    # Vol-regime helpers (iter-5 inherited)
    # ------------------------------------------------------------------

    def _update_vol_and_trend(
        self,
        instrument_id,
        bid_px: float,
        ask_px: float,
        bid_size: float,
        ask_size: float,
    ) -> None:
        """Update short-window vol, baseline samples, and mid-history trend.

        Performance: O(1) per quote tick. Stdev uses running sum + sum-of-
        squares; trend uses a bounded deque whose endpoints give the lookback.
        Median over baseline_window is O(N log N) per recompute, but only
        recomputed lazily inside `_vol_regime_is_adverse` (i.e., only on
        actual orders), not per tick.
        """
        total = bid_size + ask_size
        if total < self._min_total_size or total <= 0.0:
            return
        if bid_px <= 0.0 or ask_px <= 0.0:
            return

        mid = 0.5 * (bid_px + ask_px)
        key = str(instrument_id)

        # --- mid-history for trend ----------------------------------
        mh = self._mid_history.get(key)
        if mh is None:
            mh = deque(maxlen=self._mid_trend_window + 1)
            self._mid_history[key] = mh
        mh.append(mid)

        # --- log returns for vol -----------------------------------
        prev_mid = self._last_mid.get(key)
        self._last_mid[key] = mid
        if prev_mid is None or prev_mid <= 0.0:
            return

        try:
            ret = math.log(mid / prev_mid)
        except ValueError:
            return

        rh = self._ret_history.get(key)
        if rh is None:
            rh = deque(maxlen=self._vol_window)
            self._ret_history[key] = rh
            self._sum_r[key] = 0.0
            self._sum_r2[key] = 0.0

        if len(rh) == rh.maxlen:
            evicted = rh[0]
            self._sum_r[key] -= evicted
            self._sum_r2[key] -= evicted * evicted
        rh.append(ret)
        self._sum_r[key] += ret
        self._sum_r2[key] += ret * ret

        n = len(rh)
        if n < 2:
            return

        # Sample short-vol into baseline deque every Nth tick.
        self._tick_counter[key] = self._tick_counter.get(key, 0) + 1
        if self._tick_counter[key] % self._vol_sample_every != 0:
            return

        mean = self._sum_r[key] / n
        var = self._sum_r2[key] / n - mean * mean
        if var < 0.0:
            var = 0.0
        short_vol = math.sqrt(var)

        vh = self._vol_history.get(key)
        if vh is None:
            vh = deque(maxlen=self._baseline_window)
            self._vol_history[key] = vh
        vh.append(short_vol)

    def _mid_trend_sign(self, instrument_id) -> int:
        """Return +1, -1, or 0 for the short-window mid trend.

        Computed as sign(latest_mid - mid_oldest_in_deque) with an
        absolute eps deadzone. Returns 0 if the deque is not yet full
        (still warming up) — neutral, do NOT use as evidence.
        """
        key = str(instrument_id)
        mh = self._mid_history.get(key)
        if mh is None or len(mh) < (self._mid_trend_window + 1):
            return 0
        delta = mh[-1] - mh[0]
        if abs(delta) < self._mid_trend_eps:
            return 0
        return 1 if delta > 0 else -1

    def _vol_regime_is_adverse_directional(self, order) -> bool:
        """Return True iff the DIRECTIONAL vol-regime gate fires for this order.

        Two conditions must BOTH hold:
          (a) baseline warm AND current short-vol > vol_multiplier * baseline
              (regime burst);
          (b) the mid trend points AGAINST the trade direction:
              BUY  -> mid_trend < 0 (mid falling)
              SELL -> mid_trend > 0 (mid rising).
        Returns False otherwise (including baseline warm-up and
        neutral-trend high-vol cases — those entries are now admitted
        whereas iter-5 would have skipped them).
        """
        key = str(order.instrument_id)
        vh = self._vol_history.get(key)
        if vh is None or len(vh) < self._min_baseline_window:
            return False

        current = vh[-1]
        baseline = statistics.median(vh)
        if baseline <= 0.0:
            return False
        if current <= self._vol_multiplier * baseline:
            return False  # regime is not in a burst — admit

        trend = self._mid_trend_sign(order.instrument_id)
        if trend == 0:
            return False  # high vol but no clear direction — admit (iter-5 would skip)

        if order.side == OrderSide.BUY:
            return trend < 0  # buying into a downward burst — adverse
        else:  # SELL
            return trend > 0  # selling into an upward burst — adverse

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        self._ensure_subscribed(order.instrument_id)

        if order.is_reduce_only:
            self.submit_order(order)
            return

        # --- DIRECTIONAL vol-regime gate (this iteration's new mechanism) ---
        if self._vol_regime_is_adverse_directional(order):
            side = "BUY" if order.side == OrderSide.BUY else "SELL"
            self.log.info(
                f"SKIP {order.client_order_id} — directional vol-regime adverse "
                f"(side={side})."
            )
            return

        # --- Positional gate (iter-2 inherited) ----------------------
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty >= self._position_cap:
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
            bid_px = float(str(tick.bid_price))
            ask_px = float(str(tick.ask_price))
        except Exception:
            return
        self._update_ema(tick.instrument_id, bid_size, ask_size)
        self._update_vol_and_trend(
            tick.instrument_id, bid_px, ask_px, bid_size, ask_size
        )


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
    mid_trend_window: int = 20,
    mid_trend_eps: float = 0.25,
) -> PositionTierDirectionalVolGateAlgorithm:
    """Instantiate the PositionTierDirectionalVolGateAlgorithm.

    Parameters mirror the config dataclass; see
    PositionTierDirectionalVolGateConfig for definitions.
    """
    config = PositionTierDirectionalVolGateConfig(
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
        mid_trend_window=mid_trend_window,
        mid_trend_eps=mid_trend_eps,
    )
    return PositionTierDirectionalVolGateAlgorithm(config=config)
