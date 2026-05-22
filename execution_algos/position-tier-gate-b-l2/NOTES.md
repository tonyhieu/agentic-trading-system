# position-tier-gate-b-l2

Per-iteration experiment — arm: `base_algo=position-tier-gate`,
`mode=brief-summary`, **loop 2**. Starting point: `position-tier-gate-b-l1`.

## Hypothesis

The loop-1 summary identified a structural defect, not a parameter-tuning
miss: the loop-1 portfolio-equity circuit breaker measures realized-P&L
drawdown against an **all-time session peak**. Under the sigma=200 (high
noise) oracle config, realized P&L almost never climbs back above a prior
all-time high, so once the gate trips it latches shut for the rest of the
session. The consequence reported by loop 1: `trade_count` collapsed to
32,475 — 76% below `simple` — and Sharpe was distorted to -106.

The loop-1 `Next` field names the fix explicitly: make the breaker re-arm,
via a rolling/decaying drawdown reference and/or resuming opens after a
partial recovery, and reconsider the `drawdown_halt` value (150 USD may
engage too early).

Loop 2 applies both re-arming mechanisms:

1. **Decaying peak reference** (`peak_decay = 0.10`). The peak is no longer a
   hard maximum. A new realized-P&L high still snaps the peak up immediately,
   but on any non-high close the peak is pulled 10% of the way toward the
   current P&L. A flat or losing stretch therefore slowly lowers the
   reference bar, shrinking the measured drawdown and re-arming the gate even
   with no genuine P&L recovery. `peak_decay = 0.0` exactly reproduces loop-1
   behaviour, so this is a strict generalisation.

2. **Recovery hysteresis band** (`drawdown_halt = 220`, `drawdown_rearm =
   80`). The gate is now a latched state. It latches SKIP when drawdown
   exceeds `drawdown_halt`, and only unlatches once drawdown falls back to or
   below `drawdown_rearm`. The gap between the two thresholds stops the gate
   chattering open/shut tick-by-tick around a single line, while still
   guaranteeing it reopens after a partial recovery.

`drawdown_halt` is also relaxed 150 -> 220 USD per the loop-1 note that 150
may engage too early.

**Expected effect:** trade_count should recover substantially toward
`simple`/base levels because the gate no longer latches permanently; the gate
should still cut exposure during genuine deep drawdowns. If realized P&L
improves or holds while trade_count rises, that confirms the loop-1 skipped
subset was being over-cut by the one-way latch. If realized P&L worsens as
trade_count rises, it would indicate the throttled opens were genuinely
net-negative and the gate should stay stricter.

No look-ahead: `on_position_closed` fires after the close fill is processed,
strictly in the past relative to subsequent `on_order` calls. No order
quantity is ever modified — orders are submitted or skipped only. Reduce-only
orders always submit (intraday_flat compliance).

## Backtest Observations

Train window: 2026-03-08..2026-03-20 (12 dates). Baseline: `simple` (cached).

Aggregate metrics (`results/backtest-results.json`):

| metric          | base `position-tier-gate` | loop-1 `-b-l1` | loop-2 `-b-l2` |
|-----------------|---------------------------|----------------|----------------|
| realized_pnl    | -5892.25                  | -1675.25       | **-8857.50**   |
| mean_slippage   | 0.0                       | 0.0            | 0.0            |
| sharpe_ratio    | -27.23                    | -106.02        | -28.30         |
| max_drawdown_pct| -0.0986%                  | -0.0155%       | -0.1386%       |
| win_rate        | 0.3285                    | 0.2966         | 0.3272         |
| trade_count     | 101304                    | 32475          | 152300         |

vs base `position-tier-gate`:
  `vs_base_pnl_pct = -50.32%`  (worse — realized P&L fell from -5892 to -8857)
  `vs_base_slippage_pct = 0.0%`  (both algos and base have zero modeled slippage)

**The re-arming mechanism worked exactly as designed, and that is the bad
news.** trade_count jumped to 152,300 — far above loop-1's latched 32,475 and
even above the base's 101,304. The decaying peak plus hysteresis re-arm
clearly let the gate reopen repeatedly. But the trades it now re-admits are
net-negative: realized P&L worsened to -8857.50, a 50% regression vs base and
a complete reversal of loop-1's +71.6% vs-base advantage.

This isolates the real source of loop-1's apparent win. Loop-1 did not select
good trades — it simply stopped trading for most of the session once its
one-way latch tripped. Under sigma=200 the oracle signal is near-random, so
*not trading* is the value-preserving action and *trading more* destroys
value roughly in proportion to volume (base -5892 at 101k trades vs loop-2
-8857 at 152k trades — both around -5.8 USD per 100 trades). The loop-1
breaker was a volume suppressor dressed up as a risk control; making it
re-arm removed the suppression and surfaced the underlying negative edge.

max_drawdown also worsened (-0.0155% -> -0.1386%) because the re-armed gate
keeps adding exposure through losing stretches instead of latching out.

Sharpe recovered from -106 to -28.3, but only because that figure is an
artifact of trade count: loop-1's 32k-trade series produced a degenerate
near-zero-variance daily P&L path. -28.3 is in line with the base's -27.2 and
is not a genuine improvement.

**Conclusion for future loops:** drawdown / equity-based gating on *realized
P&L* is the wrong lever here. The only thing that helped loop-1's vs-base
number was cutting volume, and cutting volume indiscriminately is not a real
execution edge. The negative per-trade edge is structural under sigma=200, so
a future loop should either (a) gate on a *signal-quality / market-state*
feature available at order time (e.g. spread, top-of-book imbalance, recent
realized volatility) so it skips genuinely worse entries rather than a random
subset, or (b) accept that under this oracle config the execution layer
cannot manufacture positive P&L and instead optimize a slippage / IS metric
where there is real room to move. Equity-feedback gating is exhausted.
