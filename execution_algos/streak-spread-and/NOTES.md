# Algorithm Notes: streak-spread-and

## Hypothesis

**Mechanism**: Consecutive-loss streak AND spread-elevated conditioned skip.
The prior algorithm `streak-spread-tight` used an OR condition: skip when EITHER
(a) last 2 consecutive estimated PnLs are negative (streak), OR (b) current spread
> 1.1x rolling 60-tick median (spread). This iteration changes the OR to an AND:
skip only when BOTH conditions are simultaneously true.

**Inefficiency exploited**: The OR condition in `streak-spread-tight` fires on
~19.7% of signals (26,108 fewer trades). However, the spread-only trigger and
the streak-only trigger each fire in situations where only one adverse signal
is present. When the algorithm already achieved a 37.1% win rate (vs 35.6%
baseline), there may be room to retain more profitable trades by requiring
both signals to align before skipping. The AND condition is more conservative
(lower skip rate), targeting only the most adversarial regime: where historical
losses are piling up AND the spread is simultaneously elevated, indicating both
signal quality degradation and adverse fill conditions.

**Why it survives costs**: Zero-slippage fill model means every additional trade
has no incremental cost. The AND condition will skip fewer trades overall; the
question is whether those additional trades contribute positively or negatively
to PnL. If the spread alone and streak alone are each independent adverse signals,
the AND will sacrifice some filtering precision relative to OR. But if the two
signals are correlated (wide spread often accompanies choppy oracle regimes that
produce loss streaks), the AND selects a truly high-confidence adverse regime
and avoids false positives that needlessly reduce participation.

**Builds on**: streak-spread-tight (PASS, +140.52% vs baseline on full 12-date
train window). ONE targeted change: OR condition replaced with AND condition.
All other parameters identical: spread_multiplier=1.1, spread_window=60,
min_spread_window=10, streak_lookback=2.

**Alternatives considered**:
- Adjusting spread_multiplier (e.g., 1.0x or 1.15x) -- NOTES.md from
  streak-spread-tight suggests this, but fine-tuning a continuous parameter
  without EDA risks overfitting. The AND/OR logic change is more structural.
- Volume filter -- would require EDA on raw tick data; more complex for one
  targeted change.
- streak_lookback=3 -- would reduce streak sensitivity; not orthogonal to
  the AND change.

---

## Implementation Decisions

Identical to `streak-spread-tight` except the skip condition is AND (both must
be true) instead of OR (either triggers skip).

Key parameters (unchanged from streak-spread-tight):
- spread_multiplier=1.1
- spread_window=60
- min_spread_window=10
- streak_lookback=2
- _position_flat re-entry guarantee: after any skip, next open is forced-submitted

**Look-ahead bias analysis**: No look-ahead bias. The spread is computed from
the current top-of-book quote observable at order decision time. The streak is
computed from estimated PnL of prior closed positions, using historical entry
prices vs current quote -- all observable at decision time.

**Concerns**: The AND condition may under-filter relative to OR. If the two
signals are largely independent (spread alone is a strong filter, streak alone
is a strong filter), then requiring both simultaneously may reduce the total
skip rate enough that the algo loses much of its advantage over the baseline.
The test is whether the highly-selective AND skip targets a genuinely worse
subset of trades than either signal alone.

---

## Backtest Observations

**Train window**: 2026-03-08 to 2026-03-20 (12 trading dates; 2026-03-14 is Sunday, excluded).
**Baseline**: simple (TWAP-style, submits every order).
**Strategy**: oracle (sigma=5, seed=42, horizon=30s, signal_interval=1s).

**Aggregate results (12 dates)**:

| Metric              | AND (this algo) | Baseline (simple) | Delta     |
|---------------------|-----------------|-------------------|-----------|
| Realized PnL        | $3,007.00       | $1,984.00         | +51.56%   |
| Trade count         | 128,810         | 132,536           | -2.81%    |
| Mean Sharpe         | 1.568           | 0.766 (est.)      | --        |
| Max drawdown        | -2.68%          | -3.77% (est.)     | --        |
| Win rate (wtd avg)  | 35.96%          | 34.4% (est.)      | --        |
| IS weighted bps     | 0.068           | 0.037             | +81% (better IS) |
| Slippage            | 0.0             | 0.0               | 0.00%     |

**Status**: PASS (vs gate: min_pnl_improvement_pct=5.0; actual=+51.56%)

**Key observations**:

1. The AND condition produces a much lower skip rate than OR (streak-spread-tight). Whereas
   OR reduced trade count by ~19.7% vs baseline (~26k fewer trades), AND reduces it by only
   ~2.81% (~3.7k fewer trades). This confirms the hypothesis that AND targets a narrow,
   high-confidence adverse regime.

2. Despite the much smaller skip count, the AND algo still improves PnL by +51.56% over
   baseline ($3007 vs $1984). However, streak-spread-tight (OR) achieved +140.52% improvement
   ($4772 vs $1984). The OR condition is substantially more effective: wider filtering removes
   more losing trades.

3. The AND algo beats the baseline convincingly (>5% gate) but underperforms streak-spread-tight
   significantly ($3007 vs $4772). This suggests the individual signals (spread-only, streak-only)
   both have genuine filtering power independently, and requiring both simultaneously is overly
   restrictive in the other direction — it accepts too many adverse trades that either signal
   alone would have correctly excluded.

4. Win rate (35.96%) is modestly above the baseline level, confirming the AND filter has
   some selective power but much less than OR.

5. IS weighted bps is higher for AND (0.068) vs baseline (0.037). This occurs because the
   AND algo accepts orders in a wide variety of spread regimes (only skips when spread is
   high AND streak is bad simultaneously), including high-spread periods where IS bps is
   elevated. This is an artifact of fewer skips, not adverse selection improvement per se.

6. Per-day pattern: large-volume days (20260316-20260320, ~19k-24k trades/day) show the
   AND algo barely reduces trade count vs baseline (e.g., 19623 vs 20211 on 20260316), while
   low-volume days (20260308: 325 vs 351) also show small reductions. The AND rarely fires
   because both conditions must trigger simultaneously.

**Conclusion**: The OR (streak-spread-tight) is the superior filter. The AND condition is
too permissive. A natural next step is to explore variations on the OR threshold (e.g.,
tightening the spread_multiplier from 1.1x to 1.05x or the streak_lookback from 2 to 3),
or to try a weighted score combining both signals continuously rather than as discrete
binary conditions.
