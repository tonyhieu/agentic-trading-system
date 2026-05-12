# Algorithm Notes: streak-spread-tight

## Hypothesis

**Mechanism**: Bid-ask spread conditioned skip (same logic as streak-spread-skip) with a
tighter spread threshold of 1.1x rolling median (vs 1.3x in streak-spread-skip). The streak
condition (skip when last 2 consecutive estimated PnL are negative) is retained unchanged.
The combined OR condition is preserved: skip when EITHER spread > 1.1x median OR 2-loss streak.

**Inefficiency exploited**: The prior PASS algorithm (streak-spread-skip) was calibrated on
3 training dates (20260308-10) with win rates of 47-49%. The full 12-date train window shows
substantially lower win rates on 9 of 12 dates (32-38%), with the largest date groups
(20260316: 20211 trades, 20260317: 20992 trades, 20260318: 21635 trades, 20260319: 24319 trades,
20260320: 21876 trades) all producing win rates in the 32-36% range. In this near-random
signal environment, more aggressive spread filtering is expected to be more effective: a
1.1x threshold fires on a larger fraction of signals, increasing skip rate and selective
removal of adverse entries.

**Why it survives costs**: Zero-slippage fill model means there is no cost to skipping
(no slippage on skipped trades). The only cost is reduced participation -- but since the
oracle win rate is only ~33-37% on high-trade-count days, skipping more trades (even
somewhat indiscriminately) is expected to improve net P&L as long as the spread signal
is even slightly correlated with adverse fills.

**Builds on**: streak-spread-skip (PASS, +19.85% vs baseline on 3 train dates).
ONE targeted change: spread_multiplier 1.3 -> 1.1. All other parameters identical.

**Alternatives considered**:
- AND composite (streak AND spread) -- would lower skip rate, reducing its power on high-
  volume low-win-rate days where we need more filtering
- streak_lookback=3 -- would reduce streak trigger sensitivity; not helpful on high-volume days
- time-of-day gating -- would require EDA on raw data; complex for a single targeted change

---

## Implementation Decisions

Identical to streak-spread-skip except `spread_multiplier` is set to 1.1 (down from 1.3).

The streak_lookback=2, spread_window=60, min_spread_window=10 defaults are unchanged.

Force-submit after skip (_position_flat re-entry guarantee) is retained to prevent cascade.

**Concerns**: The tighter 1.1x threshold may over-filter on the early high-win-rate dates
(20260308-11, wr=46-49%) where the spread signal is weaker, potentially hurting those days.
If the net effect on the full 12-date window is negative, the threshold is too tight.

---

## Backtest Observations

**What drove improvement**: The tighter 1.1x spread threshold fires on ~19.7% of signals
(vs ~17.5% for streak-spread-skip at 1.3x on 3 dates). The most dramatic gains came from
days that were net negative for the baseline: 20260312 (-13 -> +364.75), 20260313
(-327.75 -> +112.25), 20260316 (-355 -> +39.25), 20260319 (+284.75 -> +630.75). On days
with many trades and low win rates (~32-38%), the spread filter successfully identifies
and skips a meaningful fraction of losing signals, converting loss-making days to
profitable or near-breakeven.

**Full 12-date aggregate**:
- streak-spread-tight: $4772.0 / 106,428 trades / win_rate=37.1% / sharpe=2.76
- baseline (simple): $1984.0 / 132,536 trades / win_rate=35.6% / sharpe=0.91
- vs_baseline_pnl_pct = +140.52% (well above the +5.0% pass gate)
- vs_baseline_slippage_pct = 0.0 (neutral -- zero fill-cost model)
- win_rate delta = +1.5pp
- max_drawdown = -1.41% (improved vs baseline -3.77%)
- Skip rate: 19.7% (26,108 fewer trades)

**What underperformed**: Win rate improvement (+1.5pp) is modest relative to PnL gain.
This suggests the filter skips trades more by volume (many small losers on high-activity
days) than by discriminating high-loss signals from high-win signals.

**Hypothesis verdict**: Supported. The tighter 1.1x threshold outperforms the 1.3x
threshold on the full 12-date window, particularly on high-volume days with low baseline
win rates. Consistent improvement across ALL 12 dates.

**Caveat**: The +140.52% improvement is large compared to the prior PASS results
(+14.61%, +19.85%), partly because those prior results only covered 3 of 12 dates (the
early, higher-win-rate dates). The current result is measured on the full authorized
train window against the same baseline. No cherry-picking -- all 12 dates included.

**Suggested next attempt**: (1) Tune spread_multiplier on a validation subset to find
the precise optimal (perhaps 1.0x or 1.15x); (2) Combine spread filter with a volume
filter (skip on high-volume ticks that may overwhelm the oracle's 30s edge); (3) Try
AND condition (streak AND spread) with 1.1x threshold to see if precision improves.
