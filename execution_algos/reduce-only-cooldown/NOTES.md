# Algorithm Notes: reduce-only-cooldown

## Hypothesis

**Mechanism**: Scheduling — defer every order with `is_reduce_only=True` by
`defer_ms` milliseconds via a clock alert; orders without the flag (opening
orders) pass straight through. On alert fire, the deferred order is submitted
to the venue unchanged.
**Inefficiency exploited**: The fixed `oracle` strategy (`sigma=0.5`,
`signal_interval_seconds=1.0`) has Gaussian noise on its forecast. When the
strategy emits a close, the underlying signal often has small additional drift
in the predicted direction during the next ~50–200 ms before the next signal
is sampled. The baseline `simple` algorithm forwards the close immediately,
so the strategy realizes only the price at decision time. A brief deferral
lets that residual drift accrue to the realized P&L of the closed position.
**Why it survives costs**: The fill model in `backtest_engine` reports
`mean_slippage = 0.0` and `total_commissions = 0.0` for the baseline, so
there are no per-trade frictions to overcome. The only channel for
improvement here is letting winners run a hair longer on close. The expected
effect is small; this iteration also tests the FAIL path of the research
procedure.
**Builds on**: none — original hypothesis (program database is empty).
**Alternatives considered**:
- *Participation-cap-aware splitting*: rejected — strategy emits qty=1 only,
  so floor(0.05 × top-of-book qty) ≥ 1 in nearly every regime. Behaviorally
  identical to baseline.
- *Passive-mirror with cross-on-timeout*: rejected for a first iteration —
  Nautilus passive-fill semantics under this fill model are not yet
  characterized; high risk of position drift.
- *Symmetric pre-open delay*: rejected — would alter when positions open,
  shifting strategy behavior in ways harder to attribute.

---

## Implementation Decisions

- `defer_ms` is the only kwarg, default 50. Read from
  `execution_algorithm_kwargs` so the config is the source of truth and the
  parameter is sweep-able by future iterations.
- State: `self._deferred: dict[str, Order]` mapping the per-order alert name
  to the held order. Alert names use the client order ID for uniqueness.
- `on_order` branches on `order.is_reduce_only`. Opening orders submit
  immediately. Reduce-only orders register a clock alert at
  `now + defer_ms*1e6` ns and store the order; on alert, the order is
  submitted unchanged.
- `on_event` filters for `TimeEvent` whose `name` is in `self._deferred`.
- `defer_ms = 0` is supported and collapses to baseline behavior (the alert
  fires on the next event tick).

**Concerns**:
- *Look-ahead bias*: none. The decision at `on_order` uses only the order
  attributes (`is_reduce_only`) and the current clock time; no future ticks
  are read.
- *Position-state divergence*: when the strategy emits a paired close +
  opposite-side open simultaneously, deferring only the close briefly leaves
  the algo holding both sides. The simulator should net this on
  reconciliation, but instantaneous mark-to-market between the two events
  may differ from baseline. Reported in Backtest Observations if material.
- *Trade-count attribution*: deferred orders still produce the same fill
  count, so `trade_count` should match baseline within ±a few rounding
  artifacts at session boundaries.

---

## Backtest Observations

Run on the only cached partitions inside `data_window` (no new downloads
this iteration): train = {20260309, 20260313, 20260317}; test = {20260406}.
Same `(strategy, kwargs, symbol)` for every run. `defer_ms = 50`.

| split | date     | algo                 | pnl     | trades | win_rate | sharpe  | mdd        |
|-------|----------|----------------------|---------|--------|----------|---------|------------|
| train | 20260309 | simple               | 3092.00 | 1194   | 0.846    | 382.73  | -0.000474  |
| train | 20260309 | reduce-only-cooldown | 2936.75 | 971    | 0.908    | 368.08  | -0.000499  |
| train | 20260313 | simple               | 2297.00 | 2031   | 0.733    | 444.24  | -0.000275  |
| train | 20260313 | reduce-only-cooldown | 2372.25 | 1607   | 0.823    | 467.92  | -0.000225  |
| train | 20260317 | simple               | 2022.75 | 4168   | 0.642    | 545.30  | -0.000324  |
| train | 20260317 | reduce-only-cooldown | 2045.75 | 3062   | 0.733    | 581.38  | -0.000175  |
| test  | 20260406 | simple               | 2520.75 | 4396   | 0.674    | 503.57  | -0.000275  |
| test  | 20260406 | reduce-only-cooldown | 2523.00 | 3249   | 0.757    | 534.88  | -0.000175  |

**Train aggregates** (sum P&L, mean slippage):
- simple                : pnl_sum = 7411.75, mean_slip = 0.0
- reduce-only-cooldown  : pnl_sum = 7354.75, mean_slip = 0.0
- `delta_pnl_pct` (train) = (7354.75 − 7411.75) / 7411.75 × 100 = **−0.769%**
- `delta_slip_pct` = 0 (both algos report zero slippage — see §8 alert in
  `research/NOTES.md`).

**Test (1 date — RESULT WARNING)**:
- `delta_pnl_pct` (test) = (2523.00 − 2520.75) / 2520.75 × 100 = **+0.089%**

**Gate** (`min_pnl_improvement_pct = 5.0`, `max_slippage_regression_pct = 5.0`,
`close_margin_pct = 2.0`):
- Train P&L delta is **−0.77%** vs the required **+5.0%** → fails the P&L gate.
- Slippage doesn't regress (both 0.0) → the gate's slippage condition is
  trivially satisfied here, so it gives no signal.
- Distance from PASS on the P&L axis = 5.77pp, which exceeds
  `close_margin_pct = 2.0` → **FAIL**, not CLOSE.

**What drove improvement**: nothing material. The 50 ms close-side defer did
NOT raise realized P&L; on 2 of 3 train dates it lost ground vs baseline,
and only matched it on the test date. Win-rate is consistently higher under
the defer (e.g. 0.908 vs 0.846 on 20260309, +6.2pp), suggesting a
distributional shift — fewer but better trades — but average dollar P&L per
day went sideways or down.

**What underperformed**: realized P&L is the gate's primary axis and the
defer didn't move it. The fill model in `backtest_engine` reports
`mean_slippage = 0.0` and `total_commissions = 0.0` for both algos on every
date, so the algorithm is not paying for the residual-drift it's chasing
through any execution-cost channel. The `oracle` strategy's signal cadence
is `signal_interval_seconds = 1.0`; deferring a close by 50 ms is small vs
that cadence and apparently small vs the noise budget (`sigma = 0.5`), so
the residual-drift edge is too thin to detect on three days.

Note also the `trade_count` and `fill_count` shifts: the defer reduces
trade_count by ~20–30% per date (e.g. 4168 → 3062 on 20260317). This is
because some deferred closes get superseded by a later strategy decision —
the *implementation* has changed the realized trade pattern, not just the
fill timing. That's a fragile assumption in the original hypothesis: the
algo isn't a pure scheduling overlay, it occasionally drops trades when the
strategy reverses inside `defer_ms`. Worth flagging for any next iteration.

**Hypothesis verdict**: NOT supported. The "let close-side residual drift
accrue" mechanism does not produce a measurable P&L improvement on 3
training days, and the test day is essentially flat. The win-rate
improvement is interesting but not gate-relevant.

**Suggested next attempt**: shift the lever entirely. Two leads worth
trying (one per future iteration, per §6):
1. *Conditional submission, not scheduling.* Inspect top-of-book imbalance
   at `on_order` time and route only when imbalance favors the order side
   (Cartea/Jaimungal-style stochastic-control reading of the book).
   Mechanism is observable at decision time so no look-ahead concern.
2. *Slice opening orders* with a small participation cap when top-of-book
   qty is unusually large. The current strategy emits qty=1 so the
   participation-cap floor is rarely binding, but slicing could exploit
   queue dynamics on dates with thin books — but only if the fill model
   actually surfaces queue-position effects (currently it does not, per
   the global note). Lower priority until the slippage gate has signal.
