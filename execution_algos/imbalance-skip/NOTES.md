# Algorithm Notes: imbalance-skip

## Hypothesis

**Mechanism**: At order-submission time, inspect the current top-of-book bid/ask
size imbalance. Compute:

    imbalance = (bid_size - ask_size) / (bid_size + ask_size)   in [-1, +1]

For a BUY order: a high positive imbalance (bid >> ask) signals buying pressure —
the ask side is being consumed and price is likely to rise in the very short term.
Buying into a bid-heavy book means adverse selection: we buy just as other buyers
are piling in and the ask is thin. We SKIP (do not submit) the order. When
imbalance is low or negative (balanced or ask-heavy book), fill conditions are
favourable and we submit immediately.

For a SELL order: the logic is inverted. A high negative imbalance (ask >> bid,
sell pressure) is adverse — we SKIP. A low absolute imbalance or positive
(bid-heavy) suggests we can sell into a supportive bid, so we submit.

Reduce-only (close) orders are always submitted immediately to maintain
intraday_flat compliance — we never skip closes.

**Inefficiency exploited**: The `simple` baseline submits every oracle signal
immediately regardless of book state. When imbalance is unfavourable, the fill
lands at the worst local price (just before a short-term reversal). Skipping
those fills reduces the number of adversely-selected entries while retaining
the high-quality fills in the set — improving average P&L per trade even at
lower total fill count.

**Why it survives costs**: In the zero-slippage fill model identified in
research/NOTES.md, the only P&L lever is trade selection quality. Skipping
adversely-selected entries should raise the win-rate and average realized P&L
per trade. The quantity invariant (sum(fills) <= parent.quantity) explicitly
allows skipping when conditions are unfavourable.

**Builds on**: none — original hypothesis. Does NOT retime or defer fills
(lesson from twap-defer: retiming within the 30s oracle horizon degrades edge).
This is purely a conditional-skip filter.

**Literature source**: Almgren & Chriss (2000) §4 "Value of Information" —
shows that directional drift information changes the optimal execution
trajectory. The Diverse Approaches to Optimal Execution (2026) paper uses
order-book imbalance as a key state feature in their RL execution agents
(§2.3.3, 13-dimensional state vector including spread and volatility context),
and MAP-Elites results show 8-10% performance improvements when execution
adapts to book-state signals.

**Alternatives considered**:
- Time-of-day scheduling (TWAP-style): ruled out — twap-defer showed retiming
  hurts inside the oracle horizon.
- Spread-based filter (skip when spread is wide): would reduce adverse
  selection but spread == ask_px - bid_px; in a zero-slippage model where we
  fill at top-of-book, a wide spread does not directly hurt P&L. Imbalance is
  more informative about short-term price direction.
- Participation-cap blocking: cap-boost showed that over-filtering (most orders
  blocked) destroys P&L volume. The imbalance threshold must be set conservatively
  to pass most orders through (target: skip <30% of open orders).

---

## Implementation Decisions

- **Imbalance threshold** (`skip_threshold`): set to 0.5 (skip if |imbalance|
  measured in the adverse direction exceeds 0.5). This means we only skip when
  one side of the book has >3x the qty of the other side and is in the
  adversarial direction. This is conservative — expected to pass ~75-85% of orders.
- **No-quote fallback**: if no quote is cached (first tick of day), submit
  immediately — matches baseline behaviour and avoids losing first-signal trades.
- **Reduce-only always submits**: intraday_flat requires closes; we never skip closes.
- **Single submission only**: when we decide to skip, the order is dropped entirely.
  No deferral. No retry. Quantity invariant: sum(fills) < parent.quantity for
  skipped orders, which is explicitly allowed.
- **Subscription**: subscribe to quote ticks on first order for each instrument so
  the cache is populated.

**Concerns**: The main risk is that skipping too many orders reduces P&L volume
enough to undercut the quality gain. With threshold=0.5 the skip rate should be
low, but if imbalance is typically extreme in the training data the algo may
skip more than expected. A low trade count (<30% of baseline) would trigger
a RESULT WARNING per §8. Also: using the cached quote at decision time carries
no look-ahead bias (we only see the bid/ask that existed at the moment the
strategy fires the signal).

---

## Backtest Observations

**Train dates run**: 20260308, 20260309, 20260310 (full train window).

**Per-date results (imbalance-skip vs simple)**:

| Date     | Algo PnL  | Base PnL  | Delta PnL% | Algo Trades | Base Trades | Algo Win% | Base Win% |
|----------|-----------|-----------|------------|-------------|-------------|-----------|-----------|
| 20260308 | $393.25   | $389.00   | +1.09%     | 139         | 140         | 82.01%    | 80.71%    |
| 20260309 | $3,085.50 | $3,092.00 | -0.21%     | 1181        | 1194        | 84.76%    | 84.59%    |
| 20260310 | $2,252.00 | $2,244.00 | +0.36%     | 947         | 967         | 85.96%    | 85.01%    |
| **AGG**  | $5,730.75 | $5,725.00 | **+0.10%** | 2267        | 2301        | 85.05%    | 84.49%    |

**Gate**: required +5.0% pnl improvement; slippage tied at 0.0 on both sides.
**Decision**: FAIL — +0.10% is far below the +5.0% gate (also below the CLOSE range of >=3.0%).

**What drove improvement**:
The skip filter did raise win_rate by +0.56pp across all dates, confirming the
directional hypothesis (imbalance above 0.5 is mildly adverse). On 20260308 it
produced +1.09% by avoiding 1 losing trade. On 20260310, +0.36%.

**What underperformed**:
On 20260309 (the highest-volume day), skipping 13 trades that turned out to be
winners subtracted more P&L than avoiding the few losers saved. The oracle signal
itself is already highly profitable (84.6% win rate) so a skip threshold of 0.5
removes almost as many winners as losers — the filter's discriminatory power is
insufficient.

**Hypothesis verdict**: The imbalance-skip hypothesis is directionally supported
(win rate improved) but the effect size is far too small to overcome the cost of
skipping oracle-edge winners. At threshold=0.5, the imbalance signal does not
sufficiently discriminate adverse from favorable fills in this dataset.

**Suggested next attempt**: Two options:
1. **Threshold search**: Try much more aggressive threshold (e.g., 0.8 or 0.9)
   targeting only extreme imbalance events. At 0.5 we skip ~1-2% of trades; at
   0.9 we'd skip only the top 1% most extreme cases. The signal power needs to
   be much higher in the adversarial direction.
2. **Alternative signal**: Instead of imbalance, use a different book-state
   metric. The Almgren/Chriss §4 "serial correlation" result suggests that
   price momentum in the last N ticks might be more predictive than static
   imbalance. An alternative: compare the last few mid-quote moves to the
   oracle signal direction — skip when the book is already moving in the
   oracle's predicted direction (price has run) rather than using static imbalance.
