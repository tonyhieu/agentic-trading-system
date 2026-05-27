"""ptg-pc-r3 execution algorithm.

WINNERS-RUN gate layered on position-tier-gate (cap=1).

Hypothesis (see NOTES.md):
  Position duration is strongly correlated with profitability in the base
  backtest. By SKIPPING the oracle's CLOSE when the held position is
  currently profitable and not stale, we attempt to convert short noisy
  positions into longer-hold profitable ones. The condition on current
  unrealized_pnl > 0 provides path-evidence that the trade is "going our
  way"; the next oracle CLOSE will exit the position when it goes
  break-even or red ("break-even stop" dynamic).

Algorithm (per on_order):
  1. If NOT is_reduce_only (i.e. OPEN leg):
       a. Apply the position-cap gate verbatim from position-tier-gate.
          If current absolute net qty >= position_cap, SKIP; else SUBMIT.
  2. If is_reduce_only (CLOSE leg):
       a. Look up the open Position for this instrument.
       b. If no open position: SUBMIT (defensive — should not happen).
       c. If hold_duration >= max_extend_ns: SUBMIT (force-exit stale
          position).
       d. Fetch the latest quote from cache.quote_tick(instrument_id).
          If None: SUBMIT (safe default — don't skip when we can't
          measure profitability).
       e. Compute conservative-close unrealized_pnl per unit:
            LONG  -> bid - avg_px_open  (we'd sell at the bid)
            SHORT -> avg_px_open - ask  (we'd buy at the ask)
       f. If unrealized_pnl_per_unit > 0: SKIP (let the winner run).
          Else: SUBMIT.

Quote tick subscription is lazy — on the first on_order call we
subscribe_quote_ticks() for that instrument so cache.quote_tick() returns
fresh prices for the unrealized_pnl computation.

No look-ahead: the cache reflects fills already processed and quote ticks
already delivered. The "skip" decision uses information strictly available
at the moment the CLOSE order is received by the execution algorithm.

No quantity modification: quantity invariant preserved (always SUBMIT or
SKIP, never resize).
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import PositionSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PtgPcR3Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for ptg-pc-r3.

    Parameters
    ----------
    position_cap : int
        Maximum absolute net position size (contracts) at which new OPEN-leg
        orders are still allowed. Default 1 (matches base position-tier-gate).
    max_extend_seconds : float
        Maximum hold duration past which a CLOSE is force-submitted even if
        the position is profitable. Default 1800s = 30 minutes — wide enough
        to retain the empirical 60-600s tail measured in the base backtest,
        but short enough to provide an end-of-session safety margin within a
        6.5-hour trading session.
    """

    position_cap: int = 1
    max_extend_seconds: float = 1800.0


class PtgPcR3Algorithm(ExecAlgorithm):
    """Position-tier-gate (cap=1) with a winners-run CLOSE-skip gate."""

    def __init__(self, config: PtgPcR3Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        self._max_extend_ns: int = int(config.max_extend_seconds * 1_000_000_000)
        # Track instruments for which we've already subscribed to quote ticks
        # (avoid double-subscription; lazy because we don't know the
        # instrument at on_start time).
        self._subscribed_instruments: set = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            f"PtgPcR3Algorithm started "
            f"(position_cap={self._position_cap}, "
            f"max_extend_seconds={self._max_extend_ns / 1e9:.1f})."
        )

    def on_reset(self) -> None:
        self._subscribed_instruments.clear()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _current_net_qty(self, instrument_id) -> float:
        """Return absolute net position quantity for the instrument."""
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        return sum(float(str(p.quantity)) for p in open_positions)

    def _ensure_quote_subscription(self, instrument_id) -> None:
        """Lazy-subscribe to quote ticks for this instrument."""
        if instrument_id in self._subscribed_instruments:
            return
        try:
            self.subscribe_quote_ticks(instrument_id)
            self._subscribed_instruments.add(instrument_id)
            self.log.info(f"Subscribed to quote ticks for {instrument_id}.")
        except Exception as exc:  # pragma: no cover - defensive
            self.log.warning(
                f"Failed to subscribe_quote_ticks for {instrument_id}: {exc}"
            )

    def _should_skip_close(self, order) -> bool:
        """Return True iff this CLOSE should be skipped (let the winner run)."""
        instrument_id = order.instrument_id

        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            # No open position for this instrument — defensive: submit anyway
            # (the CLOSE will be a no-op or rejected, but we don't want to
            # silently swallow it).
            return False

        # Netting OMS: at most one position per instrument.
        position = open_positions[0]

        # Stale-position force-exit.
        hold_duration_ns = self.clock.timestamp_ns() - position.ts_opened
        if hold_duration_ns >= self._max_extend_ns:
            return False

        # Need a fresh quote to compute unrealized PnL conservatively.
        quote = self.cache.quote_tick(instrument_id)
        if quote is None:
            # Safe default: don't skip when we can't measure profitability.
            return False

        avg_px_open = float(position.avg_px_open)

        if position.side == PositionSide.LONG:
            # Would sell at the bid to close.
            unrealized_per_unit = float(quote.bid_price) - avg_px_open
        elif position.side == PositionSide.SHORT:
            # Would buy at the ask to close.
            unrealized_per_unit = avg_px_open - float(quote.ask_price)
        else:
            # FLAT or NO_POSITION_SIDE — submit to be safe.
            return False

        return unrealized_per_unit > 0.0

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: gate OPENs on position-cap, gate CLOSEs on winners-run."""

        # Lazy quote-tick subscription (idempotent).
        self._ensure_quote_subscription(order.instrument_id)

        if order.is_reduce_only:
            # CLOSE leg — apply winners-run skip gate.
            if self._should_skip_close(order):
                self.log.debug(
                    f"SKIP CLOSE {order.client_order_id} — winner is "
                    f"profitable and within max_extend_seconds."
                )
                return
            self.log.debug(
                f"SUBMIT CLOSE {order.client_order_id} — not profitable or stale."
            )
            self.submit_order(order)
            return

        # OPEN leg — apply the position-cap gate (verbatim from base).
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty >= self._position_cap:
            self.log.debug(
                f"SKIP OPEN {order.client_order_id} — position cap reached "
                f"(net_qty={net_qty:.1f} >= cap={self._position_cap})."
            )
            return

        self.log.debug(
            f"SUBMIT OPEN {order.client_order_id} (net_qty={net_qty:.1f})."
        )
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    max_extend_seconds: float = 1800.0,
) -> PtgPcR3Algorithm:
    """Instantiate the ptg-pc-r3 execution algorithm."""
    config = PtgPcR3Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        max_extend_seconds=max_extend_seconds,
    )
    return PtgPcR3Algorithm(config=config)
