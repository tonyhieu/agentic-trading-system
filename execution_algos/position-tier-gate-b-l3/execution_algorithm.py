"""Position-tier-gate-b-l3 execution algorithm.

Per-iteration experiment — arm: base_algo=position-tier-gate,
mode=brief-summary, loop 3. Starting point: `position-tier-gate-b-l2`.

Loops 1 and 2 both gated the OPEN leg of each oracle signal on a
portfolio-equity circuit breaker (realized-P&L drawdown vs a peak reference).
The loop-2 brief summary concluded equity-feedback gating is exhausted: that
gate throttles a *random* subset of orders, and under sigma=200 the per-trade
edge is structurally negative, so loop-1's apparent +71.6% gain was pure
volume suppression and loop-2's re-arm (restoring volume) dropped P&L to
-50.3% vs base. The loop-2 `next` directive: gate on an order-time
market-state feature so the algo skips *genuinely worse* entries.

Loop 3 acts on that. It removes the equity circuit breaker entirely and
gates each OPEN leg on an order-time **top-of-book imbalance** feature read
from the latest cached quote.

  imbalance = (bid_size - ask_size) / (bid_size + ask_size)  in [-1, +1].

A BUY OPEN into a strongly ask-stacked book (imbalance <= -imb_threshold) or
a SELL OPEN into a strongly bid-stacked book (imbalance >= +imb_threshold)
leans against visible resting liquidity — those are the structurally
disadvantaged entries — and is skipped. All other OPEN legs submit.

NOTE — spread filter dropped after diagnosis.
  An initial loop-3 design also gated on the bid-ask spread in ticks. A
  diagnostic instrumentation run on 20260316 showed the spread of the quote
  returned by `cache.quote_tick()` in this backtest pipeline is heavily
  quantized: ~76% of quotes report exactly 25 ticks and ~24% report 50 ticks
  (p1..p75 = 25, p90..p99 = 50). It is not a granular top-of-book spread, so
  a spread-in-ticks threshold cannot finely rank entries — it can only pass
  all, pass ~76%, or pass none. A `max_spread_ticks` of 2.0 (calibrated for a
  real 1-tick MES book) skipped 100% of opens, collapsed trade_count to 1 per
  day, and on dates with zero positions crashed the engine's `_unrealized_pnl`
  (empty positions DataFrame -> KeyError 'side'). The spread filter is
  therefore removed; only the imbalance filter, whose distribution is
  genuinely continuous (-0.94..+0.94 on 20260316), is retained.

Reduce-only / closing orders always submit (intraday_flat compliance).
No order quantity is ever modified — orders are submitted or skipped only.

No look-ahead: `cache.quote_tick()` at `on_order()` time returns the most
recent quote already processed by the engine, strictly in the past relative
to the current order's ts_init. When no quote is cached yet (session
warm-up), the order is submitted (fail-open) so the filter never silently
halts the whole session.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PositionTierGateBL3Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the position-tier-gate-b-l3 execution algorithm.

    Parameters
    ----------
    imb_threshold : float
        Top-of-book imbalance magnitude (0..1) beyond which an OPEN leg taken
        on the unfavourable side of the book is skipped. 0.0 skips any OPEN
        leaning against the book at all; 1.0 effectively disables the filter
        (no real book is perfectly one-sided). Default 0.5: skip an OPEN only
        when the book leans against it by a clear majority of visible depth.
    """

    imb_threshold: float = 0.5


class PositionTierGateBL3Algorithm(ExecAlgorithm):
    """Execution algorithm that gates open orders on top-of-book imbalance.

    Opening orders (is_reduce_only == False):
      - Read the latest cached top-of-book quote for the instrument.
      - Compute imbalance = (bid_size - ask_size) / (bid_size + ask_size).
      - SKIP if the OPEN-leg direction leans against the book by more than
        `imb_threshold` (BUY into ask-stacked book / SELL into bid-stacked).
      - Otherwise SUBMIT.
      - If no quote is cached yet: SUBMIT (fail-open).

    Closing orders (is_reduce_only == True):
      - Always submitted immediately (intraday_flat compliance; exposure
        reduction is always allowed).

    No order quantity is ever modified. Quantity invariant always preserved.
    """

    def __init__(self, config: PositionTierGateBL3Config) -> None:
        super().__init__(config=config)
        self._imb_threshold: float = config.imb_threshold
        # Diagnostic counters (per session).
        self._n_submitted_open: int = 0
        self._n_skipped_imbalance: int = 0
        self._n_no_quote: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self._n_submitted_open = 0
        self._n_skipped_imbalance = 0
        self._n_no_quote = 0
        self.log.info(
            f"PositionTierGateBL3Algorithm started "
            f"(imb_threshold={self._imb_threshold})."
        )

    def on_reset(self) -> None:
        self._n_submitted_open = 0
        self._n_skipped_imbalance = 0
        self._n_no_quote = 0

    def on_stop(self) -> None:
        self.log.info(
            f"PositionTierGateBL3Algorithm stopped — "
            f"opens submitted={self._n_submitted_open}, "
            f"skipped(imbalance)={self._n_skipped_imbalance}, "
            f"no-quote fail-open={self._n_no_quote}."
        )

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route order: submit or skip based on order-time book imbalance."""

        # Reduce-only (close) orders always execute — intraday_flat compliance,
        # and they reduce exposure rather than adding to it.
        if order.is_reduce_only:
            self.log.debug(
                f"Submitting reduce-only order {order.client_order_id} immediately."
            )
            self.submit_order(order)
            return

        # --- OPEN leg: evaluate the top-of-book imbalance filter ----------

        quote = self.cache.quote_tick(order.instrument_id)
        if quote is None:
            # Session warm-up: no top-of-book quote processed yet. Fail open
            # so the filter never silently halts the whole session.
            self._n_no_quote += 1
            self._n_submitted_open += 1
            self.log.debug(
                f"SUBMIT {order.client_order_id} — no cached quote (fail-open)."
            )
            self.submit_order(order)
            return

        bid_size = float(quote.bid_size)
        ask_size = float(quote.ask_size)

        # imbalance > 0 => bid-heavy book ; imbalance < 0 => ask-heavy book.
        depth = bid_size + ask_size
        if depth > 0.0:
            imbalance = (bid_size - ask_size) / depth
        else:
            imbalance = 0.0

        unfavourable = False
        if order.side == OrderSide.BUY:
            # Buying into a strongly ask-stacked book leans against supply.
            unfavourable = imbalance <= -self._imb_threshold
        elif order.side == OrderSide.SELL:
            # Selling into a strongly bid-stacked book leans against demand.
            unfavourable = imbalance >= self._imb_threshold

        if unfavourable:
            self._n_skipped_imbalance += 1
            self.log.debug(
                f"SKIP {order.client_order_id} — leaning against book "
                f"(side={order.side_string()}, imbalance={imbalance:.3f}, "
                f"threshold={self._imb_threshold})."
            )
            # Do NOT call submit_order — quantity invariant preserved.
            return

        # --- Passed the filter — submit -----------------------------------
        self._n_submitted_open += 1
        self.log.debug(
            f"SUBMIT {order.client_order_id} — passed entry filter "
            f"(imbalance={imbalance:.3f})."
        )
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    imb_threshold: float = 0.5,
) -> PositionTierGateBL3Algorithm:
    """Instantiate and return the PositionTierGateBL3Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    imb_threshold : float
        Top-of-book imbalance magnitude (0..1) beyond which an OPEN leg
        leaning against the book is skipped. Default 0.5.
    """
    config = PositionTierGateBL3Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        imb_threshold=imb_threshold,
    )
    return PositionTierGateBL3Algorithm(config=config)
