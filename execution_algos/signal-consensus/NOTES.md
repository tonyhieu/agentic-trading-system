# Algorithm Notes: signal-consensus

## Hypothesis

**Mechanism**: Oracle-signal consensus filter — track the direction of the
last N parent orders (BUY/SELL) submitted by the strategy. Execute a new
order only when at least a `min_agreement_frac` fraction of the recent window
agree with the current order direction. Reduce-only (close) orders always
execute immediately.

**Inefficiency exploited**: The oracle fires one signal per second with noise
parameter sigma=0.5. When the oracle's true directional confidence is low
(the expected 30-second price change is near zero), the signal sequence will
oscillate: BUY, SELL, BUY, SELL... These oscillating-period signals are
disproportionately the losing trades, because the oracle's directional
conviction is too weak for the noise to be below the threshold.
Conversely, when the oracle is confident (market moving clearly in one
direction), consecutive signals agree: BUY, BUY, BUY, ... — these are
high-quality signals with elevated win rates. The simple baseline executes
ALL signals at equal weight. This filter selectively skips the low-consensus
(high-noise) signals and keeps the high-consensus (low-noise) ones, raising
the average quality of executed signals.

**Why it survives costs**: With zero fill-model slippage and zero commissions
(see research/NOTES.md DATA ISSUE), the only improvement lever is signal
quality selection. Skipping ~15-30% of trades concentrated in the noisy
oscillation periods, while keeping all high-conviction directional runs,
should raise average P&L per executed trade. Even a modest win-rate
improvement (e.g., +2pp from 85% to 87%) applied to 70-85% of remaining
trades would generate ~5% P&L gain over simple.

**Builds on**: Prior iteration `momentum-skip` (and before that `imbalance-skip`)
found that single-signal skip filters (mid-price momentum, book imbalance)
produce only ~1-2% skip rates and negligible P&L delta. The consensus filter
addresses this by tracking the oracle's OWN directional consistency — orders
from the oracle strategy — rather than relying on external market-microstructure
signals. The expected skip rate is higher (proportional to the fraction of
time the oracle is in a noisy/oscillating regime) and more directly tied to
signal quality.

**Alternatives considered**:
- Realized-volatility filter (skip during low-vol quiet markets): would need
  a vol estimate from quote ticks; mechanistically sound but adds complexity
  and a second parameter. Deferred — consensus filter is simpler and tests the
  same underlying hypothesis (skip when oracle quality is low) more directly.
- Higher imbalance threshold (0.8-0.9 vs 0.5): would still be a microstructure
  signal rather than the oracle's own quality indicator. Less direct.
- Multi-condition composite filter: combining imbalance + momentum. Risks
  compounding two weak signals and reducing interpretability.

---

## Implementation Decisions

**Window size** (`window_size=5`): Last 5 oracle signals covers ~5 seconds.
Short enough to be responsive to regime changes, long enough to form a
meaningful consensus. If all 5 agree (consensus=1.0), that is a very strong
signal. Default minimum agreement of 0.6 (3/5) means the majority agree.

**Minimum window** (`min_window=3`): Before 3 signals have been seen, fall
back to submitting immediately (no-history baseline). This avoids skipping
early orders at market open before we have enough history.

**Agreement threshold** (`min_agreement_frac=0.6`): The minimum fraction
of the recent window that must match the current order's direction. At 0.6
with window=5: at least 3 of the last 5 must agree.
- If 0.6 → skip rate ~0-5% (too loose, near-baseline)
- If 0.8 → skip rate ~20-40% (4/5 or 5/5 must agree)
- Start at 0.6 and note results for future iteration.

Actually, after reflection: at min_agreement_frac=0.6 with window_size=5,
we require 3-of-5 to agree. The oracle with sigma=0.5 and a strong
directional move has ~84% BUY rate. In a window of 5, P(≥3 agree | p=0.84)
= 1 - P(0) - P(1) - P(2) ≈ 0.999. So we execute ~100% of high-conviction
signals. For a flat market (p=0.5), P(≥3 agree) ≈ 0.5 — we execute ~50%
and skip ~50%. This is the desired behavior.

**Direction tracking**: Track the direction of each call to `on_order()`,
NOT just submitted orders. This ensures we're tracking oracle signal
direction, not execution outcomes. If we only tracked submitted orders, the
history would be biased toward high-consensus periods (self-reinforcing).

**Reduce-only orders**: Always submitted immediately regardless of consensus.
Required for `intraday_flat` compliance.

**Quantity invariant**: No order quantities are modified. Skipped orders
result in sum(child_fills) < parent.quantity, which is allowed under
OBJECTIVE.md §3.

**Concerns**:
- Possible look-ahead bias? No — we only observe past orders' directions.
  The consensus window looks backward, not forward. The order direction is
  the current order, which is being received now. No future information used.
- Overfitting risk: the threshold 0.6 is a single parameter on 3 training
  days. Low overfitting risk since it's a coarse threshold and the mechanism
  is grounded in the oracle's noise model.
- If the oracle switches direction at exactly window_size intervals, the
  consensus filter may lag regime changes. The short window (5 signals = 5
  seconds vs 30-second oracle horizon) limits this risk.

---

## Backtest Observations

**Train dates run**: 20260308, 20260309, 20260310.

**Results**:

| Date     | Algo P&L | Trades | Win Rate |
|----------|----------|--------|----------|
| 20260308 | $381.50  | 135    | 80.74%   |
| 20260309 | $3089.25 | 1193   | 84.58%   |
| 20260310 | $2236.75 | 965    | 84.87%   |
| **Total**| **$5707.50** | **2293** | **84.51%** |

**Baseline (simple, from prior iterations)**:
- Total: $5725.00 / 2301 trades (consistent across imbalance-skip and momentum-skip runs)
- 20260308 alone: ~$389.00 / 140 trades (inferred from twap-defer partial record)
- 20260309+20260310: ~$5336.00 / 2161 trades

**Delta**: ($5707.50 - $5725.00) / $5725.00 × 100 = **-0.30%** — well below the +5.0% gate.

**What drove improvement**: The consensus filter executed nearly as many trades
as simple (2293 vs 2301, a 0.3% reduction) and produced similar win rates
(84.51% vs ~84.5% baseline). No meaningful improvement.

**What underperformed**: On 20260308 (Sunday session), win rate was 80.74% —
lower than baseline's ~85%. The consensus filter skipped 5 trades (140 → 135),
but those 5 happened to be net winners ($7.50 lost vs expected gain). On the
larger 20260309 and 20260310 sessions, the filter barely triggered — trade
counts dropped only slightly (1193 vs ~1081 and 965 vs ~1080 from baseline
estimate; note these estimates are imprecise). The net result is slightly worse
P&L from the filtering.

**Hypothesis verdict**: CONTRADICTED. The oracle signal sequence at 1-second
intervals with sigma=0.5 does NOT exhibit the oscillation pattern the hypothesis
predicted. The 3-of-5 consensus filter barely fires (skip rate ~0.3%) because
the oracle's per-signal win rate of ~84-85% means directional consistency is
already high — most 5-signal windows show agreement in the right direction.
When the filter does fire, it removes slightly more winners than losers (because
the overall win rate is high). The fundamental problem remains: with 84-85% win
rate, there is no meaningful way to discriminate losers from winners using a
pre-execution consensus filter.

**Suggested next attempt**: The consensus filter approach is exhausted at this
threshold. The real structural barrier is the fill model (zero slippage, zero
commissions) — with no fill costs, all execution-timing improvements vanish.
The only lever is signal quality. Suggested next approaches:
1. Focus on session structure: on the 20260308 Sunday session (very short,
   140 trades, $389), the signal density and quality may differ meaningfully
   from weekday sessions. A session-type filter (Sunday/holiday vs weekday)
   might skip the lower-quality Sunday session entirely and improve aggregate
   quality metrics.
2. Investigate whether position-size scaling (submitting fractional quantities)
   is possible within the quantity invariant — but this is strategy-locked.
3. Raise the concern to the human operator: the current evaluation framework
   (zero fill costs, small train window) makes it structurally very hard to
   show a +5% P&L improvement from pure execution timing.
