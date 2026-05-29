"""ptg-isl-g1l1: Position-tier gate plus rolling-spread gate.

Builds on `position-tier-gate` (base for island-0). The base gates new
OPEN orders on net position cap (default cap=1 — skip any new entry while
a position is in cache). This algo ADDS a second gate: skip OPENs whose
contemporaneous top-of-book spread exceeds a rolling p75 threshold of
recent spreads. Both gates must pass for an OPEN to be submitted;
reduce-only / closing orders always execute.

Hypothesis
----------
The base position-tier-gate already prevents back-to-back concurrent
entries. The remaining loss-generating entries fire during transient
microstructure regimes (e.g., brief liquidity gaps, momentary one-sided
book pressure) where the bid-ask spread widens beyond its recent norm.
Spread-wide moments share two properties harmful to a 30s-horizon oracle:
  1. Higher implementation-shortfall cost on the fill itself
     (`is_weighted_bps` is the tracked execution objective).
  2. They often coincide with brief liquidity vacuums or pending news,
     during which the oracle's forecast is more likely to be reversed
     before the close leg fires.
Skipping new opens when the spread sits in the top quartile of recent
spread observations should reduce both bps cost and adverse-selection
loss without sacrificing many entries (~25% skip rate, applied AFTER
the position-cap gate, so the marginal skip count is lower).

Algorithm
---------
- Maintain a deque of (ts_event_ns, spread_ticks) from quote ticks
  delivered via `on_quote_tick()`. spread_ticks is computed as
  `(ask_price - bid_price)` in price units (we do not convert to
  tick units — the comparison is purely against the algo's own rolling
  history, so the unit is internally consistent).
- At `on_order()` for an OPEN:
    (gate 1) position-tier-gate: skip if net_qty >= position_cap.
    (gate 2) spread gate: prune the deque to entries within
      `window_seconds`. If at least `min_samples` samples are present,
      compute the `quantile`-th quantile of spread_ticks in the window.
      If the current spread (last sample, equivalently
      `self._latest_spread`) exceeds this quantile, SKIP.
- Both gates must pass for SUBMIT.

No look-ahead: quote ticks are inserted in chronological replay order;
the deque prune at `on_order()` uses the order's `ts_init`, never a
future timestamp. The `_latest_spread` reflects the most recent quote
delivered before this order — strictly in the past.

No quantity modification: quantity invariant always preserved.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PtgIslG1L1Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for ptg-isl-g1l1.

    Parameters
    ----------
    position_cap : int
        Inherited from position-tier-gate. Skip OPEN if absolute net
        position >= position_cap. Default 1 (proven by base).
    spread_window_seconds : float
        Rolling window for spread samples (seconds). Default 60.0 —
        long enough to capture intra-minute spread distribution but
        short enough to react to regime changes.
    spread_quantile : float
        Quantile threshold for the spread gate (0 < q < 1). Skip OPEN
        when the latest spread is strictly greater than the q-th quantile
        of the rolling window. Default 0.75 — gate the wide-spread tail.
    min_samples : int
        Minimum samples required before the spread gate fires. Below
        this, the gate is a no-op (warm-up). Default 50.
    """

    position_cap: int = 1
    spread_window_seconds: float = 60.0
    spread_quantile: float = 0.75
    min_samples: int = 50


class PtgIslG1L1Algorithm(ExecAlgorithm):
    """ExecAlgorithm: position-tier-gate combined with a rolling-spread gate."""

    def __init__(self, config: PtgIslG1L1Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        self._spread_window_ns: int = int(config.spread_window_seconds * 1_000_000_000)
        self._spread_quantile: float = config.spread_quantile
        self._min_samples: int = config.min_samples

        # Rolling spread samples: (ts_event_ns, spread).
        self._spread_deque: deque[tuple[int, float]] = deque()
        # Most recent observed spread (used as the comparison point).
        self._latest_spread: float | None = None

        # Subscription tracking (we need quote ticks).
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"PtgIslG1L1Algorithm started "
            f"(position_cap={self._position_cap}, "
            f"spread_window={self._spread_window_ns / 1e9:.1f}s, "
            f"spread_quantile={self._spread_quantile:.2f}, "
            f"min_samples={self._min_samples})."
        )

    def on_reset(self) -> None:
        self._spread_deque.clear()
        self._latest_spread = None
        self._subscribed.clear()

    # ------------------------------------------------------------------
    # Subscription helper
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Quote tick handler — maintain rolling spread samples
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        try:
            bid = float(str(tick.bid_price))
            ask = float(str(tick.ask_price))
        except Exception:
            return
        spread = ask - bid
        if spread < 0.0:
            # Defensive: crossed book — skip the sample.
            return
        self._spread_deque.append((tick.ts_event, spread))
        self._latest_spread = spread

    # ------------------------------------------------------------------
    # Gate helpers
    # ------------------------------------------------------------------

    def _current_net_qty(self, instrument_id) -> float:
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        return sum(float(str(p.quantity)) for p in open_positions)

    def _prune_spread_window(self, cutoff_ns: int) -> None:
        while self._spread_deque and self._spread_deque[0][0] < cutoff_ns:
            self._spread_deque.popleft()

    def _spread_gate_skip(self, order) -> bool:
        """Return True if the latest spread sits above the rolling quantile."""
        cutoff_ns = order.ts_init - self._spread_window_ns
        self._prune_spread_window(cutoff_ns)

        n = len(self._spread_deque)
        if n < self._min_samples or self._latest_spread is None:
            return False  # warm-up: do not gate

        # Quantile via sorted copy. n is bounded by window (seconds-scale).
        sorted_spreads = sorted(s for _, s in self._spread_deque)
        # Linear interpolation: index = q * (n - 1)
        idx_f = self._spread_quantile * (n - 1)
        lo = int(idx_f)
        hi = min(lo + 1, n - 1)
        frac = idx_f - lo
        threshold = sorted_spreads[lo] * (1.0 - frac) + sorted_spreads[hi] * frac

        if self._latest_spread > threshold:
            self.log.debug(
                f"SPREAD SKIP {order.client_order_id} — "
                f"latest_spread={self._latest_spread:.5f} > "
                f"q{self._spread_quantile:.2f}={threshold:.5f} "
                f"(n={n})."
            )
            return True
        return False

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only (close) orders always execute — intraday_flat compliance.
        if order.is_reduce_only:
            self.submit_order(order)
            return

        # Gate 1: position-tier-gate (inherited base behavior).
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty >= self._position_cap:
            self.log.debug(
                f"POSITION SKIP {order.client_order_id} — net_qty={net_qty:.1f} "
                f">= cap={self._position_cap}."
            )
            return

        # Gate 2: spread gate.
        if self._spread_gate_skip(order):
            return

        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    spread_window_seconds: float = 60.0,
    spread_quantile: float = 0.75,
    min_samples: int = 50,
) -> PtgIslG1L1Algorithm:
    config = PtgIslG1L1Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        spread_window_seconds=spread_window_seconds,
        spread_quantile=spread_quantile,
        min_samples=min_samples,
    )
    return PtgIslG1L1Algorithm(config=config)
