# Algorithm Notes: passive-aggressive-ladder

## Hypothesis

**Mechanism**: Passive-then-aggressive order laddering — for each open-leg entry, first
post a passive limit order at the same-side top of book (BUY at bid_px, SELL at ask_px).
If the passive order fills, the spread is captured (we collected the bid-ask spread).
If the passive order has not filled within `passive_timeout_ticks` quote-tick updates,
cancel it and submit a marketable market order (aggressive fallback) to ensure entry is
executed before the signal expires. Reduce-only (position-closing) orders always execute
aggressively to honor the intraday_flat constraint and avoid unbounded close-leg risk.

**Inefficiency exploited**: The `simple` baseline always crosses the spread as a taker
(market order), paying the full bid-ask spread on every open leg. In liquid markets with
frequent two-sided flow, a material fraction of open orders can be filled passively at the
bid (for buys) or ask (for sells) when the market temporarily trades at our resting limit.
Capturing these "passive fills" earns rather than pays the spread. Even if only a minority
of opens fill passively, each passive fill saves the full half-spread in implementation
shortfall vs the aggressive baseline.

**Why it survives costs**: The oracle strategy sends ~130k orders over the 12-day train
window at ~$1984 realized PnL. Each order is 1 MES contract. MES tick size is $1.25;
typical MES spread is 1 tick = $1.25. Capturing the spread on 10-20% of entries by
posting passive would save ~13k-26k half-spreads × $0.625 = $8k-$16k. Even with a
fraction of those passives failing (timeout to aggressive) at modestly worse prices (e.g.
because the market moved away), the net capture should still be positive given the oracle
signal is directionally informed and the spread is small relative to the signal horizon.

**Builds on**: none — original hypothesis. The four prior passing algorithms (streak-spread-tight,
ob-imbalance-gate, vol-regime-sizer, microprice-divergence-gate) all operate by skipping or
sizing entries based on signal quality signals. This algorithm is mechanically distinct: it
changes *how* the order is placed rather than *whether* to place it. All prior algorithms use
market orders for all entries; this algorithm posts limit orders first.

**Alternatives considered**:
- Pure passive (GTC limit, no timeout): risks stale fills when the oracle signal has expired
  and the market has moved far from entry, leading to adverse open positions that must be
  closed at a loss. Timeout + aggressive fallback mitigates this.
- Timeout based on wall-clock milliseconds rather than tick count: tick-count is simpler
  and more reproducible in backtests where time between ticks varies significantly intraday.
- Passive with size > 1 (post more than 1 contract): violates quantity invariant; each
  parent order is 1 contract.
- Skip if passive times out: equivalent to prior skip-gate algorithms but without
  signal-quality conditioning; expected to underperform them. Not chosen.

---

## Implementation Decisions

The algorithm uses `spawn_limit(primary, qty, passive_price, reduce_primary=False)` for
the passive phase. With `reduce_primary=False`, the primary order retains its original
`leaves_qty`. This is necessary because if the limit is accepted and then canceled (after
timeout), Nautilus does NOT restore the primary's reduced quantity — the quantity deduction
from `spawn_limit` with `reduce_primary=True` is committed once accepted. Using
`reduce_primary=False` keeps the primary as a quantity reservoir. When the passive child
is canceled, `spawn_market(primary, primary.leaves_qty)` executes the aggressive fallback,
reducing the primary to zero.

When the passive child fills, the primary is never submitted as a market order. To prevent
the primary from being double-filled (since it still has `leaves_qty>0`), we track filled
primaries and discard any subsequent spawn attempts. In practice, once the child fills,
`on_order_filled` is triggered and we mark the primary as completed; no further spawning
is attempted.

**Tick timeout**: `passive_timeout_ticks=5`. Rationale: at ~1 signal per second and
~10-30 quote ticks per second in MES, 5 ticks corresponds to roughly 200-500ms of market
time — short enough that the signal hasn't significantly degraded, but long enough for
typical price oscillations to sometimes deliver the passive fill. The value is configurable.

**Concerns**:
- `reduce_primary=False` means we hold a live reference to the primary order. If somehow
  both the passive child and a secondary market order fire simultaneously (race condition in
  non-backtest environments), we could overfill. In the backtest engine this is deterministic
  and safe.
- The backtest engine's `FillModel.fill_limit_inside_spread()` returns `False` by default,
  meaning a BUY LIMIT at `bid_px` fills only when the ask crosses down to `bid_px` or below.
  This IS genuine passive fill behavior — the engine correctly simulates queue/crossing fills
  for limit orders. This was verified before implementation.
- Participation cap: the parent order is 1 contract (from the oracle strategy). We always
  spawn 1 contract per parent — no size inflation.
- Intraday flat: reduce-only orders always execute aggressively (market order immediately).

---

## Backtest Observations

**Status**: FAIL — realized_pnl=-$1430.32 vs baseline $1984.00; vs_baseline_pnl_pct=-172.1%; Sharpe=-1.053 vs +0.909.

**What drove improvement**: None. The algorithm UNDERPERFORMED the baseline on every metric across all 12 train dates.

**What underperformed**: The entire passive-then-aggressive mechanism. 

Root cause (confirmed via per-date analysis on 20260308):
1. With `passive_timeout_ticks=5`, approximately 48% of passive limit orders fill and 52% time out.
2. Passive fills have favorable IS (mean ~ -$0.49 per order) — the spread IS captured.
3. BUT aggressive fallbacks (after timeout) have dramatically worse IS than simple baseline:
   - Simple baseline open IS = +$0.14 per fill
   - Passive-aggressive fallback open IS = +$0.82 per fill (5.9x worse!)
4. The delay of 5 quote ticks causes the aggressive fallback to fire after the oracle-predicted
   price move has already begun. For a correct BUY signal, the ask has risen by the time the
   fallback fires, so we pay a higher-than-baseline ask. Net IS from the ladder is +$94 vs
   simple baseline +$78 on date 20260308.
5. Aggregate across 12 dates: IS_total=$10,120 vs baseline $6,693 (+51.3 bps adverse).

Adverse selection on passive fills: passive BUY LIMIT at bid fills when the ask drops to
the bid — i.e., when the market is moving AGAINST the BUY signal. This means passive fills
systematically select for bad oracle trades (signal was wrong). The oracle's noisy signal
(sigma=5, 30s horizon) means this adverse selection materially degrades the passive fill set.

**Hypothesis verdict**: REJECTED for this signal/market combination.
The hypothesis is theoretically valid (capturing the spread on passive fills has positive
expected value in a maker-taker model). However, it fails for the oracle strategy because:
- The oracle signals are directionally informed over a 30s horizon
- Directional momentum means passive fills occur predominantly when signals are incorrect
  (price reverts to our passive limit, confirming the signal was wrong)
- The timeout delay causes the aggressive fallback to fire AFTER adverse price movement
- Net execution cost = worse than simple baseline

**Engine feasibility confirmed**: The backtest engine DOES model passive fills correctly
(`FillModel.fill_limit_inside_spread() = False`). The issue is not the engine; the hypothesis
itself does not deliver positive value for this particular signal.

**Suggested next attempt**: If passive-aggressive laddering is to be revisited, it would
need either:
1. A much shorter timeout (1-2 ticks) combined with a smarter signal-quality filter —
   only post passive when the oracle signal is uncertain (low |signal|), and cross immediately
   when signal is strong.
2. A different entry price for the passive leg — e.g., posting at mid rather than bid/ask,
   which avoids the adverse-selection problem (but reduces spread capture proportionally).
3. Using passive only for REDUCE-ONLY (close) orders where adverse selection is less severe,
   and keeping aggressive for open orders — the reverse of what this algorithm does.
