# Algorithm Notes: pnl-spread-skip-2skip

## Hypothesis

**Mechanism**: Extend the skip window of `pnl-spread-skip` from 1 consecutive skip to 2 consecutive skips after an OR trigger fires (post-loss PnL <= -3.0 USD OR spread > 1.5x rolling median), while preserving the forced re-entry guarantee that prevents cascade suppression.

**Inefficiency exploited**: `pnl-spread-skip` (PASS +15.96%) skips only 1 order after a regime signal fires, then immediately re-arms. If the adverse regime (persistent oracle noise OR wide spread) lasts for 2 oracle cycles (~2 seconds), a 2-skip window would filter out 2 bad trades per trigger instead of 1, doubling the P&L benefit per skip event.

**Why it survives costs**: The forced re-entry guarantee (after exactly 2 skips, the next open is always submitted) prevents cascade suppression. The parent algorithm demonstrated +15.96% P&L improvement with only 4.1% skip rate (226 skips / 5522 trades). A 2-skip window with forced re-entry would at most double the skip rate to ~8%, still leaving 92%+ of trades executing. The key lesson from `pnl-spread-skip-2win` (FAIL -83.74%) is that forced re-entry is essential — dropping it caused 79% skip rate via cascade.

**Builds on**: `pnl-spread-skip` (PASS +15.96%). One targeted change vs parent: extend skip_window from 1 to 2 with correct cascade prevention.

**Alternatives considered**:
- Time-of-day filtering (orthogonal angle): rejected for this iteration to isolate the 2-skip hypothesis.
- AND combination: already tested as `pnl-spread-skip-and` (CLOSE +2.79%) — too few skip events.
- The failed `pnl-spread-skip-2win` dropped forced re-entry entirely, causing cascade. This iteration correctly preserves it.

---

## Implementation Decisions

**Forced re-entry mechanism**: Use a `_skips_remaining` counter (initialized to 0). When a trigger fires:
- If `_skips_remaining == 0` (normal state): set `_skips_remaining = 2`, skip current order.
- If `_skips_remaining > 0`: decrement, skip if still > 0 after decrement, else force re-entry.

Equivalently: `_skips_remaining` counts remaining skips. On trigger: set to 2. On each subsequent open order: if `_skips_remaining > 0`, decrement and skip; if `_skips_remaining == 0`, submit (forced re-entry). After forced re-entry, re-arm the trigger normally.

**Cascade prevention**: The `_position_flat` flag from parent is replaced by the `_skips_remaining` counter. When `_skips_remaining` reaches 0, the next open is forced through, preventing a new trigger from immediately re-arming. (Wait: we should NOT check for new triggers during forced re-entry. After the 2-skip window, submit unconditionally.)

**Edge case — first open of session**: Submit immediately, start tracking.

**Reduce-only orders**: Always submitted (intraday_flat compliance).

**Parameter inheritance**: Same thresholds as parent — pnl_skip_threshold=-3.0, spread_multiplier=1.5, spread_window=60. One change only: max_skips=2.

**Concerns**: In-sample trigger parameters inherited from parent (mild overfitting risk). If the adverse regime does NOT persist 2 oracle cycles, the 2-skip window will skip winners that would have recovered by the second cycle, potentially harming P&L.

---

## Backtest Observations

**What drove improvement**: The 2-skip window still beats the simple baseline by +11.42% ($1768.00 vs $1586.75, 5116 vs 5522 trades). The forced re-entry mechanism correctly prevents cascade — skip rate is ~7.3% (406 skips / 5522 trades vs parent's ~4.1%), and all 3 dates show positive delta vs baseline. Max drawdown improved vs simple on every date.

**What underperformed**: The 2-skip variant is WORSE than the 1-skip parent (`pnl-spread-skip`): $1768 vs $1840 (-$72), +11.42% vs +15.96% (-4.54pp). The extra skip in the 2-skip window removes winners that would have recovered between skip 1 and skip 2. Mean Sharpe 116.18 vs 117.65 (parent). The hypothesis that the adverse regime persists for 2 oracle cycles is NOT well-supported: the second skip hurts on net across all 3 training dates.

**Hypothesis verdict**: CONTRADICTED for the improvement hypothesis. The regime captured by the OR(pnl, spread) signal does NOT consistently persist for 2 oracle cycles. The parent's 1-skip design is optimal — skipping 1 order after a trigger, then forcing re-entry, captures the regime break point precisely. A 2nd skip overshoots and removes signal-quality-improved fills.

**Per-date**: 20260308 +5.34% ($148.00/321 vs $140.50/351), 20260309 +8.53% ($941.75/2660 vs $867.75/2863), 20260310 +17.24% ($678.25/2135 vs $578.50/2308). All positive, all PASS individually.

**vs parent pnl-spread-skip**: $1768 vs $1840 (-$72, -4.54pp). Refinement NOT successful by §6 targets (min_pnl_delta_pct=+2.0 requires improvement, not regression). Algorithm still PASS vs baseline gate.

**Suggested next attempt**: The 2-skip extension does not improve the parent. Two alternative refinements for a future iteration:
  (a) Time-of-day filtering as an orthogonal angle (skip during known low-quality windows early/late session).
  (b) Adaptive threshold: dynamically widen the PnL skip threshold (-3.0) during high-volatility regimes (e.g., spread > 2x median), keeping the spread threshold constant.
  The parent `pnl-spread-skip` at +15.96% is the current leader and its architecture (1-skip + forced re-entry + OR combination) appears optimal for the training window.
