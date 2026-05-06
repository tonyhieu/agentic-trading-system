# Algorithm Notes: momentum-skip

## Hypothesis

**Mechanism**: Mid-price momentum conditioned skip. At submission time, compute
the slope of the mid-price over the most recent N quote ticks. For a BUY order,
skip if momentum is strongly positive (mid has been rising — we are buying into a
completed move). For a SELL order, skip if momentum is strongly negative (mid has
been falling — we are selling into a completed move). Reduce-only orders always
submit immediately for intraday_flat compliance.

**Inefficiency exploited**: The oracle signal fires every 1 second with a 30-second
look-ahead horizon. When a signal arrives, the price may have already moved
substantially in the signal's direction within the preceding ticks. In that case the
"edge" the oracle provided has already been consumed: buying now means buying at a
higher price after the move, rather than before. Simple baseline does not condition
on this state — it always submits. By skipping orders where the price already ran in
the direction of the trade, we avoid adverse-selection from "stale-signal" entries.

**Why it survives costs**: In the zero-slippage fill model the entire edge differential
must show up in realized P&L from better average-fill-price timing. Skipping a fill
where the price has already moved 0.5+ ticks in the trade direction means we avoid
locking in a fill at the top of a local move. The oracle window is 30 seconds;
if the price moved in the first 1-2 seconds of that window, the remaining signal
value is uncertain. The threshold is intentionally conservative (only skip when
mid drift exceeds a significant fraction of typical tick size) to avoid filtering
too many trades.

**Builds on**: imbalance-skip — that algorithm used a static book snapshot (imbalance
at the moment of submission) and achieved only +0.10% vs baseline at threshold=0.5.
Its NOTES suggested trying "compare recent mid-price moves to oracle direction (skip
if price already ran in oracle direction, suggesting signal is stale)" — this algorithm
tests exactly that suggestion, using price momentum over a short rolling window instead
of instantaneous book imbalance.

**Alternatives considered**:
- Higher-threshold imbalance skip (0.8-0.9): per imbalance-skip NOTES, but imbalance
  is a static snapshot — unclear if 0.8 threshold adds discriminatory power vs 0.5.
  Momentum is a richer temporal signal.
- TWAP splitting: the oracle's edge is concentrated at signal time; splitting across
  many ticks would average down the edge. twap-defer showed this already.
- Deferral until adverse momentum passes: risky look-ahead; if we wait for price to
  reverse we might never fill (price could continue in the same direction). Skip is
  cleaner (no re-submission).

---

## Implementation Decisions

The momentum signal uses a rolling window of the last `window_size` (default 5) quote
ticks. Mid-price = (bid_px + ask_px) / 2. Drift = (mid[-1] - mid[0]) / (n - 1) ticks,
normalized to ticks by dividing by the minimum observed spread or a fixed tick-size
constant.

We maintain a deque of recent mid-prices per instrument (max length = `window_size`).
On each `on_quote_tick`, append the new mid. On `on_order`, check the drift:

- If window has fewer than `min_window` (default 3) samples: submit immediately
  (insufficient data to assess momentum, default to baseline behavior).
- Momentum threshold `momentum_threshold` in units of ticks (default 0.5 ticks
  = half a minimum-price-increment). Skip if abs drift exceeds this AND direction
  is adverse.

Parameters read from config.yaml execution_constraints block where applicable;
window_size and momentum_threshold are algorithm-specific kwargs.

**Concerns**: No look-ahead bias — we only use the cached quote tick history from
`on_quote_tick` calls, which are prior events in the event queue. The skip decision
uses only past observations. The main risk is overfitting the threshold to the 3-day
train window; we keep the default conservative (0.5 tick) to minimize this.

---

## Backtest Observations

Train dates: 20260308, 20260309, 20260310. Threshold: momentum_threshold=1.25e8 (~half a MES tick). Window=5, min_window=3.

Per-date results (momentum-skip vs simple):
- 20260308: $360.75 (124 trades) vs $389.00 (140 trades), delta=-7.26%, win_rate 80.65% vs 80.71%
- 20260309: $2917.25 (1073 trades) vs $3092.00 (1194 trades), delta=-5.65%, win_rate 85.93% vs 84.59%
- 20260310: $2109.75 (860 trades) vs $2244.00 (967 trades), delta=-5.98%, win_rate 86.05% vs 85.01%

Aggregated: momentum-skip $5387.75 / 2057 trades vs simple $5725.00 / 2301 trades
delta_pnl_pct = -5.89% (gate: +5.0% needed) — FAIL

**What drove improvement**: Win rate improved by +1.13pp (85.66% vs 84.53%) — consistent with the hypothesis that filtering out orders where price has already moved in the trade direction does remove some lower-quality entries.

**What underperformed**: The P&L gain from improved win rate was far outweighed by the 244 trades skipped. Each skipped trade on average was profitable (~$2.32 per trade from simple baseline), so 244 skips = approximately -$566 of lost P&L vs baseline. The algorithm is net negative on every single date, consistently around -6%. The oracle's signal is so strong that even adversely-momentum-loaded orders are profitable in expectation — there is no subset of oracle orders that the momentum filter correctly identifies as unprofitable.

**Hypothesis verdict**: Contradicted. The oracle signal does not exhibit the "already-consumed momentum" dynamic we hypothesized. Two possible explanations: (a) at 1-second signal intervals with a 30-second horizon, a half-tick of mid-price movement in the prior 5 ticks is insufficient to distinguish stale vs fresh signals — most of the 30-second edge remains regardless; (b) the threshold (0.5 tick) is too tight, generating too many skips (244 total), or too loose to filter only the truly stale signals. Given the consistent ~6% loss across all dates, the directional P&L effect is robust — this mechanism does not work at this parameter setting.

**Suggested next attempt**: The "skip oracle orders" design has now been tried with book imbalance (imbalance-skip) and price momentum (this algo) — both fail by ~6% because the oracle has positive expected value on nearly every trade. The fundamental challenge is that the oracle is so strong that filters must not reduce trade count. A structurally different approach: instead of skipping orders, try to IMPROVE FILL QUALITY by submitting limit orders slightly inside the spread (passive execution) when the book allows it, capturing a better fill price than top-of-book market orders — but this requires verifying the fill model supports limit-order queue simulation. Alternatively, look at order ROUTING: if multiple instruments or time-slices are available, concentrate execution in periods with historically better fills. A third path: accept that P&L improvement vs simple is extremely hard with this oracle setup and focus on reducing execution risk (drawdown) rather than P&L, which may matter more in live trading even if the backtest gate doesn't reward it.
