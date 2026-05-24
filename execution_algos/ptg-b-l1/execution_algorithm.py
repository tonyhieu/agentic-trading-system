"""ptg-b-l1: position-tier-gate + position-age cooldown override.

Derived from `position-tier-gate` (the base). The base unconditionally
skips any OPEN order while a position is already open (net_qty >= cap=1).
Because the oracle fires CLOSE+OPEN at the same timestamp, the cache still
shows the old position when the new OPEN arrives, so the new OPEN is
always skipped — every signal-flip reversal is gated out.

This loop adds one targeted change: gate the skip on position age. If the
current position has been held for at least `min_age_ns`, allow the
reversal OPEN through; if the position is "fresh" (just opened, likely a
flip-flop), keep the base's skip behavior.

Rationale (informed only by inspecting the base algo; this is loop 1 of
the brief-summary arm and prior-loop context is empty):

The base ptg's success comes from killing every reversal that fires at
the same timestamp as a close. But not all reversals are noise -- some
reflect a real, sustained signal flip. The base treats them uniformly.
A natural conditioning axis is position age: a reversal arriving 0-1
ticks after an entry is almost certainly a noisy flip-flop; a reversal
arriving N seconds later is more likely a genuine regime change worth
participating in.

Mechanism additions over base:
  * Read the open position's `ts_opened` from the cache. Compute
    `age_ns = order.ts_init - position.ts_opened`. (If no open
    position, falls through to base behavior -- SUBMIT.)
  * If position is at/above cap AND age_ns < min_age_ns: SKIP
    (preserve the base's "kill flip-flop reversal" behavior).
  * If position is at/above cap AND age_ns >= min_age_ns: SUBMIT
    (override the base skip -- treat as a matured reversal).
  * Below cap: SUBMIT (same as base).
  * Reduce-only: SUBMIT unconditionally (intraday_flat compliance,
    same as base).

Quantity invariant: never modified -- skip or submit, never split.
No look-ahead: `position.ts_opened` is set when the open fill is
processed; `order.ts_init` for the incoming order is strictly later
than any fill already in the cache.
"""
from __future__ import annotations

from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId


class PtgBL1Config(ExecAlgorithmConfig, frozen=True):
    """Configuration for ptg-b-l1.

    Parameters
    ----------
    position_cap : int
        Same semantics as base position-tier-gate. Default 1: skip new
        opens while any position is open (subject to the age override).
    min_age_ns : int
        Minimum age of the current open position (in nanoseconds) before
        the position-cap skip is overridden and the reversal OPEN is
        allowed through. Default 5_000_000_000 (5 seconds). At 5 seconds,
        the oracle has had time to fire ~5 signals on the original side
        before flipping -- a flip after that horizon is more likely to
        reflect a sustained direction change than a one-tick noise flip.
    """

    position_cap: int = 1
    min_age_ns: int = 5_000_000_000  # 5 seconds


class PtgBL1Algorithm(ExecAlgorithm):
    """position-tier-gate with a position-age override for matured reversals.

    For each incoming order:
      * Reduce-only:     SUBMIT (intraday_flat compliance).
      * Open, below cap: SUBMIT (no exposure constraint hit).
      * Open, at/above cap:
          - If current position age < min_age_ns:  SKIP  (likely flip-flop)
          - If current position age >= min_age_ns: SUBMIT (matured reversal)

    Diagnostic counters: submitted_normal, skipped_fresh,
    submitted_aged_override.
    """

    def __init__(self, config: PtgBL1Config) -> None:
        super().__init__(config=config)
        self._position_cap: int = config.position_cap
        self._min_age_ns: int = config.min_age_ns

        # Diagnostic counters
        self._submitted_normal: int = 0
        self._submitted_aged_override: int = 0
        self._skipped_fresh: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.log.info(
            "PtgBL1Algorithm started "
            f"(position_cap={self._position_cap} contracts, "
            f"min_age_ns={self._min_age_ns} = {self._min_age_ns / 1e9:.2f}s)."
        )

    def on_reset(self) -> None:
        self._submitted_normal = 0
        self._submitted_aged_override = 0
        self._skipped_fresh = 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _net_qty_and_oldest_ts_opened(
        self, instrument_id
    ) -> tuple[float, int | None]:
        """Return (absolute net qty, ts_opened of the oldest open position).

        Netting OMS: typically one open position per instrument. We
        compute net_qty as the sum of absolute quantities across all
        currently open positions and return the minimum `ts_opened`
        across them (the longest-held position's open timestamp), so
        the age check uses the most-mature position when computing
        the override.
        """
        open_positions = self.cache.positions_open(instrument_id=instrument_id)
        if not open_positions:
            return 0.0, None

        total = 0.0
        oldest_ts: int | None = None
        for p in open_positions:
            total += float(str(p.quantity))
            ts = p.ts_opened
            if oldest_ts is None or ts < oldest_ts:
                oldest_ts = ts
        return total, oldest_ts

    # ------------------------------------------------------------------
    # Main order handler
    # ------------------------------------------------------------------

    def on_order(self, order) -> None:
        # Reduce-only (close) orders always execute -- intraday_flat.
        if order.is_reduce_only:
            self.submit_order(order)
            return

        net_qty, oldest_ts = self._net_qty_and_oldest_ts_opened(order.instrument_id)

        # Below cap -- always submit (same as base).
        if net_qty < self._position_cap:
            self._submitted_normal += 1
            self.submit_order(order)
            return

        # At/above cap. Apply age-override logic.
        if oldest_ts is None:
            # Defensive: cap was reported as hit but no position is open.
            # Submit so we never deadlock on a missing position record.
            self._submitted_normal += 1
            self.submit_order(order)
            return

        age_ns = order.ts_init - oldest_ts

        if age_ns >= self._min_age_ns:
            # Matured -- override the base skip; treat as a real reversal.
            self._submitted_aged_override += 1
            self.log.debug(
                f"SUBMIT {order.client_order_id} (cap hit but matured: "
                f"age={age_ns / 1e9:.2f}s >= {self._min_age_ns / 1e9:.2f}s, "
                f"override=True). "
                f"counts: norm={self._submitted_normal} "
                f"aged={self._submitted_aged_override} "
                f"skip_fresh={self._skipped_fresh}"
            )
            self.submit_order(order)
            return

        # Fresh position -- preserve the base's skip behavior.
        self._skipped_fresh += 1
        self.log.debug(
            f"SKIP {order.client_order_id} (cap hit and fresh: "
            f"age={age_ns / 1e9:.2f}s < {self._min_age_ns / 1e9:.2f}s)."
        )
        # Do NOT call submit_order -- quantity invariant preserved.


def get_execution_algorithm(
    exec_id: str = "MY_GENERIC_ALGO",
    position_cap: int = 1,
    min_age_ns: int = 5_000_000_000,
) -> PtgBL1Algorithm:
    """Instantiate the ptg-b-l1 position-tier-gate + age-override algorithm."""
    config = PtgBL1Config(
        exec_algorithm_id=ExecAlgorithmId(exec_id),
        position_cap=position_cap,
        min_age_ns=min_age_ns,
    )
    return PtgBL1Algorithm(config=config)
