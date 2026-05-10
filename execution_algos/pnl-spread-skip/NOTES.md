# Algorithm Notes: pnl-spread-skip

## Hypothesis

**Mechanism**: Skip the OPEN leg of an oracle signal when EITHER (a) the
immediately preceding closed position suffered a realized P&L <= -3.0 USD
(12+ tick adverse move), OR (b) the current bid-ask spread exceeds
1.5x the rolling 60-tick median spread. The two conditions are applied as
an OR: fire on either signal. Reduce-only (close) orders are always submitted.

**Inefficiency exploited**: `pnl-regime-skip` (the parent) exploits serial
persistence in oracle quality after a large adverse outcome — achieving +5.66%
vs baseline. `spread-filter` independently achieved +2.25% vs baseline by
skipping orders when the market microstructure signals elevated uncertainty.
The two signals are orthogonal in nature:
- PnL signal: backward-looking, captures temporal regime persistence in the
  oracle's error structure.
- Spread signal: contemporaneous, captures market-maker uncertainty at
  execution time, which is correlated with short-horizon adverse selection.

Combining them as an OR should raise the total skip rate on adverse trades
while maintaining selectivity — each signal independently catches a different
failure mode of the near-random (sigma=5) oracle.

**Why it survives costs**: Zero-commission, zero-slippage fill model. The
edge comes entirely from selectively not executing orders that, in expectation
(across both signals), tend to lose. Both signals had directionally positive
individual performance. The OR combination should yield a higher total
skip count with acceptable precision.

**Builds on**: `pnl-regime-skip` (PASS, +5.66%) — adding the spread condition
as a second skip trigger. `spread-filter` (FAIL, +2.25%) — borrowing the
spread threshold and rolling-window logic. One targeted change vs parent:
add the spread OR condition.

**Alternatives considered**:
1. AND combination (PnL AND spread): would have very low skip rate (events
   must co-occur), likely too rare to add value beyond single signal.
2. 2-skip window after loss (skip next 2 opens after loss): would increase
   skip rate via persistence but may over-filter and skip winners.
3. Tighter spread threshold (1.2x): higher skip rate but lower precision.
4. Pure spread-filter: already tested, only +2.25%.

---

## Implementation Decisions

The algorithm combines the PnL-regime logic from `pnl-regime-skip` with the
spread-filter logic from `spread-filter`:

- **PnL threshold**: -3.0 USD (12 ticks), same as parent. Read from
  config.yaml `execution_constraints.pnl_skip_threshold` or default.
- **Spread multiplier**: 1.5x median of rolling 60-tick spread window, same
  as `spread-filter`. Read from config.yaml or default.
- **Skip condition (OR)**: skip if prev_pnl <= -3.0 OR spread > 1.5x median.
- **Skip cascade prevention**: _position_flat flag (inherited from parent):
  if the last open was skipped, force re-entry on the next open regardless
  of both signals.
- **Reduce-only orders**: always submitted (intraday_flat compliance).

**P&L estimation**: identical to `pnl-regime-skip` — estimate via quote-tick
cache at open-order decision time, not via on_order_filled callbacks (avoids
Nautilus sequencing issues).

**Spread computation**: at each on_order() call, read the current quote tick
and compute spread = ask_price - bid_price. Append to a deque of length 60.
Skip if spread > 1.5 * median(deque) AND len(deque) >= 10 (warm-up guard).

**Concerns**:
- The OR combination may over-skip when both signals fire simultaneously
  on the same adverse event, potentially missing re-entry opportunities.
- The _position_flat re-entry guard was designed for single-skip; it still
  works for the OR combination since the guard fires on the next open after
  any skip event.
- Both thresholds (-3.0 and 1.5x) are inherited from in-sample analysis on
  the same training window. Dual in-sample fitting increases overfitting risk.
  Flag in research/NOTES.md.

---

## Backtest Observations

**Results (train window, all 3 dates):**

| Date | Algo PnL | Algo Trades | Baseline PnL | Baseline Trades | Delta PnL % |
|------|----------|-------------|--------------|-----------------|-------------|
| 20260308 | $147.75 | 333 | $140.50 | 351 | +5.16% |
| 20260309 | $1006.50 | 2762 | $867.75 | 2863 | +15.99% |
| 20260310 | $685.75 | 2201 | $578.50 | 2308 | +18.54% |
| **Total** | **$1840.00** | **5296** | **$1586.75** | **5522** | **+15.96%** |

Mean slippage: 0.0 for both (neutral). STATUS: PASS (gate: +5.0%).

**Win rates by date**: 20260308 48.35%, 20260309 49.13%, 20260310 50.02%.
Baseline win rates: 20260308 46.72%, 20260309 47.89%, 20260310 49.09%.
Win rate delta aggregate: +1.14 pp.

**Mean Sharpe**: algo 117.65, baseline 99.78. Sharpe delta +17.87.
**Max drawdown**: algo -0.3349%, baseline -0.4298% (drawdown improved).

**Comparison vs parent (pnl-regime-skip):**
- Parent PnL: $1676.50 / 5401 trades → algo $1840.00 / 5296 trades
- Delta vs parent: +9.75% (refinement target: +2.0% — EXCEEDED)
- Sharpe delta vs parent: +9.81 (refinement target: +0.10 — EXCEEDED)

**What drove improvement**: The OR combination adds ~105 additional skips
(5522 - 5296 = 226 fewer trades vs baseline; pnl-regime-skip had 121 fewer).
The spread trigger fires independently of the PnL trigger, catching wide-spread
adverse regimes that the PnL signal misses. The combination is synergistic:
spread anomalies identify market-uncertainty regimes that overlap with, but are
not identical to, post-large-loss regimes.

**What underperformed**: 20260308 shows only +5.16% — the Sunday evening short
session has fewer spread anomaly events (thin book, fewer wide-spread ticks), so
the spread trigger adds less value on that date. Still PASS on its own.

**Hypothesis verdict**: Confirmed. Adding the spread condition as an OR to the
PnL skip condition substantially improves over the parent algorithm. The synergy
supports the hypothesis that the two signals are orthogonal — they fire in
complementary regimes. The OR gate increases total skip rate from ~2.2% (parent)
to ~4.1% (this algo) while improving both PnL and win rate, indicating the
additional skipped trades are net-negative expected value.

**CAVEAT**: Both the PnL threshold (-3.0 USD) and the spread multiplier (1.5x)
were inherited from in-sample analysis on the same 3 training dates. Dual
in-sample parameter fitting increases overfitting risk vs the parent. The OOS
result on the held-out test window will be the true validation.

**RESULT WARNING**: The very high Sharpe ratios (85-146 per date) are an
artifact of the zero-slippage, zero-commission fill model. They are not
meaningful in the absolute sense; only deltas and P&L matter.

**Suggested next attempt**: (1) Cross-validate the spread threshold at 2.0x
(more conservative) to reduce false positives in OOS. (2) Try an AND condition
(PnL AND spread) for a lower skip rate but higher precision filter. (3) Explore
a 2-skip window after combined trigger events — if both signals fire together,
the regime persistence may warrant skipping 2 consecutive opens.
