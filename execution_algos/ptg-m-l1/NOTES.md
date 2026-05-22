# ptg-m-l1 — NOTES

Per-iteration experiment, base `position-tier-gate`, context mode `metrics-only`,
loop 1.

## Hypothesis

Starting point: `position-tier-gate` (base algo for loop 1).

Base metrics (the fixed comparison point for all 8 loops):
  realized_pnl = 4262.5, sharpe = 17.62, win_rate = 0.372,
  trade_count = 90433, mean_slippage = 0.0.

Observation from the numbers only: the base algo turns over ~90k trades with a
win rate of only 0.372. The base gate is purely positional — it skips a new
open leg whenever any position is already open (`position_cap=1`). That
serializes entry, but it still re-arms the instant the prior position closes,
so a noisy oracle reversal one second later immediately produces another full
open. With a 0.372 win rate, a large fraction of those back-to-back re-entries
are losers.

Targeted change for this loop: add a **post-open cooldown**. Keep the existing
positional cap, but additionally gate new open legs on a minimum elapsed time
since the most recent submitted open. The cooldown lets a just-closed losing
entry "settle" before capital is recommitted, filtering the highest-churn
back-to-back opens. Reduce-only (close) orders remain unconditional so
intraday_flat is never violated and exposure can always be reduced.

Expectation: trade_count falls, win_rate rises (the filtered re-entries are
disproportionately losers given win_rate < 0.5), and realized_pnl improves or
holds because fewer low-quality entries are taken. Cooldown chosen at 2.0 s —
twice the oracle's 1.0 s signal cadence — so at most every other signal can
open, without starving entry entirely.

## Backtest Observations

Train window (12 dates, 2026-03-08..2026-03-20), `--use-cached-baseline`.

ptg-m-l1 results:
  realized_pnl   = 4262.5
  mean_slippage  = 0.0
  sharpe_ratio   = 17.619
  max_drawdown   = -0.0173 %
  win_rate       = 0.37204
  trade_count    = 90433

vs base `position-tier-gate`:
  vs_base_pnl_pct      = 0.00 %
  vs_base_slippage_pct = 0.00 %  (both 0.0 slippage — ratio undefined, treated as 0)

Outcome: identical to base on every metric, to all printed digits. The
post-open cooldown gate had no measurable effect.

Why: the positional cap (`position_cap=1`) already serializes entry — a new
open is only ever eligible once the prior position is flat. Consecutive
submitted opens are therefore separated by at least one full position
lifetime, which on this strategy/data is already longer than the 2.0 s
cooldown. The cooldown branch is reachable only when two opens both clear
the positional gate within 2 s of each other, and that never happens. The
two gates are redundant under `position_cap=1`; the cooldown is dominated.

Implication for a future loop: to change behaviour, the cooldown must be
either (a) much longer than a typical position lifetime so it actually
bites after a flat, or (b) the positional gate must be loosened
(`position_cap >= 2`) so the cooldown becomes the active constraint on
stacking. A purely additive gate that is strictly weaker than an existing
one cannot move the metrics.
