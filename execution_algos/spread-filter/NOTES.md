# Algorithm Notes: spread-filter

## Hypothesis

**Mechanism**: At each parent order arrival, compute the current bid-ask spread from
the top-of-book quote. Compare it to the median spread over the last `window_size`
quotes (default 60). If the spread is wider than `spread_threshold × median_spread`
(default 2.0), skip the order (do not submit). Reduce-only orders (position-closing)
always execute immediately regardless of spread. Open orders that are skipped are
not retried — the oracle signal is assumed to have expired.

**Inefficiency exploited**: The simple baseline submits every order immediately
without regard to the execution regime. Wide bid-ask spreads signal high market
uncertainty: when market-makers widen the spread, they are protecting themselves
against informed order flow — this typically coincides with moments of elevated
short-term volatility and reduced price predictability. During these moments, the
oracle's 30-second forecast is more likely to be overwhelmed by noise (the oracle
uses sigma=5 noise on top of the true signal), producing losing trades. By skipping
orders when spread is anomalously wide, we avoid execution in high-uncertainty
regimes where the oracle's edge is most likely to be absent.

**Why it survives costs**: In the zero-slippage backtest environment, skipping a
losing trade is pure gain ($~1.50 per loser avoided). If wide-spread moments
disproportionately correspond to oracle errors, even a modest 10% skip rate with
any improvement in loser-to-winner ratio of skipped orders would improve P&L.
The oracle's baseline win rate is 84-85%; we need to skip windows where the win
rate is below ~70% to achieve net positive selection.

**Builds on**: none — original hypothesis. Related to `imbalance-skip` which
used order-book depth imbalance as the filter; this uses spread width instead,
which captures a different dimension of market uncertainty.

**Alternatives considered**:
- Continue with skip-based imbalance/momentum at higher thresholds (tried; diminishing
  returns because the book imbalance and inter-signal momentum signals are weak discriminators)
- Defer open orders until spread normalizes (rejected — twap-defer showed deferral
  hurts because oracle signal decays within 30s)
- Take-profit / early exit mechanism (rejected — exec algo cannot spontaneously generate
  reduce-only orders without a parent signal; it can only act on parent orders)
- Limit order posting to capture spread (deferred — complex interaction with nautilus
  fill model; would require cancel-and-resubmit logic)

---

## Implementation Decisions

The exec algo:
1. Subscribes to quote ticks for the instrument in `on_start`.
2. Maintains a `deque(maxlen=window_size)` of recent spread values (float, price units).
3. In `on_order`: reads the latest quote from `self.cache.quote_tick(instrument_id)`.
   Computes spread = ask_price - bid_price (in instrument price units).
   If the deque has fewer than `min_window` entries (default 10), submits immediately
   (insufficient history to compute a reliable baseline).
   Otherwise: computes median of the deque. If spread > spread_threshold × median and
   the order is NOT reduce-only → skip. All other cases → submit immediately.
4. Appends spread to the deque on each quote tick (via `on_quote_tick`).

**Concern**: The deque tracks spreads from quote ticks received by the algo, which
arrive via `subscribe_quote_ticks`. In the Nautilus backtest, subscriptions are
serviced before `on_order` is called for that same timestamp. This should be fine —
the deque is populated by earlier-in-time quotes, not future quotes, so no look-ahead
bias. **However**: if the current quote and the order arrive in the same clock tick,
the spread computed from that quote is the "contemporaneous" spread, not a future
value. This is valid for an execution decision — the algo observes the spread at
decision time. Not look-ahead.

**Parameters from config.yaml**: Read at `on_start` from the config file.
- `window_size`: 60 (approx 1 minute of quotes at ~1 quote/second)
- `spread_threshold`: 2.0 (skip if spread > 2× median)
- `min_window`: 10 (minimum history before activating the filter)

**Concerns**: 
1. The oracle only trains on 3 dates; with 2301 baseline trades over 3 dates,
   the filter needs to skip enough trades to matter (~5% skip rate minimum) while
   maintaining strong discrimination. Wide spreads may be too rare to achieve
   meaningful skip rates.
2. The zero-slippage environment means spread width doesn't directly affect fill
   cost — only the P&L from position direction matters. So spread width is an
   indirect signal, not a direct cost measure.

---

## Backtest Observations

**Config context**: sigma=5 (changed from 0.5 in prior iterations — see research/NOTES.md DATA ISSUE).
Oracle win rate under sigma=5 is ~48%, near-random. Prior iterations had ~84% win rate (sigma=0.5).
The comparison baseline is simple=$1586.75/5522 trades over 3 train dates (20260308-20260310).

**Per-date results**:
- 20260308: SF pnl=$147.50, 349 trades, win_rate=46.99% vs simple $140.50, 351 trades, 46.72%
- 20260309: SF pnl=$893.25, 2858 trades, win_rate=48.04% vs simple $867.75, 2863 trades, 47.89%
- 20260310: SF pnl=$581.75, 2303 trades, win_rate=49.15% vs simple $578.50, 2308 trades, 49.09%

**Aggregate**:
- spread-filter: $1622.50 / 5510 trades / win_rate=48.44% / mean_sharpe=102.64
- simple: $1586.75 / 5522 trades / win_rate=48.32% / mean_sharpe=99.78
- delta_pnl = +$35.75 (+2.25%); delta_slippage = 0.0 (both zero); delta_trades = -12

**What drove improvement**: The spread filter consistently (+$7, +$25.50, +$3.25 per date) improved
P&L by skipping a small number of open orders when spreads were wide. The skip rate was low
(~12/5522 = 0.2% difference in trade count), but the skipped orders were slightly more likely to be
losers than winners. The win rate improved by +0.12pp (48.44% vs 48.32%).

**What underperformed**: The improvement was far below the 5% gate. The spread signal at threshold=2.0x
median fires very rarely (the spread in CME futures appears to be quite stable with few anomalous spikes).
The 0.2% skip rate is too low to move the aggregate P&L meaningfully.

**Hypothesis verdict**: Directionally SUPPORTED but effect size too small. Spread width IS a mild
predictor of trade quality, but the filter fires too rarely to produce 5% improvement. The near-random
oracle (sigma=5) makes any single-signal filter's job much harder: you need to identify the ~48% winning
vs ~52% losing trades in a much less predictable regime.

**STATUS: FAIL** — delta_pnl = +2.25%, below the 3% CLOSE threshold (which requires 3-5% for CLOSE, ≥5% for PASS).

**Suggested next attempt**: 
1. Lower spread_threshold from 2.0 to 1.2-1.5 to fire more often — the rare extreme spikes are
   not discriminating well; lower threshold should increase skip rate substantially (5-15%) and may
   produce a larger total P&L difference (with a risk of hurting win rate if non-extreme spreads
   are not predictive).
2. Alternatively: try a COMPOSITE filter combining spread width AND directional momentum — when
   both signals agree the trade is adverse, skip. Single signals may be insufficient at sigma=5.
3. With sigma=5, consider whether any skip-based approach can achieve 5%: it requires identifying
   ~55% of losing trades correctly with <10% false positive rate on winners. This is a high bar
   for book-state signals alone.
4. The most important action: ask the human operator to clarify whether sigma=5 is intentional
   or whether it should be restored to 0.5 for comparability with prior iterations.
