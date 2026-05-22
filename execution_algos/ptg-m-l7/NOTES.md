# ptg-m-l7 — per-iteration experiment (position-tier-gate, metrics-only, loop 7)

## Hypothesis

Context mode is metrics-only: the only prior-loop information available is the
`metrics` block of loop-1 .. loop-6. Hypothesis is derived solely from those
numbers.

Prior-loop metrics (numbers only):

| Loop | trade_count | pnl_vs_base | sharpe |
|------|-------------|-------------|--------|
| 1    | 90433       | +0.0%       | 17.62  |
| 2    | 47725       | -23.1%      | 15.81  |
| 3    | 84541       | -7.0%       | 16.95  |
| 4    | 136734      | -96.3%      | 0.60   |
| 5    | 136734      | -96.3%      | 0.60   |
| 6    | 92461       | -8.4%       | 16.59  |

Plotting `pnl_vs_base` against `trade_count` gives a single-peaked curve that
maximizes at trade_count = 90433 (loop 1, where pnl_vs_base = 0.0%). Every
deviation from that count costs P&L:

- Under-trading: loop 2 (47725, -23.1%), loop 3 (84541, -7.0%).
- Over-trading: loop 6 (92461, -8.4%), loops 4/5 (136734, -96.3% collapse).

Loop 6 overshot the peak: 92461 is +2028 above 90433. Loop 3 undershot:
84541 is -5892 below the peak. The peak (90433) sits between loop 3 and
loop 6, so a trade_count in (84541, 92461) closer to 90433 should lift
pnl_vs_base above both loop 3's -7.0% and loop 6's -8.4%, toward 0%.

Loop 6's mechanism: position_cap=1 (tight integer gate, the loop-3 regime at
84541) plus a deterministic 1-in-`admit_every` fractional admit on gated opens.
With admit_every=16 it lifted trade_count from 84541 to 92461 — i.e. it
admitted ~7920 gated opens. To land on ~90433 instead, only ~5892 gated opens
should be admitted (90433 - 84541). The raw gated-open population implied by
loop 6 is roughly admitted * admit_every = 7920 * 16 ≈ 126720. Admitting
5892 of those requires admit_every ≈ 126720 / 5892 ≈ 21.5.

**Change vs ptg-m-l6:** keep position_cap=1 and the fractional-admit
mechanism unchanged; raise `admit_every` from 16 to 22. This throttles the
fractional pass-through so trade_count drops from loop 6's 92461 toward the
90433 peak, expected to land slightly above 84541 + 126720/22 ≈ 84541 + 5760 ≈
90300 — within ~150 trades of the peak. Expected pnl_vs_base: better than both
loop 3 (-7.0%) and loop 6 (-8.4%), approaching 0%.

No look-ahead, no quantity modification — same structural guarantees as
ptg-m-l6. Single parameter change.

## Backtest Observations

Train window 2026-03-08 .. 2026-03-21 (12 dates), `--use-cached-baseline`.

| metric          | ptg-m-l7   | position-tier-gate (base) |
|-----------------|------------|---------------------------|
| realized_pnl    | 3987.25    | 4262.50                   |
| mean_slippage   | 0.0        | 0.0                       |
| sharpe_ratio    | 16.77      | 17.62                     |
| max_drawdown_pct| -0.0193    | -0.0173                   |
| win_rate        | 0.3701     | 0.3720                    |
| trade_count     | 91982      | 90433                     |

- vs_base_pnl_pct      = -6.46%
- vs_base_slippage_pct = 0.0% (both sides zero slippage — top-of-book only)

The hypothesis held directionally. Raising `admit_every` from 16 to 22
lowered trade_count from loop 6's 92461 to 91982 — closer to the 90433 peak
— and pnl_vs_base improved correspondingly: -6.46% beats both loop 6 (-8.4%)
and loop 3 (-7.0%). This is the best non-base loop in the arm so far.

The single-peaked trade_count -> pnl model continues to fit. The peak is
90433; ptg-m-l7 lands at 91982, +1549 above it (loop 6 was +2028, loop 3 was
-5892). The realized throttle was weaker than the projection predicted
(expected ~90300; actual 91982): the implied raw gated-open population is
larger than the loop-6 back-of-envelope estimate, so each extra unit of
admit_every removes fewer trades than assumed. A future loop should raise
admit_every a little further (toward ~26-30) to shave the remaining ~1549
trades off and land on the peak — or, since integer admit_every steps still
overshoot the exact peak, consider a finer fractional admit (e.g. admit
a target *count* of gated opens rather than a 1-in-K ratio) to hit 90433
precisely.

Trade counts are large (tens of thousands per date) — no low-count caveat.
