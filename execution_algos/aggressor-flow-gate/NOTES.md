# Algorithm Notes: aggressor-flow-gate

## Hypothesis

**Mechanism**: Maintain a short rolling window of recent trade prints (last N
seconds, default 10s), classifying each as buyer-initiated (BUYER aggressor,
crossed the ask) or seller-initiated (SELLER aggressor, hit the bid). Compute
a signed net aggressor flow = buy_volume - sell_volume over the window. For a
BUY oracle signal, skip the open leg when net flow is strongly negative
(sell-dominated, below -flow_threshold). For a SELL signal, skip when net
flow is strongly positive (buy-dominated, above +flow_threshold). Reduce-only
/ position-closing orders always execute. After any skip, _position_flat = True
so the next open order is submitted unconditionally (anti-cascade guarantee
matching all other passing algorithms).

**Inefficiency exploited**: The baseline "simple" algorithm submits every
oracle open indiscriminately, entering against the prevailing short-term
order flow. When market participants are aggressively selling (a stream of
SELLER-aggressor prints), a BUY entry faces immediate adverse selection:
the price is moving against the new position. By measuring the signed sum
of recently-traded aggressor volume, we quantify this directional momentum
in the trade tape and avoid the highest-cost entries.

**Why it survives costs**: Aggressor flow (realized marketable order flow)
is a distinct and complementary signal to resting-book imbalance. While
ob-imbalance-gate and microprice-divergence-gate condition on the sizes of
unaggressed limit orders sitting in the queue, aggressor flow measures
actual crossing interest -- trades that have already happened. These two can
diverge sharply: a thin offer side (ob-imbalance favors BUY) can coexist
with heavy recent sell aggression (flow warns against BUY). The hypothesis
is that the flow signal has stronger near-term directional predictive power
because it reflects committed, revealed directional intent rather than
hypothetical limit queue patience.

The edge needs to survive only a modest skip rate. Prior passing algorithms
(streak-spread-tight, ob-imbalance-gate) achieved PASS with ~20% skip rates.
A 10-15% skip rate here at similar quality improvement suffices.

**Builds on**: none -- original hypothesis. Not a refinement of any prior
passing algorithm.

**Alternatives considered**:
- Pure volume imbalance from the resting book (ob-imbalance-gate, done,
  PASS -- excluded per directive).
- Microprice divergence (done, PASS -- excluded per directive).
- Trade count ratio instead of volume: simpler but ignores trade size;
  volume-weighted flow is more informative for futures.
- Longer window (60s): risks picking up stale signal after reversals.
  10s matches the oracle's 30s horizon_seconds but is short enough to
  reflect immediate aggressor interest.
- Threshold = 0 (skip on any net adverse flow): too aggressive -- noise
  in trade flow would cause excessive skipping. A volume threshold
  filters out near-balanced periods where signal is ambiguous.

---

## Implementation Decisions

- **Rolling window by time (10s default)**: Use nanosecond timestamps from
  trade ticks. Maintain a deque of (ts_event_ns, signed_volume) tuples.
  Prune entries older than `window_seconds` before each evaluation.
  This is look-ahead free: we only use trades that occurred before the
  current order's ts_init.

- **Signed volume**: BUY aggressor contributes +size, SELLER aggressor
  contributes -size. NO_AGGRESSOR trades contribute 0 (not common in
  futures MBP1 data but handled defensively).

- **flow_threshold**: Skip when |net_flow| >= flow_threshold AND direction
  is adverse. Default 2 (skip when net adverse flow >= 2 contracts in the
  window). This is intentionally small -- futures contract sizes are 1 lot
  each; 2 contracts of net adverse flow in 10s is a meaningful signal.

- **Subscription**: call `subscribe_trade_ticks(instrument_id)` on first
  order so we start receiving `on_trade_tick` callbacks. Use `self.cache.trade_ticks`
  to back-fill if needed, or rely purely on the subscription callback to
  fill the deque.

- **No look-ahead bias**: the deque at decision time only contains trades
  with ts_event < order.ts_init (pruned by the time window). The trade
  stream in the backtest is replay in chronological order, so any trade
  tick delivered before the order event is by definition prior in time.

- **Warm-up handling**: if the deque is empty (start of session or first
  few seconds), submit unconditionally -- no signal, no skip.

- **Quantity invariant**: never modify order.quantity. Only skip or submit.

**Concerns**: 
- The backtest replays ticks in chronological order. Trade ticks that
  arrive at the same nanosecond as the order event are edge cases --
  we treat them as "already known" (ts_event <= order.ts_init is safe).
- No look-ahead: we never peek at future trades; only the rolling deque
  of past trades is used.

---

## Backtest Observations

Train window: 12 dates (2026-03-08 to 2026-03-20, excluding 2026-03-14 and
2026-03-21 -- no data, consistent with all prior runs).

**Results summary**:
- aggressor-flow-gate: realized_pnl=$3,059.25, trade_count=103,947, sharpe=1.63
- simple baseline:     realized_pnl=$1,984.00, trade_count=132,536, sharpe=0.91
- vs_baseline_pnl_pct: +54.20% (gate: >=5.0%) → PASS
- vs_baseline_slippage_pct: 0.0% (gate: <=5.0%) → PASS
- mean_slippage: 0.0 both sides (zero fill-cost model)
- trade reduction: 21.6% (28,589 fewer trades)
- is_weighted_bps: 0.0457 vs 0.0375 (+21.9% worse IS) -- IS slightly worse
  because many skipped trades would have been low-IS (the filter skips both
  good and adverse entries, but also keeps more profitable entries overall)
- max_drawdown_pct: -0.0236% vs -0.0377% (37% improved)
- win_rate: 36.2% vs 35.6% (+0.6pp)

**What drove improvement**: The rolling signed aggressor flow from trade prints
correctly identifies short-term directional momentum in the trade tape. When
sellers are aggressively hitting bids (net_flow <= -2.0), BUY entries face
adverse price moves within the oracle's 30s horizon. Skipping those entries
improves per-trade quality. Beat baseline on 10/12 dates (20260308 was slight
underperformance: $135.50 vs $140.50; 20260311 effectively tied: $395.50 vs
$394.75). Consistent broad-based improvement -- not driven by 1-2 outlier dates.

**What underperformed**: The is_weighted_bps (implementation shortfall) rose by
21.9% vs baseline. This is because the filter holds back entries during
adverse-flow periods, but those exact moments sometimes offer the best fill
prices (the market is being pushed to a temporary extreme by aggressors -- the
oracle signal that fire there can have favorable arrival prices). So while net
P&L improves, the execution quality metric (IS vs arrival mid) slightly worsens.
This is an inherent tension in flow-based gating.

**Hypothesis verdict**: SUPPORTED. Realized aggressor flow from trade prints has
directional predictive power that complements static resting-book signals.
The 10s rolling window with a 2-contract threshold provides an effective gate
with a 21.6% skip rate, matching the 19-20% range of top-performing ob-imbalance
and microprice-divergence algorithms. Net P&L improvement of +54.2% vs baseline
exceeds all prior algorithms except the top two book-based gates.

**Suggested next attempt**: Combine aggressor-flow-gate with the session-clock
skip windows (session-clock-gate). The two signals are orthogonal by construction
(one is temporal, one is from the trade tape), and their skips would rarely overlap.
A combined gate could potentially achieve a 25-30% combined skip rate with better
per-date consistency. Alternatively, tune the window to 5s (closer to 1-signal-interval
of 1s but more responsive) or raise the threshold to 3-4 contracts to see if a
stricter filter further concentrates the skip benefit.
