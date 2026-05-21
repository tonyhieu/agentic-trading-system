# Algorithm Notes: streak-spread-tighter

## Hypothesis

**Mechanism**: Bid-ask spread conditioned skip with spread_multiplier=1.0 — skip the open
leg of an oracle signal when current spread >= rolling-median spread (not just > 1.1x median).
Streak condition (skip when last 2 consecutive estimated PnL both negative) is retained unchanged.
Combined OR condition preserved: skip when EITHER spread >= median OR 2-loss streak.

**Inefficiency exploited**: streak-spread-tight (PASS, +140.52% vs baseline) uses spread_multiplier=1.1,
meaning it only skips when spread is more than 10% above the rolling median. On high-trade-count
dates (20260316: 16,246 trades, wr=34.79%; 20260317: 16,679 trades, wr=33.34%), there are many
adverse entries at or near the typical spread. Setting spread_multiplier=1.0 fires whenever spread
is at or above median — roughly 50% of ticks — filtering out a larger fraction of adverse entries
on these high-volume, low-win-rate days. The oracle win rate on these days is near random (33-35%),
so removing more entries is expected to improve net P&L as long as the removed entries are not
systematically from the winning half.

**Why it survives costs**: Zero-slippage fill model means no fill cost on skipped trades. The only
cost is reduced participation. Since oracle win rate is only ~33-37% on high-volume days, skipping
~50% of ticks (instead of ~19.7%) should remove a larger proportion of losers when the oracle
signal is near-random in the spread dimension.

**Builds on**: streak-spread-tight (PASS, +140.52% vs baseline on 12 train dates).
ONE targeted change: spread_multiplier 1.1 -> 1.0. All other parameters identical.

**Alternatives considered**:
- AND composite (streak AND spread with 1.1x) -- would reduce skip rate, reducing filtering power
  on high-volume low-win-rate days where aggressive filtering is needed
- streak_lookback=3 -- requires 3 consecutive losses; reduces streak trigger sensitivity
- time-of-day gating -- would require EDA; too complex for single targeted change
- spread_multiplier=0.9 (skip when spread < 90% of median, i.e., below-median) -- inverts the
  logic; not supported by the hypothesis (we want to skip high-spread moments, not low-spread)

---

## Implementation Decisions

Identical to streak-spread-tight except `spread_multiplier` is set to 1.0 (down from 1.1).

The spread_window=60, min_spread_window=10 defaults are unchanged. streak_lookback=2 unchanged.

The _position_flat re-entry guarantee is retained unchanged to prevent cascade.

With spread_multiplier=1.0, the spread trigger fires when spread > 1.0 * median, i.e., strictly
greater than the current rolling median. This means ticks exactly at the median do not trigger
(strict inequality preserved from the original implementation). Approximately 50% of ticks
should trigger on any day where spread has a symmetric distribution around the median.

**Concerns**: Risk of over-filtering on early dates (20260308-11) with higher win rates (48-54%).
Those dates have 272-2,351 trades and already perform well. The additional filtering may reduce
participation on profitable trades there. However, the aggregate effect is likely still positive
because those early dates contribute a small fraction of total trades (~4,500 of 106,428 total).

---

## Backtest Observations

**What drove improvement**: NONE — the algorithm performs catastrophically worse than both
the baseline and the prior passing algorithm (streak-spread-tight).

**Full aggregate (9 of 12 dates — 3 largest dates timed out at 180s subprocess limit)**:
- streak-spread-tighter: $-4,666.25 / 58,045 trades / win_rate=32.84% / sharpe=-25.62
- baseline (simple): $+1,120.25 / 64,706 trades / win_rate=35.75% / sharpe=+4.76
- vs_baseline_pnl_pct = -516.54% (threshold: must be ≥ +5%; FAIL by extreme margin)
- 3 dates timed out (20260318, 20260319, 20260320) — too slow under 180s subprocess limit

Note: the 3 timed-out dates are the LARGEST dates (20K+ oracle signals each). If included,
the aggregate would be even worse.

**What underperformed**: Everything. The spread_multiplier=1.0 fires on ~50% of oracle
ticks (whenever spread > rolling median). The _position_flat forced-re-entry mechanism
(designed to prevent cascade skipping) then submits the immediately following order
regardless of spread level. Since spread autocorrelates at 1-second timescale, this
creates a systematic pattern: skip high-spread tick → force-submit next tick (also
potentially high-spread) → check spread → skip → force-submit... The net result is
a chaotic alternating pattern that:
  (a) removes ~50% of oracle signals (hurting P&L by reducing participation)
  (b) submits at arguably-wrong moments (post-skip forced entries at still-elevated spread)
  (c) significantly reduces win rate (32.84% vs 35.75% for baseline)
  (d) causes extreme performance degradation on ALL dates tested

Additionally, the algorithm is too SLOW: the 3 largest dates (20260318: 21K signals,
20260319: 24K signals, 20260320: 22K signals) exceeded the 180s subprocess timeout.
This suggests the algorithm's per-order processing is O(n) due to the rolling median
computation (statistics.median on a deque of 60 elements), which becomes expensive
at 20K+ events with 1-second signal intervals.

**Hypothesis verdict**: REFUTED. The hypothesis that spread_multiplier=1.0 would
improve on streak-spread-tight (1.1x) by more aggressively filtering adverse entries
is decisively wrong. The _position_flat forced-re-entry mechanism becomes destructive
at 50% skip rates: it submits orders immediately after high-spread skips, defeating
the spread filter entirely. The filter is effective only at low skip rates (<20%)
where forced re-entries are infrequent.

**Suggested next attempt**: 
(1) Keep spread_multiplier=1.1 (the proven PASS value), but instead of simple OR logic,
    try a DELAY mechanism: rather than skipping entirely, defer the open order by
    waiting until spread falls back below 1.1x median (checking on each subsequent tick).
    This avoids the forced-re-entry problem while still avoiding high-spread executions.
(2) Alternatively, try an ENTIRELY DIFFERENT approach: look at the time-of-day dimension.
    The streak-spread-tight NOTES suggested examining whether the first portion of the
    session has different win rate characteristics. A time filter that avoids the first
    N minutes of session (when spreads are typically wider) might improve precision
    without the forced-re-entry problem.
(3) Return to streak-spread-tight and try streak_lookback=3 (3 consecutive losses) 
    to reduce false-positive skips on the early, higher-win-rate dates.

