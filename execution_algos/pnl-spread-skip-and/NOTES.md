# Algorithm Notes: pnl-spread-skip-and

## Hypothesis

**Mechanism**: Skip the OPEN leg of an oracle signal when BOTH (a) the
immediately preceding closed position suffered a per-trade realized P&L <=
-3.0 USD (12+ tick adverse move), AND (b) the current bid-ask spread exceeds
1.5x the rolling 60-tick median spread. The AND combination requires both
signals to fire simultaneously — a stricter, higher-precision skip criterion
vs the OR variant.

**Inefficiency exploited**: In `pnl-spread-skip` (PASS +15.96%), the OR
combination fires on ~226 trades (4.1% of the 5522 baseline trades). Some
of these skipped trades are winners (the oracle at sigma=5 has ~48% win rate,
so roughly 109 of 226 skipped trades might have been winners). The AND filter
targets only the intersection — ticks where both regime persistence (recent
bad P&L) and contemporaneous market uncertainty (wide spread) coincide. At
this intersection, adverse selection is highest and the oracle signal is least
reliable. Skipping fewer but more precisely identified trades should preserve
more of the skip gain while reducing false-positive skips (skipped winners).

**Why it survives costs**: Zero-slippage fill model (as noted in
research/NOTES.md). All improvement must come from P&L delta. With fewer skips,
the AND filter reduces the risk of removing profitable oracle signals. The AND
criterion is harder to satisfy — both bad P&L AND wide spread must co-occur —
which requires genuine adverse conditions in both temporal and contemporaneous
dimensions simultaneously.

**Builds on**: `pnl-spread-skip` (PASS, +15.96% vs baseline). One targeted
change: flip the boolean combination from OR → AND. All thresholds remain
identical (pnl_skip_threshold=-3.0, spread_multiplier=1.5, spread_window=60).
No other parameters changed.

**Alternatives considered**:
- 2-skip window (skip for 2 consecutive opens after a loss): more aggressive
  but compounds the false-positive problem.
- AND with tighter thresholds: confounds the attribution — the OR vs AND
  comparison would be muddled.
- Threshold sensitivity sweep on the AND variant: correct as a future step
  only if AND shows improvement over OR.

---

## Implementation Decisions

The implementation is nearly identical to `pnl-spread-skip`. The only change
is the condition in `on_order()`:

```python
# OLD (OR):
if pnl_trigger or spread_trigger:

# NEW (AND):
if pnl_trigger and spread_trigger:
```

All other logic (cascade-prevention _position_flat flag, quote-tick-based PnL
estimation, reduce-only always submits, spread warm-up guard) is preserved
identically. The _position_flat flag still applies after any AND-triggered skip,
which forces re-entry on the following open order to prevent cascade.

**Concerns**: 
- The AND criterion may fire rarely (possibly 0-10 times per date), making
  the result statistically fragile. If skip count drops below ~5 total across
  the 3 training dates, flag as RESULT WARNING.
- If AND skips no trades at all, the result equals the simple baseline —
  report that explicitly and log as FAIL (no improvement).
- In-sample threshold fitting risk is REDUCED vs OR variant: the AND
  intersection is harder to over-engineer because both conditions must co-occur
  on the same exact tick.

---

## Backtest Observations

**What drove improvement**: The AND combination still outperforms the simple
baseline (+2.79% P&L delta over 3 training dates), because on the 16 trades
where both signals fire simultaneously, the adverse regime is confirmed by two
independent indicators. These 16 skips happen to be mostly losing trades (net
P&L gain from skipping them is $44.25 = $1631.00 - $1586.75).

**What underperformed**: The AND combination fires on only 16 trades total
across 3 dates (vs 226 skips for the OR variant). With so few skips, the
P&L delta is +2.79% — far below both the 5.0% pass gate and the OR
variant's +15.96%. The AND criterion is too restrictive: the two signals
rarely co-occur at the same tick. The spread signal fires on wide-spread
ticks; the PnL signal fires immediately after a loss; these rarely
coincide at the exact same moment. The OR combination's wider net
captures genuinely orthogonal subsets of adverse trades.

**Hypothesis verdict**: CONTRADICTED. The prediction was that AND would
offer higher precision at the expense of recall, achieving similar or
better P&L with fewer skips. Instead, AND achieves only ~7% of the OR
variant's P&L improvement (+2.79% vs +15.96%) with ~7% of the skips
(16 vs 226). The precision is not meaningfully higher — both signals
co-occur so rarely that the AND gate is essentially not firing. The
result suggests the two signals are genuinely orthogonal in time (they
capture different moments), not co-occurring subsets of the same adverse
environment.

RESULT WARNING: Only 16 total skips across 3 dates (1 on 20260308, 11
on 20260309, 4 on 20260310). The observed +2.79% P&L improvement is
based on a very small number of skip decisions. Statistical confidence
is low — this could be noise.

Status: CLOSE (2.79% vs 5.0% gate; above the 2.0% close_margin_pct).
Does NOT meet refinement targets vs parent pnl-spread-skip (-13.17pp
P&L delta vs parent).

**Suggested next attempt**: Return to OR combination as the higher-performer.
Try a 2-skip window variant: after a triggering condition (PnL OR spread),
skip the next 2 consecutive open orders instead of just 1. This increases
the filter's impact without compounding the AND precision problem. However,
this is an aggressive change that risks over-skipping — implement with a
cascade guard allowing at most N consecutive skips. Alternatively, explore
a completely different axis: time-of-day filtering (avoid early/late session
oracle trades when the signal-to-noise ratio is lowest).
