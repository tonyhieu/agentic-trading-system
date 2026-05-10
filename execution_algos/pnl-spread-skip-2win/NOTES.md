# Algorithm Notes: pnl-spread-skip-2win

## Hypothesis

**Mechanism**: After an OR trigger fires (post-loss PnL <= -3.0 USD OR current
spread > 1.5x rolling median), skip the next 2 consecutive OPEN orders before
re-entering. The parent `pnl-spread-skip` skips only 1 open after each trigger.
This variant tests whether extending the skip window to 2 opens captures more of
the adverse regime that follows the triggering event.

**Inefficiency exploited**: The parent algorithm (`pnl-spread-skip`, PASS +15.96%)
demonstrated that adverse regimes persist at least one oracle period (1 second)
after the triggering event. The remaining question is whether the adverse
regime persists for TWO oracle cycles. If the oracle's noise component clusters
in multi-signal bursts, skipping 2 opens instead of 1 would avoid more losing
trades without over-filtering. The oracle operates on a 1-second cadence; the
spread and loss regime signals are slow-moving relative to tick data — 2 seconds
of skip may still be well within the persistence window.

**Why it survives costs**: Zero-commission, zero-slippage fill model. Edge comes
entirely from selective non-execution of expected-losing trades. With the parent's
+15.96%, the skip rate was ~4.1% (226 fewer trades vs 5522 baseline). A 2-skip
window could raise the effective skip rate to ~8%. The question is whether the
additional skipped trades are net-negative in expectation. Given the parent's
win rate improvement (+1.14 pp), the skipped trades were net-negative. If the
adverse regime persists 2 cycles, the second skip should also be net-negative.

**Builds on**: `pnl-spread-skip` (PASS, +15.96% vs baseline, +9.75% vs
`pnl-regime-skip`). One targeted change: extend skip window from 1 to 2
consecutive opens after each trigger event.

**Alternatives considered**:
1. 3-skip window: too aggressive — may over-filter and skip too many winners
   in a near-50% win-rate environment.
2. Time-of-day filter: orthogonal approach; suggested but not the parent's
   primary weakness.
3. Cross-validate the spread threshold (2.0x): a separate one-parameter change
   targeting false positive reduction rather than regime persistence.
4. Keep 1-skip window but lower the PnL threshold (e.g., -5.0 USD): fewer
   triggers, different trade-off vs the 2-skip approach.

---

## Implementation Decisions

Replace the `_position_flat: bool` flag (1-skip counter) in the parent with
`_skips_remaining: int`. After each trigger event, set `_skips_remaining = 2`
(skip the next 2 opens). On each open order call, if `_skips_remaining > 0`,
skip and decrement. If `_skips_remaining == 0`, proceed normally. After a
trigger fires during an active skip window (skips_remaining > 0), we do NOT
reset to 2 — we let the countdown continue (consecutive triggers don't stack).
This prevents indefinite suppression.

- **PnL threshold**: -3.0 USD (same as parent, from config.yaml or default).
- **Spread multiplier**: 1.5x median (same as parent).
- **Spread window**: 60 ticks (same as parent).
- **Skip window**: 2 consecutive opens after any trigger.
- **First open**: always submitted (no prior data).

**Cascade prevention**: The counter-based approach is cleaner than the boolean
flag for the 2-skip case: `_skips_remaining` counts down from 2 to 0 over the
next two open orders. The counter replaces the `_position_flat` bool but
serves the same cascade-prevention purpose (re-entry is guaranteed after
at most 2 skips).

**Concerns**:
- Increasing the skip rate from ~4.1% to ~8% in a near-50% win-rate oracle
  environment risks skipping more winners than losers in the second window.
  The data will clarify.
- Both thresholds (-3.0 and 1.5x) are inherited from in-sample analysis.
  The 2-skip window is an additional in-sample choice. Overfitting risk
  increases with each parameter. OOS will be the true test.
- No look-ahead bias: skip decision at open-order time uses only the current
  quote tick (contemporaneous) and the history of submitted orders — no
  future information used.

---

## Backtest Observations

**Results (train window, all 3 dates):**

| Date | Algo PnL | Algo Trades | Baseline PnL | Baseline Trades | Delta PnL % |
|------|----------|-------------|--------------|-----------------|-------------|
| 20260308 | $31.50 | 4 | $140.50 | 351 | -77.58% |
| 20260309 | $48.25 | 394 | $867.75 | 2863 | -94.44% |
| 20260310 | $178.25 | 763 | $578.50 | 2308 | -69.19% |
| **Total** | **$258.00** | **1161** | **$1586.75** | **5522** | **-83.74%** |

Mean slippage: 0.0 for both (neutral). STATUS: FAIL.

**What drove the failure**: The 2-skip window caused catastrophic over-filtering.
The algo executed only 1161 trades vs 5522 baseline — a 79% skip rate vs the parent's
4.1% skip rate. On 20260308, only 4 trades were executed vs 351 baseline.

**Root cause — cascade suppression**: The parent algorithm (`pnl-spread-skip`) has
a critical re-entry safety mechanism: after any skip, `_position_flat = True` forces
the NEXT open to submit unconditionally, regardless of both signals. This prevents
cascade by guaranteeing re-entry one period after each skip.

In the 2-win implementation, after the triggered skip, `_skips_remaining = 1` causes
the next open to also skip (decrement to 0). The order after that runs full evaluation
with NO forced re-entry. With the spread or PnL signals re-firing immediately (because
the conditions that triggered the first skip persist), a new 2-skip window arms
immediately. This creates a near-permanent suppression: the algo almost never submits
because every time it recovers to `_skips_remaining = 0`, a fresh trigger fires.

**Win rate degradation**: 45.74% vs 48.32% baseline (-2.58 pp). With 79% of trades
skipped, the remaining submitted trades are not preferentially better — they are the
rare intervals when neither signal fires, which are not systematically winners.

**Hypothesis verdict**: CONTRADICTED. The 2-skip window does not capture regime
persistence — it creates a cascade suppression loop. The parent's forced re-entry
mechanism after 1 skip was not incidental; it is essential to preventing cascade.
Any multi-skip extension must include a forced re-entry guarantee after the skip
window expires.

**What underperformed**: Everything — PnL, trade count, win rate all worse.

**Suggested next attempt**:
1. Add a forced re-entry after the 2-skip window: after `_skips_remaining` decrements
   to 0, set `_position_flat = True` for the NEXT open (same as parent's guarantee).
   This fixes the cascade. Worth retesting with this correction.
2. Alternatively, investigate time-of-day filtering on the parent — a completely
   different angle that does not risk cascade.
3. The parent `pnl-spread-skip` at +15.96% remains the benchmark; any extension
   must not break its cascade prevention.
