"""sip-ptg-l3 execution algorithm.

Position-tier gate with a tight-spread OVERRIDE.

Hypothesis (see NOTES.md):
  The base `position-tier-gate` unconditionally skips OPEN orders whenever
  the cache shows a non-zero net position (the same-ts_init CLOSE+OPEN
  flip event). This defers the directional flip by ~1 sec. In tight-spread
  regimes, the flip is more likely correct (calm orderly book correlates
  with reliable oracle signals per the loop-2 fill-spread bucketing), so
  the base's serialization gives up timing edge.

  This algorithm OVERRIDES the base skip when the on-order top-of-book
  spread is tight (<= 0.25 USD = 1 MES minimum tick), submitting the OPEN
  at the same ts_init as the in-flight CLOSE. When the spread is wider,
  the base's skip is preserved.

  Reduce-only orders are always submitted (intraday_flat compliance,
  unchanged from base).

  This is the OPPOSITE direction of loop-2: loop-2 added skips on tight
  fills, loop-3 removes skips on tight fills. The loop-2 lesson — chain
  reactions matter — is acknowledged via a one-day counterfactual probe
  (see NOTES.md).

Constraints:
  - Quantity invariant: only skips/submits, never changes quantity.
  - top_of_book_only: never walks the book.
  - participation_cap: order quantity is unchanged from the strategy's
    emission; the engine still enforces top-of-book fills.
  - intraday_flat: reduce-only orders always submit unconditionally.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class SipPtgL3Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for sip-ptg-l3.

    Parameters
    ----------
    position_cap : int
        Inherited from base `position-tier-gate`. Without the override,
        OPEN orders are skipped when absolute net position >= position_cap.
        Default 1.
    spread_threshold : float
        Top-of-book spread (USD) at or below which a base-would-skip OPEN
        is OVERRIDDEN (submitted instead of skipped). Default 0.25 USD =
        1 MES minimum tick (inclusive: override fires when spread <= 0.25).
    """

    position_cap: int = 1
    spread_threshold: float = 0.25


class SipPtgL3Algorithm(ExecAlgorithm):
    """Position-tier gate with tight-spread override.

    Order routing:
      - Reduce-only: submit unconditionally.
      - OPEN with net_qty < position_cap: submit (base behavior).
      - OPEN with net_qty >= position_cap:
          - If on-order spread is unavailable: skip (preserve base).
          - If on-order spread <= spread_threshold: OVERRIDE -> submit.
          - Otherwise: skip (preserve base).

    The spread is read from `self.cache.quote_tick(instrument_id)`. If no
    quote is in the cache (start of session before first quote tick is
    processed), the algorithm preserves base behavior (skip).

    No order quantity modification -- quantity invariant preserved.
    No book walking -- top-of-book-only preserved.
    """

    def __init__(self, config: SipPtgL3Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        self._spread_threshold: float = config.spread_threshold

    def on_start(self) -> None:
        self.log.info(
            f"SipPtgL3Algorithm started "
            f"(position_cap={self._position_cap} contracts, "
            f"spread_threshold={self._spread_threshold} USD)."
        )

    def on_reset(self) -> None:
        pass  # No mutable state -- all conditioning lives in the cache.

    def _current_net_qty(self, instrument_id) -> float:
        """Return absolute net position quantity for the instrument."""
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0
        total = sum(float(str(p.quantity)) for p in open_positions)
        return total

    def _current_spread(self, instrument_id) -> float | None:
        """Return top-of-book spread (USD) from the latest cached quote tick.

        Returns None when the cache has no quote yet for the instrument
        (start-of-session edge case). Callers treat None as "spread unknown"
        and preserve base behavior (skip).
        """
        quote = self.cache.quote_tick(instrument_id)
        if quote is None:
            return None
        try:
            ask = float(quote.ask_price)
            bid = float(quote.bid_price)
        except (AttributeError, TypeError, ValueError):
            return None
        spread = ask - bid
        if spread < 0:
            return None  # Crossed book -- treat as unknown.
        return spread

    def on_order(self, order) -> None:
        """Route order: submit or skip based on portfolio state + book spread."""

        # Reduce-only orders bypass all gates (intraday_flat compliance).
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # Base gate: cache shows flat -> submit (unchanged from base).
        net_qty = self._current_net_qty(order.instrument_id)
        if net_qty < self._position_cap:
            self.log.debug(
                f"SUBMIT {order.client_order_id} -- position below cap "
                f"(net_qty={net_qty:.1f} < cap={self._position_cap})."
            )
            self.submit_order(order)
            return

        # Base would skip (net_qty >= position_cap). Check spread override.
        spread = self._current_spread(order.instrument_id)
        if spread is not None and spread <= self._spread_threshold:
            self.log.debug(
                f"OVERRIDE-SUBMIT {order.client_order_id} -- tight spread "
                f"(spread={spread:.4f} <= threshold={self._spread_threshold:.4f}, "
                f"net_qty={net_qty:.1f})."
            )
            self.submit_order(order)
            return

        # Spread wide (or unknown) -- preserve base skip.
        self.log.debug(
            f"SKIP {order.client_order_id} -- position cap reached and "
            f"spread not tight (net_qty={net_qty:.1f}, spread={spread})."
        )
        return


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    spread_threshold: float = 0.25,
) -> SipPtgL3Algorithm:
    """Instantiate and return the SipPtgL3Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    position_cap : int
        Maximum absolute net position (contracts) before triggering the
        base's skip rule on new OPEN orders. Default 1.
    spread_threshold : float
        Top-of-book spread (USD) at or below which a base-would-skip OPEN
        is overridden and submitted instead. Default 0.25 USD (1 MES tick,
        inclusive).
    """
    config = SipPtgL3Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        spread_threshold=spread_threshold,
    )
    return SipPtgL3Algorithm(config=config)
