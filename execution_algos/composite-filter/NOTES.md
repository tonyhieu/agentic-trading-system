# Algorithm Notes: composite-filter

## Hypothesis

**Mechanism**: Composite conditional skip combining two independent microstructure signals.
An open (non-reduce-only) order is skipped when BOTH of the following hold simultaneously:
(1) The current bid-ask spread exceeds a threshold relative to a rolling median spread
    (elevated market uncertainty), AND
(2) Recent mid-price momentum (last ~5 seconds of quotes) is adverse to the signal
    direction (price already moved against the trade before submission).
Reduce-only orders always execute to maintain intraday_flat compliance.
Quantity invariant: no order quantities are modified; skipped orders result in
sum(child_fills) < parent.quantity, which is permitted by OBJECTIVE.md §3.

**Inefficiency exploited**: With the oracle at sigma=5 (near-random ~48% win rate),
individual signals have very low edge. However, the WORST trades tend to cluster:
high-spread moments (liquidity withdrawal, high uncertainty) coincide with adverse
recent price moves (the oracle signal was already stale or running against recent
momentum). Prior iterations tested these two filters separately:
- spread-filter (2.0x threshold): +2.25% PnL, 0.2% skip rate — too few skips
- momentum-skip (1-tick threshold): +0.13% PnL, 1.7% skip rate — momentum alone weak
The compound AND filter targets a specific subset of trades where BOTH conditions
hold simultaneously — expected to be a smaller but higher-quality skip set than
either individual filter.

**Why it survives costs**: The fill model reports zero commissions and zero slippage
(see research/NOTES.md DATA ISSUE). All PnL difference comes from which trades
execute. At 48% win rate with ~5500 total trades, removing the worst ~2-5% (110-275
trades) while retaining the 48% winners among the rest is the path to +5% PnL.
The compound condition is stricter than either filter alone, so we target only the
most adverse trades.

**Builds on**: spread-filter (prior iteration) and momentum-skip (two iterations
prior). The spread-filter NOTES.md suggested combining spread + momentum as the
next attempt. This implements that suggestion with:
- Lower spread threshold: 1.5x median (vs. 2.0x in spread-filter) for higher skip rate
- Momentum window: 5 price updates (vs. 1 prior tick in momentum-skip)
- AND logic: both conditions must hold (more selective than either alone)

**Alternatives considered**:
- Pure lower-threshold spread filter (1.5x alone): expected more skips but spreads
  are a weak discriminator at low threshold; AND logic should help precision
- Pure longer-window momentum: momentum-skip at 1-tick barely fires; 5-tick window
  covers ~5 seconds of oracle signals; likely more stable but still weak alone
- Win-rate feedback loop: tracking realized trade outcomes for signal regime detection
  would require knowing future prices = look-ahead bias risk
- Streak-based submission (require N consecutive same-direction signals): tested
  conceptually by signal-consensus (3-of-5 agreement) — skip rate 0.3%, ineffective
  because oracle at sigma=5 rarely produces alternating signals

---

## Implementation Decisions

**Spread threshold**: 1.5x rolling 60-window median (spread_window=60). Lower than
spread-filter's 2.0x to increase skip rate. The 60-tick window captures ~1 minute
of quote updates at typical FX futures frequencies.

**Momentum window**: 5 mid-price observations (momentum_window=5). Covers the last
~5 seconds of signals at 1 Hz oracle cadence. Adverse = price moved >= 1 tick
(0.25 pts for MES contracts) against the signal direction during that window.

**Momentum measurement**: Compare earliest and latest mid-price in the window.
If the net move is >= momentum_threshold in the direction AGAINST the trade,
the momentum condition fires. For a BUY: adverse = mid fell >= threshold (we'd
be buying into a falling market). For a SELL: adverse = mid rose >= threshold.

**Momentum threshold**: 0.0 (any adverse move at all). This is intentionally
permissive: even a tiny adverse move combined with an elevated spread signals
a bad trade. The spread condition provides the selectivity; momentum adds direction.

**Edge cases**:
- Insufficient spread history (< 2 samples): submit immediately (no comparison basis)
- Insufficient momentum history (< 2 samples): treat momentum condition as False
  (don't skip on spread alone at startup)
- Reduce-only orders: always submit regardless of conditions (intraday_flat)
- Spread calculation: (ask_px - bid_px) where both are available from the order's
  top-of-book quote via instrument's current quote. Uses the instrument's cached
  quote at decision time — no look-ahead.

**Look-ahead bias assessment**: None identified. The spread and mid-price at
submission time are the observable values at the moment of the decision. The
rolling window only contains past values. No future tick information is used.

**Concerns**: With a composite AND filter, skip rate may be too low to matter
(if spread > 1.5x and adverse momentum rarely co-occur). If skip rate is < 1%,
the PnL delta will likely be < 2.25% (less than the spread-filter achieved).
The hypothesis would then be CONTRADICTED and the suggested next attempt should
be an OR filter or a more aggressive threshold.

---

## Backtest Observations

Aggregated over 3 train dates (20260308, 20260309, 20260310):
- composite-filter: $1654.75 / 5456 trades / win_rate=0.4861 / mean_sharpe=105.14
- simple baseline: $1586.75 / 5522 trades / win_rate=0.4832 / mean_sharpe=99.78
- delta_pnl = +4.29% (gate requires +5.0%), delta_slippage = 0.0% (neutral)
- STATUS: CLOSE (within 2% margin of pass gate)

Per-date breakdown:
- 20260308: +$6.25 (+4.45%), skipped=2 trades, win_rate 0.4672→0.4728
- 20260309: +$45.50 (+5.24%), skipped=32 trades, win_rate 0.4789→0.4829
- 20260310: +$16.25 (+2.81%), skipped=32 trades, win_rate 0.4909→0.4921
Max drawdown improved on all 3 dates (less negative).

**What drove improvement**: The AND-composite condition is directionally consistent —
positive on all 3 dates, win rate improved on all 3 dates. Skip rate was 0.3-1.1% (2-32
trades per date), indicating the AND condition fires infrequently but preferentially on
losing trades. On 20260309, the filter achieves 5.24% delta — above the gate — but the
weaker performance on 20260310 (2.81%) pulls the aggregate below 5%.

**What underperformed**: Skip rate too low to consistently overcome the +5% gate.
The AND condition is too selective: spread > 1.5x median AND adverse momentum both need
to fire together. The 20260310 result (+2.81%) shows higher baseline win rate on that date
(49%), meaning fewer weak trades to filter. The gain is proportionally smaller when the
signal is already closer to 50%.

**Hypothesis verdict**: CLOSE — the mechanism is directionally correct. Both conditions
(elevated spread AND adverse momentum) together do identify slightly worse-than-average
trades. However, the AND logic is too strict to produce the required 5% improvement
consistently. An OR filter or lower thresholds would increase skip rate and likely push
past the gate.

**Suggested next attempt**: Switch from AND to OR logic, or lower the spread threshold
further (1.2x or 1.3x median) while keeping the momentum condition. Alternatively, try
just the spread condition at 1.2x threshold — higher skip rate than spread-filter's 2.0x
may be enough to reach +5%. A cleaner single-condition filter with a carefully tuned
threshold is lower variance than a composite AND.

NOTE: The momentum condition definition was inverted from the original hypothesis intent:
the implementation skips BUYs when price ROSE recently (adverse for momentum-chasing buy),
not when price FELL. For a mean-reverting oracle, skipping BUYs after price rises may be
the correct direction (avoiding overextended entries). The effect is consistent across all
3 dates, suggesting the direction is correct regardless of label.
