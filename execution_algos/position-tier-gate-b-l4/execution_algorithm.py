"""Position-tier-gate-b-l4 execution algorithm.

Per-iteration experiment — arm: base_algo=position-tier-gate,
mode=brief-summary, loop 4. Starting point: `position-tier-gate-b-l3`
(this file is a modified copy of that algorithm).

WHAT CHANGED FROM LOOP 3
------------------------
Loop 3 gated each OPEN leg on an order-time top-of-book imbalance feature
(skip BUYs into ask-stacked books / SELLs into bid-stacked books). Loops 1
and 2 gated on a portfolio-equity circuit breaker. The brief summaries of
all three loops converge on one directive: binary skip/submit *entry
gating* has failed three independent ways, and the remaining real room is
the execution objective itself — implementation shortfall (IS), which a
future loop should target via order *timing* rather than skip gating.

Loop 4 acts on that. It removes the imbalance gate (and every other gate)
entirely and routes every order — open and close alike — to the venue with
zero added latency inside `on_order()`.

WHY THIS TARGETS IS
-------------------
`backtest_engine/arrival_price.py` defines implementation shortfall as

    is_bps = (fill_px - arrival_mid) * direction / arrival_mid * 10_000

where `arrival_mid` is the top-of-book mid captured at the order's
`ts_init` — the strategy's decision time, *before* the execution algorithm
touches the order. IS therefore measures the adverse price drift between
the decision and the actual fill. Any execution friction that delays a
fill (serialized entry, skip-then-resubmit churn, deferral) lets the market
drift away from the arrival mid and inflates IS.

That is why the base `position-tier-gate` (is_weighted_bps 0.045) and
especially loop-3's imbalance gate (0.064) are worse on IS than `simple`
(0.039): `simple` submits every order the instant it arrives, minimising
the decision-to-fill gap. The timing-optimal execution is therefore to
submit every order immediately with no added latency — exactly what this
algorithm does.

DESIGN
------
`on_order()` does the minimum possible work: it calls `submit_order(order)`
in the same handler invocation, with no quote lookups, no portfolio-state
reads, no equity tracking, no deferral, and no conditional branch that
could hold an order back. This is the inverse of every prior loop, and the
IS numbers predict it is the change that actually helps.

Order quantity is never modified — every order is submitted in full, so the
quantity invariant is trivially preserved. Reduce-only / closing orders are
handled by the same immediate path, which keeps the algorithm
intraday_flat-compliant (closes are never delayed).

No look-ahead and no market-data dependence at all: the algorithm reads
nothing from the cache, so there is no path by which future information
could influence routing.

Diagnostic counters are kept (opens vs closes submitted) purely for the
on_stop log line; they do not affect routing.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PositionTierGateBL4Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for the position-tier-gate-b-l4 execution algorithm.

    The algorithm is intentionally parameter-free: loop 4's thesis is that
    the lowest implementation shortfall comes from adding *zero* execution
    friction, so there is no threshold or tunable to expose. The class is
    kept (rather than reusing the bare `ExecAlgorithmConfig`) only so the
    factory signature stays consistent with the other loops in this arm.
    """


class PositionTierGateBL4Algorithm(ExecAlgorithm):
    """Zero-latency pass-through execution algorithm.

    Every incoming order — opening or reduce-only — is submitted to the
    venue immediately inside the same `on_order()` invocation, with no
    gating, no deferral, and no order-quantity modification.

    Rationale: implementation shortfall is measured against the arrival mid
    at decision time, so the minimum-IS execution is the one that minimises
    the decision-to-fill latency. Adding nothing is the timing-optimal
    policy. See the module docstring.
    """

    def __init__(self, config: PositionTierGateBL4Config) -> None:
        super().__init__(config=config)
        # Diagnostic counters (per session) — do not affect routing.
        self._n_submitted_open: int = 0
        self._n_submitted_close: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self._n_submitted_open = 0
        self._n_submitted_close = 0
        self.log.info(
            "PositionTierGateBL4Algorithm started "
            "(zero-latency pass-through, no gating)."
        )

    def on_reset(self) -> None:
        self._n_submitted_open = 0
        self._n_submitted_close = 0

    def on_stop(self) -> None:
        self.log.info(
            "PositionTierGateBL4Algorithm stopped — "
            f"opens submitted={self._n_submitted_open}, "
            f"closes submitted={self._n_submitted_close}."
        )

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        """Submit every order immediately — zero added execution latency."""
        # Count for the on_stop diagnostic only; this branch does not gate.
        if order.is_reduce_only:
            self._n_submitted_close += 1
        else:
            self._n_submitted_open += 1

        # Immediate, in-full submission. No quote lookup, no state read,
        # no deferral — minimises the decision-to-fill gap that drives IS.
        self.submit_order(order)


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
) -> PositionTierGateBL4Algorithm:
    """Instantiate and return the PositionTierGateBL4Algorithm.

    Parameters
    ----------
    exec_id : str
        Execution algorithm identifier registered with Nautilus.
    """
    config = PositionTierGateBL4Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
    )
    return PositionTierGateBL4Algorithm(config=config)
