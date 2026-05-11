# Algorithm Notes: spread-filter-tight

## Hypothesis

**Mechanism**: Bid-ask spread conditioned skip with a tighter (more aggressive) threshold.
At order submission, compute the current spread from top-of-book quote. Track a rolling
window of 60 recent spread values. Skip open (non-reduce-only) orders when spread >
1.3 × median(recent_spreads). Reduce-only orders always execute.

**Inefficiency exploited**: The prior iteration `spread-filter` used a threshold of
2.0×median and achieved +2.25% P&L improvement on the sigma=5 train window, but fired
on only ~0.2% of trades (12 fewer trades than the 5522 baseline). The effect was
directionally correct but too small to reach the +5% gate. The core insight: elevated
spread still signals higher uncertainty (lower oracle reliability) under sigma=5, but
the 2.0× threshold was too conservative. By lowering to 1.3×, the filter fires on a
meaningfully larger fraction of trades (~1-3% expected), producing a proportionally
larger P&L delta while the per-trade discriminating power should remain positive since
the spread signal is consistent.

**Why it survives costs**: With zero fill-model slippage and zero commissions (see
research/NOTES.md DATA ISSUE), the only lever is signal quality selection. The spread
filter skips trades where the oracle's 30-second forecast is less reliable (market
makers widen spreads during uncertainty spikes). With sigma=5 (48% win rate), even a
modest improvement to ~49-50% win rate on executed trades — achievable by skipping
~2% of the most-adverse trades — should generate +5% aggregate P&L delta if the
skipped set is concentrated at <40% win rate.

**Builds on**: `spread-filter` (prior iteration). ONE targeted change: spread multiplier
from 2.0 to 1.3. All other logic is identical (rolling window=60, reduce-only always
executes, same mid-price computation pattern). No other modifications to avoid
confounding.

**Alternatives considered**:
- Composite spread + momentum filter: combining two signals risks over-filtering and
  reducing the executable set too aggressively, hurting coverage. Also adds a second
  parameter. Deferred — one change at a time.
- Threshold 1.5×: intermediate option. 1.3 is chosen as the more aggressive point
  to maximize chance of crossing the +5% gate; 1.5 would be a natural follow-up if
  1.3 over-fires.
- Adaptive threshold (percentile-based): more robust but adds complexity. Deferred.

---

## Implementation Decisions

**Threshold 1.3×median**: The 2.0× threshold from spread-filter fired on ~0.2% of
trades. A 1.3× threshold on a reasonably shaped spread distribution should fire on
a 5-20× larger fraction. The exact fire rate will depend on the empirical spread
distribution, which is right-skewed — most ticks have a tight spread, with occasional
spikes. At 1.3× we capture more of the "modestly elevated" spread regime, not just
the extreme spikes.

**Rolling window 60 ticks**: Unchanged from spread-filter. Provides a stable median
estimate while being responsive to intraday regime changes. At ~1 tick/second per
instrument, this covers ~60 seconds of recent spread history.

**Reduce-only orders always execute**: Required for intraday_flat compliance. Closing
orders must always execute regardless of spread conditions.

**Quantity invariant**: Skipped orders result in sum(child_fills) < parent.quantity,
allowed by OBJECTIVE.md §3.

**Concerns**:
- No look-ahead bias: spread at order submission time is observable. The rolling
  median uses only past ticks. No future information used.
- Risk of over-filtering: if 1.3× fires on 10%+ of trades, we may be skipping too
  many and reducing P&L by volume effects. The oracle at 48% win rate means each
  trade has slight positive expected value — skipping too many reduces aggregate P&L
  even if the per-trade quality improves. This is a real risk at 1.3×.
- Overfitting risk: low — threshold 1.3 is a single number on 3 training days, and
  the mechanism is grounded in market microstructure theory.

---

## Backtest Observations

**Train dates run**: 20260308, 20260309, 20260310.

**Results**:

| Date     | Algo P&L  | Trades | Win Rate | Baseline P&L | Baseline Trades | Baseline WR |
|----------|-----------|--------|----------|--------------|-----------------|-------------|
| 20260308 | $180.50   | 336    | 49.70%   | $140.50      | 351             | 46.72%      |
| 20260309 | $981.00   | 2755   | 48.97%   | $867.75      | 2863            | 47.89%      |
| 20260310 | $657.00   | 2180   | 50.41%   | $578.50      | 2308            | 49.09%      |
| **Total**| **$1818.50** | **5271** | **49.61%** | **$1586.75** | **5522** | **48.32%** |

**Gate check**:
- vs_baseline_pnl_pct = +14.61% (gate: >=5.0%) — PASS
- vs_baseline_slippage_pct = 0.0% (gate: <=5.0% regression) — PASS
- STATUS: **PASS**

**What drove improvement**: The tighter 1.3× threshold skipped ~4.5% of trades (251 fewer
than baseline 5522). Those skipped trades had a lower-than-average win rate — the spread
filter successfully identified modestly elevated spread periods as adverse entry conditions
in the sigma=5 regime. Win rate improved +1.29pp (49.61% vs 48.32%), and the aggregate
P&L improvement of +14.61% is consistent across all 3 train dates (20260308: +$40, +28%
over small base; 20260309: +$113, +13%; 20260310: +$78.50, +14%).

**What underperformed**: The Sharpe improvement metric is unreliable under the zero
fill-cost model (per research/NOTES.md DATA ISSUE). The per-trade win rate improvement
(+1.29pp) is modest — the primary driver is the accumulation of small per-trade gains
across ~5000 trades.

**Hypothesis verdict**: SUPPORTED. The 1.3× spread threshold fires on ~4.5% of trades
(compared to ~0.2% at 2.0×), yielding a meaningful P&L delta. The directional evidence
from spread-filter (+2.25% at 0.2% skip rate) scaled approximately as expected: 4.5%
skip rate at 1.3× produced +14.61%. The oracle at sigma=5 (48% win rate) does exhibit
measurable adverse selection concentrated in elevated-spread ticks, and the 1.3× threshold
captures this effectively.

**Suggested next attempt**: (1) Tune the threshold further — 1.1× or 1.5× — to find the
optimal skip rate vs discriminating power tradeoff. (2) Add an asymmetric threshold: apply
the 1.3× filter only during specific intraday windows (e.g., near session open/close where
spreads are typically elevated for structural reasons vs information-driven reasons). (3)
Combine the spread filter with a momentum check (skip when BOTH spread elevated AND recent
mid-price moved adversely) — composite may achieve higher skip rate without over-filtering.
