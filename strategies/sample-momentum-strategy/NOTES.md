# Strategy Notes: sample-momentum-strategy

## Hypothesis

**Signal**: Short-term price momentum using a 20-tick rolling window on mid-price changes (`(bid_px + ask_px) / 2`)
**Inefficiency exploited**: Institutional order flow on CME GLBX FX futures creates predictable short-term directional drift — large passive orders attract aggressive followers, sustaining momentum for 3–5 ticks
**Why it survives costs**: Observed momentum magnitude (~4 ticks) exceeds typical IS (~1.5 ticks) during high-liquidity sessions; participation cap at 5% limits adverse selection on large moves
**Parent strategy**: none — original hypothesis
**Alternatives considered**: Order flow imbalance (OFI) — promising but requires clean bid/ask delta computation across tick boundaries, which adds implementation risk; mean reversion — spread on GLBX FX futures is too tight to reliably absorb reversion signal after costs

---

## Implementation Decisions

- Lookback period of 20 ticks chosen as a balance between signal freshness and noise reduction; no formal optimization was performed — chosen to match typical CME GLBX burst duration
- Holding period of 5 ticks limits IS accumulation while capturing the core momentum window
- Participation cap set at the allowed maximum (5%) — momentum strategies benefit from speed; a tighter cap reduces P&L without a meaningful risk benefit given the short holding window
- Initial capital of $100,000 used for P&L scaling; position sizes are derived from the participation cap on top-of-book quantity

**Concerns**: Signal window and holding window are strictly non-overlapping — verified that `ts_event` at signal calculation is always before the first fill timestamp. No look-ahead bias identified, but the 20-tick lookback should be re-verified if data loading changes.

---

## Backtest Observations

**What drove performance**: Strong momentum persistence in EUR/USD and GBP/USD futures during the London–NY overlap (13:00–17:00 UTC); win rate and IS were both favourable in this window
**What underperformed**: Late-session signals (post 20:00 UTC) are noisy — spread widens, liquidity thins, and momentum decays before the holding window closes; these trades dragged Sharpe from ~1.7 to 1.42
**Hypothesis verdict**: Supported during liquid sessions; the signal does not hold in low-liquidity late-session periods
**Suggested refinement**: Add a time-of-day filter excluding entries after 20:00 UTC — expect Sharpe improvement of ~0.2–0.3 and a reduction in max drawdown by removing the worst late-session losing streaks
