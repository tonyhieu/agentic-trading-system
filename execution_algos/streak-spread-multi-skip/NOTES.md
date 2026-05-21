# Algorithm Notes: streak-spread-multi-skip

## Hypothesis

**Mechanism**: Building on `streak-spread-tight` (PASS, +140.52% vs baseline on 12 train dates).
ONE targeted change: replace the hard "forced re-entry after exactly 1 skip" guarantee with
"forced re-entry after at most max_consecutive_skips=3 consecutive skips."

In `streak-spread-tight`, whenever an open order is skipped (streak OR spread trigger),
`_position_flat` is set to True, causing the VERY NEXT open order to always be submitted
regardless of conditions. The key weakness identified in the `streak-spread-tighter` failure
analysis: "forced re-entries often fire at still-elevated spread, defeating the filter entirely."
Spread is autocorrelated at the 1-second signal cadence (oracle signal_interval_seconds=1.0),
meaning the tick immediately after a skip often has the same elevated spread that caused the
skip. The forced re-entry at that point enters adversely.

This algorithm allows the filter to continue blocking up to `max_consecutive_skips=3`
consecutive open orders before forcing re-entry. After 3 consecutive skips, the next open is
always submitted (preserving the anti-cascade guarantee). This avoids the immediate-post-skip
adverse entry while still guaranteeing eventual participation.

**Inefficiency exploited**: The forced re-entry after 1 skip enters adversely when spread
autocorrelates — i.e., when the spread was elevated at tick T (causing a skip), it is often
still elevated at tick T+1 (the forced re-entry). Allowing 2-3 skips lets the autocorrelation
decay before re-entering, improving entry quality on high-activity days where spread
autocorrelation is strong and the forced-re-entry mechanism would otherwise fire into the same
adverse condition.

**Why it survives costs**: Zero-slippage fill model means the cost of skipping additional
trades is zero direct cost. The benefit of avoiding adverse forced re-entries should improve
win rate on days where spread autocorrelation is high. The max_consecutive_skips=3 cap
prevents cascade and ensures intraday_flat compliance by guaranteeing eventual participation.

**Builds on**: `streak-spread-tight` (PASS, +140.52% vs baseline). ONE targeted change:
`max_consecutive_skips` from 1 (implicit) to 3 (explicit). All other parameters unchanged:
spread_multiplier=1.1, spread_window=60, min_spread_window=10, streak_lookback=2.

**Alternatives considered**:
- AND condition (skip only when BOTH streak AND spread trigger) — reduces skip rate, less
  effective on high-volume low-win-rate days; suggested by NOTES.md but expected to be
  weaker than fixing the re-entry logic
- Longer spread_window=120 — would smooth out autocorrelation but adds latency to signal;
  more complex change
- Time-of-day gate — interesting but requires EDA on raw data; too many changes at once
- max_consecutive_skips=2 (vs 3) — 3 chosen to give autocorrelation sufficient time to
  decay at 1s signal cadence (3 signals = 3 seconds, roughly matches spread mean-reversion
  horizon at HF); could be tuned in a future refinement

---

## Implementation Decisions

Identical to `streak-spread-tight` except:
- Added `max_consecutive_skips: int = 3` config parameter
- `_position_flat` (bool) replaced by `_consecutive_skips: int` counter
- Force re-entry when `_consecutive_skips >= max_consecutive_skips`
- After submitting any order (initial, forced re-entry, or normal), reset counter to 0

The streak-tracking logic (`_streak_triggered`) is preserved exactly. The spread logic
(`_spread_triggered`) is preserved exactly. The `_record_open` bookkeeping is preserved exactly.

No order quantity is ever modified. Quantity invariant always preserved.

**Concerns**: If spread autocorrelation is weaker than expected on some dates, allowing 3
skips instead of 1 will hurt participation rate without improving entry quality — net negative
on those dates. The 3-skip cap prevents full cascade but a sustained elevated-spread regime
could cause 33% reduction in trades. However, the baseline shows negative PnL on most
high-volume days anyway, so reduced participation on adverse days is generally beneficial.

No look-ahead bias: all decisions use only the current quote (top-of-book, observable at
decision time) and historical PnL estimates from prior fills.

---

## Backtest Observations

**What drove the regression**: Catastrophic across all 11 completed dates (20260319 timed
out at 180s subprocess limit; same as streak-spread-tighter). Every date is negative vs
baseline, and negative vs streak-spread-tight.

Full 11-date aggregate (20260319 excluded due to timeout):
- streak-spread-multi-skip: $-3,937.50 / 77,578 trades / win_rate=33.4% / sharpe=-26.99
- baseline (simple, 11 dates): $1,699.25 / 108,217 trades / win_rate=35.6%
- vs_baseline_pnl_pct = -331.72% (far below +5.0% pass gate)
- Win rate regressed on ALL dates: multi-skip produces 30-42% vs baseline 32-49%

Per-date comparison (multi-skip vs streak-spread-tight):
- 20260308: -38.75 vs +181.00 (regression -219.75)
- 20260309: -418.00 vs +1112.50 (regression -1530.50)
- 20260310: -304.25 vs +706.00 (regression -1010.25)
- 20260311: -374.75 vs +520.50 (regression -895.25)
- 20260312: -488.25 vs +364.75 (regression -853.00)
- 20260313: -690.00 vs +112.25 (regression -802.25)
- 20260315: -63.25 vs +20.50 (regression -83.75)
- 20260316: -657.50 vs +39.25 (regression -696.75)
- 20260317: -419.50 vs +61.75 (regression -481.25)
- 20260318: -238.75 vs +449.25 (regression -688.00)
- 20260320: -244.50 vs +573.50 (regression -818.00)

**Root cause analysis**: The multi-skip introduces a cascade failure through the
`_streak_triggered()` side effect. When the algorithm skips orders 1, 2, 3 consecutively,
`_streak_triggered()` is called on EACH of those skipped orders, updating `_prev_pnl_1`
and `_prev_pnl_2` each time using the CURRENT quote as a pseudo-close price for the
last real position. This over-samples the same real position 3 times, creating artificial
streak patterns that persist even after the actual market condition changes. The result:
more skipping on GOOD days (20260308-20260311 with 47-54% baseline win rates), and no
improvement on bad days (the forced re-entries still occur into elevated-spread conditions).

Additionally, the trade count reduction is more severe than expected: 77K vs 106K for
streak-spread-tight (-26.7%), on only 11 dates. This confirms the algorithm is skipping
too aggressively due to the streak tracker corruption.

**What underperformed**: Everything — all dates, all metrics. Unlike streak-spread-tighter
(which was bad only because of 1.0x threshold), multi-skip is bad because it corrupts the
streak state through repeated side-effect calls during consecutive skips.

**Hypothesis verdict**: Rejected. The multi-skip idea was flawed because `_streak_triggered()`
has a side effect (updating PnL history) that was called on every skip evaluation. Allowing
3 consecutive skips means the streak history is updated 3x from the same position, creating
artificial streak persistence that causes over-filtering on good days.

**Fix required for this approach**: The `_streak_triggered()` side effect must be separated
from the evaluation logic — update PnL history ONLY when an order is actually submitted
(in `_record_open`), not during skip evaluations. Without this fix, multi-skip is worse
than streak-spread-tight.

**Suggested next attempt**: (1) Try the multi-skip concept with the streak state update
ONLY in `_record_open` (not in `_streak_triggered`). This would be a pure re-entry logic
change without the state corruption. (2) Alternatively, explore a completely different
direction: the book imbalance signal (BookImbalance__Lipton.md) as a timing filter for
child order submission — skip when imbalance is unfavorable rather than using spread.
(3) The 20260319/20260320 timeout issue suggests these large dates (21K-24K trades)
need algorithmic efficiency attention; the `statistics.median()` call on a 60-element
deque per tick may be bottlenecking.

