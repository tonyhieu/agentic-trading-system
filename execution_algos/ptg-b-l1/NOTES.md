# Algorithm Notes: ptg-b-l1

Experiment arm: `per_iteration_experiment` / base `position-tier-gate` /
context mode `brief-summary` / loop 1.

## Context loaded for this loop

None. Loop 1 of the brief-summary arm has no prior loops to summarize, so
`context_chars_in = 0`. Hypothesis derives directly from the base algo
`position-tier-gate`.

## Hypothesis

The base `position-tier-gate` skips every OPEN order that arrives while a
position is already open (net_qty >= cap=1). Because the oracle fires
CLOSE+OPEN at the *same* `ts_init`, the cache still shows the old position
when the new OPEN arrives, so *every reversal OPEN* is unconditionally
gated out. This rule conditions on portfolio state only -- it does not
differentiate noisy 1-tick flip-flops from genuine, sustained signal
reversals.

**Change:** add a position-age override. When the cap is hit but the
current position has been held for at least `min_age_ns` (default 5
seconds), allow the OPEN through. Below that age threshold, preserve
the base's skip.

Expected effect:
* trade_count: rises modestly above the base (some matured reversals are
  now executed) and remains far below the unfiltered baseline.
* realized P&L: should improve if matured reversals are profitable on
  average; should degrade if even matured reversals are noisy enough that
  the base's blanket skip was correct.
* slippage: zero-fill model, so no slippage effect either way.

Risk: if the oracle's flip pattern is roughly age-independent (signals
are just as noisy at 5s as at 1s), this lets noise back in and drags pnl
toward the unfiltered baseline rather than above the base algo.

## Implementation Decisions

* Read the open position's `ts_opened` via
  `cache.positions_open(instrument_id)` and compute
  `age_ns = order.ts_init - position.ts_opened` at `on_order()`. Both
  attributes are general Nautilus `Position` API (`Position.ts_opened`
  and `Order.ts_init`); not domain-specific.
* `min_age_ns = 5_000_000_000` (5 seconds). The oracle fires at 1-second
  cadence (per `research/config.yaml -> strategy.kwargs.signal_interval_seconds`).
  5 seconds gives the position time to absorb 5 oracle signals on the
  original side before a flip is treated as "matured."
* When multiple open positions exist (netting OMS edge case), use the
  *oldest* `ts_opened` so the age check uses the most-mature position --
  this is the conservative interpretation of "the position has matured."
* Defensive: if the cap is reported as hit but no open position is found
  (race or accounting edge case), SUBMIT rather than deadlock.
* Quantity invariant preserved: skip or submit, never modify.
* Reduce-only orders always SUBMIT (intraday_flat compliance, same as
  base).

## Backtest Observations

11-date apples-to-apples train aggregate (Sun-Fri 2026-03-08..2026-03-20,
with 20260319 OOM-killed inside the docker subprocess and dropped from
BOTH sides by the runner).

Vs `simple` baseline (gate comparison):
* realized_pnl: $879.25  vs $43.25   -> +1932.95% (well above +5.0% PASS gate)
* sharpe_ratio: 4.299    vs ~0.01    -> strong improvement
* mean_slippage: 0.0     vs 0.0      -> no regression (zero fill-cost model;
  see research/NOTES.md)
* max_drawdown_pct: -3.89%
* win_rate: 35.65%
* trade_count: 83,581 vs 111,489 (-25%; algo still gates many opens)
* is_weighted_bps: 0.0430 (vs simple baseline +0.673; ptg-b-l1 captures
  arrival mid better in absolute bps terms)

Vs base `position-tier-gate` on same 11 dates (informational; not the gate):
* realized_pnl: $879.25  vs $3,564.25 -> -75.33%
* trade_count: 83,581    vs 73,802    -> +13.25%
* Per-date: ptg-b-l1 is WORSE than the base on all 11 dates -- in absolute
  dollars (range -$32 to -$450 per date) and on 3 of 11 dates the algo
  flips to net-negative pnl (20260312/13/16/17) where the base was
  positive or near-zero.

What drove the result:
* Vs simple: the base's position-cap mechanism (which ptg-b-l1 inherits)
  is doing most of the work -- skipping the bulk of reversal opens keeps
  the algo from chasing every noisy 1-second oracle flip.
* Vs base: the 5-second age override is letting too many reversals
  through. The age filter is firing on roughly 9,779 more orders than the
  base would have submitted (the +13.25% trade_count delta) and those
  extra orders are *systematically money-losing*. This is the opposite of
  the hypothesis -- matured reversals are NOT better than blanket-gated
  reversals at this strategy/oracle horizon. At 30-second oracle
  horizon, a position older than 5 seconds is already mid-life relative
  to the signal; flipping it just realizes a worse entry than holding.

Hypothesis verdict: CONTRADICTED. The age-override added trades that
destroyed pnl relative to the base. The base's blanket reversal-skip is
correct precisely because the oracle's "matured" signals are not
meaningfully better than its fresh ones at this cadence -- a 5-second-old
position is still well inside the 30-second forecast window, so a flip
is information-poor.

Gate status vs `simple`: PASS (+1932.95% >> +5.0%). Note this is a
brief-summary arm loop -- the per-loop comparison that matters for
refinement is vs the base algo, where ptg-b-l1 is materially WORSE.

Single highest-leverage next-loop change: invert the age semantics --
keep the base's blanket reversal-skip and instead lengthen the holding
window (e.g. force-hold an open position for >= 5s by refusing
reduce-only orders younger than that), or add a *signal-strength* (not
age) override -- e.g. submit a reversal OPEN only when the new oracle
edge magnitude exceeds the previous edge by a multiplier. The age
dimension alone is not a useful filter on this oracle.

