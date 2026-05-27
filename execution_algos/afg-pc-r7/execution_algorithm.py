"""afg-pc-r7 -- Magnitude-Conditional Chain Extension AFG (short-window anchored).

Refinement of afg-pc-r6 (the empirical pc-experiment winner). Preserves r6's
Two-Path Additive gate (Path A: 10s long_net adverse beyond 2.0; Path B: 2s
short_net adverse beyond 5.0) and r6's directional-chain state machine
verbatim for chain positions 0 - 3.

NEW: At chain position 3, when the gate would re-fire on the same direction,
extend the chain to position 4 (absolute cap = 4) iff BOTH:
    (a) current_short_mag >= intensification_ratio * first_short_mag
    (b) current_short_mag >= burst_threshold (acute-burst floor)
Otherwise force-submit and reset (r6 behavior).

  - first_short_mag is recorded at the moment the chain starts (position 0 -> 1)
    as |short_net at first skip|, where short_net is computed over the same
    short_window as Path B (default 2s).
  - current_short_mag is |short_net at the would-be 4th skip|.
  - intensification_ratio default 1.5.

This is a STRICTLY narrower extension condition than r6's force-submit at
position 3: it never removes a skip r6 would make; it only adds at most one
extra skip per chain, conditional on regime intensification.

Direction-change still force-submits and resets (r2/r6 behavior).
Reduce-only always submits. First-signal warm-up always submits.

No look-ahead: only trade ticks with ts_event <= order.ts_init are in the
deque at decision time; first_short_mag is recorded only after evaluation.

Quantity invariant: never modify order.quantity. Only submit or skip.
"""
from __future__ import annotations

from collections import deque

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class AFGPCR7Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for afg-pc-r7.

    Parameters
    ----------
    long_window_seconds : float
        Path A long-window look-back. Default 10.0s (matches r6).
    long_threshold : float
        Path A skip threshold (default 2.0 contracts, matches r6).
    short_window_seconds : float
        Path B short-window look-back (default 2.0s, matches r6).
    burst_threshold : float
        Path B skip threshold (default 5.0 contracts, matches r6).
        Also doubles as the acute-burst floor for the magnitude-conditional
        chain-extension rule.
    max_consecutive_skips : int
        Absolute cap on consecutive same-direction skips (default 4).
        Position-3 skip is taken under r6's same conditions; position-4 skip
        requires the additional magnitude-conditional rule below.
    base_cap : int
        Chain position at which the magnitude-conditional extension rule is
        evaluated (default 3, matching r6's hard cap). At chain position
        `base_cap`, force-submit is replaced by conditional-extension logic.
    intensification_ratio : float
        Multiplier required between current_short_mag and first_short_mag for
        the chain to extend past `base_cap`. Default 1.5.
    """

    long_window_seconds: float = 10.0
    long_threshold: float = 2.0
    short_window_seconds: float = 2.0
    burst_threshold: float = 5.0
    max_consecutive_skips: int = 4
    base_cap: int = 3
    intensification_ratio: float = 1.5


class AFGPCR7Algorithm(ExecAlgorithm):
    """Magnitude-Conditional Chain Extension AFG -- see module docstring."""

    def __init__(self, config: AFGPCR7Config) -> None:
        super().__init__(config=config)
        assert config.long_window_seconds > 0, "long_window_seconds must be > 0"
        assert config.short_window_seconds > 0, "short_window_seconds must be > 0"
        assert config.short_window_seconds < config.long_window_seconds, (
            "short_window_seconds must be < long_window_seconds"
        )
        assert config.long_threshold > 0, "long_threshold must be > 0"
        assert config.burst_threshold > 0, "burst_threshold must be > 0"
        assert config.base_cap >= 1, "base_cap must be >= 1"
        assert config.max_consecutive_skips >= config.base_cap, (
            "max_consecutive_skips must be >= base_cap"
        )
        assert config.intensification_ratio > 1.0, (
            "intensification_ratio must be > 1.0 (extension requires strict intensification)"
        )

        self._long_window_ns: int = int(config.long_window_seconds * 1_000_000_000)
        self._short_window_ns: int = int(config.short_window_seconds * 1_000_000_000)
        self._long_threshold: float = float(config.long_threshold)
        self._burst_threshold: float = float(config.burst_threshold)
        self._max_consecutive_skips: int = int(config.max_consecutive_skips)
        self._base_cap: int = int(config.base_cap)
        self._intensification_ratio: float = float(config.intensification_ratio)

        # Single deque of (ts_event_ns: int, signed_vol: float), pruned to long window.
        self._flow_deque: deque[tuple[int, float]] = deque()
        self._long_net: float = 0.0

        # Most recent short_net computed in _gate_fires. Used to (a) record
        # first_short_mag at chain start, (b) read current_short_mag at the
        # magnitude-conditional extension check. Updated EVERY time
        # _gate_fires runs, so always reflects the most recent order's
        # decision-time short_net.
        self._short_net_last: float = 0.0

        # First-signal / warm-up.
        self._position_flat: bool = True

        # Directional-chain state.
        self._consecutive_skips: int = 0
        self._last_skipped_side: OrderSide | None = None
        # |short_net| at the first skip in the current chain.
        self._first_short_mag: float = 0.0

        # Subscription tracking.
        self._subscribed: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"AFGPCR7Algorithm started "
            f"(long_window={self._long_window_ns / 1e9:.1f}s, "
            f"long_threshold={self._long_threshold:.2f}, "
            f"short_window={self._short_window_ns / 1e9:.1f}s, "
            f"burst_threshold={self._burst_threshold:.2f}, "
            f"base_cap={self._base_cap}, "
            f"max_consecutive_skips={self._max_consecutive_skips}, "
            f"intensification_ratio={self._intensification_ratio:.2f})."
        )

    def on_reset(self) -> None:
        self._flow_deque.clear()
        self._long_net = 0.0
        self._short_net_last = 0.0
        self._position_flat = True
        self._consecutive_skips = 0
        self._last_skipped_side = None
        self._first_short_mag = 0.0
        self._subscribed.clear()

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    def _ensure_subscribed(self, instrument_id) -> None:
        key = str(instrument_id)
        if key not in self._subscribed:
            self.subscribe_trade_ticks(instrument_id)
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed.add(key)

    # ------------------------------------------------------------------
    # Trade tick handler
    # ------------------------------------------------------------------

    def on_trade_tick(self, tick) -> None:
        aggressor = tick.aggressor_side
        size = float(str(tick.size))

        if aggressor == AggressorSide.BUYER:
            signed_vol = size
        elif aggressor == AggressorSide.SELLER:
            signed_vol = -size
        else:
            signed_vol = 0.0

        self._flow_deque.append((tick.ts_event, signed_vol))
        self._long_net += signed_vol

    # ------------------------------------------------------------------
    # Window pruning + dual-window gate
    # ------------------------------------------------------------------

    def _prune_long_window(self, cutoff_ns: int) -> None:
        while self._flow_deque and self._flow_deque[0][0] < cutoff_ns:
            _, old_vol = self._flow_deque.popleft()
            self._long_net -= old_vol

    def _compute_short_net(self, short_cutoff_ns: int) -> float:
        short_net = 0.0
        for ts, vol in reversed(self._flow_deque):
            if ts < short_cutoff_ns:
                break
            short_net += vol
        return short_net

    def _gate_fires(self, order) -> bool:
        """Return True iff Path A OR Path B fires (skip the order).

        Side effect: stores the freshly computed short_net in self._short_net_last
        regardless of outcome, so callers can read the decision-time short signal.
        """
        long_cutoff_ns = order.ts_init - self._long_window_ns
        self._prune_long_window(long_cutoff_ns)

        # Compute short_net unconditionally so it is always available to callers.
        short_cutoff_ns = order.ts_init - self._short_window_ns
        short_net = self._compute_short_net(short_cutoff_ns)
        self._short_net_last = short_net

        if not self._flow_deque:
            return False  # Warm-up.

        # Path A
        if order.side == OrderSide.BUY:
            path_a = self._long_net <= -self._long_threshold
        else:
            path_a = self._long_net >= self._long_threshold

        if path_a:
            return True

        # Path B
        if order.side == OrderSide.BUY:
            return short_net <= -self._burst_threshold
        else:
            return short_net >= self._burst_threshold

    # ------------------------------------------------------------------
    # Chain-state helpers
    # ------------------------------------------------------------------

    def _reset_chain(self) -> None:
        self._consecutive_skips = 0
        self._last_skipped_side = None
        self._first_short_mag = 0.0

    def _start_chain(self, side: OrderSide) -> None:
        """Record a chain start at position 1. Captures first_short_mag."""
        self._consecutive_skips = 1
        self._last_skipped_side = side
        self._first_short_mag = abs(self._short_net_last)

    def _extend_chain(self, side: OrderSide) -> None:
        """Increment chain position; side must equal _last_skipped_side."""
        self._consecutive_skips += 1
        self._last_skipped_side = side

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        self._ensure_subscribed(order.instrument_id)

        # Reduce-only orders always execute -- intraday_flat compliance.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # First-signal / warm-up unconditional submit.
        if self._position_flat:
            self.log.debug(
                f"First open (warm-up); submitting {order.client_order_id}."
            )
            self._position_flat = False
            self._reset_chain()
            self.submit_order(order)
            return

        # ----- Directional-chain state machine -----
        if self._consecutive_skips == 0:
            if self._gate_fires(order):
                self.log.info(
                    f"SKIP {order.client_order_id} -- adverse flow "
                    f"(long_net={self._long_net:.2f}, "
                    f"short_net={self._short_net_last:.2f}, "
                    f"side={'BUY' if order.side == OrderSide.BUY else 'SELL'}); "
                    f"starting chain."
                )
                self._start_chain(order.side)
                return
            else:
                self._reset_chain()
                self.submit_order(order)
                return

        # consecutive_skips >= 1: chain active.

        # (a) Direction change -- force-submit and reset.
        if order.side != self._last_skipped_side:
            self.log.info(
                f"FORCE-SUBMIT {order.client_order_id} -- direction change "
                f"(chain side={self._last_skipped_side}, new side={order.side}); "
                f"resetting chain (length was {self._consecutive_skips})."
            )
            self._reset_chain()
            self.submit_order(order)
            return

        # (b) Absolute cap reached -- force-submit and reset.
        if self._consecutive_skips >= self._max_consecutive_skips:
            self.log.info(
                f"FORCE-SUBMIT {order.client_order_id} -- absolute cap reached "
                f"(consecutive_skips={self._consecutive_skips} >= "
                f"max={self._max_consecutive_skips}); resetting chain."
            )
            self._reset_chain()
            self.submit_order(order)
            return

        # (c) Same direction, chain still active (consecutive_skips in [1, max-1]).
        # Evaluate gate.
        gate_fired = self._gate_fires(order)
        if not gate_fired:
            self._reset_chain()
            self.submit_order(order)
            return

        # Gate fired same direction. If we're at base_cap (e.g., 3) we must
        # consult the magnitude-conditional extension rule before extending.
        if self._consecutive_skips >= self._base_cap:
            current_short_mag = abs(self._short_net_last)
            intensified = (
                current_short_mag >= self._intensification_ratio * self._first_short_mag
            )
            above_floor = current_short_mag >= self._burst_threshold
            if intensified and above_floor:
                self.log.info(
                    f"EXTEND-CHAIN {order.client_order_id} -- "
                    f"position {self._consecutive_skips + 1} (cap-conditional): "
                    f"current_short_mag={current_short_mag:.2f} >= "
                    f"{self._intensification_ratio:.2f} * "
                    f"first_short_mag={self._first_short_mag:.2f} "
                    f"AND >= burst_threshold={self._burst_threshold:.2f}."
                )
                self._extend_chain(order.side)
                return
            else:
                self.log.info(
                    f"FORCE-SUBMIT {order.client_order_id} -- "
                    f"position {self._consecutive_skips} cap, intensification not met "
                    f"(current_short_mag={current_short_mag:.2f}, "
                    f"first_short_mag={self._first_short_mag:.2f}, "
                    f"need >= {self._intensification_ratio * self._first_short_mag:.2f} "
                    f"AND >= {self._burst_threshold:.2f}); resetting chain."
                )
                self._reset_chain()
                self.submit_order(order)
                return

        # Normal chain extension (position 1 -> 2, 2 -> 3) when below base_cap.
        self.log.info(
            f"SKIP {order.client_order_id} -- chain extension "
            f"(consecutive_skips={self._consecutive_skips + 1}, "
            f"long_net={self._long_net:.2f}, short_net={self._short_net_last:.2f})."
        )
        self._extend_chain(order.side)
        return

    def on_quote_tick(self, tick) -> None:
        """Passively receive quote ticks (quote-cache side-effects only)."""
        pass


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    long_window_seconds: float = 10.0,
    long_threshold: float = 2.0,
    short_window_seconds: float = 2.0,
    burst_threshold: float = 5.0,
    max_consecutive_skips: int = 4,
    base_cap: int = 3,
    intensification_ratio: float = 1.5,
) -> AFGPCR7Algorithm:
    """Instantiate and return the AFGPCR7Algorithm.

    Defaults match the round-3 hypothesis: r6 verbatim parameters plus
    base_cap=3 (r6's hard cap), max_consecutive_skips=4 (one extra position
    available via conditional rule), intensification_ratio=1.5.
    """
    config = AFGPCR7Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        long_window_seconds=long_window_seconds,
        long_threshold=long_threshold,
        short_window_seconds=short_window_seconds,
        burst_threshold=burst_threshold,
        max_consecutive_skips=max_consecutive_skips,
        base_cap=base_cap,
        intensification_ratio=intensification_ratio,
    )
    return AFGPCR7Algorithm(config=config)
