"""Position-tier-gate-b-l5 execution algorithm.

Per-iteration experiment — arm: base_algo=position-tier-gate,
mode=brief-summary, loop 5. Starting point: `position-tier-gate-b-l4`
(this file is a modified copy of that algorithm).

WHAT CHANGED FROM LOOP 4
------------------------
Loop 4 was a zero-latency pass-through: `on_order()` submitted every order
immediately in full as a MARKET order. It confirmed implementation
shortfall (IS) is fixed across binary submit/skip policies — its
`is_weighted_bps` (0.04497) sat within 0.08% of the base (0.04501) — and
its `next` directive named the one untried structural lever: order
TRANSFORMATION (modify quantity via child slicing, or add genuine timing
offsets) rather than the skip/submit dichotomy that has now failed four
ways.

A pre-implementation check ruled out the *quantity* half: every order in
this pipeline is `quantity == 1` (`trade_size` defaults to `Decimal("1")`),
and a 1-lot cannot be split into smaller children (Nautilus' own TWAP
example bails out for exactly this case). This loop therefore takes the
*order-type / timing* half of the transformation lever.

THE TRANSFORMATION — PASSIVE-THEN-AGGRESSIVE
--------------------------------------------
Every prior loop and the base submit MARKET orders, which take liquidity
and pay the full bid-ask spread on every fill. Loop 5 makes each OPEN leg
*provide* liquidity first:

  1. On `on_order()` for an OPEN leg, read the latest cached top-of-book
     quote. Spawn a post-only LIMIT (a CHILD order, `reduce_primary=False`
     so the primary is left intact and at full quantity) for the full
     parent quantity at the SAME-SIDE TOUCH (BUY at the bid, SELL at the
     ask). The primary MARKET order is *held back* — not submitted.
  2. Set a `passive_timeout_ms` time alert keyed to this order.
  3. On the alert: re-fetch the spawned limit. If it filled, the parent
     intent is satisfied — do nothing (the held-back primary is never
     submitted). If it is still open, cancel it and submit the held-back
     primary MARKET order to sweep the position aggressively.

Reduce-only CLOSE legs bypass the passive path entirely and route straight
to MARKET — intraday_flat requires that closes are never delayed.

WHY A CHILD LIMIT, NOT A REDUCED PRIMARY
----------------------------------------
Nautilus' spawn API reduces the primary's quantity when `reduce_primary` is
True; spawning a child for the *entire* parent quantity would drive the
primary to zero, and `OrderUpdated` rejects a non-positive quantity
(`Condition.positive`). With `quantity == 1` there is no partial split that
leaves a positive primary. The resolution: spawn the limit with
`reduce_primary=False` (the primary keeps its full quantity, untouched) and
treat the *primary itself* as the deferred market fallback. Exactly one of
the two — the passive limit OR the primary market — ultimately fills the
1-lot parent intent, so the total filled quantity is always exactly the
parent quantity.

WHY THIS TARGETS IS
-------------------
`backtest_engine/arrival_price.py` defines

    is_bps = (fill_px - arrival_mid) * direction / arrival_mid * 10_000

A market BUY fills at the ask — roughly `+half_spread` of IS. A post-only
limit BUY that rests at the bid and fills there costs roughly
`-half_spread` — a price *better* than the arrival mid. On every order
where the passive limit fills before the timeout, IS improves by
approximately the full spread; on every order where it does not, the market
fallback reproduces exactly the base/loop-4 outcome.

INVARIANTS
----------
- Quantity: exactly one of {passive limit, primary market} fills the 1-lot
  parent intent. The primary is submitted on the timeout path ONLY when the
  limit is still open (unfilled); if the limit filled, the primary is never
  submitted. Total filled quantity == parent quantity.
- intraday_flat: CLOSE orders never enter the passive path; the passive
  window on opens (`passive_timeout_ms`) is short and far inside session.
- No look-ahead: the touch price comes from `cache.quote_tick()` at
  `on_order()` time — the most recent quote at or before the order's
  `ts_init`. No future data is read.
- Fail-open: if no quote is cached yet (session warmup), the primary is
  submitted immediately as a plain MARKET order — identical to base/loop-4.
"""
from __future__ import annotations

import pandas as pd

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PositionTierGateBL5Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the position-tier-gate-b-l5 execution algorithm.

    Parameters
    ----------
    passive_timeout_ms : int
        How long (milliseconds) a post-only limit may rest at the touch
        before the market fallback fires. Short enough that a 30 s-horizon
        oracle signal is not stale by fill time and intraday_flat is
        uncompromised; long enough to give the touch a realistic chance to
        be hit.
    """

    passive_timeout_ms: int = 750


class PositionTierGateBL5Algorithm(ExecAlgorithm):
    """Passive-then-aggressive execution algorithm.

    Each OPEN leg first rests a post-only limit (a child order) at the
    same-side touch; if it is unfilled after `passive_timeout_ms` the
    held-back primary market order is submitted to sweep the position.
    Reduce-only CLOSE legs route straight to market. See the module
    docstring for the IS rationale.
    """

    def __init__(self, config: PositionTierGateBL5Config) -> None:
        super().__init__(config=config)
        self._timeout = pd.Timedelta(milliseconds=config.passive_timeout_ms)
        # Map: time-alert name -> (primary order, spawned limit order).
        self._pending: dict[str, tuple] = {}
        self._alert_seq: int = 0
        # Diagnostic counters (per session) — do not affect routing.
        self._n_open: int = 0
        self._n_close: int = 0
        self._n_passive_spawned: int = 0
        self._n_market_fallback: int = 0
        self._n_fail_open: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self._reset_state()
        self.log.info(
            "PositionTierGateBL5Algorithm started "
            f"(passive-then-aggressive, timeout={self._timeout})."
        )

    def on_reset(self) -> None:
        self._reset_state()

    def on_stop(self) -> None:
        self.clock.cancel_timers()
        self.log.info(
            "PositionTierGateBL5Algorithm stopped — "
            f"opens={self._n_open}, closes={self._n_close}, "
            f"passive_spawned={self._n_passive_spawned}, "
            f"market_fallback={self._n_market_fallback}, "
            f"fail_open={self._n_fail_open}."
        )

    def _reset_state(self) -> None:
        self._pending = {}
        self._alert_seq = 0
        self._n_open = 0
        self._n_close = 0
        self._n_passive_spawned = 0
        self._n_market_fallback = 0
        self._n_fail_open = 0

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Route CLOSE legs to market; OPEN legs through the passive path."""
        # --- CLOSE legs: never delayed (intraday_flat). -----------------
        if order.is_reduce_only:
            self._n_close += 1
            self.submit_order(order)
            return

        self._n_open += 1

        # --- OPEN legs: try to provide liquidity at the touch. ----------
        quote = self.cache.quote_tick(order.instrument_id)
        if quote is None:
            # Session warmup — no quote cached yet. Fail open: behave
            # exactly like the base / loop-4 (immediate market).
            self._n_fail_open += 1
            self.submit_order(order)
            return

        if order.side == OrderSide.BUY:
            touch_price = quote.bid_price
        elif order.side == OrderSide.SELL:
            touch_price = quote.ask_price
        else:  # pragma: no cover - defensive
            self.submit_order(order)
            return

        # Spawn a post-only LIMIT child for the full parent quantity at the
        # same-side touch. `reduce_primary=False` leaves the primary intact
        # at full quantity so it can serve as the deferred market fallback.
        # post_only guarantees the limit can never cross the spread.
        limit = self.spawn_limit(
            primary=order,
            quantity=order.quantity,
            price=touch_price,
            time_in_force=TimeInForce.GTC,
            post_only=True,
            reduce_primary=False,
        )
        self.submit_order(limit)
        self._n_passive_spawned += 1

        # Schedule the market-fallback sweep. The primary itself is held
        # back (NOT submitted here) — it becomes the fallback order.
        self._alert_seq += 1
        alert_name = f"ptg_b_l5_sweep_{self._alert_seq}"
        self._pending[alert_name] = (order, limit)
        self.clock.set_time_alert(
            name=alert_name,
            alert_time=self.clock.utc_now() + self._timeout,
            callback=self._on_passive_timeout,
        )

    # ------------------------------------------------------------------
    # Time-alert callback — market fallback for an unfilled passive limit
    # ------------------------------------------------------------------

    def _on_passive_timeout(self, event) -> None:
        """If the passive limit is still open, cancel it and sweep the
        position with the held-back primary market order."""
        entry = self._pending.pop(event.name, None)
        if entry is None:
            return
        primary, limit = entry

        # Re-fetch the live limit order from the cache — the local handle
        # may be stale w.r.t. fill / cancel state.
        live_limit = self.cache.order(limit.client_order_id)

        if live_limit is not None and live_limit.is_closed:
            # The passive limit already resolved. If it FILLED, the 1-lot
            # parent intent is satisfied and the held-back primary must NOT
            # be submitted (that would double the position). If it was
            # canceled/rejected/expired for any reason, fall through to the
            # market sweep so the parent intent is still honoured.
            if live_limit.is_open or getattr(live_limit, "filled_qty", None):
                if live_limit.filled_qty and live_limit.filled_qty > 0:
                    return  # passive fill captured — done.

        if live_limit is not None and live_limit.is_open:
            # Still resting and unfilled — cancel it before sweeping.
            self.cancel_order(live_limit)

        # Submit the held-back primary MARKET order to sweep the position.
        live_primary = self.cache.order(primary.client_order_id)
        if live_primary is None:
            return
        if not live_primary.is_open and live_primary.is_closed:
            # Primary already resolved (defensive — should not happen since
            # it is held back). Nothing to do.
            return

        self.submit_order(live_primary)
        self._n_market_fallback += 1


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
) -> PositionTierGateBL5Algorithm:
    """Instantiate and return the PositionTierGateBL5Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    """
    config = PositionTierGateBL5Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
    )
    return PositionTierGateBL5Algorithm(config=config)
