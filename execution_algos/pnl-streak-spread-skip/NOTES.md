# Algorithm Notes: pnl-streak-spread-skip

## Hypothesis

**Mechanism**: Skip the OPEN leg of an oracle signal when EITHER (a) the last
TWO consecutive closed positions BOTH had negative PnL (any amount < 0 USD),
forming a consecutive-loss streak, OR (b) the current bid-ask spread exceeds
1.5x the rolling 60-tick median spread. The OR combination and forced re-entry
guarantee from `pnl-spread-skip` are preserved. Reduce-only orders always
execute.

**Inefficiency exploited**: `pnl-spread-skip` (PASS, +15.96%) uses a single-trade
PnL threshold of -$3 (12-tick adverse move) to trigger skips. The -$3 threshold
fires on only ~2.6% of all trades (the tail of the loss distribution). This
iteration tests whether a **consecutive-loss streak** (2 back-to-back losses of
any magnitude) is a stronger or more frequent regime signal.

Rationale for the streak approach:
- In a near-random oracle (sigma=5, ~49% win rate), a single loss is uninformative:
  P(random loss) ≈ 51%, so individual losses occur nearly every other trade.
- Two consecutive losses are more informative: P(2 consecutive random losses) ≈ 26%,
  but if losses are serially correlated (adverse regime persists), actual
  P(loss | prev loss) > 51%.
- The PnL signal in pnl-regime-skip/pnl-spread-skip demonstrated serial correlation
  exists at the -$3 level. The streak approach captures the same correlation at
  ALL loss magnitudes, not just large ones.
- The streak is threshold-free for the PnL component — no in-sample parameter
  fitting for that signal, unlike the -$3 threshold.

The spread condition is unchanged (1.5x rolling 60-tick median) as it was the
second key signal in the parent.

**Why it survives costs**: Zero-commission, zero-slippage fill model. The edge
depends on the serial correlation of losses being strong enough to survive the
increase in skip rate (streak fires more frequently than -$3 threshold). If the
streak condition fires on ~10-15% of opportunities but with sufficient precision,
the net PnL impact is positive. If it over-triggers (low precision), P&L will
regress — this is the key hypothesis test.

**Builds on**: `pnl-spread-skip` (PASS, +15.96%) — replacing the single-trade
PnL threshold (-$3) with a consecutive-2-loss streak condition. One targeted
change vs parent: PnL trigger logic. Spread condition (1.5x, window=60) unchanged.

**Alternatives considered**:
1. Lower single-trade threshold (-$1.50): fires on 14% of trades — too aggressive,
   likely over-filters winners. Not chosen.
2. Rolling N-trade sum (N=5): requires tracking multiple fills, harder to implement
   robustly with Nautilus quote-tick estimation. Not chosen.
3. Threshold at -$2.00 (intermediate): moderate calibration, but still an in-sample
   parameter choice. Not chosen (streak is more principled).
4. Time-of-day filter: EDA showed skip gains are distributed across all hours
   (not concentrated in specific UTC windows), so time-of-day gating would
   require removing gains from off-hours. Not chosen for this iteration.

---

## Implementation Decisions

- **Streak tracking**: maintain `_prev_pnl_1` (most recent) and `_prev_pnl_2`
  (second most recent) estimated trade PnL. Both are estimated via quote-tick
  prices at open-order decision time, identical to the parent's estimation method.
- **Streak trigger**: fires when both `_prev_pnl_1 < 0` AND `_prev_pnl_2 < 0`.
  Threshold-free for the streak — any negative PnL counts.
- **Forced re-entry**: `_position_flat` flag preserved. After any skip, the next
  OPEN order is always submitted. When that position closes, it updates `_prev_pnl_1`
  and the prior `_prev_pnl_1` shifts to `_prev_pnl_2`.
- **Spread condition**: identical to parent (1.5x, window=60, warm-up=10).
- **State initialization**: on first open, `_prev_pnl_1` and `_prev_pnl_2` are
  both None — submit immediately. After first close, `_prev_pnl_1` is set, but
  `_prev_pnl_2` is still None — still submit (need 2 prior trades for streak).
  Skip only armed after 2 completed trades.
- **After a skip**: `_prev_pnl_1` and `_prev_pnl_2` are NOT updated (no trade
  completed). The forced re-entry clears `_position_flat`, and the next actual
  close shifts PnL history.

**Concerns**:
- Higher skip rate than parent: if P(streak) ≈ 25% and spread adds another ~5%,
  total skip rate may reach 20-30%. If too many winners are skipped, P&L regresses.
- The streak condition fires on micro-losses (e.g., $-0.25 followed by $-0.25),
  which may not signal real regime persistence — just random noise from the
  near-coin-flip oracle.
- No look-ahead bias: all estimation uses quote prices available at on_order()
  decision time, not future prices.

---

## Backtest Observations

**Results (train window, all 3 dates):**

| Date | Algo PnL | Algo Trades | Baseline PnL | Baseline Trades | Delta PnL % |
|------|----------|-------------|--------------|-----------------|-------------|
| 20260308 | $162.00 | 285 | $140.50 | 351 | +15.30% |
| 20260309 | $1068.75 | 2410 | $867.75 | 2863 | +23.16% |
| 20260310 | $679.50 | 1901 | $578.50 | 2308 | +17.46% |
| **Total** | **$1910.25** | **4596** | **$1586.75** | **5522** | **+20.39%** |

Mean slippage: 0.0 for both (neutral). STATUS: PASS (gate: +5.0%).

**Win rates by date**: 20260308 52.28%, 20260309 51.29%, 20260310 50.34%.
Baseline win rates: 20260308 46.72%, 20260309 47.89%, 20260310 49.09%.
Win rate delta aggregate: +2.64 pp (50.96% vs 48.32%).

**Mean Sharpe**: algo 127.50, baseline 99.78. Sharpe delta +27.72.
**Max drawdown** (per-date): algo -0.0014%, -0.0028%, -0.0019% — baseline -0.0024%, -0.0043%, -0.0028%.
All drawdowns improved.

**Trades skipped**: 66, 453, 407 across dates (4.4%, 15.8%, 17.6% of baseline trades).
Total skips: 926 (vs 226 for parent pnl-spread-skip, ~4.1%).

**Comparison vs parent (pnl-spread-skip, current leader):**
- Parent PnL: $1840.00 / 5296 trades (+15.96% vs baseline)
- This algo: $1910.25 / 4596 trades (+20.39% vs baseline)
- Delta vs parent: +3.82% PnL (refinement target: +2.0% — EXCEEDED)
- Sharpe delta vs parent: +9.85 (refinement target: +0.10 — EXCEEDED)
- Win rate delta vs parent: +1.51 pp (target: +2.0 pp — slightly below, but both PnL and Sharpe targets exceeded)

**What drove improvement**: The consecutive-2-loss streak signal fires much more
frequently than the parent's single-trade -$3 threshold (~17% average skip rate
vs ~4% for parent). The streak captures SMALLER losses that the parent's -$3
threshold misses, and these small-loss pairs turn out to be regime-predictive.
Per-date performance is uniformly better (20260308 +15.30%, 20260309 +23.16%,
20260310 +17.46%), suggesting the signal is robust across session types.

**What underperformed**: The higher skip rate (926 vs 226 in parent) increases
the risk of overfitting to the training window. The streak signal fires on any
two consecutive negative PnL estimates, which may be more sensitive to the
Nautilus fill-model specifics (zero-slippage fills, exact price rounding)
than the -$3 threshold. OOS generalization is uncertain.

**Hypothesis verdict**: CONFIRMED — the consecutive-2-loss streak signal is a
stronger regime indicator than the single large-loss (-$3) threshold in the
parent. The signal captures serial correlation at smaller loss magnitudes.
However, the substantially higher skip rate warrants caution about OOS
generalization.

**CAVEAT**: Two sources of in-sample fitting: (1) the spread threshold (1.5x,
inherited from parent), (2) the streak concept itself was validated on the same
3 training dates. The higher skip rate (17% vs 4% in parent) amplifies any
overfitting effect. The OOS Lambda result will be the true test.

**RESULT WARNING**: Very high Sharpe values (89-167 per date) are artifacts of
the zero-slippage fill model. Only P&L and win rate deltas are meaningful.

**Suggested next attempt**: (1) Test 3-consecutive-loss streak (even higher
precision but lower skip rate). (2) Validate streak threshold with magnitude
filter (both losses < -$0.50) to reduce noise from micro-losses near $0.
(3) Explore time-of-day gating of the streak signal: the EDA analysis showed
hours 13-19 UTC contribute most of the skip-related gains; restricting streak
skips to US hours might improve precision.
