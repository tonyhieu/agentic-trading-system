# Algorithm Notes: composite-or

## Hypothesis

**Mechanism**: Conditional skip using OR logic — skip an opening order when
EITHER the current spread exceeds 1.5x the rolling-60-window median spread
OR recent mid-price momentum is adverse to the trade direction. Reduce-only
orders are always submitted. No quantity modification.

**Inefficiency exploited**: `composite-filter` (prior iteration, CLOSE at
+4.29%) used AND logic which was too selective — only 2–32 skips across 3
train dates. The filter caught some losing trades but its skip rate was too
low to accumulate the 5% P&L improvement required for PASS. With sigma=5
oracle (near-coin-flip signal), there are many marginal/losing trades in both
directions. The OR condition identifies a strictly larger set of adverse
regimes: ticks where EITHER the book looks uncertain (spread elevated) OR
momentum has already moved against us. Each sub-signal alone targets a
different class of bad entry; combining with OR catches more of them without
doubling up on any signal overlap.

**Why it survives costs**: Under the current fill model (zero slippage,
zero commissions), P&L gains come entirely from avoiding losing trades.
The spread sub-signal identifies high-uncertainty regimes where the near-random
oracle more frequently predicts incorrectly. The momentum sub-signal identifies
ticks where the price already moved against the trade direction (adverse
entry). Combining with OR should increase skip rate from ~0.3-1.1% (AND) to
potentially 5-15%, targeting a large enough fraction of below-average trades
to move the aggregate P&L delta from +4.29% to ≥ +5.0%.

**Builds on**: `composite-filter` — same parameters (spread_mult=1.5,
spread_window=60, momentum_window=5, momentum_threshold=0.0), single
targeted change from AND to OR logic.

**Alternatives considered**: (1) Lower spread threshold to 1.2-1.3x — this
would be a different single change than changing the logic operator. OR logic
is a purer targeted change that directly addresses the stated weakness from
`composite-filter` NOTES.md ("AND condition is too selective"). (2) Spread-only
at 1.3x threshold — also valid but trades off specificity differently. The OR
path was the explicit suggestion in `composite-filter` NOTES.md.

---

## Implementation Decisions

The implementation is a direct copy of `composite-filter` with two changes:
1. Logic operator: `if spread_fires and momentum_fires:` → `if spread_fires or momentum_fires:`
2. Momentum threshold: `momentum_threshold = 0.0` → `momentum_threshold = 0.25`

The threshold change is necessary to prevent a degenerate case. During initial
testing with `momentum_threshold=0.0`, the OR condition fired on 100% of orders
because ANY non-zero mid-price move triggers the momentum condition — and in a
1-second-cadence oracle environment, the mid-price almost always changes between
consecutive observations. Setting threshold to 0.25 (one minimum tick for MES
futures) mirrors `momentum-skip` (which had ~1.7% skip rate at this threshold)
and combines with the spread filter in OR mode.

Parameters:
- `spread_window = 60` (rolling median window)
- `spread_mult = 1.5` (threshold multiplier, same as composite-filter)
- `momentum_window = 5` (mid-price history length)
- `momentum_threshold = 0.25` (one minimum tick, prevents sub-tick noise firing)

Reduce-only orders always submit (intraday_flat compliance, quantity invariant).

**Concerns**: OR logic may be too aggressive. If the oracle's 48-49% win rate
is uniformly distributed across all market regimes, then OR-filtered trades
would also have ~48-49% win rate and skipping them would be neutral rather
than beneficial. The hypothesis relies on the spread and momentum signals
having at least marginal predictive power for the specific sub-population of
trades they target. This is testable — if the win rate among OR-skipped trades
is below 48-49%, the filter adds value; if above, it's net harmful. Win rate
improvement across dates will be monitored in the Backtest Observations.

An initial run with threshold=0.0 produced 0 fills (100% skip rate) —
confirming the threshold=0.25 fix is necessary for meaningful backtest results.

---

## Backtest Observations

**What drove improvement**: The OR logic with momentum_threshold=0.25 skipped ~33.6%
of opening orders across all 3 train dates (1855 of 5522). The skipped orders had a
lower-than-average win rate — the trades that were executed (47.8-49.8% winners skipped
implied) showed +2.71pp higher win rate than simple (51.02% vs 48.32%). This confirms
the hypothesis: the spread-elevated OR adverse-momentum signal identifies a sub-population
of oracle orders with below-average quality, and filtering them out improves aggregate
P&L. The OR configuration achieves ~33% skip rate vs ~1% for AND, which is why OR
crosses the +5% P&L gate while AND stayed at +4.29%.

**What underperformed**: The improvement is uneven across dates:
- 20260308 (short session): +12.81% — small session, 108 skips
- 20260309: +7.12% — strong improvement, 953 skips
- 20260310: +2.25% — weaker improvement, 794 skips

20260310 being the weakest at +2.25% is concerning. If the gate were per-date
rather than aggregate, 20260310 would be below the close margin. The aggregate
passes due to the strong 20260308 and 20260309 performance. The high skip rate
(~34%) on 20260310 may be removing too many winners on that date.

**Hypothesis verdict**: SUPPORTED. The OR condition catches a meaningful fraction of
losing-quality orders. Win rate improved by +2.71pp (51.02% vs 48.32%) despite
a ~34% reduction in trades, demonstrating the filtered trades had below-average
win rates. Max drawdown improved substantially (-0.0020 vs -0.0043 for simple).
Mean Sharpe improved (127.96 vs 99.78 for simple), though Sharpe here is unreliable
given the zero-slippage fill model.

**Suggested next attempt**: The 20260310 underperformance (+2.25%) suggests the skip
rate may need tuning per market regime. Options: (1) raise spread_mult to 1.7-2.0
to reduce over-filtering on 20260310 while keeping OR logic; (2) try asymmetric
thresholds (lower for spread, higher for momentum); (3) add a minimum trade-count
floor per session to avoid depleting too many oracle signals in lower-volatility
sessions. A per-date calibration approach would be another direction, though it
risks overfitting to the 3-date train window.

**Implementation notes**: Two bugs were discovered during testing:
1. Initial `momentum_threshold=0.0` caused 100% skip rate (any price tick fires
   momentum condition in an OR configuration). Fixed by setting threshold=0.25.
2. Initial `exec_id="COMPOSITE_OR"` caused 0 fills (strategy routes orders to
   "MY_GENERIC_ALGO"). Fixed to match other algos.
